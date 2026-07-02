"""persistent_budget.py — SQLite-persisted budget controller.

Layer 2 — v0.2.0.  Replaces in-memory budget with persistent storage.
Prevents budget reset on restart.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


@dataclass
class PersistentBudgetController:
    """Budget controller with SQLite persistence."""

    db_path: Path = field(default_factory=lambda: Path("data/budget.db"))
    monthly_budget_usd: float = 300.0
    daily_limit_usd: float = 10.0
    cycle_limit_usd: float = 1.0
    economy_mode_threshold: float = 0.30
    alert_threshold_percent: float = 0.80

    def __post_init__(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        self._ensure_daily_reset()

    def _init_db(self) -> None:
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS budget_state (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    total_spent REAL DEFAULT 0.0,
                    daily_spent REAL DEFAULT 0.0,
                    cycle_spent REAL DEFAULT 0.0,
                    economy_mode INTEGER DEFAULT 0,
                    current_day TEXT DEFAULT '',
                    cycle_count INTEGER DEFAULT 0,
                    updated_at TEXT DEFAULT ''
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS expenses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    amount REAL NOT NULL,
                    category TEXT NOT NULL,
                    detail TEXT,
                    track_id TEXT,
                    timestamp TEXT NOT NULL
                )
            """)
            conn.execute("""
                INSERT OR IGNORE INTO budget_state (id) VALUES (1)
            """)
            conn.commit()

    def _load_state(self) -> dict[str, Any]:
        with sqlite3.connect(str(self.db_path)) as conn:
            row = conn.execute(
                "SELECT total_spent, daily_spent, cycle_spent, economy_mode, current_day, cycle_count FROM budget_state WHERE id = 1"
            ).fetchone()
            if row:
                return {
                    "total_spent": row[0],
                    "daily_spent": row[1],
                    "cycle_spent": row[2],
                    "economy_mode": bool(row[3]),
                    "current_day": row[4],
                    "cycle_count": row[5],
                }
            return {
                "total_spent": 0.0, "daily_spent": 0.0, "cycle_spent": 0.0,
                "economy_mode": False, "current_day": "", "cycle_count": 0,
            }

    def _save_state(self, state: dict[str, Any]) -> None:
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(
                """UPDATE budget_state SET
                    total_spent = ?, daily_spent = ?, cycle_spent = ?,
                    economy_mode = ?, current_day = ?, cycle_count = ?, updated_at = ?
                WHERE id = 1""",
                (
                    state["total_spent"], state["daily_spent"], state["cycle_spent"],
                    int(state["economy_mode"]), state["current_day"], state["cycle_count"],
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            conn.commit()

    def _ensure_daily_reset(self) -> None:
        state = self._load_state()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if state["current_day"] != today:
            state["daily_spent"] = 0.0
            state["current_day"] = today
            self._save_state(state)

    def check_budget(self, estimated_cost: float) -> bool:
        self._ensure_daily_reset()
        state = self._load_state()
        if state["total_spent"] + estimated_cost > self.monthly_budget_usd:
            return False
        if state["daily_spent"] + estimated_cost > self.daily_limit_usd:
            return False
        if state["cycle_spent"] + estimated_cost > self.cycle_limit_usd:
            return False
        return True

    def record_expense(
        self,
        amount: float,
        category: str = "llm",
        detail: str = "",
        track_id: Optional[str] = None,
    ) -> bool:
        self._ensure_daily_reset()
        state = self._load_state()

        # Check before recording
        if not self.check_budget(amount):
            return False

        state["total_spent"] += amount
        state["daily_spent"] += amount
        state["cycle_spent"] += amount

        # Check economy mode trigger
        remaining_pct = self.get_remaining_percent()
        if remaining_pct <= self.economy_mode_threshold and not state["economy_mode"]:
            state["economy_mode"] = True

        self._save_state(state)

        # Record expense
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(
                "INSERT INTO expenses (amount, category, detail, track_id, timestamp) VALUES (?, ?, ?, ?, ?)",
                (amount, category, detail, track_id, datetime.now(timezone.utc).isoformat()),
            )
            conn.commit()

        return True

    def get_remaining(self) -> float:
        state = self._load_state()
        return max(0.0, self.monthly_budget_usd - state["total_spent"])

    def get_remaining_percent(self) -> float:
        if self.monthly_budget_usd <= 0:
            return 0.0
        return self.get_remaining() / self.monthly_budget_usd

    def get_burn_rate(self) -> float:
        state = self._load_state()
        if state["cycle_count"] <= 0:
            return 0.0
        return state["total_spent"] / state["cycle_count"]

    def enter_economy_mode(self) -> None:
        state = self._load_state()
        state["economy_mode"] = True
        self._save_state(state)

    def exit_economy_mode(self) -> None:
        state = self._load_state()
        state["economy_mode"] = False
        self._save_state(state)

    @property
    def economy_mode(self) -> bool:
        return self._load_state()["economy_mode"]

    def new_cycle(self) -> None:
        state = self._load_state()
        state["cycle_spent"] = 0.0
        state["cycle_count"] += 1
        self._save_state(state)

    def get_snapshot(self, cycle_number: int) -> dict[str, Any]:
        state = self._load_state()
        rate = self.get_burn_rate()
        remaining = self.get_remaining()
        projected = None
        if rate > 0:
            projected = cycle_number + int(remaining / rate)
        return {
            "cycle_number": cycle_number,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "total_budget_usd": self.monthly_budget_usd,
            "spent_usd": state["total_spent"],
            "remaining_usd": remaining,
            "burn_rate_per_cycle": rate,
            "projected_depletion_cycle": projected,
            "economy_mode_active": state["economy_mode"],
            "daily_spent": state["daily_spent"],
        }

    def is_alert_threshold_reached(self) -> bool:
        state = self._load_state()
        return (state["total_spent"] / self.monthly_budget_usd) >= self.alert_threshold_percent
