"""F8 Addendum — A-10: Token Budget Types.

Conservative-then-escalate token budgets with self-calibration.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass(frozen=True)
class TokenBudgetTier:
    """Token budget configuration per F-level range.

    Starting points; calibrate after 500 cycles per F-level.
    """

    f_level_min: int
    f_level_max: int
    starting_budget: int
    escalation_multiplier: float = 2.0


# Default tiers
DEFAULT_TOKEN_TIERS: tuple[TokenBudgetTier, ...] = (
    TokenBudgetTier(f_level_min=1, f_level_max=3, starting_budget=4096),
    TokenBudgetTier(f_level_min=4, f_level_max=6, starting_budget=8192),
    TokenBudgetTier(f_level_min=7, f_level_max=9, starting_budget=16384),
    TokenBudgetTier(f_level_min=10, f_level_max=12, starting_budget=32768),
)


@dataclass(frozen=True)
class EscalationRecord:
    """Records a token budget escalation event."""

    task_id: str
    original_budget: int
    escalated_budget: int
    hit_limit_again: bool
    f_level: int
    track_id: str
    cycle_id: str


@dataclass(frozen=True)
class TokenCalibrationData:
    """Calibration data for a track/F-level combination.

    After 500 cycles per F-level: compute actual p50/p75/p99.
    Adjust starting budget accordingly.
    """

    track_id: str
    f_level: int
    p50_tokens: int
    p75_tokens: int
    p99_tokens: int
    sample_count: int
    last_calibrated: str
    recommended_budget: int

    @classmethod
    def compute_recommended(
        cls,
        p75: int,
        p99: int,
        current_budget: int,
    ) -> int:
        """Compute recommended budget from percentile data.

        If p75 consistently below budget: lower it.
        If p50 consistently near budget: raise it.
        """
        # Target: p75 with 50% headroom
        recommended = int(p75 * 1.5)
        # Don't exceed p99 too much
        recommended = min(recommended, int(p99 * 1.2))
        return recommended
