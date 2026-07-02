"""mistake_book.py — Experience replay buffer for adversarial test cases.

Layer 4 — v0.2.0.  Based on Code-A1's Mistake Book.
Tracks historically failed tests to prevent regression and improve robustness.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


@dataclass(frozen=True)
class FailedAttempt:
    """A single failed attempt record."""
    attempt_id: str
    task_id: str
    code: str
    test_input: str
    expected_output: str
    actual_output: str
    error_type: str
    cycle_number: int
    timestamp: str


@dataclass
class MistakeBook:
    """Experience replay buffer tracking historically challenging test cases.

    From Code-A1: "Mistake Book experience replay buffer tracks
    historically failed tests" — stabilizes training by maintaining
    frontier of challenging cases.
    """

    db_path: Path = field(default_factory=lambda: Path("layer0/data/meta_learning/mistake_book.db"))
    max_entries: int = 5000
    min_occurrences_for_replay: int = 2

    def __post_init__(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS mistakes (
                    attempt_id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    code TEXT NOT NULL,
                    test_input TEXT NOT NULL,
                    expected_output TEXT NOT NULL,
                    actual_output TEXT NOT NULL,
                    error_type TEXT NOT NULL,
                    cycle_number INTEGER NOT NULL,
                    timestamp TEXT NOT NULL,
                    replay_count INTEGER DEFAULT 0
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_task ON mistakes(task_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_error ON mistakes(error_type)")
            conn.commit()

    def record_failure(
        self,
        task_id: str,
        code: str,
        test_input: str,
        expected_output: str,
        actual_output: str,
        error_type: str,
        cycle_number: int,
    ) -> None:
        """Record a failed attempt in the Mistake Book."""
        attempt_id = f"fail_{cycle_number}_{task_id}_{hash(code) & 0xFFFFFFFF}"
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(
                """INSERT OR REPLACE INTO mistakes
                (attempt_id, task_id, code, test_input, expected_output, actual_output, error_type, cycle_number, timestamp, replay_count)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, COALESCE((SELECT replay_count FROM mistakes WHERE attempt_id = ?), 0) + 1)""",
                (attempt_id, task_id, code, test_input, expected_output, actual_output, error_type, cycle_number, datetime.now(timezone.utc).isoformat(), attempt_id),
            )
            conn.commit()
        self._prune_old_entries()

    def get_challenging_tests(
        self,
        task_id: Optional[str] = None,
        error_type: Optional[str] = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Get historically challenging tests for replay.

        Returns tests that have failed multiple times (frontier cases).
        """
        query = "SELECT * FROM mistakes WHERE replay_count >= ?"
        params = [self.min_occurrences_for_replay]
        if task_id:
            query += " AND task_id = ?"
            params.append(task_id)
        if error_type:
            query += " AND error_type = ?"
            params.append(error_type)
        query += " ORDER BY replay_count DESC, cycle_number DESC LIMIT ?"
        params.append(limit)

        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

    def get_failure_patterns(self, limit: int = 20) -> list[dict[str, Any]]:
        """Get most common failure patterns across all tasks."""
        with sqlite3.connect(str(self.db_path)) as conn:
            rows = conn.execute(
                """SELECT error_type, COUNT(*) as count, MAX(timestamp) as last_seen
                FROM mistakes GROUP BY error_type ORDER BY count DESC LIMIT ?""",
                (limit,),
            ).fetchall()
        return [{"error_type": r[0], "count": r[1], "last_seen": r[2]} for r in rows]

    def _prune_old_entries(self) -> None:
        with sqlite3.connect(str(self.db_path)) as conn:
            count = conn.execute("SELECT COUNT(*) FROM mistakes").fetchone()[0]
            if count > self.max_entries:
                to_delete = count - self.max_entries
                conn.execute(
                    f"DELETE FROM mistakes WHERE attempt_id IN (SELECT attempt_id FROM mistakes ORDER BY cycle_number ASC LIMIT {to_delete})"
                )
                conn.commit()

    def get_stats(self) -> dict[str, Any]:
        with sqlite3.connect(str(self.db_path)) as conn:
            total = conn.execute("SELECT COUNT(*) FROM mistakes").fetchone()[0]
            replayable = conn.execute(
                "SELECT COUNT(*) FROM mistakes WHERE replay_count >= ?",
                (self.min_occurrences_for_replay,),
            ).fetchone()[0]
        return {"total_entries": total, "replayable_entries": replayable}
