"""Layer 2 — Budget controller.

Tracks spending against monthly/daily/cycle limits. Manages economy mode
transitions and per-track cost attribution.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from ..result import Result, LedgerError, LedgerErrorType


class BudgetController:
    """Manages budget tracking, economy mode, and cost attribution."""

    def __init__(
        self,
        monthly_budget_usd: float = 100.0,
        daily_limit_usd: float = 10.0,
        cycle_limit_usd: float = 1.0,
        economy_mode_threshold: float = 0.30,
        alert_threshold_percent: float = 0.80,
    ) -> None:
        self._monthly_budget = monthly_budget_usd
        self._daily_limit = daily_limit_usd
        self._cycle_limit = cycle_limit_usd
        self._economy_threshold = economy_mode_threshold
        self._alert_threshold = alert_threshold_percent

        self._total_spent: float = 0.0
        self._daily_spent: float = 0.0
        self._cycle_spent: float = 0.0
        self._economy_mode: bool = False
        self._per_track_spent: dict[str, float] = {}
        self._cycle_count: int = 0
        self._current_day: str = ""

    def check_budget(self, estimated_cost: float) -> Result[bool, LedgerError]:
        """Check if an expense is within budget limits."""
        self._ensure_daily_reset()

        if self._total_spent + estimated_cost > self._monthly_budget:
            return Result(value=False)
        if self._daily_spent + estimated_cost > self._daily_limit:
            return Result(value=False)
        if self._cycle_spent + estimated_cost > self._cycle_limit:
            return Result(value=False)
        return Result(value=True)

    def record_expense(
        self,
        amount: float,
        category: str = "llm",
        detail: str = "",
        track_id: Optional[str] = None,
    ) -> Result[None, LedgerError]:
        """Record an expense and update all counters."""
        self._ensure_daily_reset()

        self._total_spent += amount
        self._daily_spent += amount
        self._cycle_spent += amount

        if track_id:
            self._per_track_spent[track_id] = (
                self._per_track_spent.get(track_id, 0.0) + amount
            )

        # Check economy mode trigger
        remaining_pct = self.get_remaining_percent()
        if remaining_pct <= self._economy_threshold and not self._economy_mode:
            self._economy_mode = True

        return Result(value=None)

    def get_remaining(self) -> float:
        return max(0.0, self._monthly_budget - self._total_spent)

    def get_remaining_percent(self) -> float:
        if self._monthly_budget <= 0:
            return 0.0
        return self.get_remaining() / self._monthly_budget

    def get_burn_rate(self) -> float:
        """Average cost per cycle."""
        if self._cycle_count <= 0:
            return 0.0
        return self._total_spent / self._cycle_count

    def get_projected_depletion_cycle(self) -> Optional[int]:
        """Estimate when budget will run out at current burn rate."""
        rate = self.get_burn_rate()
        if rate <= 0:
            return None
        remaining = self.get_remaining()
        return self._cycle_count + int(remaining / rate)

    def enter_economy_mode(self) -> None:
        self._economy_mode = True

    def exit_economy_mode(self) -> None:
        self._economy_mode = False

    @property
    def economy_mode(self) -> bool:
        return self._economy_mode

    def new_cycle(self) -> None:
        """Reset per-cycle counters."""
        self._cycle_spent = 0.0
        self._cycle_count += 1

    def get_per_track_spending(self) -> dict[str, float]:
        return dict(self._per_track_spent)

    def get_track_budget_percent(self, track_id: str) -> float:
        """What fraction of total budget has this track consumed."""
        if self._monthly_budget <= 0:
            return 0.0
        return self._per_track_spent.get(track_id, 0.0) / self._monthly_budget

    def is_alert_threshold_reached(self) -> bool:
        return (self._total_spent / self._monthly_budget) >= self._alert_threshold

    def get_snapshot(self, cycle_number: int) -> dict[str, Any]:
        return {
            "cycle_number": cycle_number,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "total_budget_usd": self._monthly_budget,
            "spent_usd": self._total_spent,
            "remaining_usd": self.get_remaining(),
            "burn_rate_per_cycle": self.get_burn_rate(),
            "projected_depletion_cycle": self.get_projected_depletion_cycle(),
            "economy_mode_active": self._economy_mode,
            "daily_spent": self._daily_spent,
            "per_track_spent": dict(self._per_track_spent),
        }

    def _ensure_daily_reset(self) -> None:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if today != self._current_day:
            self._daily_spent = 0.0
            self._current_day = today
