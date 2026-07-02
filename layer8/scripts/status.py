"""Layer 8 — Status Script.

Quick CLI status: pass rate, cycle count, budget, alerts, active tracks.
No dashboard required — reads directly from database.
~100 lines | Category: CLI
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import datetime, timezone
from typing import Any, Optional


def get_status(db_path: str) -> None:
    """Print system status to stdout."""
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
    except sqlite3.OperationalError:
        print(f"Error: Cannot open database at {db_path}")
        sys.exit(1)

    print("\n═══ Self-Improving AI — System Status ═══\n")

    # System state
    state = _get_states(conn)
    status = state.get("system_status", "unknown")
    economy = state.get("economy_mode_active", "false")
    overnight = state.get("overnight_active", "false")
    tier = state.get("graduation_tier", "G0")

    status_symbol = "●" if status == "running" else "○"
    print(f"  System:    {status_symbol} {status}")
    print(f"  Economy:   {'ON' if economy == 'true' else 'off'}")
    print(f"  Overnight: {'ACTIVE' if overnight == 'true' else 'off'}")
    print(f"  Tier:      {tier}")

    # Pass rate
    rate = _query_scalar(
        conn,
        "SELECT COUNT(CASE WHEN outcome='PASS' THEN 1 END)*1.0 / "
        "NULLIF(COUNT(*),0) FROM cycle WHERE is_benchmark=0 OR is_benchmark IS NULL",
    )
    rate_str = f"{rate * 100:.1f}%" if rate else "N/A"

    # Cycle count
    total = _query_scalar(conn, "SELECT COUNT(*) FROM cycle") or 0
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    today_count = (
        _query_scalar(
            conn, "SELECT COUNT(*) FROM cycle WHERE created_at >= ?", (today_str,)
        )
        or 0
    )

    print(f"\n  Pass Rate: {rate_str}")
    print(f"  Cycles:    {total} total, {today_count} today")

    # Budget
    month_start = datetime.now(timezone.utc).strftime("%Y-%m-01")
    monthly_spent = (
        _query_scalar(
            conn,
            "SELECT COALESCE(SUM(cost_usd),0) FROM cost_event WHERE created_at >= ?",
            (month_start,),
        )
        or 0.0
    )
    daily_spent = (
        _query_scalar(
            conn,
            "SELECT COALESCE(SUM(cost_usd),0) FROM cost_event WHERE created_at >= ?",
            (today_str,),
        )
        or 0.0
    )
    print(f"\n  Budget:    ${daily_spent:.2f} today, ${monthly_spent:.2f} this month")

    # Alerts
    alerts = _query_scalar(
        conn, "SELECT COUNT(*) FROM alert WHERE acknowledged=0"
    ) or 0
    print(f"  Alerts:    {alerts} unacknowledged")

    # Approvals
    approvals = _query_scalar(
        conn, "SELECT COUNT(*) FROM approval_queue WHERE status='PENDING'"
    ) or 0
    print(f"  Approvals: {approvals} pending")

    # Active tracks
    tracks = _query_scalar(
        conn,
        "SELECT COUNT(DISTINCT track_id) FROM cost_event "
        "WHERE created_at >= date('now', '-7 days')",
    ) or 0
    print(f"  Tracks:    {tracks} active")

    # Agents
    agents = _query_scalar(
        conn,
        "SELECT COUNT(*) FROM agent_registry WHERE state NOT IN ('DISSOLVED', 'PROPOSED')",
    ) or 0
    print(f"  Agents:    {agents} active/training")

    print("\n═════════════════════════════════════════\n")
    conn.close()


def _get_states(conn: sqlite3.Connection) -> dict[str, str]:
    try:
        rows = conn.execute("SELECT key, value FROM system_state").fetchall()
        return {r["key"]: r["value"] for r in rows}
    except sqlite3.OperationalError:
        return {}


def _query_scalar(
    conn: sqlite3.Connection, sql: str, params: tuple[Any, ...] = ()
) -> Any:
    try:
        row = conn.execute(sql, params).fetchone()
        return row[0] if row else None
    except sqlite3.OperationalError:
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Quick system status")
    parser.add_argument("--db", default="data/system.db", help="Database path")
    args = parser.parse_args()
    get_status(args.db)


if __name__ == "__main__":
    main()
