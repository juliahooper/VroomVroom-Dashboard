"""
Web enabling – Flask server with structured entry point.

At entry point: initialise config, initialise logging, register routes, then run.
- GET /hello   → returns the text "Hello World"
- GET /health  → returns "OK" and status 200
- GET /metrics → returns JSON (cached with TTL; one thread updates, others serve cache).
- GET /youtube/vroom-vroom → fetches current view count from YouTube API, stores snapshot, returns JSON (on-demand).

Run: python -m src.web_app  (or gunicorn for production).
"""
from __future__ import annotations

import json
import logging
import os
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, current_app, redirect, send_from_directory

from .blocktimer import BlockTimer
from .configlib import AppConfig, ConfigError, load_config, load_mobile_config, setup_logging
from .datasnapshot import create_snapshot
from .metrics_cache import MetricsCache
from .metrics_reader import MetricsError, read_metrics

logger = logging.getLogger(__name__)

# Key used to store VroomVroom AppConfig on the Flask app
APP_CONFIG_KEY = "VROOMVROOM_APP_CONFIG"
# Key for the metrics response cache (TTL-based, thread-safe)
METRICS_CACHE_KEY = "METRICS_CACHE"
# Default cache TTL in seconds (invalidation rule)
CACHE_TTL_SECONDS = 30.0
# Default web server port (override with VROOMVROOM_WEB_PORT)
DEFAULT_WEB_PORT = 5000


def create_app(config: AppConfig | None = None) -> Flask:
    """Create the Flask application instance. Optionally attach config for /metrics."""
    app = Flask(__name__)
    if config is not None:
        app.config[APP_CONFIG_KEY] = config
    return app


def register_routes(app: Flask) -> None:
    """Register all URL routes on the Flask app."""
    _project_root = Path(__file__).resolve().parent.parent
    _frontend_dist = _project_root / "frontend" / "dist"

    # Serve built React dashboard at /dashboard/ (if frontend/dist exists)
    if _frontend_dist.exists():
        @app.route("/dashboard")
        def redirect_dashboard():
            return redirect("/dashboard/")

        @app.route("/dashboard/")
        def serve_dashboard_index():
            return send_from_directory(_frontend_dist, "index.html")

        @app.route("/dashboard/<path:path>")
        def serve_dashboard_assets(path: str):
            return send_from_directory(_frontend_dist, path)

    # Register Snapshots CRUD blueprint – raw SQL (POST/GET/PUT/DELETE /snapshots)
    from .snapshots import snapshots_bp
    app.register_blueprint(snapshots_bp)

    # Register ORM blueprint – SQLAlchemy (POST/GET /orm/snapshots, GET /orm/devices)
    from .orm_routes import orm_bp
    app.register_blueprint(orm_bp)

    # Register mobile blueprint – Firestore metrics (config-driven)
    from .mobile_routes import mobile_bp
    app.register_blueprint(mobile_bp)

    @app.route("/hello")
    def hello() -> str:
        """When someone visits /hello we return this string."""
        return "Hello World"

    @app.route("/health")
    def health() -> tuple[str, int]:
        """When someone visits /health we return 'OK' and HTTP status 200 (success)."""
        return "OK", 200

    @app.route("/metrics")
    def metrics():
        """
        GET /metrics: return JSON from cache if valid; else one thread refreshes,
        others serve cached data. Uses BlockTimer (RAII). JSON serialised at the last moment.
        """
        cfg = current_app.config.get(APP_CONFIG_KEY)
        if cfg is None:
            return _json_response(
                {"error": "Server not configured for metrics"}, 503
            )

        cache = current_app.config.get(METRICS_CACHE_KEY)
        if cache is None:
            return _json_response(
                {"error": "Metrics cache not initialised"}, 503
            )

        def build_response() -> dict:
            """Build metrics response dict (run by at most one thread when cache is stale)."""
            start_read_utc = datetime.now(timezone.utc)
            metrics_dict = read_metrics()
            thresholds = asdict(cfg.danger_thresholds)
            snapshot = create_snapshot(
                device_id=cfg.device_id,
                metrics_dict=metrics_dict,
                thresholds=thresholds,
            )
            respond_utc = datetime.now(timezone.utc)
            return {
                "start_read_utc": start_read_utc.isoformat(),
                "respond_utc": respond_utc.isoformat(),
                "device_id": snapshot.device_id,
                "timestamp_utc": snapshot.timestamp_utc.isoformat(),
                "metrics": [
                    {
                        "name": m.name,
                        "value": m.value,
                        "unit": m.unit,
                        "status": m.status,
                    }
                    for m in snapshot.metrics
                ],
            }

        with BlockTimer("metrics_handler", log_level=logging.INFO):
            try:
                response_obj = cache.get_or_compute(build_response)
            except MetricsError as e:
                logger.warning("Metrics read failed: %s", e)
                return _json_response({"error": str(e)}, 503)

            return _json_response(response_obj, 200)

    @app.route("/youtube/vroom-vroom")
    def youtube_vroom_vroom():
        """
        GET /youtube/vroom-vroom: fetch current view count from YouTube Data API v3,
        store as a snapshot (device youtube-vroom-vroom, metric total_streams), return JSON.
        On-demand only; requires YOUTUBE_API_KEY environment variable.
        """
        from .orm_dto import snapshot_from_dto
        from .orm_models import get_session
        from .youtube_fetcher import YouTubeFetcherError, get_view_count

        try:
            view_count = get_view_count()
        except YouTubeFetcherError as e:
            logger.warning("YouTube fetch failed: %s", e)
            return _json_response({"error": str(e)}, 503)

        timestamp_utc = datetime.now(timezone.utc)
        dto = {
            "device_id": "youtube-vroom-vroom",
            "timestamp_utc": timestamp_utc.isoformat(),
            "metrics": [
                {
                    "name": "total_streams",
                    "value": float(view_count),
                    "unit": "count",
                    "status": "normal",
                }
            ],
        }
        try:
            with get_session() as session:
                snapshot = snapshot_from_dto(dto, session)
                # Build response in same spirit as /metrics
                response_obj = {
                    "timestamp_utc": timestamp_utc.isoformat(),
                    "device_id": "youtube-vroom-vroom",
                    "total_streams": view_count,
                    "snapshot_id": snapshot.id,
                    "metrics": [
                        {"name": "total_streams", "value": view_count, "unit": "count", "status": "normal"}
                    ],
                }
        except Exception as e:
            logger.exception("Failed to persist YouTube snapshot")
            return _json_response({"error": f"Failed to store snapshot: {e}"}, 500)

        return _json_response(response_obj, 200)


