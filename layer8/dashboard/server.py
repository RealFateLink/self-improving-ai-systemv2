"""Layer 8 — Dashboard Server.

Embedded HTTP server using Python http.server. Read-only DB connection.
Route dispatch for API and HTML endpoints. Auto-refresh support.
Localhost binding by default.
~300 lines | Category: DASHBOARD
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
from functools import partial
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Any, Optional
from urllib.parse import urlparse, parse_qs

logger = logging.getLogger(__name__)

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8420
DEFAULT_REFRESH_SECONDS = 30


class DashboardRequestHandler(BaseHTTPRequestHandler):
    """HTTP request handler for the monitoring dashboard.

    Routes:
      /                → Dashboard HTML page
      /api/*           → JSON API endpoints
      /health          → Health check
    """

    api: Optional[Any] = None
    html_renderer: Optional[Any] = None
    refresh_seconds: int = DEFAULT_REFRESH_SECONDS

    def do_GET(self) -> None:
        """Handle GET requests."""
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        query = parse_qs(parsed.query)

        try:
            if path == "" or path == "/":
                self._serve_dashboard()
            elif path == "/health":
                self._serve_health()
            elif path.startswith("/api/"):
                self._serve_api(path, query)
            else:
                self._send_404()

        except Exception as exc:
            logger.error("Request error for %s: %s", self.path, exc)
            self._send_error(500, str(exc))

    def _serve_dashboard(self) -> None:
        """Serve the main dashboard HTML page."""
        if self.html_renderer is None:
            self._send_error(503, "HTML renderer not initialized")
            return

        html = self.html_renderer.render(
            refresh_seconds=self.refresh_seconds
        )
        self._send_response(200, html, content_type="text/html")

    def _serve_health(self) -> None:
        """Serve health check."""
        self._send_json(200, {"status": "ok", "service": "dashboard"})

    def _serve_api(self, path: str, query: dict[str, list[str]]) -> None:
        """Route API requests to the API module."""
        if self.api is None:
            self._send_error(503, "API not initialized")
            return

        # Route mapping
        routes: dict[str, Any] = {
            "/api/snapshot": self.api.get_snapshot,
            "/api/tracks": self.api.get_tracks,
            "/api/cost-detailed": self.api.get_cost_detailed,
            "/api/cycles": lambda: self.api.get_cycles(
                n=int(query.get("n", ["100"])[0])
            ),
            "/api/approvals": self.api.get_approvals,
            "/api/benchmarks": self.api.get_benchmarks,
            "/api/self-model": self.api.get_self_model,
            "/api/agents": self.api.get_agents,
            "/api/graduation": self.api.get_graduation,
            "/api/integrity": self.api.get_integrity,
        }

        # Skill deep-dive: /api/skill/{skill_id}
        if path.startswith("/api/skill/"):
            skill_id = path[len("/api/skill/"):]
            data = self.api.get_skill_detail(skill_id)
            self._send_json(200, data)
            return

        handler = routes.get(path)
        if handler is None:
            self._send_404()
            return

        data = handler()
        self._send_json(200, data)

    # ── Response Helpers ─────────────────────────────────────────────────────

    def _send_response(
        self, code: int, body: str, content_type: str = "text/plain"
    ) -> None:
        self.send_response(code)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        encoded = body.encode("utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _send_json(self, code: int, data: Any) -> None:
        body = json.dumps(data, default=str, indent=2)
        self._send_response(code, body, content_type="application/json")

    def _send_404(self) -> None:
        self._send_json(404, {"error": "Not found", "path": self.path})

    def _send_error(self, code: int, message: str) -> None:
        self._send_json(code, {"error": message})

    def log_message(self, format: str, *args: Any) -> None:
        """Override to use Python logging instead of stderr."""
        logger.debug("Dashboard: %s", format % args)


class DashboardServer:
    """Embedded HTTP server for the monitoring dashboard.

    READ-ONLY: Uses a separate read-only SQLite connection.
    Localhost binding by default. Warning if bound to 0.0.0.0.
    """

    def __init__(
        self,
        db_path: str,
        config: Any,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
    ) -> None:
        self._db_path = db_path
        self._config = config
        self._host = host
        self._port = port
        self._server: Optional[HTTPServer] = None
        self._thread: Optional[threading.Thread] = None
        self._refresh_seconds = getattr(
            config, "refresh_interval_seconds", DEFAULT_REFRESH_SECONDS
        )

        if host == "0.0.0.0":
            logger.warning(
                "Dashboard bound to 0.0.0.0 — accessible from network. "
                "Consider using 127.0.0.1 for security."
            )

    def start(self) -> None:
        """Start the dashboard server in a background thread."""
        # Create read-only DB connection
        ro_uri = f"file:{self._db_path}?mode=ro"
        ro_conn = sqlite3.connect(ro_uri, uri=True, check_same_thread=False)
        ro_conn.row_factory = sqlite3.Row

        # Create API and HTML renderer
        from .api import DashboardAPI
        from .html import DashboardHTML

        api = DashboardAPI(ro_conn, self._config)
        html_renderer = DashboardHTML(self._config)

        # Configure handler
        DashboardRequestHandler.api = api
        DashboardRequestHandler.html_renderer = html_renderer
        DashboardRequestHandler.refresh_seconds = self._refresh_seconds

        self._server = HTTPServer(
            (self._host, self._port), DashboardRequestHandler
        )

        self._thread = threading.Thread(
            target=self._server.serve_forever,
            daemon=True,
            name="dashboard-server",
        )
        self._thread.start()

        logger.info(
            "Dashboard started at http://%s:%d (refresh: %ds)",
            self._host,
            self._port,
            self._refresh_seconds,
        )

    def stop(self) -> None:
        """Stop the dashboard server."""
        if self._server:
            self._server.shutdown()
            logger.info("Dashboard stopped")

    @property
    def url(self) -> str:
        return f"http://{self._host}:{self._port}"
