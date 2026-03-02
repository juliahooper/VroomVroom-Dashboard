"""
WSGI entry point for production deployment with gunicorn.

This file is the bridge between the WSGI server (gunicorn) and the Flask app.
Gunicorn imports this module and looks for the callable named 'application'.

Working directory: run gunicorn from the project root (VroomVroom-Dashboard/)
so that config/config.json and logs/ resolve correctly.

Usage (on VM, from project root with venv active):
    gunicorn wsgi:application --bind 0.0.0.0:5000 --workers 2

Environment variables (optional overrides):
    VROOMVROOM_CONFIG   Path to config JSON  (default: config/config.json)
    VROOMVROOM_WEB_PORT Port for Flask dev server only; gunicorn uses --bind instead
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Ensure the project root is on the Python path so 'src' is importable
_project_root = Path(__file__).resolve().parent
sys.path.insert(0, str(_project_root))

# Load .env from project root (e.g. YOUTUBE_API_KEY) before any app code uses env vars
from dotenv import load_dotenv
load_dotenv(_project_root / ".env")

from src.configlib import ConfigError, load_config, load_mobile_config, setup_logging
from src.metrics_cache import MetricsCache
from src.mobile_collector import MobileDataCollector, init_firebase
from src.mobile_routes import MOBILE_COLLECTOR_KEY, MOBILE_CONFIG_KEY
from src.web_app import (
    CACHE_TTL_SECONDS,
    METRICS_CACHE_KEY,
    create_app,
    register_routes,
)

# Determine config path from environment or fall back to default
_config_path = os.environ.get("VROOMVROOM_CONFIG", "config/config.json")

try:
    _config = load_config(_config_path)
except ConfigError as e:
    # gunicorn captures stderr; raise so the worker fails fast with a clear message
    raise RuntimeError(f"VroomVroom config error: {e}") from e

# Set up logging before creating the app so all startup messages are captured
setup_logging(_config)

# SQLAlchemy engine (in orm_models) reads this at import time; set before register_routes
os.environ["VROOMVROOM_SQL_ECHO"] = "1" if _config.sql_echo else "0"

# Initialise the database (creates tables + seeds metric_type rows if needed)
from src.database import init_db
init_db()

# Optional mobile (Firestore) config and collector
_mobile_config = load_mobile_config(_config_path)
if _mobile_config:
    init_firebase(_mobile_config)
    application = create_app(_config)
    application.config[MOBILE_CONFIG_KEY] = _mobile_config
    application.config[MOBILE_COLLECTOR_KEY] = MobileDataCollector(_mobile_config)
else:
    application = create_app(_config)
    application.config[MOBILE_CONFIG_KEY] = None
    application.config[MOBILE_COLLECTOR_KEY] = None

application.config[METRICS_CACHE_KEY] = MetricsCache(ttl_seconds=CACHE_TTL_SECONDS)
register_routes(application)
