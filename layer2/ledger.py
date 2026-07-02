"""Layer 2 — SQLite-based ledger for persistent storage.

Manages all database operations with WAL mode, parameterized queries,
and Result-typed returns. Implements LedgerProtocol.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Generator, Optional

from ..result import Result, LedgerError, LedgerErrorType


class LedgerManager:
    """SQLite-backed storage implementing LedgerProtocol."""

    def __init__(self, db_path: Path, schema_path: Optional[Path] = None) -> None:
        self._db_path = db_path
        self._schema_path = schema_path
        self._local = threading.local()

    @property
    def _conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            conn = sqlite3.connect(str(self._db_path), timeout=5.0)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA busy_timeout=5000")
            conn.row_factory = sqlite3.Row
            self._local.conn = conn
        return self._local.conn

    def initialize(self) -> Result[None, LedgerError]:
        """Initialize database schema."""
        if self._schema_path and self._schema_path.exists():
            try:
                schema = self._schema_path.read_text()
                self._conn.executescript(schema)
                return Result(value=None)
            except sqlite3.Error as exc:
                return Result(error=LedgerError(
                    error_type=LedgerErrorType.INTEGRITY_VIOLATION,
                    message=f"Schema init failed: {exc}",
                ))
        return Result(value=None)

    def close(self) -> None:
        if hasattr(self._local, "conn") and self._local.conn:
            self._local.conn.close()
            self._local.conn = None

    @contextmanager
    def transaction(self) -> Generator[sqlite3.Connection, None, None]:
        """Context manager for atomic transactions."""
        conn = self._conn
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    # === Cycle CRUD ===

    def write_cycle(self, record: dict[str, Any]) -> Result[None, LedgerError]:
        try:
            with self.transaction() as conn:
                cols = ", ".join(record.keys())
                placeholders = ", ".join("?" * len(record))
                values = [
                    json.dumps(v) if isinstance(v, (dict, list)) else v
                    for v in record.values()
                ]
                conn.execute(
                    f"INSERT INTO cycle ({cols}) VALUES ({placeholders})", values
                )
            return Result(value=None)
        except sqlite3.IntegrityError as exc:
            return Result(error=LedgerError(
                error_type=LedgerErrorType.DUPLICATE,
                message=f"Cycle write failed: {exc}",
            ))
        except sqlite3.Error as exc:
            return Result(error=LedgerError(
                error_type=LedgerErrorType.INTEGRITY_VIOLATION,
                message=f"Cycle write error: {exc}",
            ))

    def read_cycle(self, cycle_number: int) -> Result[dict[str, Any], LedgerError]:
        try:
            row = self._conn.execute(
                "SELECT * FROM cycle WHERE cycle_number = ?", (cycle_number,)
            ).fetchone()
            if row is None:
                return Result(error=LedgerError(
                    error_type=LedgerErrorType.NOT_FOUND,
                    message=f"Cycle {cycle_number} not found",
                ))
            return Result(value=dict(row))
        except sqlite3.Error as exc:
            return Result(error=LedgerError(
                error_type=LedgerErrorType.INTEGRITY_VIOLATION,
                message=f"Cycle read error: {exc}",
            ))

    def read_cycles(self, start: int, end: int) -> Result[list[dict], LedgerError]:
        try:
            rows = self._conn.execute(
                "SELECT * FROM cycle WHERE cycle_number BETWEEN ? AND ? ORDER BY cycle_number",
                (start, end),
            ).fetchall()
            return Result(value=[dict(r) for r in rows])
        except sqlite3.Error as exc:
            return Result(error=LedgerError(
                error_type=LedgerErrorType.INTEGRITY_VIOLATION,
                message=str(exc),
            ))

    def query_cycles(self, **filters: Any) -> Result[list[dict], LedgerError]:
        try:
            conditions = []
            values = []
            for key, value in filters.items():
                conditions.append(f"{key} = ?")
                values.append(value)
            where = " AND ".join(conditions) if conditions else "1=1"
            rows = self._conn.execute(
                f"SELECT * FROM cycle WHERE {where} ORDER BY cycle_number DESC LIMIT 1000",
                values,
            ).fetchall()
            return Result(value=[dict(r) for r in rows])
        except sqlite3.Error as exc:
            return Result(error=LedgerError(
                error_type=LedgerErrorType.INTEGRITY_VIOLATION,
                message=str(exc),
            ))

    # === Generic CRUD ===

    def insert(self, table: str, record: dict[str, Any]) -> Result[None, LedgerError]:
        try:
            with self.transaction() as conn:
                cols = ", ".join(record.keys())
                placeholders = ", ".join("?" * len(record))
                values = [
                    json.dumps(v) if isinstance(v, (dict, list)) else v
                    for v in record.values()
                ]
                conn.execute(f"INSERT INTO {table} ({cols}) VALUES ({placeholders})", values)
            return Result(value=None)
        except sqlite3.IntegrityError as exc:
            return Result(error=LedgerError(error_type=LedgerErrorType.DUPLICATE, message=str(exc)))
        except sqlite3.Error as exc:
            return Result(error=LedgerError(error_type=LedgerErrorType.INTEGRITY_VIOLATION, message=str(exc)))

    def update(
        self, table: str, key_col: str, key_val: Any,
        updates: dict[str, Any],
    ) -> Result[None, LedgerError]:
        try:
            with self.transaction() as conn:
                set_clause = ", ".join(f"{k} = ?" for k in updates)
                values = [
                    json.dumps(v) if isinstance(v, (dict, list)) else v
                    for v in updates.values()
                ]
                values.append(key_val)
                conn.execute(
                    f"UPDATE {table} SET {set_clause} WHERE {key_col} = ?", values
                )
            return Result(value=None)
        except sqlite3.Error as exc:
            return Result(error=LedgerError(error_type=LedgerErrorType.INTEGRITY_VIOLATION, message=str(exc)))

    def query(
        self, table: str, where: str = "1=1",
        params: tuple = (), limit: int = 1000,
    ) -> Result[list[dict], LedgerError]:
        try:
            rows = self._conn.execute(
                f"SELECT * FROM {table} WHERE {where} LIMIT ?",
                (*params, limit),
            ).fetchall()
            return Result(value=[dict(r) for r in rows])
        except sqlite3.Error as exc:
            return Result(error=LedgerError(error_type=LedgerErrorType.INTEGRITY_VIOLATION, message=str(exc)))

    def get_by_id(self, table: str, id_col: str, id_val: Any) -> Result[Optional[dict], LedgerError]:
        try:
            row = self._conn.execute(
                f"SELECT * FROM {table} WHERE {id_col} = ?", (id_val,)
            ).fetchone()
            return Result(value=dict(row) if row else None)
        except sqlite3.Error as exc:
            return Result(error=LedgerError(error_type=LedgerErrorType.INTEGRITY_VIOLATION, message=str(exc)))

    def count(self, table: str, where: str = "1=1", params: tuple = ()) -> Result[int, LedgerError]:
        try:
            row = self._conn.execute(
                f"SELECT COUNT(*) as cnt FROM {table} WHERE {where}", params
            ).fetchone()
            return Result(value=row["cnt"] if row else 0)
        except sqlite3.Error as exc:
            return Result(error=LedgerError(error_type=LedgerErrorType.INTEGRITY_VIOLATION, message=str(exc)))

    # === Track Operations (NEW) ===

    def get_track_definition(self, track_id: str) -> Result[Optional[dict], LedgerError]:
        return self.get_by_id("track_definition", "track_id", track_id)

    def get_all_track_definitions(self) -> Result[list[dict], LedgerError]:
        return self.query("track_definition")

    def get_track_performance(self, track_id: str) -> Result[Optional[dict], LedgerError]:
        return self.get_by_id("track_performance", "track_id", track_id)

    def update_track_performance(self, track_id: str, updates: dict) -> Result[None, LedgerError]:
        updates["updated_at"] = datetime.now(timezone.utc).isoformat()
        return self.update("track_performance", "track_id", track_id, updates)

    def get_track_graduation_state(self, track_id: str, gate: str) -> Result[Optional[dict], LedgerError]:
        return self.query(
            "track_graduation_state",
            where="track_id = ? AND gate_name = ?",
            params=(track_id, gate),
            limit=1,
        ).map(lambda rows: rows[0] if rows else None) if False else self._track_grad_state(track_id, gate)

    def _track_grad_state(self, track_id: str, gate: str) -> Result[Optional[dict], LedgerError]:
        try:
            row = self._conn.execute(
                "SELECT * FROM track_graduation_state WHERE track_id = ? AND gate_name = ? ORDER BY id DESC LIMIT 1",
                (track_id, gate),
            ).fetchone()
            return Result(value=dict(row) if row else None)
        except sqlite3.Error as exc:
            return Result(error=LedgerError(error_type=LedgerErrorType.INTEGRITY_VIOLATION, message=str(exc)))

    def log_track_schedule(self, record: dict) -> Result[None, LedgerError]:
        record.setdefault("created_at", datetime.now(timezone.utc).isoformat())
        return self.insert("track_schedule_log", record)

    def insert_cross_track_insight(self, record: dict) -> Result[None, LedgerError]:
        record.setdefault("created_at", datetime.now(timezone.utc).isoformat())
        return self.insert("cross_track_insights", record)

    def log_graduation_ceiling(self, record: dict) -> Result[None, LedgerError]:
        record.setdefault("created_at", datetime.now(timezone.utc).isoformat())
        return self.insert("graduation_ceiling_flags", record)

    def insert_graduation_override(self, record: dict) -> Result[None, LedgerError]:
        record.setdefault("created_at", datetime.now(timezone.utc).isoformat())
        return self.insert("graduation_overrides", record)

    def log_task_generation(self, record: dict) -> Result[None, LedgerError]:
        record.setdefault("created_at", datetime.now(timezone.utc).isoformat())
        return self.insert("task_generation_log", record)

    def get_task_generation_capability(self, track_id: str) -> Result[Optional[dict], LedgerError]:
        return self.get_by_id("task_generation_capability", "track_id", track_id)

    def update_task_generation_capability(self, track_id: str, updates: dict) -> Result[None, LedgerError]:
        updates["updated_at"] = datetime.now(timezone.utc).isoformat()
        return self.update("task_generation_capability", "track_id", track_id, updates)

    # === Pattern Operations ===

    def insert_pattern(self, record: dict) -> Result[None, LedgerError]:
        return self.insert("patterns", record)

    def get_pattern(self, pattern_id: str) -> Result[Optional[dict], LedgerError]:
        return self.get_by_id("patterns", "pattern_id", pattern_id)

    def query_patterns(self, status: Optional[str] = None, limit: int = 100) -> Result[list[dict], LedgerError]:
        if status:
            return self.query("patterns", "status = ?", (status,), limit)
        return self.query("patterns", limit=limit)

    # === Failure Chain Operations ===

    def insert_failure_narrative(self, record: dict) -> Result[None, LedgerError]:
        return self.insert("failure_narratives", record)

    def insert_failure_chain(self, record: dict) -> Result[None, LedgerError]:
        return self.insert("failure_chains", record)

    def get_failure_chain(self, chain_id: str) -> Result[Optional[dict], LedgerError]:
        return self.get_by_id("failure_chains", "chain_id", chain_id)

    def get_active_failure_chains(self, limit: int = 50) -> Result[list[dict], LedgerError]:
        return self.query("failure_chains", "status IN ('growing', 'stable')", limit=limit)

    # === Strategy Operations ===

    def insert_strategy_update(self, record: dict) -> Result[None, LedgerError]:
        return self.insert("strategy_updates", record)

    def get_active_strategies(self, limit: int = 20) -> Result[list[dict], LedgerError]:
        return self.query("strategy_updates", "status IN ('proposed', 'in_probation', 'confirmed')", limit=limit)

    # === Agent Operations ===

    def insert_agent(self, record: dict) -> Result[None, LedgerError]:
        return self.insert("agent_registry", record)

    def get_agent(self, agent_id: str) -> Result[Optional[dict], LedgerError]:
        return self.get_by_id("agent_registry", "agent_id", agent_id)

    def list_agents(self, lifecycle: Optional[str] = None) -> Result[list[dict], LedgerError]:
        if lifecycle:
            return self.query("agent_registry", "lifecycle = ?", (lifecycle,))
        return self.query("agent_registry")

    def update_agent(self, agent_id: str, updates: dict) -> Result[None, LedgerError]:
        return self.update("agent_registry", "agent_id", agent_id, updates)

    # === Benchmark Operations ===

    def insert_benchmark_session(self, record: dict) -> Result[None, LedgerError]:
        return self.insert("benchmark_sessions", record)

    def insert_benchmark_result(self, record: dict) -> Result[None, LedgerError]:
        return self.insert("benchmark_results", record)

    def get_benchmark_session(self, session_id: str) -> Result[Optional[dict], LedgerError]:
        return self.get_by_id("benchmark_sessions", "session_id", session_id)

    # === Approval Operations ===

    def insert_approval_request(self, record: dict) -> Result[None, LedgerError]:
        return self.insert("approval_queue", record)

    def get_pending_approvals(self) -> Result[list[dict], LedgerError]:
        return self.query("approval_queue", "status = 'pending'")

    def update_approval(self, request_id: str, updates: dict) -> Result[None, LedgerError]:
        return self.update("approval_queue", "request_id", request_id, updates)

    # === Analytics Operations ===

    def get_recent_pass_rate(self, n_cycles: int = 100, track_id: Optional[str] = None) -> Result[float, LedgerError]:
        try:
            if track_id:
                rows = self._conn.execute(
                    "SELECT passed FROM cycle WHERE domain_track = ? ORDER BY cycle_number DESC LIMIT ?",
                    (track_id, n_cycles),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT passed FROM cycle ORDER BY cycle_number DESC LIMIT ?",
                    (n_cycles,),
                ).fetchall()
            if not rows:
                return Result(value=0.0)
            passed = sum(1 for r in rows if r["passed"])
            return Result(value=passed / len(rows))
        except sqlite3.Error as exc:
            return Result(error=LedgerError(error_type=LedgerErrorType.INTEGRITY_VIOLATION, message=str(exc)))

    def get_cycle_count(self, track_id: Optional[str] = None) -> Result[int, LedgerError]:
        if track_id:
            return self.count("cycle", "domain_track = ?", (track_id,))
        return self.count("cycle")

    # === System Events ===

    def log_system_event(self, record: dict) -> Result[None, LedgerError]:
        record.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
        return self.insert("system_events", record)

    # === Budget Tracking ===

    def insert_budget_snapshot(self, record: dict) -> Result[None, LedgerError]:
        return self.insert("budget_snapshots", record)

    def insert_llm_call(self, record: dict) -> Result[None, LedgerError]:
        return self.insert("llm_call_log", record)

    def get_total_spent(self, since: Optional[str] = None) -> Result[float, LedgerError]:
        try:
            if since:
                row = self._conn.execute(
                    "SELECT COALESCE(SUM(cost_usd), 0) as total FROM llm_call_log WHERE timestamp >= ?",
                    (since,),
                ).fetchone()
            else:
                row = self._conn.execute(
                    "SELECT COALESCE(SUM(cost_usd), 0) as total FROM llm_call_log"
                ).fetchone()
            return Result(value=float(row["total"]) if row else 0.0)
        except sqlite3.Error as exc:
            return Result(error=LedgerError(error_type=LedgerErrorType.INTEGRITY_VIOLATION, message=str(exc)))
