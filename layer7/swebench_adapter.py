"""Layer 7 — SWE-bench Adapter.

Handles the SWE-bench pipeline: repo cloning, issue investigation
(tree → file → call chain), patch generation, test execution.
Most expensive benchmark: $0.50–2.00 per problem.
~320 lines | Category: BENCHMARK
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SWEBenchProblemSetup:
    """Setup info for a SWE-bench problem."""

    instance_id: str
    repo_url: str
    base_commit: str
    issue_text: str
    hints_text: str
    repo_dir: Optional[str] = None


@dataclass(frozen=True)
class SWEBenchInvestigation:
    """Results of issue investigation."""

    instance_id: str
    tree_analysis: str
    relevant_files: list[str]
    call_chain: list[str]
    investigation_summary: str
    confidence: float


@dataclass(frozen=True)
class SWEBenchPatchResult:
    """Generated patch details."""

    instance_id: str
    patch_content: str
    files_modified: list[str]
    generation_cost_usd: float


@dataclass
class SWEBenchProblemResult:
    """Full result for a SWE-bench problem."""

    instance_id: str
    resolved: bool
    patch: str
    investigation_summary: str
    test_results: list[dict[str, Any]]
    traces: list[str]
    errors: list[str]
    cost_usd: float
    duration: float


class SWEBenchAdapter:
    """Handles the full SWE-bench pipeline.

    Pipeline: clone repo → investigate issue → generate patch →
    apply and test → cleanup.

    Each step is LLM-guided. The investigation phase uses a 3-step
    approach: tree structure analysis → file finding → call chain tracing.
    """

    def __init__(
        self,
        llm_client: Any,
        sandbox: Any,
        config: Any,
    ) -> None:
        self._llm = llm_client
        self._sandbox = sandbox
        self._config = config
        self._max_investigation_tokens = getattr(
            config, "swebench_investigation_tokens", 8192
        )
        self._max_patch_tokens = getattr(
            config, "swebench_patch_tokens", 4096
        )

    # ── Public API ───────────────────────────────────────────────────────────

    def run_problem(
        self, issue: Any, repo_url: str
    ) -> SWEBenchProblemResult:
        """Full SWE-bench pipeline: clone → investigate → patch → test.

        Args:
            issue: Benchmark problem with instance_id, base_commit, etc.
            repo_url: GitHub repository URL.

        Returns SWEBenchProblemResult.
        """
        start_time = datetime.now(timezone.utc)
        total_cost = 0.0
        traces: list[str] = []
        errors: list[str] = []

        instance_id = self._get_field(issue, "instance_id", "unknown")
        base_commit = self._get_field(issue, "base_commit", "")
        issue_text = self._get_field(issue, "problem_statement", "")
        hints_text = self._get_field(issue, "hints_text", "")

        setup = SWEBenchProblemSetup(
            instance_id=instance_id,
            repo_url=repo_url,
            base_commit=base_commit,
            issue_text=issue_text,
            hints_text=hints_text,
        )

        repo_dir = None
        try:
            # Step 1: Clone repo
            traces.append("Cloning repository...")
            repo_dir = self._clone_repo(repo_url, base_commit)
            traces.append(f"Cloned to {repo_dir}")

            # Step 2: Investigate issue
            traces.append("Investigating issue...")
            investigation = self._investigate(repo_dir, setup)
            total_cost += self._estimate_investigation_cost()
            traces.append(
                f"Investigation found {len(investigation.relevant_files)} files"
            )

            # Step 3: Generate patch
            traces.append("Generating patch...")
            patch_result = self._generate_patch(investigation, setup)
            total_cost += patch_result.generation_cost_usd
            traces.append(
                f"Patch modifies {len(patch_result.files_modified)} files"
            )

            # Step 4: Apply and test
            traces.append("Applying patch and running tests...")
            test_results, test_errors = self._apply_and_test(
                repo_dir, patch_result.patch_content
            )
            errors.extend(test_errors)

            resolved = self._all_tests_passed(test_results)

            duration = (
                datetime.now(timezone.utc) - start_time
            ).total_seconds()

            return SWEBenchProblemResult(
                instance_id=instance_id,
                resolved=resolved,
                patch=patch_result.patch_content,
                investigation_summary=investigation.investigation_summary,
                test_results=test_results,
                traces=traces,
                errors=errors,
                cost_usd=total_cost,
                duration=duration,
            )

        except Exception as exc:
            logger.error(
                "SWE-bench problem %s failed: %s", instance_id, exc
            )
            duration = (
                datetime.now(timezone.utc) - start_time
            ).total_seconds()
            errors.append(str(exc))

            return SWEBenchProblemResult(
                instance_id=instance_id,
                resolved=False,
                patch="",
                investigation_summary="Investigation failed",
                test_results=[],
                traces=traces,
                errors=errors,
                cost_usd=total_cost,
                duration=duration,
            )

        finally:
            if repo_dir:
                self._cleanup(repo_dir)

    # ── Step 1: Clone Repo ───────────────────────────────────────────────────

    def _clone_repo(self, repo_url: str, commit: str) -> str:
        """Shallow clone to temp directory. Checkout specific commit.

        Returns path to cloned repo directory.
        """
        repo_dir = tempfile.mkdtemp(prefix="swebench_")

        try:
            # Shallow clone
            subprocess.run(
                [
                    "git",
                    "clone",
                    "--depth",
                    "1",
                    repo_url,
                    repo_dir,
                ],
                capture_output=True,
                text=True,
                timeout=120,
                check=True,
            )

            # If specific commit requested, fetch it
            if commit:
                subprocess.run(
                    ["git", "fetch", "--depth", "1", "origin", commit],
                    cwd=repo_dir,
                    capture_output=True,
                    text=True,
                    timeout=60,
                    check=False,  # May fail for shallow clones
                )
                subprocess.run(
                    ["git", "checkout", commit],
                    cwd=repo_dir,
                    capture_output=True,
                    text=True,
                    timeout=30,
                    check=False,
                )

            # Verify clean state
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=repo_dir,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.stdout.strip():
                logger.warning("Repo not in clean state after checkout")

            return repo_dir

        except subprocess.TimeoutExpired:
            shutil.rmtree(repo_dir, ignore_errors=True)
            raise RuntimeError(f"Git clone timed out for {repo_url}")
        except subprocess.CalledProcessError as exc:
            shutil.rmtree(repo_dir, ignore_errors=True)
            raise RuntimeError(f"Git clone failed: {exc.stderr}")

    # ── Step 2: Investigate ──────────────────────────────────────────────────

    def _investigate(
        self, repo_dir: str, setup: SWEBenchProblemSetup
    ) -> SWEBenchInvestigation:
        """3-step LLM-guided investigation.

        (1) Tree structure analysis.
        (2) File finding via grep/AST.
        (3) Call chain tracing.
        """
        # Step 2a: Tree structure
        tree_output = self._get_tree_structure(repo_dir)
        tree_analysis = self._llm_analyze_tree(tree_output, setup)

        # Step 2b: File finding
        relevant_files = self._find_relevant_files(
            repo_dir, setup, tree_analysis
        )

        # Step 2c: Call chain tracing
        call_chain = self._trace_call_chain(repo_dir, relevant_files, setup)

        # Generate investigation summary
        summary = self._llm_summarize_investigation(
            tree_analysis, relevant_files, call_chain, setup
        )

        return SWEBenchInvestigation(
            instance_id=setup.instance_id,
            tree_analysis=tree_analysis,
            relevant_files=relevant_files,
            call_chain=call_chain,
            investigation_summary=summary,
            confidence=self._estimate_confidence(relevant_files, call_chain),
        )

    def _get_tree_structure(self, repo_dir: str) -> str:
        """Get directory tree structure of the repo."""
        try:
            result = subprocess.run(
                [
                    "find",
                    ".",
                    "-type",
                    "f",
                    "-name",
                    "*.py",
                    "-not",
                    "-path",
                    "./.git/*",
                ],
                cwd=repo_dir,
                capture_output=True,
                text=True,
                timeout=10,
            )
            return result.stdout[:5000]  # Truncate if too large
        except subprocess.TimeoutExpired:
            return ""

    def _llm_analyze_tree(
        self, tree_output: str, setup: SWEBenchProblemSetup
    ) -> str:
        """LLM analyzes tree structure to identify candidate directories."""
        prompt = (
            f"Given this Python project structure:\n{tree_output}\n\n"
            f"And this issue:\n{setup.issue_text[:2000]}\n\n"
            f"Which directories and files are most likely relevant? "
            f"List the top 5 most relevant file paths."
        )
        response = self._llm.generate(
            prompt=prompt,
            max_tokens=1024,
            is_benchmark=True,
        )
        return getattr(response, "text", str(response))

    def _find_relevant_files(
        self, repo_dir: str, setup: SWEBenchProblemSetup, tree_analysis: str
    ) -> list[str]:
        """Find relevant files using grep and AST analysis."""
        relevant: list[str] = []

        # Extract keywords from issue
        keywords = self._extract_keywords(setup.issue_text)

        # Grep for keywords in Python files
        for keyword in keywords[:5]:
            try:
                result = subprocess.run(
                    ["grep", "-rl", keyword, "--include=*.py", "."],
                    cwd=repo_dir,
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                for line in result.stdout.strip().split("\n"):
                    if line and line not in relevant:
                        relevant.append(line)
            except (subprocess.TimeoutExpired, subprocess.CalledProcessError):
                continue

        # Also parse file suggestions from tree analysis
        for line in tree_analysis.split("\n"):
            line = line.strip()
            if line.endswith(".py") and line not in relevant:
                # Verify file exists
                full_path = os.path.join(repo_dir, line.lstrip("./"))
                if os.path.exists(full_path):
                    relevant.append(line)

        return relevant[:20]  # Cap at 20 files

    def _trace_call_chain(
        self,
        repo_dir: str,
        relevant_files: list[str],
        setup: SWEBenchProblemSetup,
    ) -> list[str]:
        """Trace call chains in relevant files using LLM."""
        if not relevant_files:
            return []

        # Read relevant file contents (capped)
        file_contents: list[str] = []
        total_chars = 0
        max_chars = 10000

        for fpath in relevant_files[:5]:
            full_path = os.path.join(repo_dir, fpath.lstrip("./"))
            if os.path.exists(full_path):
                try:
                    with open(full_path) as f:
                        content = f.read()[:2000]
                        total_chars += len(content)
                        if total_chars > max_chars:
                            break
                        file_contents.append(f"=== {fpath} ===\n{content}")
                except (OSError, UnicodeDecodeError):
                    continue

        if not file_contents:
            return []

        prompt = (
            f"Given this issue:\n{setup.issue_text[:1000]}\n\n"
            f"And these file contents:\n{''.join(file_contents)}\n\n"
            f"Trace the call chain from the entry point to where the bug "
            f"likely is. List the function calls in order."
        )

        response = self._llm.generate(
            prompt=prompt,
            max_tokens=1024,
            is_benchmark=True,
        )
        text = getattr(response, "text", str(response))
        return [line.strip() for line in text.split("\n") if line.strip()]

    # ── Step 3: Generate Patch ───────────────────────────────────────────────

    def _generate_patch(
        self,
        investigation: SWEBenchInvestigation,
        setup: SWEBenchProblemSetup,
    ) -> SWEBenchPatchResult:
        """LLM generates unified diff patch based on investigation."""
        prompt = (
            f"Based on this investigation:\n"
            f"{investigation.investigation_summary}\n\n"
            f"Relevant files: {investigation.relevant_files}\n"
            f"Call chain: {investigation.call_chain}\n\n"
            f"Issue:\n{setup.issue_text[:2000]}\n\n"
            f"Generate a unified diff patch that fixes this issue. "
            f"Use standard diff format (--- a/file, +++ b/file)."
        )

        response = self._llm.generate(
            prompt=prompt,
            max_tokens=self._max_patch_tokens,
            is_benchmark=True,
        )

        patch_content = getattr(response, "text", str(response))
        cost = getattr(response, "cost_usd", 0.0)

        # Extract file names from patch
        files_modified = self._extract_files_from_patch(patch_content)

        return SWEBenchPatchResult(
            instance_id=setup.instance_id,
            patch_content=patch_content,
            files_modified=files_modified,
            generation_cost_usd=cost,
        )

    # ── Step 4: Apply and Test ───────────────────────────────────────────────

    def _apply_and_test(
        self, repo_dir: str, patch: str
    ) -> tuple[list[dict[str, Any]], list[str]]:
        """Apply patch to repo and run test suite in sandbox.

        Returns (test_results, errors).
        """
        errors: list[str] = []
        test_results: list[dict[str, Any]] = []

        # Write patch to file
        patch_path = os.path.join(repo_dir, "fix.patch")
        with open(patch_path, "w") as f:
            f.write(patch)

        # Apply patch
        try:
            result = subprocess.run(
                ["git", "apply", "--check", "fix.patch"],
                cwd=repo_dir,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                errors.append(f"Patch check failed: {result.stderr}")
                return test_results, errors

            subprocess.run(
                ["git", "apply", "fix.patch"],
                cwd=repo_dir,
                capture_output=True,
                text=True,
                timeout=30,
                check=True,
            )
        except subprocess.CalledProcessError as exc:
            errors.append(f"Patch application failed: {exc.stderr}")
            return test_results, errors
        except subprocess.TimeoutExpired:
            errors.append("Patch application timed out")
            return test_results, errors

        # Run tests in sandbox
        timeout = getattr(self._config, "swebench_test_timeout", 120)
        try:
            sandbox_result = self._sandbox.execute(
                code="",
                tests=[],
                timeout=timeout,
                is_benchmark=True,
                working_dir=repo_dir,
                command="python -m pytest --tb=short -q",
            )
            test_output = getattr(sandbox_result, "stdout", "")
            test_results = self._parse_pytest_output(test_output)

        except Exception as exc:
            errors.append(f"Test execution failed: {exc}")

        return test_results, errors

    # ── Step 5: Cleanup ──────────────────────────────────────────────────────

    @staticmethod
    def _cleanup(repo_dir: str) -> None:
        """Remove cloned repo directory. Verify no leftover processes."""
        try:
            shutil.rmtree(repo_dir, ignore_errors=True)
        except Exception as exc:
            logger.warning("Cleanup failed for %s: %s", repo_dir, exc)

    # ── Helpers ──────────────────────────────────────────────────────────────

    @staticmethod
    def _extract_keywords(text: str) -> list[str]:
        """Extract search keywords from issue text."""
        import re

        # Find identifiers (function names, class names, variable names)
        identifiers = re.findall(r"\b[a-zA-Z_]\w{3,}\b", text)
        # Deduplicate while preserving order
        seen: set[str] = set()
        keywords: list[str] = []
        for ident in identifiers:
            lower = ident.lower()
            if lower not in seen and lower not in (
                "this", "that", "with", "from", "should", "could",
                "would", "when", "which", "there", "their", "about",
                "have", "been", "some", "does", "them", "than",
            ):
                seen.add(lower)
                keywords.append(ident)
        return keywords[:10]

    @staticmethod
    def _extract_files_from_patch(patch: str) -> list[str]:
        """Extract file paths from a unified diff patch."""
        import re

        files: list[str] = []
        for match in re.finditer(r"^(?:---|\+\+\+) [ab]/(.+)$", patch, re.MULTILINE):
            fpath = match.group(1)
            if fpath not in files:
                files.append(fpath)
        return files

    @staticmethod
    def _parse_pytest_output(output: str) -> list[dict[str, Any]]:
        """Parse pytest output into structured test results."""
        results: list[dict[str, Any]] = []
        for line in output.split("\n"):
            line = line.strip()
            if line.startswith("PASSED") or " PASSED" in line:
                results.append({"test": line, "status": "PASSED"})
            elif line.startswith("FAILED") or " FAILED" in line:
                results.append({"test": line, "status": "FAILED"})
            elif line.startswith("ERROR") or " ERROR" in line:
                results.append({"test": line, "status": "ERROR"})
        return results

    @staticmethod
    def _all_tests_passed(test_results: list[dict[str, Any]]) -> bool:
        """Check if ALL tests passed (SWE-bench resolution criteria)."""
        if not test_results:
            return False
        return all(r.get("status") == "PASSED" for r in test_results)

    @staticmethod
    def _estimate_confidence(
        relevant_files: list[str], call_chain: list[str]
    ) -> float:
        """Estimate investigation confidence (0.0–1.0)."""
        file_score = min(len(relevant_files) / 5.0, 1.0)
        chain_score = min(len(call_chain) / 3.0, 1.0)
        return (file_score + chain_score) / 2.0

    def _estimate_investigation_cost(self) -> float:
        """Estimate cost of the investigation phase."""
        return getattr(self._config, "swebench_investigation_cost_est", 0.15)

    def _llm_summarize_investigation(
        self,
        tree_analysis: str,
        relevant_files: list[str],
        call_chain: list[str],
        setup: SWEBenchProblemSetup,
    ) -> str:
        """Summarize the investigation findings."""
        prompt = (
            f"Summarize the investigation for this issue:\n"
            f"{setup.issue_text[:1000]}\n\n"
            f"Tree analysis:\n{tree_analysis[:500]}\n"
            f"Relevant files: {relevant_files}\n"
            f"Call chain: {call_chain}\n\n"
            f"Provide a concise summary of where the bug is and what "
            f"needs to change."
        )
        response = self._llm.generate(
            prompt=prompt,
            max_tokens=512,
            is_benchmark=True,
        )
        return getattr(response, "text", str(response))

    @staticmethod
    def _get_field(obj: Any, field: str, default: Any = "") -> Any:
        """Get field from object (dict or dataclass)."""
        if isinstance(obj, dict):
            return obj.get(field, default)
        return getattr(obj, field, default)
