"""selector.py — Scores all candidates and chooses winner.

Stage 8.  Produces selection confidence.
Confidence is ADVISORY, not hard gating (eligible gating defined by
ConfidenceUseCase, not blanket thresholds).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

__all__ = ["Selector", "SelectionResult"]


@dataclass(frozen=True)
class CandidateScore:
    """Composite score for a single candidate."""
    candidate_id: str
    test_score: float         # 0.0–1.0 from dynamic verifier
    static_score: float       # 0.0–1.0 from static reviewer
    semantic_score: float     # 0.0–1.0 from semantic critic
    composite: float          # Weighted aggregate
    breakdown: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class SelectionResult:
    """Result of candidate selection."""
    winner_id: str | None
    winner_score: CandidateScore | None
    all_scores: tuple[CandidateScore, ...]
    confidence: float         # 0.0–1.0
    confidence_basis: str
    all_failed: bool


@dataclass
class Selector:
    """Scores candidates and selects the winner.

    Uses scoring weights from Layer 3 linear_scorer if available,
    otherwise uses default weights.

    Dependencies:
      - linear_scorer (Layer 3): for weight-based scoring (optional)
    """

    linear_scorer: Any = None
    config: dict[str, Any] = field(default_factory=dict)

    # Default weights.
    weight_test: float = 0.50
    weight_static: float = 0.20
    weight_semantic: float = 0.30

    def select(
        self,
        candidates: list[Any],
        verifications: list[Any],
        reviews: list[Any],
        critiques: list[Any],
        cycle_context: dict[str, Any],
    ) -> tuple[bool, Any]:
        """Score and select winner.

        Returns (True, ModuleResult) or (False, ModuleError).
        """
        from .intent_interpreter import ModuleResult, ModuleError

        try:
            # Build lookup maps.
            verify_map = {getattr(v, "candidate_id", ""): v for v in verifications}
            review_map = {getattr(r, "candidate_id", ""): r for r in reviews}
            critique_map = {getattr(c, "candidate_id", ""): c for c in critiques}

            scores: list[CandidateScore] = []

            for candidate in candidates:
                cid = getattr(candidate, "candidate_id", "")
                v = verify_map.get(cid)
                r = review_map.get(cid)
                c = critique_map.get(cid)

                test_score = getattr(v, "pass_rate", 0.0) if v else 0.0
                static_score = (1.0 if getattr(r, "passed", False) else 0.3) if r else 0.5
                semantic_score = getattr(c, "overall_quality", 0.5) if c else 0.5

                # Use Layer 3 scorer if available.
                if self.linear_scorer:
                    try:
                        composite = self.linear_scorer.score({
                            "test": test_score,
                            "static": static_score,
                            "semantic": semantic_score,
                        })
                    except Exception:
                        composite = self._default_composite(test_score, static_score, semantic_score)
                else:
                    composite = self._default_composite(test_score, static_score, semantic_score)

                scores.append(CandidateScore(
                    candidate_id=cid,
                    test_score=test_score,
                    static_score=static_score,
                    semantic_score=semantic_score,
                    composite=composite,
                    breakdown={
                        "test": test_score,
                        "static": static_score,
                        "semantic": semantic_score,
                    },
                ))

            # Sort by composite score.
            scores.sort(key=lambda s: s.composite, reverse=True)
            all_failed = all(s.test_score == 0.0 for s in scores)

            winner = None
            winner_score = None
            if scores and not all_failed:
                winner_score = scores[0]
                winner = winner_score.candidate_id

            # Confidence: based on score gap between top candidates.
            confidence, basis = self._compute_confidence(scores, all_failed)

            result = SelectionResult(
                winner_id=winner,
                winner_score=winner_score,
                all_scores=tuple(scores),
                confidence=confidence,
                confidence_basis=basis,
                all_failed=all_failed,
            )

            warnings = []
            if all_failed:
                warnings.append({
                    "type": "ALL_CANDIDATES_FAILED",
                    "severity": "CAUTION",
                    "message": "All candidates failed verification.",
                })

            return True, ModuleResult(primary=result, warnings=warnings)

        except Exception as exc:
            return False, ModuleError(
                error_type="RECOVERABLE",
                message=f"Selection failed: {exc}",
                is_retryable=False,
            )

    def _default_composite(
        self, test: float, static: float, semantic: float
    ) -> float:
        """Default weighted composite score."""
        return (
            self.weight_test * test
            + self.weight_static * static
            + self.weight_semantic * semantic
        )

    def _compute_confidence(
        self, scores: list[CandidateScore], all_failed: bool
    ) -> tuple[float, str]:
        """Compute selection confidence."""
        if all_failed:
            return 0.0, "all_candidates_failed"
        if not scores:
            return 0.0, "no_candidates"
        if len(scores) == 1:
            return 0.5, "single_candidate"

        # Confidence based on gap between first and second.
        gap = scores[0].composite - scores[1].composite
        if gap > 0.3:
            return 0.9, f"clear_winner_gap={gap:.2f}"
        elif gap > 0.1:
            return 0.7, f"moderate_gap={gap:.2f}"
        else:
            return 0.4, f"close_competition_gap={gap:.2f}"