def _json_response(obj: dict, status: int) -> tuple[str, int, dict]:
    """Return a JSON-serialised response with application/json content type."""
    return json.dumps(obj, indent=2), status, {"Content-Type": "application/json"}


def main() -> int:
    """
    Entry point: initialise once (config, logging, app, routes), then run server.
    After app.run(), the process responds to HTTP events; startup code is not re-run.
    See docs/EXECUTION_ORDER.md. Returns 0 on success, 2 on config error.
    """
    # Load .env from project root so YOUTUBE_API_KEY (and optional overrides) are set
    from dotenv import load_dotenv
    _project_root = Path(__file__).resolve().parent.parent
    load_dotenv(_project_root / ".env")

    config_path = os.environ.get(
        "VROOMVROOM_CONFIG", str(Path("config") / "config.json")
    )
    try:
        config = load_config(config_path)
    except ConfigError as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        return 2

    setup_logging(config)
    logger.info("Web server starting (config: %s)", config_path)

    # SQLAlchemy engine (orm_models) reads this at import time; set before register_routes
    os.environ["VROOMVROOM_SQL_ECHO"] = "1" if config.sql_echo else "0"

    # Initialise the database (creates tables if they don't exist yet)
    from .database import init_db
    init_db()

    # Optional mobile (Firestore) config and collector
    from .mobile_collector import MobileDataCollector, init_firebase
    from .mobile_routes import MOBILE_COLLECTOR_KEY, MOBILE_CONFIG_KEY
    mobile_config = load_mobile_config(config_path)
    if mobile_config:
        init_firebase(mobile_config)
        app = create_app(config)
        app.config[MOBILE_CONFIG_KEY] = mobile_config
        app.config[MOBILE_COLLECTOR_KEY] = MobileDataCollector(mobile_config)
    else:
        app = create_app(config)
        app.config[MOBILE_CONFIG_KEY] = None
        app.config[MOBILE_COLLECTOR_KEY] = None

    app.config[METRICS_CACHE_KEY] = MetricsCache(ttl_seconds=CACHE_TTL_SECONDS)
    register_routes(app)

    port = int(os.environ.get("VROOMVROOM_WEB_PORT", str(DEFAULT_WEB_PORT)))
    logger.info("Listening on 0.0.0.0:%s", port)
    app.run(host="0.0.0.0", port=port, debug=False)
    return 0


# Entry point when run as python -m src.web_app; not executed when web_app is imported.
if __name__ == "__main__":
    sys.exit(main())
