"""Layer 8 — Dashboard HTML.

Embedded HTML/CSS/JS for single-page dashboard. No build tools.
Auto-refresh via polling. 15 panels in priority order.
~260 lines | Category: DASHBOARD
"""
from __future__ import annotations

from typing import Any


class DashboardHTML:
    """Generates the single-page dashboard HTML.

    No external dependencies or build tools. All CSS and JS inline.
    Auto-refresh via fetch() polling at configurable interval.
    """

    def __init__(self, config: Any) -> None:
        self._config = config

    def render(self, refresh_seconds: int = 30) -> str:
        """Render the full dashboard HTML page."""
        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Self-Improving AI — Dashboard</title>
    <style>
        {self._css()}
    </style>
</head>
<body>
    <div id="app">
        <header id="status-banner" class="panel banner">
            <h1>Self-Improving Engineering AI</h1>
            <div id="status-indicators"></div>
        </header>

        <div id="smart-digest" class="panel digest" style="display:none">
            <h2>Welcome Back</h2>
            <div id="digest-content"></div>
            <button onclick="dismissDigest()">Dismiss</button>
        </div>

        <div id="action-queue" class="panel">
            <h2>Action Queue</h2>
            <div id="action-content"></div>
        </div>

        <div class="grid-2col">
            <div id="learning-curve" class="panel">
                <h2>Learning Curve</h2>
                <div id="learning-content"></div>
            </div>
            <div id="change-attribution" class="panel">
                <h2>Change Attribution</h2>
                <div id="attribution-content"></div>
            </div>
        </div>

        <div id="track-performance" class="panel">
            <h2>Track Performance</h2>
            <div id="track-content"></div>
        </div>

        <div id="skill-heatmap" class="panel">
            <h2>Skill Heatmap</h2>
            <div id="heatmap-content"></div>
        </div>

        <div class="grid-2col">
            <div id="cost-roi" class="panel">
                <h2>Cost &amp; ROI</h2>
                <div id="cost-content"></div>
            </div>
            <div id="failure-spotlight" class="panel">
                <h2>Failure Spotlight</h2>
                <div id="failure-content"></div>
            </div>
        </div>

        <div class="grid-2col">
            <div id="time-to-milestone" class="panel">
                <h2>Time to Milestone</h2>
                <div id="milestone-content"></div>
            </div>
            <div id="agent-overview" class="panel">
                <h2>Agent Overview</h2>
                <div id="agent-content"></div>
            </div>
        </div>

        <div id="benchmark-section" class="panel operator-only">
            <h2>Benchmark Results (Operator Only)</h2>
            <div id="benchmark-content"></div>
        </div>

        <div class="grid-2col">
            <div id="knowledge-summary" class="panel">
                <h2>Knowledge Summary</h2>
                <div id="knowledge-content"></div>
            </div>
            <div id="honesty-panel" class="panel">
                <h2>Honesty Panel</h2>
                <div id="honesty-content"></div>
            </div>
        </div>

        <div id="activity-feed" class="panel">
            <h2>Activity Feed</h2>
            <div id="feed-content"></div>
        </div>

        <footer>
            <span id="last-updated"></span>
            <span>Auto-refresh: {refresh_seconds}s</span>
        </footer>
    </div>

    <script>
        {self._javascript(refresh_seconds)}
    </script>
