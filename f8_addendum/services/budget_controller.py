"""F8 Addendum — A-10: Conservative Token Budget Controller.

Conservative-then-escalate strategy: start low, escalate on max_tokens hit,
self-calibrate after 500 cycles per F-level.
~70 lines | Integrates with L5 orchestrator and L2 ledger.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from ..types.budget import (
    DEFAULT_TOKEN_TIERS,
    EscalationRecord,
    TokenBudgetTier,
    TokenCalibrationData,
)

logger = logging.getLogger(__name__)


class BudgetController:
    """Manages conservative-then-escalate token budgets.

    Tier 1: Conservative default by F-level and track.
    Tier 2: Escalation on max_tokens hit (retry with 2x).
    Self-calibration after 500 cycles per F-level.
    """

    def __init__(self, ledger: Any, config: Any) -> None:
        self._ledger = ledger
        self._config = config
        self._tiers = DEFAULT_TOKEN_TIERS
        self._calibration_threshold = getattr(
            config, "budget_calibration_threshold", 500
        )

    def get_conservative_budget(
        self, track_id: str, f_level: int
    ) -> int:
        """Get the starting token budget for this track/F-level.

        First checks for calibrated budget; falls back to tier defaults.
        """
        # Check for calibrated budget
        calibrated = self._get_calibrated_budget(track_id, f_level)
        if calibrated is not None:
            return calibrated

        # Fall back to tier default
        for tier in self._tiers:
            if tier.f_level_min <= f_level <= tier.f_level_max:
                return tier.starting_budget

        return 4096  # Safe default

    def escalate_budget(self, current_budget: int) -> int:
        """Compute escalated budget (2x current)."""
        return current_budget * 2

    def record_and_calibrate(
        self,
        track_id: str,
        f_level: int,
        actual_tokens: int,
    ) -> None:
        """Record actual token usage and recalibrate if threshold met.

        After 500 cycles per F-level:
          - If p75 consistently below budget: lower budget.
          - If p50 consistently near budget: raise budget.
        """
        self._ledger.record_output_tokens(track_id, f_level, actual_tokens)

        # Check if calibration is due
        sample_count = self._ledger.get_token_sample_count(track_id, f_level)
        if sample_count < self._calibration_threshold:
            return

        # Compute percentiles
        stats = self._ledger.get_token_percentiles(track_id, f_level)
        if stats is None:
            return

        current_budget = self.get_conservative_budget(track_id, f_level)
        recommended = TokenCalibrationData.compute_recommended(
            p75=stats["p75"],
            p99=stats["p99"],
            current_budget=current_budget,
        )

        # Store calibration
        self._ledger.store_token_calibration(
            track_id=track_id,
            f_level=f_level,
            p50=stats["p50"],
            p75=stats["p75"],
            p99=stats["p99"],
            sample_count=sample_count,
            recommended_budget=recommended,
        )

        if recommended != current_budget:
            logger.info(
                "Token budget calibrated for %s/F%d: %d → %d (p75=%d, p99=%d)",
                track_id,
                f_level,
                current_budget,
                recommended,
                stats["p75"],
                stats["p99"],
            )

    def record_escalation(
        self,
        task_id: str,
        original_budget: int,
        escalated_budget: int,
        hit_limit_again: bool,
        f_level: int,
        track_id: str,
        cycle_id: str,
    ) -> EscalationRecord:
        """Record a token budget escalation event."""
        record = EscalationRecord(
            task_id=task_id,
            original_budget=original_budget,
            escalated_budget=escalated_budget,
            hit_limit_again=hit_limit_again,
            f_level=f_level,
            track_id=track_id,
            cycle_id=cycle_id,
        )

        if hit_limit_again:
            # Update task metadata for future runs
            self._ledger.update_task_token_requirement(
                task_id, escalated_budget
            )
            logger.info(
                "Task %s requires higher tier (hit limit at %d)",
                task_id,
                escalated_budget,
            )

        return record

    def get_budget_warning(
        self, total: int, remaining: int
    ) -> Optional[str]:
        """Generate budget warning when remaining < 25% of total."""
        if remaining < total * 0.25:
            return (
                "Token budget is running low. Prioritize correctness over "
                "documentation. Omit docstrings if needed."
            )
        return None

    # ── Internal ─────────────────────────────────────────────────────────────

    def _get_calibrated_budget(
        self, track_id: str, f_level: int
    ) -> Optional[int]:
        """Get calibrated budget from the ledger, if available."""
        data = self._ledger.get_calibrated_budget(track_id, f_level)
        if data is not None:
            return data.get("recommended_budget")
        return None
