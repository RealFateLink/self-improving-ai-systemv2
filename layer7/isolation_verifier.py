"""Layer 7 — Isolation Verifier.

Five contamination checks to verify benchmark data hasn't leaked into
the training system. All checks must pass before a benchmark session
proceeds. Run before every session.
~200 lines | Category: BENCHMARK
"""
from __future__ import annotations

import hashlib
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Optional

logger = logging.getLogger(__name__)


class CheckSeverity(StrEnum):
    """Severity of an isolation check failure."""

    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


@dataclass(frozen=True)
class IsolationCheckResult:
    """Result of a single isolation check."""

    check_name: str
    check_number: int
    passed: bool
    detail: str
    severity: CheckSeverity = CheckSeverity.WARNING
    items_checked: int = 0
    items_flagged: int = 0


@dataclass(frozen=True)
class IsolationVerificationResult:
    """Aggregate result of all 5 isolation checks."""

    overall_passed: bool
    checks: tuple[IsolationCheckResult, ...]
    issues: list[IsolationCheckResult]
    verified_at: str
    benchmark_data_dir: str


class IsolationVerifier:
    """Verifies benchmark data hasn't leaked into the training system.

    Five contamination checks:
      1. Filesystem isolation — no symlinks from benchmark data.
      2. Task metadata isolation — no benchmark IDs in task tables.
      3. Embedding isolation — no benchmark text in embedding index.
      4. Pattern isolation — no benchmark patterns in injectable state.
      5. Version integrity — benchmark files match expected hashes.

    All checks must pass before a benchmark session proceeds
    (unless --force flag is used).
    """

    def __init__(self, ledger: Any, config: Any) -> None:
        self._ledger = ledger
        self._config = config
        self._benchmark_data_dir = getattr(
            config, "benchmark_data_dir", "benchmark_data"
        )
        self._system_dirs = getattr(
            config,
            "system_dirs",
            ("gym_data", "templates", "patterns"),
        )

    def verify(self) -> IsolationVerificationResult:
        """Run all 5 contamination checks.

        Returns IsolationVerificationResult with overall pass/fail,
        per-check results, and list of issues.
        """
        checks: list[IsolationCheckResult] = [
            self._check_filesystem_isolation(),
            self._check_task_metadata_isolation(),
            self._check_embedding_isolation(),
            self._check_pattern_isolation(),
            self._check_version_integrity(),
        ]

        issues = [c for c in checks if not c.passed]
        overall_passed = len(issues) == 0

        result = IsolationVerificationResult(
            overall_passed=overall_passed,
            checks=tuple(checks),
            issues=issues,
            verified_at=datetime.now(timezone.utc).isoformat(),
            benchmark_data_dir=self._benchmark_data_dir,
        )

        if overall_passed:
            logger.info("Isolation verification PASSED (5/5 checks)")
        else:
            logger.warning(
                "Isolation verification FAILED: %d/%d checks failed",
                len(issues),
                len(checks),
            )

        return result

    # ── Check 1: Filesystem Isolation ────────────────────────────────────────

    def _check_filesystem_isolation(self) -> IsolationCheckResult:
        """Verify benchmark_data/ has no symlinks into system directories.

        Method: os.walk + os.path.islink. No benchmark paths in
        gym_data/, templates/, or pattern files.
        """
        items_checked = 0
        items_flagged = 0
        flagged_paths: list[str] = []

        # Check for symlinks in benchmark data dir
        if os.path.exists(self._benchmark_data_dir):
            for root, dirs, files in os.walk(self._benchmark_data_dir):
                for name in dirs + files:
                    full_path = os.path.join(root, name)
                    items_checked += 1
                    if os.path.islink(full_path):
                        target = os.path.realpath(full_path)
                        for sys_dir in self._system_dirs:
                            if sys_dir in target:
                                items_flagged += 1
                                flagged_paths.append(
                                    f"{full_path} -> {target}"
                                )

        # Check system dirs for benchmark references
        for sys_dir in self._system_dirs:
            if not os.path.exists(sys_dir):
                continue
            for root, dirs, files in os.walk(sys_dir):
                for name in files:
                    full_path = os.path.join(root, name)
                    items_checked += 1
                    if os.path.islink(full_path):
                        target = os.path.realpath(full_path)
                        if self._benchmark_data_dir in target:
                            items_flagged += 1
                            flagged_paths.append(f"{full_path} -> {target}")

        passed = items_flagged == 0
        detail = (
            "No symlinks between benchmark and system directories"
            if passed
            else f"Found {items_flagged} symlinks: {flagged_paths[:5]}"
        )

        return IsolationCheckResult(
            check_name="filesystem_isolation",
            check_number=1,
            passed=passed,
            detail=detail,
            severity=CheckSeverity.CRITICAL if not passed else CheckSeverity.WARNING,
            items_checked=items_checked,
            items_flagged=items_flagged,
        )

    # ── Check 2: Task Metadata Isolation ─────────────────────────────────────

    def _check_task_metadata_isolation(self) -> IsolationCheckResult:
        """Verify no benchmark IDs in task_metadata table.

        Method: search for BM-, HE-, MBPP-, LCB-, SWE- prefixes.
        """
        prefixes = ("BM-", "HE-", "MBPP-", "LCB-", "SWE-")
        total_found = 0
        found_ids: list[str] = []

        for prefix in prefixes:
            matches = self._ledger.search_task_metadata_by_prefix(prefix)
            total_found += len(matches)
            found_ids.extend(matches[:3])

        passed = total_found == 0
        detail = (
            "No benchmark IDs found in task_metadata"
            if passed
            else f"Found {total_found} benchmark IDs in task_metadata: {found_ids[:5]}"
        )

        return IsolationCheckResult(
            check_name="task_metadata_isolation",
            check_number=2,
            passed=passed,
            detail=detail,
            severity=CheckSeverity.CRITICAL if not passed else CheckSeverity.WARNING,
            items_checked=len(prefixes),
            items_flagged=total_found,
        )

    # ── Check 3: Embedding Isolation ─────────────────────────────────────────

    def _check_embedding_isolation(self) -> IsolationCheckResult:
        """Verify no benchmark problem text in embedding index.

        Method: Sample 10 benchmark problems. Compute embeddings.
        Search for >0.95 similarity in main index.
        """
        sample_size = getattr(self._config, "isolation_sample_size", 10)
        similarity_threshold = 0.95

        problems = self._ledger.load_benchmark_data(
            f"{self._benchmark_data_dir}/humaneval.json"
        )
        if not problems:
            return IsolationCheckResult(
                check_name="embedding_isolation",
                check_number=3,
                passed=True,
                detail="No benchmark data to check",
                items_checked=0,
                items_flagged=0,
            )

        sample = problems[:sample_size]
        items_flagged = 0
        flagged: list[str] = []

        for prob in sample:
            prob_dict = prob if isinstance(prob, dict) else getattr(prob, "__dict__", {})
            text = prob_dict.get("prompt", "") or prob_dict.get("text", "")
            if not text:
                continue

            similar = self._ledger.search_similar(
                text, threshold=similarity_threshold, limit=1
            )
            if similar:
                items_flagged += 1
                flagged.append(
                    prob_dict.get("task_id", "unknown")
                )

        passed = items_flagged == 0
        detail = (
            f"Sampled {len(sample)} problems, no embeddings found"
            if passed
            else (
                f"Found {items_flagged} benchmark texts in embedding index: "
                f"{flagged[:5]}"
            )
        )

        return IsolationCheckResult(
            check_name="embedding_isolation",
            check_number=3,
            passed=passed,
            detail=detail,
            severity=CheckSeverity.CRITICAL if not passed else CheckSeverity.WARNING,
            items_checked=len(sample),
            items_flagged=items_flagged,
        )

    # ── Check 4: Pattern Isolation ───────────────────────────────────────────

    def _check_pattern_isolation(self) -> IsolationCheckResult:
        """Verify no benchmark-derived patterns in prompt-injectable state.

        Method: Check pattern_library for source_type=BENCHMARK_DERIVED
        with status != AGENT_LOCAL. Should be zero.
        """
        injectable_benchmark_patterns = (
            self._ledger.count_injectable_benchmark_patterns()
        )

        passed = injectable_benchmark_patterns == 0
        detail = (
            "No benchmark-derived patterns in injectable state"
            if passed
            else (
                f"Found {injectable_benchmark_patterns} benchmark-derived "
                f"patterns in injectable state"
            )
        )

        return IsolationCheckResult(
            check_name="pattern_isolation",
            check_number=4,
            passed=passed,
            detail=detail,
            severity=CheckSeverity.CRITICAL if not passed else CheckSeverity.WARNING,
            items_checked=1,
            items_flagged=injectable_benchmark_patterns,
        )

    # ── Check 5: Version Integrity ───────────────────────────────────────────

    def _check_version_integrity(self) -> IsolationCheckResult:
        """Verify benchmark data files match expected hashes.

        Method: SHA-256 of each benchmark file vs stored hashes
        in benchmark_versions table.
        """
        benchmark_files = {
            "humaneval": f"{self._benchmark_data_dir}/humaneval.json",
            "mbpp": f"{self._benchmark_data_dir}/mbpp.json",
            "livecodebench": f"{self._benchmark_data_dir}/livecodebench.json",
            "swebench": f"{self._benchmark_data_dir}/swebench.json",
        }

        items_checked = 0
        items_flagged = 0
        mismatches: list[str] = []

        for name, path in benchmark_files.items():
            if not os.path.exists(path):
                continue

            items_checked += 1
            actual_hash = self._compute_file_hash(path)
            expected_hash = self._ledger.get_benchmark_version_hash(name)

            if expected_hash is not None and actual_hash != expected_hash:
                items_flagged += 1
                mismatches.append(
                    f"{name}: expected={expected_hash[:12]}..., "
                    f"actual={actual_hash[:12]}..."
                )

        passed = items_flagged == 0
        detail = (
            f"All {items_checked} benchmark files match expected hashes"
            if passed
            else f"Hash mismatch on {items_flagged} files: {mismatches}"
        )

        return IsolationCheckResult(
            check_name="version_integrity",
            check_number=5,
            passed=passed,
            detail=detail,
            severity=CheckSeverity.WARNING,
            items_checked=items_checked,
            items_flagged=items_flagged,
        )

    # ── Helpers ──────────────────────────────────────────────────────────────

    @staticmethod
    def _compute_file_hash(path: str) -> str:
        """Compute SHA-256 hash of a file."""
        sha256 = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return sha256.hexdigest()
