"""
VroomVroom Dashboard – Dash + Plotly UI.

Live view: latest snapshot as boat-themed gauges (tachometer = thread count,
speedometer = disk I/O, half-circle = RAM). Historic view: time-series charts.
Uses GET /orm/snapshots/latest and GET /orm/snapshots?expand=metrics.
"""
from __future__ import annotations

import logging
import os
from collections import defaultdict
from urllib.parse import urljoin

import dash
import plotly.graph_objects as go
import requests
from dash import dcc, html
from dash.dependencies import Input, Output

logger = logging.getLogger(__name__)

# API base URL when callbacks run server-side (same host as Flask)
API_BASE = os.environ.get("VROOMVROOM_API", "http://127.0.0.1:5000")
DEFAULT_DEVICE = os.environ.get("VROOMVROOM_DEVICE", "pc-01")
LIVE_REFRESH_INTERVAL_MS = 15_000  # 15 s
HISTORY_LIMIT = 100

# Metric name (from API) -> display label and gauge type
METRIC_CONFIG = {
    "Running Threads": {"label": "Thread count", "gauge": "tachometer", "unit": "count"},
    "Disk Usage": {"label": "Disk usage", "gauge": "speedometer", "unit": "%"},
    "RAM Usage": {"label": "RAM usage", "gauge": "fuel", "unit": "%"},
}


def _api_get(path: str, params: dict | None = None) -> dict | list:
    """GET JSON from API; raises requests.HTTPError on non-2xx."""
    url = urljoin(API_BASE + "/", path.lstrip("/"))
    r = requests.get(url, params=params or {}, timeout=10)
    r.raise_for_status()
    return r.json()


def _metric_by_name(metrics: list[dict], name: str) -> dict | None:
    for m in metrics:
        if m.get("name") == name:
            return m
    return None


def _build_live_gauges(snapshot: dict) -> list[go.Figure]:
    """Build Plotly gauge figures for Live view (tachometer, speedometer, half-circle)."""
    metrics = snapshot.get("metrics") or []
    figures = []

    # Tachometer (boat RPM metaphor) – Running Threads
    m = _metric_by_name(metrics, "Running Threads")
    v = m["value"] if m else 0
    mx = 400  # sensible max for thread count
    figures.append(
        go.Figure(
            go.Indicator(
                mode="gauge+number",
                value=v,
                number={"suffix": ""},
                title={"text": "Thread count<br>(RPM)"},
                gauge={
                    "axis": {"range": [0, mx], "tickwidth": 1},
                    "bar": {"color": "#1e88e5"},
                    "steps": [
                        {"range": [0, mx * 0.6], "color": "#e3f2fd"},
                        {"range": [mx * 0.6, mx * 0.85], "color": "#fff3e0"},
                        {"range": [mx * 0.85, mx], "color": "#ffebee"},
                    ],
                    "threshold": {
                        "line": {"color": "#c62828", "width": 4},
                        "thickness": 0.75,
                        "value": 300,
                    },
                },
            ),
            layout=dict(
                margin=dict(l=20, r=20, t=50, b=20),
                paper_bgcolor="rgba(227, 242, 253, 0.9)",
                font=dict(size=12),
                height=280,
            ),
        )
    )

    # Speedometer (speed metaphor) – Disk Usage %
    m = _metric_by_name(metrics, "Disk Usage")
    v = m["value"] if m else 0
    mx = 100  # percent
    figures.append(
        go.Figure(
            go.Indicator(
                mode="gauge+number",
                value=v,
                number={"suffix": "%"},
                title={"text": "Disk usage<br>(Speed)"},
                gauge={
                    "axis": {"range": [0, mx], "tickwidth": 1},
                    "bar": {"color": "#0d47a1"},
                    "steps": [
                        {"range": [0, mx * 0.6], "color": "#e3f2fd"},
                        {"range": [mx * 0.6, mx * 0.85], "color": "#bbdefb"},
                        {"range": [mx * 0.85, mx], "color": "#ffcdd2"},
                    ],
                    "threshold": {
                        "line": {"color": "#c62828", "width": 4},
                        "thickness": 0.75,
                        "value": 90,
                    },
                },
            ),
            layout=dict(
                margin=dict(l=20, r=20, t=50, b=20),
                paper_bgcolor="rgba(227, 242, 253, 0.9)",
                font=dict(size=12),
                height=280,
            ),
        )
    )

    # Half-circle fuel gauge – RAM Usage
    m = _metric_by_name(metrics, "RAM Usage")
    v = m["value"] if m else 0
    figures.append(
        go.Figure(
            go.Indicator(
                mode="gauge+number",
                value=v,
                number={"suffix": "%"},
                title={"text": "RAM usage<br>(Fuel)"},
                gauge={
                    "shape": "angular",
                    "axis": {"range": [0, 100], "tickwidth": 1},
                    "bar": {"color": "#1565c0"},
                    "steps": [
                        {"range": [0, 50], "color": "#e8f5e9"},
                        {"range": [50, 75], "color": "#fff9c4"},
                        {"range": [75, 100], "color": "#ffcdd2"},
                    ],
                    "threshold": {
                        "line": {"color": "#c62828", "width": 4},
                        "thickness": 0.75,
                        "value": 85,
                    },
                },
            ),
            layout=dict(
                margin=dict(l=20, r=20, t=50, b=20),
                paper_bgcolor="rgba(227, 242, 253, 0.9)",
                font=dict(size=12),
                height=280,
            ),
        )
    )

    return figures


