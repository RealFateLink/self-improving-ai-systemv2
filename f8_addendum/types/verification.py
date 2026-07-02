"""F8 Addendum — A-3: Verification Verdict Taxonomy.

Replaces binary pass/fail with PASS/PARTIAL/FAIL for the dynamic verifier.
PARTIAL signals a candidate has value even if not fully correct.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Optional


class VerificationVerdict(StrEnum):
    """Three-state verification verdict."""

    PASS = "PASS"
    """All tests pass. Proceed to selection. Selector weight: 1.0."""

    PARTIAL = "PARTIAL"
    """Some tests pass (ratio recorded). Route failing subset to
    failure analysis. Selector weight: pass_ratio * 0.8."""

    FAIL = "FAIL"
    """Zero tests pass OR sandbox error. Route to full failure
    analysis. Selector weight: 0.0."""


# Selector weight mapping
VERDICT_WEIGHTS: dict[VerificationVerdict, float] = {
    VerificationVerdict.PASS: 1.0,
    VerificationVerdict.FAIL: 0.0,
    # PARTIAL weight = pass_ratio * 0.8 (computed dynamically)
}


@dataclass(frozen=True)
class EnhancedVerificationResult:
    """Extended verification result with verdict taxonomy.

    Adds pass_ratio and failing_test_ids to the base
    DynamicVerificationResult type.
    """

    verdict: VerificationVerdict
    pass_ratio: float  # 0.0–1.0
    total_tests: int
    passed_tests: int
    failed_tests: int
    failing_test_ids: tuple[str, ...]
    execution_time_seconds: float
    sandbox_error: Optional[str] = None
    needs_re_verify: bool = False
    """True when FAIL + failure analyzer produced a fix suggestion.
    Fixed candidate MUST be re-verified before entering selector."""

    @property
    def selector_weight(self) -> float:
        """Compute selector weight based on verdict."""
        if self.verdict == VerificationVerdict.PASS:
            return 1.0
        if self.verdict == VerificationVerdict.FAIL:
            return 0.0
        # PARTIAL
        return self.pass_ratio * 0.8

    @classmethod
    def from_test_results(
        cls,
        test_results: list[dict[str, Any]],
        execution_time: float,
        sandbox_error: Optional[str] = None,
    ) -> EnhancedVerificationResult:
        """Factory: build from raw test results.

        PARTIAL re-submissions only re-run failing tests.
        """
        if sandbox_error:
            return cls(
                verdict=VerificationVerdict.FAIL,
                pass_ratio=0.0,
                total_tests=len(test_results),
                passed_tests=0,
                failed_tests=len(test_results),
                failing_test_ids=tuple(
                    r.get("test_id", str(i))
                    for i, r in enumerate(test_results)
                ),
                execution_time_seconds=execution_time,
                sandbox_error=sandbox_error,
            )

        total = len(test_results)
        passed = sum(1 for r in test_results if r.get("passed", False))
        failed = total - passed

        failing_ids = tuple(
            r.get("test_id", str(i))
            for i, r in enumerate(test_results)
            if not r.get("passed", False)
        )

        if total == 0:
            verdict = VerificationVerdict.FAIL
        elif passed == total:
            verdict = VerificationVerdict.PASS
        elif passed > 0:
            verdict = VerificationVerdict.PARTIAL
        else:
            verdict = VerificationVerdict.FAIL

        pass_ratio = passed / total if total > 0 else 0.0

        return cls(
            verdict=verdict,
            pass_ratio=pass_ratio,
            total_tests=total,
            passed_tests=passed,
            failed_tests=failed,
            failing_test_ids=failing_ids,
            execution_time_seconds=execution_time,
        )