</body>
</html>"""

    @staticmethod
    def _css() -> str:
        """Inline CSS for the dashboard."""
        return """
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #0d1117;
            color: #c9d1d9;
            line-height: 1.5;
        }
        #app {
            max-width: 1400px;
            margin: 0 auto;
            padding: 16px;
        }
        .panel {
            background: #161b22;
            border: 1px solid #30363d;
            border-radius: 8px;
            padding: 16px;
            margin-bottom: 16px;
        }
        .banner {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 20px;
        }
        .banner h1 { font-size: 20px; font-weight: 600; }
        .digest { border-left: 4px solid #58a6ff; }
        .grid-2col {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 16px;
        }
        h2 {
            font-size: 14px;
            font-weight: 600;
            text-transform: uppercase;
            color: #8b949e;
            margin-bottom: 12px;
        }
        .metric {
            font-size: 32px;
            font-weight: 700;
            color: #f0f6fc;
        }
        .metric-label {
            font-size: 12px;
            color: #8b949e;
        }
        .status-green { color: #3fb950; }
        .status-amber { color: #d29922; }
        .status-red { color: #f85149; }
        .badge {
            display: inline-block;
            padding: 2px 8px;
            border-radius: 12px;
            font-size: 12px;
            font-weight: 600;
        }
        .badge-green { background: #238636; color: #fff; }
        .badge-amber { background: #9e6a03; color: #fff; }
        .badge-red { background: #da3633; color: #fff; }
        table {
            width: 100%;
            border-collapse: collapse;
        }
        th, td {
            text-align: left;
            padding: 8px;
            border-bottom: 1px solid #21262d;
            font-size: 13px;
        }
        th { color: #8b949e; font-weight: 600; }
        button {
            background: #21262d;
            color: #c9d1d9;
            border: 1px solid #30363d;
            padding: 6px 16px;
            border-radius: 6px;
            cursor: pointer;
            font-size: 13px;
        }
        button:hover { background: #30363d; }
        footer {
            display: flex;
            justify-content: space-between;
            padding: 16px 0;
            font-size: 12px;
            color: #484f58;
        }
        @media (max-width: 768px) {
            .grid-2col { grid-template-columns: 1fr; }
        }
        """

    @staticmethod
    def _javascript(refresh_seconds: int) -> str:
        """Inline JavaScript for auto-refresh and data binding."""
        return f"""
        const REFRESH_MS = {refresh_seconds * 1000};

        async function fetchData(endpoint) {{
            try {{
                const res = await fetch(endpoint);
                return await res.json();
            }} catch (e) {{
                console.error('Fetch error:', endpoint, e);
                return null;
            }}
        }}

        function updateBanner(data) {{
            if (!data) return;
            const el = document.getElementById('status-indicators');
            const statusClass = data.status === 'running' ? 'status-green' :
                               data.status === 'stopped' ? 'status-red' : 'status-amber';
            el.innerHTML = `
                <span class="${{statusClass}}">${{data.status || 'unknown'}}</span>
                &nbsp;|&nbsp; Pass Rate: <strong>${{(data.pass_rate * 100).toFixed(1)}}%</strong>
                &nbsp;|&nbsp; Cycles: <strong>${{data.cycle_count}}</strong>
                &nbsp;|&nbsp; Tier: <strong>${{data.graduation_tier}}</strong>
                &nbsp;|&nbsp; Alerts: <strong>${{data.alerts?.total || 0}}</strong>
                &nbsp;|&nbsp; Approvals: <strong>${{data.pending_approvals}}</strong>
            `;
        }}

        function updateDigest(data) {{
            if (!data?.smart_digest) return;
            const d = data.smart_digest;
            document.getElementById('smart-digest').style.display = 'block';
            document.getElementById('digest-content').innerHTML = `
                <p>You were away for <strong>${{d.absence_hours}}h</strong>.</p>
                <p>Cycles completed: ${{d.cycles_completed}}</p>
                <p>Alerts fired: ${{d.alerts_fired}}</p>
                <p>Pending approvals: ${{d.pending_approvals}}</p>
            `;
        }}

        function updateCost(data) {{
            if (!data) return;
            const el = document.getElementById('cost-content');
            el.innerHTML = `
                <div class="metric">${{data.monthly_projection ? '$' + data.monthly_projection : '--'}}</div>
                <div class="metric-label">Monthly Projection</div>
                <p>Cost/pp improvement: ${{data.cost_per_pp || 'N/A'}}</p>
            `;
        }}

        function updateAgents(data) {{
            if (!data?.agents?.length) {{
                document.getElementById('agent-content').innerHTML = '<p>No active agents</p>';
                return;
            }}
            let html = '<table><tr><th>Agent</th><th>State</th><th>Track</th></tr>';
            data.agents.forEach(a => {{
                html += `<tr><td>${{a.agent_id}}</td><td>${{a.state}}</td><td>${{a.domain_track || ''}}</td></tr>`;
            }});
            html += '</table>';
            document.getElementById('agent-content').innerHTML = html;
        }}

        function updateTimestamp() {{
            document.getElementById('last-updated').textContent =
                'Last updated: ' + new Date().toLocaleTimeString();
        }}

        function dismissDigest() {{
            document.getElementById('smart-digest').style.display = 'none';
        }}

        async function refresh() {{
            const snapshot = await fetchData('/api/snapshot');
            updateBanner(snapshot);
            updateDigest(snapshot);

            const cost = await fetchData('/api/cost-detailed');
            updateCost(cost);

            const agents = await fetchData('/api/agents');
            updateAgents(agents);

            updateTimestamp();
        }}

        // Initial load
        refresh();
        // Auto-refresh
        setInterval(refresh, REFRESH_MS);
        """