def _build_historic_charts(snapshots: list[dict]) -> list[go.Figure]:
    """Build time-series line charts per metric (X=time, Y=value)."""
    if not snapshots:
        empty = go.Figure(layout=dict(
            annotations=[dict(text="No historic data", x=0.5, y=0.5, showarrow=False)],
            height=300,
        ))
        return [empty, empty, empty]

    # Group by metric name: name -> [(timestamp_utc, value), ...]
    series = defaultdict(list)
    for s in snapshots:
        ts = s.get("timestamp_utc") or ""
        for m in s.get("metrics") or []:
            name = m.get("name")
            if name in METRIC_CONFIG:
                try:
                    val = float(m.get("value", 0))
                except (TypeError, ValueError):
                    val = 0
                series[name].append((ts, val))

    # Sort each series by time (oldest first for chart)
    for name in series:
        series[name].sort(key=lambda x: x[0])

    figures = []
    for metric_name, cfg in METRIC_CONFIG.items():
        points = series.get(metric_name, [])
        if not points:
            fig = go.Figure(layout=dict(
                title=cfg["label"],
                height=300,
                annotations=[dict(text="No data", x=0.5, y=0.5, showarrow=False)],
            ))
        else:
            x = [p[0] for p in points]
            y = [p[1] for p in points]
            fig = go.Figure(
                go.Scatter(x=x, y=y, mode="lines+markers", name=cfg["label"], line=dict(width=2)),
                layout=dict(
                    title=cfg["label"] + " over time",
                    xaxis_title="Time (UTC)",
                    yaxis_title=cfg["unit"],
                    margin=dict(l=50, r=30, t=40, b=60),
                    paper_bgcolor="rgba(255,255,255,0.95)",
                    height=300,
                    xaxis=dict(tickangle=-45),
                ),
            )
        figures.append(fig)

    return figures


def create_dashboard(server=None, url_base_pathname: str = "/dashboard/"):
    """Create Dash app and layout; register callbacks. Optionally bind to Flask server."""
    app = dash.Dash(
        __name__,
        server=server,
        url_base_pathname=url_base_pathname,
        suppress_callback_exceptions=True,
        assets_folder=os.path.join(os.path.dirname(__file__), "..", "assets"),
    )

    # Inject full-width layout and hidden scrollbar so they apply to html/body (override any Dash wrappers)
    app.index_string = """<!DOCTYPE html>
<html>
<head>
    {%metas%}
    <title>{%title%}</title>
    {%favicon%}
    {%css%}
    <style>
        html, body { margin: 0; padding: 0; width: 100%%; min-height: 100%%; background: #0a4d7a; overflow-x: hidden; }
        html { scrollbar-width: none; }
        body::-webkit-scrollbar { width: 0; height: 0; background: transparent; }
        *::-webkit-scrollbar { width: 0; height: 0; background: transparent; }
        body > div { width: 100%% !important; max-width: none !important; padding: 0 !important; margin: 0 !important; }
        #react-root, ._dash-app { width: 100%% !important; max-width: none !important; padding: 0 !important; margin: 0 !important; }
    </style>
</head>
<body>
    {%app_entry%}
    <footer>
        {%config%}
        {%scripts%}
        {%renderer%}
    </footer>
</body>
</html>"""

    # Only finalBackground.svg
    app.layout = html.Div(
        [
            html.Link(rel="stylesheet", href="/dashboard/assets/boat-theme.css"),
            html.Img(
                src="/dashboard/assets/finalBackground.svg",
                alt="Background",
                className="boat-bg-image",
            ),
        ],
        className="dashboard-container",
    )

    return app
