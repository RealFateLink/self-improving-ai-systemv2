"""dynamic_verifier.py — Executes candidates in sandbox.

Stage 6.  INVARIANT-CORE module.
Runs tests and scaling analysis.
Isolates infrastructure failures from learning failures.
Batch-wrapper parity with single-call semantics.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Optional

__all__ = ["DynamicVerifier", "VerificationResult"]


@dataclass(frozen=True)
class TestOutcome:
    """Result of running a single test."""
    test_name: str
    passed: bool
    duration_ms: float = 0.0
    error: str = ""


@dataclass(frozen=True)
class VerificationResult:
    """Verification result for a candidate."""
    candidate_id: str
    all_passed: bool
    tests_run: int
    tests_passed: int
    test_outcomes: tuple[TestOutcome, ...]
    execution_time_ms: float
    is_infrastructure_failure: bool = False
    infrastructure_error: str = ""
    scaling_score: float | None = None

    @property
    def pass_rate(self) -> float:
        if self.tests_run == 0:
            return 0.0
        return self.tests_passed / self.tests_run


@dataclass
class DynamicVerifier:
    """Executes code candidates in sandbox and runs tests.

    INVARIANT-CORE: infrastructure failures are isolated from learning failures.

    Dependencies:
      - sandbox (Layer 2): for execution environment
    """

    sandbox: Any = None
    config: dict[str, Any] = field(default_factory=dict)
    timeout_ms: int = 30000

    def verify(
        self,
        candidate: Any,
        task: Any,
        cycle_context: dict[str, Any],
    ) -> tuple[bool, Any]:
        """Verify a single candidate.

        Returns (True, ModuleResult) or (False, ModuleError).
        """
        from .intent_interpreter import ModuleResult, ModuleError

        code = getattr(candidate, "code", "")
        cid = getattr(candidate, "candidate_id", "unknown")
        tests = getattr(task, "tests", None) or getattr(task, "test_suite", "")
        language = (
            candidate.metadata.get("language", "python")
            if hasattr(candidate, "metadata") else "python"
        )

        if self.sandbox is None:
            return False, ModuleError(
                error_type="INFRASTRUCTURE",
                message="No sandbox configured.",
                is_retryable=False,
            )

        try:
            start = time.monotonic()
            result = self.sandbox.run(
                code=code,
                tests=tests,
                language=language,
                timeout_ms=self.timeout_ms,
            )
            elapsed = (time.monotonic() - start) * 1000

            # Parse sandbox result.
            if isinstance(result, dict):
                all_passed = result.get("all_passed", False)
                outcomes = self._parse_outcomes(result)
                infra_fail = result.get("infrastructure_error", False)
                infra_msg = result.get("infrastructure_message", "")
            else:
                all_passed = bool(result)
                outcomes = ()
                infra_fail = False
                infra_msg = ""

            vr = VerificationResult(
                candidate_id=cid,
                all_passed=all_passed and not infra_fail,
                tests_run=len(outcomes),
                tests_passed=sum(1 for o in outcomes if o.passed),
                test_outcomes=outcomes,
                execution_time_ms=elapsed,
                is_infrastructure_failure=infra_fail,
                infrastructure_error=infra_msg,
            )

            warnings = []
            if infra_fail:
                warnings.append({
                    "type": "INFRASTRUCTURE_FAILURE",
                    "severity": "CRITICAL",
                    "message": f"Infrastructure failure for {cid}: {infra_msg}",
                })

            return True, ModuleResult(primary=vr, warnings=warnings)

        except Exception as exc:
            # Treat unexpected exceptions as infrastructure failures.
            return False, ModuleError(
                error_type="INFRASTRUCTURE",
                message=f"Sandbox execution error: {exc}",
                is_retryable=True,
            )

    def verify_batch(
        self,
        candidates: list[Any],
        task: Any,
        cycle_context: dict[str, Any],
    ) -> tuple[bool, Any]:
        """Batch verification — semantic wrapper over single-call path.

        Batch/single parity: identical results regardless of call path.
        """
        from .intent_interpreter import ModuleResult, ModuleError

        results: list[VerificationResult] = []
        all_warnings: list[dict[str, Any]] = []
        infra_failures = 0

        for candidate in candidates:
            ok, result = self.verify(candidate, task, cycle_context)
            if ok:
                results.append(result.primary)
                all_warnings.extend(result.warnings)
                if result.primary.is_infrastructure_failure:
                    infra_failures += 1
            else:
                all_warnings.append({
                    "type": "VERIFY_PARTIAL_FAILURE",
                    "severity": "CAUTION",
                    "message": f"Verification failed for {getattr(candidate, 'candidate_id', '?')}: {result.message}",
                })
                infra_failures += 1

        # If ALL failures are infrastructure, that's an infrastructure error.
        if infra_failures == len(candidates) and candidates:
            return False, ModuleError(
                error_type="INFRASTRUCTURE",
                message=f"All {len(candidates)} candidates hit infrastructure failures.",
                is_retryable=True,
                partial_envelope=ModuleResult(primary=results, warnings=all_warnings),
            )

        return True, ModuleResult(primary=results, warnings=all_warnings)

    def _parse_outcomes(self, result: dict[str, Any]) -> tuple[TestOutcome, ...]:
        """Parse test outcomes from sandbox result."""
        outcomes = []
        raw_tests = result.get("test_results", result.get("tests", []))
        if isinstance(raw_tests, list):
            for t in raw_tests:
                if isinstance(t, dict):
                    outcomes.append(TestOutcome(
                        test_name=t.get("name", "unnamed"),
                        passed=t.get("passed", False),
                        duration_ms=t.get("duration_ms", 0.0),
                        error=t.get("error", ""),
                    ))
        return tuple(outcomes)
