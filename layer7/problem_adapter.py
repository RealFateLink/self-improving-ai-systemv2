"""Layer 7 — Problem Adapter.

Converts benchmark problems (HumanEval JSON, MBPP JSON, LiveCodeBench format)
into TaskSpec-compatible format. Assigns BM- prefixed task_ids.
~160 lines | Category: BENCHMARK
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Prefix mappings for benchmark task IDs
BENCHMARK_PREFIXES: dict[str, str] = {
    "humaneval": "BM-HE",
    "mbpp": "BM-MBPP",
    "livecodebench": "BM-LCB",
    "swebench": "BM-SWE",
}


@dataclass(frozen=True)
class BenchmarkTaskSpec:
    """TaskSpec-compatible representation of a benchmark problem.

    BM- prefix on task_id triggers BM- namespace enforcement
    throughout Layers 2-6.
    """

    task_id: str
    description: str
    visible_tests: tuple[str, ...]
    hidden_tests: tuple[str, ...]
    language: str
    is_benchmark: bool = True
    benchmark_name: str = ""
    time_limit_seconds: Optional[float] = None
    memory_limit_mb: Optional[int] = None
    metadata: dict[str, Any] = field(default_factory=dict)


class ProblemAdapter:
    """Converts benchmark problems into TaskSpec-compatible format.

    Each benchmark has its own adaptation logic. All adapted tasks
    receive BM- prefixed task_ids to trigger namespace enforcement.
    """

    def __init__(self, config: Any) -> None:
        self._config = config

    def adapt(self, problem: Any, benchmark_name: str) -> BenchmarkTaskSpec:
        """Convert a benchmark problem into a BenchmarkTaskSpec.

        Args:
            problem: Raw benchmark problem (dict or object).
            benchmark_name: Name of the benchmark (humaneval, mbpp, etc.).

        Returns BenchmarkTaskSpec with BM- prefixed task_id.
        """
        adapters = {
            "humaneval": self._adapt_humaneval,
            "mbpp": self._adapt_mbpp,
            "livecodebench": self._adapt_livecodebench,
            "swebench": self._adapt_swebench,
        }

        adapter_fn = adapters.get(benchmark_name)
        if adapter_fn is None:
            raise ValueError(f"Unknown benchmark: {benchmark_name}")

        return adapter_fn(problem, benchmark_name)

    # ── Benchmark-Specific Adapters ──────────────────────────────────────────

    def _adapt_humaneval(
        self, problem: Any, benchmark_name: str
    ) -> BenchmarkTaskSpec:
        """Adapt HumanEval problem.

        164 Python functions. Docstring + function signature → TaskSpec.
        visible_tests from examples, hidden_tests from canonical suite.
        """
        prob = self._as_dict(problem)
        task_id_raw = prob.get("task_id", "")
        # Extract numeric part: HumanEval/0 → 000
        num = task_id_raw.split("/")[-1] if "/" in task_id_raw else task_id_raw
        task_id = f"{BENCHMARK_PREFIXES['humaneval']}-{int(num):03d}"

        prompt = prob.get("prompt", "")
        canonical_solution = prob.get("canonical_solution", "")
        test_code = prob.get("test", "")
        entry_point = prob.get("entry_point", "")

        # Extract visible tests from docstring examples
        visible = self._extract_docstring_examples(prompt)

        # Hidden tests from canonical test suite
        hidden = self._parse_test_cases(test_code)

        return BenchmarkTaskSpec(
            task_id=task_id,
            description=prompt,
            visible_tests=tuple(visible),
            hidden_tests=tuple(hidden),
            language=self._normalize_language(prob),
            benchmark_name=benchmark_name,
            metadata={
                "entry_point": entry_point,
                "original_task_id": task_id_raw,
            },
        )

    def _adapt_mbpp(
        self, problem: Any, benchmark_name: str
    ) -> BenchmarkTaskSpec:
        """Adapt MBPP problem.

        500 Python tasks. 3 visible tests + hidden tests.
        Description + visible tests → TaskSpec.
        """
        prob = self._as_dict(problem)
        task_id_num = prob.get("task_id", 0)
        task_id = f"{BENCHMARK_PREFIXES['mbpp']}-{int(task_id_num):04d}"

        description = prob.get("text", "")
        test_list = prob.get("test_list", [])
        challenge_test_list = prob.get("challenge_test_list", [])

        # First 3 tests visible, rest hidden
        visible = test_list[:3]
        hidden = test_list[3:] + challenge_test_list

        return BenchmarkTaskSpec(
            task_id=task_id,
            description=description,
            visible_tests=tuple(str(t) for t in visible),
            hidden_tests=tuple(str(t) for t in hidden),
            language=self._normalize_language(prob),
            benchmark_name=benchmark_name,
            metadata={
                "original_task_id": task_id_num,
                "test_setup_code": prob.get("test_setup_code", ""),
            },
        )

    def _adapt_livecodebench(
        self, problem: Any, benchmark_name: str
    ) -> BenchmarkTaskSpec:
        """Adapt LiveCodeBench problem.

        Rolling set with time and memory limits.
        Problem statement + constraints → TaskSpec.
        """
        prob = self._as_dict(problem)
        problem_id = prob.get("problem_id", "")
        task_id = f"{BENCHMARK_PREFIXES['livecodebench']}-{problem_id}"

        description = prob.get("problem_statement", "")
        examples = prob.get("examples", [])
        test_cases = prob.get("test_cases", [])

        visible = [
            f"Input: {ex.get('input', '')}\nExpected: {ex.get('output', '')}"
            for ex in examples
        ]
        hidden = [
            f"Input: {tc.get('input', '')}\nExpected: {tc.get('output', '')}"
            for tc in test_cases
        ]

        return BenchmarkTaskSpec(
            task_id=task_id,
            description=description,
            visible_tests=tuple(visible),
            hidden_tests=tuple(hidden),
            language=self._normalize_language(prob),
            benchmark_name=benchmark_name,
            time_limit_seconds=prob.get("time_limit", None),
            memory_limit_mb=prob.get("memory_limit", None),
            metadata={
                "difficulty": prob.get("difficulty", ""),
                "tags": prob.get("tags", []),
                "original_id": problem_id,
            },
        )

    def _adapt_swebench(
        self, problem: Any, benchmark_name: str
    ) -> BenchmarkTaskSpec:
        """Adapt SWE-bench problem.

        Real GitHub issues. Repo → patch → test.
        Issue description + repo info → TaskSpec.
        """
        prob = self._as_dict(problem)
        instance_id = prob.get("instance_id", "")
        # Hash for shorter ID
        short_hash = hashlib.sha256(instance_id.encode()).hexdigest()[:8]
        task_id = f"{BENCHMARK_PREFIXES['swebench']}-{short_hash}"

        issue_text = prob.get("problem_statement", "")
        repo = prob.get("repo", "")
        base_commit = prob.get("base_commit", "")
        test_patch = prob.get("test_patch", "")

        return BenchmarkTaskSpec(
            task_id=task_id,
            description=issue_text,
            visible_tests=(),  # No visible tests for SWE-bench
            hidden_tests=(test_patch,) if test_patch else (),
            language=self._normalize_language(prob),
            benchmark_name=benchmark_name,
            metadata={
                "instance_id": instance_id,
                "repo": repo,
                "base_commit": base_commit,
                "repo_url": f"https://github.com/{repo}",
                "hints_text": prob.get("hints_text", ""),
            },
        )

    # ── Helpers ──────────────────────────────────────────────────────────────

    @staticmethod
    def _normalize_language(problem: Any) -> str:
        """Map benchmark language to system Language enum. Default Python."""
        prob = problem if isinstance(problem, dict) else {}
        lang = prob.get("language", "python").lower()
        language_map = {
            "python": "PYTHON",
            "python3": "PYTHON",
            "py": "PYTHON",
            "javascript": "JAVASCRIPT",
            "js": "JAVASCRIPT",
            "typescript": "TYPESCRIPT",
            "ts": "TYPESCRIPT",
            "java": "JAVA",
            "cpp": "CPP",
            "c++": "CPP",
            "rust": "RUST",
            "go": "GO",
        }
        return language_map.get(lang, "PYTHON")

    @staticmethod
    def _extract_docstring_examples(prompt: str) -> list[str]:
        """Extract example test cases from a function's docstring."""
        examples: list[str] = []
        in_examples = False
        for line in prompt.split("\n"):
            stripped = line.strip()
            if stripped.startswith(">>>"):
                in_examples = True
                examples.append(stripped)
            elif in_examples and stripped:
                examples.append(stripped)
            elif in_examples and not stripped:
                in_examples = False
        return examples

    @staticmethod
    def _parse_test_cases(test_code: str) -> list[str]:
        """Parse test function into individual assertions."""
        assertions: list[str] = []
        for line in test_code.split("\n"):
            stripped = line.strip()
            if stripped.startswith("assert"):
                assertions.append(stripped)
        return assertions

    @staticmethod
    def _as_dict(problem: Any) -> dict[str, Any]:
        """Convert problem to dict if it isn't already."""
        if isinstance(problem, dict):
            return problem
        return getattr(problem, "__dict__", {})
