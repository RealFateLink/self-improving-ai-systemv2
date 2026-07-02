"""Layer 8 — Dashboard Entry Point.

Start the dashboard server. Passes --host, --port, --db, --config.
~35 lines | Category: CLI
"""
from __future__ import annotations

import argparse
import sys


def main() -> None:
    """Entry point for the dashboard server."""
    parser = argparse.ArgumentParser(description="Start the monitoring dashboard")
    parser.add_argument("--host", default="127.0.0.1", help="Bind address")
    parser.add_argument("--port", type=int, default=8420, help="Port")
    parser.add_argument("--db", default="data/system.db", help="Database path")
    parser.add_argument("--config", default="config/system_config.yaml", help="Config path")

    args = parser.parse_args()

    # Lazy import to avoid circular dependencies
    from ..dashboard.server import DashboardServer

    # Minimal config object
    class Config:
        refresh_interval_seconds = 30
        digest_threshold_hours = 4
        daily_budget_usd = 10.0
        monthly_budget_usd = 200.0

    server = DashboardServer(
        db_path=args.db,
        config=Config(),
        host=args.host,
        port=args.port,
    )

    print(f"Starting dashboard at http://{args.host}:{args.port}")
    server.start()

    # Keep running
    try:
        import time
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.stop()


if __name__ == "__main__":
    main()
