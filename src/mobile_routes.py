"""
Mobile metrics API: config-driven Firestore data exposed as JSON.
GET /mobile/locations, /mobile/metrics/latest, /mobile/metrics/history, /mobile/snapshot (unified).
"""

from __future__ import annotations

import logging
from dataclasses import asdict

from flask import Blueprint, current_app, request

from .mobile_collector import MobileDataCollector
from .mobile_snapshot_bridge import mobile_history_to_snapshots, mobile_to_snapshot
from .web_app import _json_response

logger = logging.getLogger(__name__)

mobile_bp = Blueprint("mobile", __name__, url_prefix="/mobile")

# App config keys for mobile (set at startup)
MOBILE_CONFIG_KEY = "VROOMVROOM_MOBILE_CONFIG"
MOBILE_COLLECTOR_KEY = "VROOMVROOM_MOBILE_COLLECTOR"

DEFAULT_LOCATION_ID = "loc_lough_dan"


def _collector() -> MobileDataCollector | None:
    return current_app.config.get(MOBILE_COLLECTOR_KEY) if current_app else None


def _mobile_unavailable():
    return _json_response({"error": "Mobile data source not configured or disabled."}, 503)


@mobile_bp.route("/locations", methods=["GET"])
def list_locations():
    """GET /mobile/locations – list locations (id, name, county) from Firestore."""
    coll = _collector()
    if coll is None:
        return _mobile_unavailable()
    try:
        locations = coll.list_locations()
        return _json_response({"locations": [asdict(l) for l in locations]}, 200)
    except Exception as e:
        logger.exception("GET /mobile/locations failed: %s", e)
        return _json_response({"error": str(e)}, 500)


def _build_unified_snapshot_dict(location_id: str, coll: MobileDataCollector) -> dict | None:
    """Build the unified snapshot payload (same shape as PC /metrics snapshot) for a location."""
    series = coll.get_time_series(location_id)
    latest_point = series[-1] if series else None
    count_results = []
    cfg = current_app.config.get(MOBILE_CONFIG_KEY)
    if cfg:
        for src in cfg.count_sources:
            cr = coll.get_count(location_id, metric_id=src.metric_id)
            if cr:
                count_results.append(cr)
    snapshot = mobile_to_snapshot(location_id, latest_point, count_results)
    return {
        "device_id": snapshot.device_id,
        "timestamp_utc": snapshot.timestamp_utc.isoformat(),
        "metrics": [{"name": m.name, "value": m.value, "unit": m.unit, "status": m.status} for m in snapshot.metrics],
    }


@mobile_bp.route("/metrics/latest", methods=["GET"])
def metrics_latest():
    """
    GET /mobile/metrics/latest?locationId=loc_lough_dan
    Returns latest time-series point, count metrics, and a unified snapshot (same shape as PC /metrics).
    """
    coll = _collector()
    if coll is None:
        return _mobile_unavailable()
    location_id = request.args.get("locationId", DEFAULT_LOCATION_ID)
    try:
        series = coll.get_time_series(location_id)
        latest_point = series[-1] if series else None
        counts = []
        cfg = current_app.config.get(MOBILE_CONFIG_KEY)
        if cfg:
            for src in cfg.count_sources:
                cr = coll.get_count(location_id, metric_id=src.metric_id)
                if cr:
                    counts.append(asdict(cr))
        out = {
            "location_id": location_id,
            "latest_point": asdict(latest_point) if latest_point else None,
            "counts": counts,
            "snapshot": _build_unified_snapshot_dict(location_id, coll),
        }
        return _json_response(out, 200)
    except Exception as e:
        logger.exception("GET /mobile/metrics/latest failed: %s", e)
        return _json_response({"error": str(e)}, 500)


@mobile_bp.route("/snapshot", methods=["GET"])
def get_snapshot():
    """
    GET /mobile/snapshot?locationId=loc_lough_dan
    Returns a unified snapshot (device_id, timestamp_utc, metrics) in the same shape as PC /metrics,
    so dashboards can consume one format for all sources.
    """
    coll = _collector()
    if coll is None:
        return _mobile_unavailable()
    location_id = request.args.get("locationId", DEFAULT_LOCATION_ID)
    try:
        payload = _build_unified_snapshot_dict(location_id, coll)
        return _json_response(payload, 200)
    except Exception as e:
        logger.exception("GET /mobile/snapshot failed: %s", e)
        return _json_response({"error": str(e)}, 500)


@mobile_bp.route("/metrics/history", methods=["GET"])
def metrics_history():
    """
    GET /mobile/metrics/history?locationId=loc_lough_dan&metricId=water_readings
    Returns time-series points for graphing (timestamp_millis, values).
    """
    coll = _collector()
    if coll is None:
        return _mobile_unavailable()
    location_id = request.args.get("locationId", DEFAULT_LOCATION_ID)
    metric_id = request.args.get("metricId")
    try:
        points = coll.get_time_series(location_id, metric_id=metric_id or None)
        return _json_response({
            "location_id": location_id,
            "points": [asdict(p) for p in points],
        }, 200)
    except Exception as e:
        logger.exception("GET /mobile/metrics/history failed: %s", e)
        return _json_response({"error": str(e)}, 500)


@mobile_bp.route("/snapshots/history", methods=["GET"])
def snapshots_history():
    """
    GET /mobile/snapshots/history?locationId=loc_lough_dan&limit=500
    Returns historic mobile snapshots from Firebase (same shape as /orm/snapshots)
    so the frontend can use one format for historic charts. Data comes from
    Firestore only (no PostgreSQL).
    """
    coll = _collector()
    if coll is None:
        return _mobile_unavailable()
    location_id = request.args.get("locationId", DEFAULT_LOCATION_ID)
    limit = request.args.get("limit", type=int) or 500
    limit = max(1, min(limit, 1000))
    try:
        points = coll.get_time_series(location_id, limit_override=limit)
        count_results = []
        cfg = current_app.config.get(MOBILE_CONFIG_KEY)
        if cfg:
            for src in cfg.count_sources:
                cr = coll.get_count(location_id, metric_id=src.metric_id)
                if cr:
                    count_results.append(cr)
        snapshots = mobile_history_to_snapshots(location_id, points, count_results)
        payload = [
            {
                "device_id": s.device_id,
                "timestamp_utc": s.timestamp_utc.isoformat(),
                "metrics": [{"name": m.name, "value": m.value, "unit": m.unit, "status": m.status} for m in s.metrics],
            }
            for s in snapshots
        ]
        return _json_response(payload, 200)
    except Exception as e:
        logger.exception("GET /mobile/snapshots/history failed: %s", e)
        return _json_response({"error": str(e)}, 500)
