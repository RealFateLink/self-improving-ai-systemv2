"""Layer 8 — Approve Script.

CLI for approval queue: list pending, approve with confirmation,
decline with required reason. Handles 8 approval types.
~130 lines | Category: CLI
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from typing import Any, Optional


APPROVAL_TYPES = [
    "STRATEGY_UPDATE",
    "AGENT_PROPOSAL",
    "TRACK_ACTIVATION",
    "TRACK_DEACTIVATION",
    "GRADUATION_GATE",
    "CONFIG_CHANGE_DANGEROUS",
    "AGENT_MERGE",
    "SELF_IMPROVEMENT",
]


def list_pending(conn: sqlite3.Connection) -> None:
    """List all pending approval items."""
    cursor = conn.execute(
        "SELECT * FROM approval_queue WHERE status = 'PENDING' "
        "ORDER BY created_at DESC"
    )
    rows = cursor.fetchall()

    if not rows:
        print("No pending approvals.")
        return

    print(f"\n{'ID':<20} {'Type':<25} {'Created':<22} {'Summary'}")
    print("-" * 90)
    for row in rows:
        item_id = row["item_id"] if "item_id" in row.keys() else row[0]
        item_type = row["item_type"] if "item_type" in row.keys() else row[1]
        created = row["created_at"] if "created_at" in row.keys() else row[2]
        summary = row["summary"] if "summary" in row.keys() else row[3]
        print(f"{item_id:<20} {item_type:<25} {created:<22} {summary}")

    print(f"\n{len(rows)} pending approval(s)")


def show_detail(conn: sqlite3.Connection, item_id: str) -> None:
    """Show detailed information for an approval item."""
    cursor = conn.execute(
        "SELECT * FROM approval_queue WHERE item_id = ?", (item_id,)
    )
    row = cursor.fetchone()

    if not row:
        print(f"Approval item '{item_id}' not found.")
        return

    print(f"\n{'='*60}")
    row_dict = dict(row)
    for key, value in row_dict.items():
        if key == "evidence_json":
            print(f"  {key}:")
            try:
                evidence = json.loads(value)
                print(json.dumps(evidence, indent=4))
            except (json.JSONDecodeError, TypeError):
                print(f"    {value}")
        else:
            print(f"  {key}: {value}")
    print(f"{'='*60}")


def approve_item(conn: sqlite3.Connection, item_id: str) -> None:
    """Approve an item with confirmation."""
    cursor = conn.execute(
        "SELECT item_id, item_type, summary FROM approval_queue "
        "WHERE item_id = ? AND status = 'PENDING'",
        (item_id,),
    )
    row = cursor.fetchone()

    if not row:
        print(f"Pending item '{item_id}' not found.")
        return

    print(f"\nApprove: {row['item_type']} — {row['summary']}")
    confirm = input("Confirm approval? [y/N]: ").strip().lower()

    if confirm != "y":
        print("Cancelled.")
        return

    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "UPDATE approval_queue SET status = 'APPROVED', resolved_at = ? "
        "WHERE item_id = ?",
        (now, item_id),
    )
    conn.commit()
    print(f"Approved: {item_id}")


def decline_item(
    conn: sqlite3.Connection, item_id: str, reason: str
) -> None:
    """Decline an item with required reason."""
    if not reason.strip():
        print("Error: Reason is required for declining.")
        sys.exit(1)

    cursor = conn.execute(
        "SELECT item_id FROM approval_queue "
        "WHERE item_id = ? AND status = 'PENDING'",
        (item_id,),
    )
    row = cursor.fetchone()

    if not row:
        print(f"Pending item '{item_id}' not found.")
        return

    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "UPDATE approval_queue SET status = 'DECLINED', "
        "resolved_at = ?, decline_reason = ? WHERE item_id = ?",
        (now, reason, item_id),
    )
    conn.commit()
    print(f"Declined: {item_id} — Reason: {reason}")


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Manage the approval queue"
    )
    parser.add_argument("--db", default="data/system.db", help="Database path")
    parser.add_argument("--list", action="store_true", help="List pending items")
    parser.add_argument("--detail", metavar="ID", help="Show item details")
    parser.add_argument("--approve", metavar="ID", help="Approve an item")
    parser.add_argument("--decline", metavar="ID", help="Decline an item")
    parser.add_argument(
        "--reason", default="", help="Reason for declining (required)"
    )

    args = parser.parse_args()

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row

    if args.list:
        list_pending(conn)
    elif args.detail:
        show_detail(conn, args.detail)
    elif args.approve:
        approve_item(conn, args.approve)
    elif args.decline:
        decline_item(conn, args.decline, args.reason)
    else:
        parser.print_help()

    conn.close()


if __name__ == "__main__":
    main()
