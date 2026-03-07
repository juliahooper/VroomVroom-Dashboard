"""
ORM-backed snapshot endpoints (SQLAlchemy). Same DB as snapshots.py; compare approaches.

Routes: POST/GET /orm/snapshots, GET /orm/snapshots/<id>, GET /orm/devices, POST /orm/upload_snapshot.
ORM ↔ DTO mapping via orm_dto (to_dict/from_dict style).
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import asdict

from flask import Blueprint, current_app, request
from sqlalchemy import func, select
from sqlalchemy.orm import joinedload, selectinload

from .configlib import FALLBACK_DEVICE_ID, FALLBACK_THRESHOLDS
from .datasnapshot import create_snapshot
from .metrics_reader import MetricsError, read_metrics
from .orm_dto import (
    device_to_dto,
    snapshot_from_dto,
    snapshot_to_detail_dto,
    snapshot_to_summary_dto,
    validate_snapshot_upload_dto,
)
from .mobile_snapshot_bridge import MOBILE_DEVICE_ID_PREFIX
from .orm_models import Device, Snapshot, SnapshotMetric, get_session
from .snapshot_backup import append_backup, append_failed
from .web_app import APP_CONFIG_KEY, _json_response

logger = logging.getLogger(__name__)

# Retries and backup: persist up to 3 times; on failure log to failed_snapshots.jsonl for replay
_UPLOAD_RETRY_ATTEMPTS = 3
_UPLOAD_RETRY_DELAY_SEC = 0.5
# Serialize snapshot writes per process so concurrent POSTs don't hit SQLite at once (no queue server)
_upload_lock = threading.Lock()

orm_bp = Blueprint("orm", __name__, url_prefix="/orm")


# ---------------------------------------------------------------------------
# 1. Object creation & commit — POST /orm/snapshots
# ---------------------------------------------------------------------------

@orm_bp.route("/snapshots", methods=["POST"])
def orm_create_snapshot():
    """POST /orm/snapshots — read live metrics, create Device/Snapshot/SnapshotMetric via ORM, commit."""
    cfg = None
    try:
        from flask import current_app
        from .web_app import APP_CONFIG_KEY
        cfg = current_app.config.get(APP_CONFIG_KEY)
    except RuntimeError:
        pass

    try:
        metrics_dict = read_metrics()
    except MetricsError as e:
        logger.error("POST /orm/snapshots – metrics read failed: %s", e)
        return _json_response({"error": f"Could not read OS metrics: {e}"}, 503)

    if cfg is not None:
        thresholds = asdict(cfg.danger_thresholds)
        device_id  = cfg.device_id
    else:
        thresholds = FALLBACK_THRESHOLDS
        device_id  = FALLBACK_DEVICE_ID

    snapshot_obj = create_snapshot(
        device_id=device_id,
        metrics_dict=metrics_dict,
        thresholds=thresholds,
    )

    # DTO from domain snapshot → ORM via explicit mapping
    dto = {
        "device_id": snapshot_obj.device_id,
        "timestamp_utc": snapshot_obj.timestamp_utc.isoformat(),
        "metrics": [
            {"name": m.name, "value": m.value, "unit": m.unit, "status": m.status}
            for m in snapshot_obj.metrics
        ],
    }

    with get_session() as session:
        snapshot = snapshot_from_dto(dto, session)
        # session.commit() on exit
        summary = snapshot_to_summary_dto(snapshot)
        summary["stored_via"] = "sqlalchemy_orm"

    logger.info("POST /orm/snapshots – stored id=%d", summary["id"])
    return _json_response(summary, 201)


# ---------------------------------------------------------------------------
# 1b. POST /upload_snapshot — accept JSON DTO, validate, persist, return structured response
# ---------------------------------------------------------------------------

@orm_bp.route("/upload_snapshot", methods=["POST"])
def upload_snapshot():
    """
    POST /orm/upload_snapshot — deserialize JSON DTO, validate required fields,
    create ORM objects, persist in a transaction, return structured JSON.

    Request body: { "device_id": str, "timestamp_utc": str (ISO 8601), "metrics": [ { "name", "value", "unit", "status" }, ... ] }
    Response: 201 with { "id", "device_id", "device_label", "timestamp_utc", "metric_count", "uploaded": true }
    """
    if not request.is_json:
        return _json_response({"error": "Content-Type must be application/json"}, 400)

    data = request.get_json(silent=True)
    if data is None:
        return _json_response({"error": "Invalid or empty JSON body"}, 400)

    try:
        dto = validate_snapshot_upload_dto(data)
    except ValueError as e:
        return _json_response({"error": str(e)}, 400)

    last_error = None
    for attempt in range(1, _UPLOAD_RETRY_ATTEMPTS + 1):
        try:
            with _upload_lock:
                with get_session() as session:
                    snapshot = snapshot_from_dto(dto, session)
                    summary = snapshot_to_summary_dto(snapshot)
                    summary["uploaded"] = True
                append_backup(dto)
            logger.info("POST /orm/upload_snapshot – stored id=%d device=%s", summary["id"], summary["device_id"])
            return _json_response(summary, 201)
        except Exception as e:
            last_error = e
            logger.warning("POST /orm/upload_snapshot – attempt %d/%d failed: %s", attempt, _UPLOAD_RETRY_ATTEMPTS, e)
            if attempt < _UPLOAD_RETRY_ATTEMPTS:
                time.sleep(_UPLOAD_RETRY_DELAY_SEC)

    append_failed(dto, str(last_error))
    logger.exception("POST /orm/upload_snapshot – persist failed after %d attempts", _UPLOAD_RETRY_ATTEMPTS)
    return _json_response({"error": f"Failed to persist snapshot: {last_error}"}, 500)


# ---------------------------------------------------------------------------
# 2. Query filtering — GET /orm/snapshots?device=pc-01&limit=10
# ---------------------------------------------------------------------------

@orm_bp.route("/snapshots", methods=["GET"])
def orm_list_snapshots():
    """GET /orm/snapshots — list snapshots (optional ?device=, ?limit=, ?expand=metrics)."""
    device_filter = request.args.get("device")
    expand_metrics = request.args.get("expand") == "metrics"
    try:
        limit = min(int(request.args.get("limit", 50)), 200)
    except ValueError:
        limit = 50

    with get_session() as session:
        opts = [
            joinedload(Snapshot.device),
            selectinload(Snapshot.snapshot_metrics).joinedload(SnapshotMetric.metric_type)
            if expand_metrics
            else selectinload(Snapshot.snapshot_metrics),
        ]
        stmt = (
            select(Snapshot)
            .options(*opts)
            .order_by(Snapshot.id.desc())
            .limit(limit)
        )
        if device_filter:
            stmt = stmt.join(Snapshot.device).where(Device.device_id == device_filter)

        snapshots = session.scalars(stmt).all()
        result = (
            [snapshot_to_detail_dto(s) for s in snapshots]
            if expand_metrics
            else [snapshot_to_summary_dto(s) for s in snapshots]
        )

    logger.info(
        "GET /orm/snapshots – returning %d snapshots (filter=%r, expand=%s)",
        len(result), device_filter, "metrics" if expand_metrics else "no",
    )
    return _json_response(result, 200)


@orm_bp.route("/snapshots/latest", methods=["GET"])
def orm_latest_snapshot():
    """GET /orm/snapshots/latest?device=... — single latest snapshot with full metrics."""
    device_filter = request.args.get("device") or "pc-01"
    with get_session() as session:
        stmt = (
            select(Snapshot)
            .options(
                joinedload(Snapshot.device),
                selectinload(Snapshot.snapshot_metrics).joinedload(SnapshotMetric.metric_type),
            )
            .join(Snapshot.device)
            .where(Device.device_id == device_filter)
            .order_by(Snapshot.id.desc())
            .limit(1)
        )
        snapshot = session.scalars(stmt).first()
        if snapshot is None:
            return _json_response(
                {"error": f"No snapshots found for device {device_filter!r}"},
                404,
            )
        result = snapshot_to_detail_dto(snapshot)
    logger.info("GET /orm/snapshots/latest – device=%r id=%d", device_filter, result["id"])
    return _json_response(result, 200)


# ---------------------------------------------------------------------------
# 3. Relationship navigation — GET /orm/snapshots/<id>
# ---------------------------------------------------------------------------

@orm_bp.route("/snapshots/<int:snapshot_id>", methods=["GET"])
def orm_get_snapshot(snapshot_id: int):
    """GET /orm/snapshots/<id> — full detail with metrics via selectinload (avoids N+1)."""
    with get_session() as session:
        snapshot = session.scalars(
            select(Snapshot)
            .options(
                joinedload(Snapshot.device),
                selectinload(Snapshot.snapshot_metrics).joinedload(SnapshotMetric.metric_type),
            )
            .where(Snapshot.id == snapshot_id)
        ).first()

        if snapshot is None:
            return _json_response({"error": f"Snapshot {snapshot_id} not found"}, 404)

        result = snapshot_to_detail_dto(snapshot)
        result["retrieved_via"] = "sqlalchemy_orm"

    logger.info(
        "GET /orm/snapshots/%d – found (%d metrics)", snapshot_id, len(result["metrics"])
    )
    return _json_response(result, 200)


# ---------------------------------------------------------------------------
# 4. Session management + aggregate query — GET /orm/devices
# ---------------------------------------------------------------------------

@orm_bp.route("/devices", methods=["GET"])
def orm_list_devices():
    """GET /orm/devices — list devices with snapshot count (aggregate query)."""
    with get_session() as session:
        # Aggregate query: count snapshots per device without loading all snapshot rows
        stmt = (
            select(
                Device.id,
                Device.device_id,
                Device.label,
                Device.first_seen,
                func.count(Snapshot.id).label("snapshot_count"),
            )
            .outerjoin(Device.snapshots)   # outerjoin so devices with 0 snapshots appear
            .group_by(Device.id)
            .order_by(Device.id)
        )

        rows = session.execute(stmt).all()
        result = [
            device_to_dto(
                row.id,
                row.device_id,
                row.label,
                row.first_seen,
                snapshot_count=row.snapshot_count,
            )
            for row in rows
        ]
    # Session is closed here — don't access ORM objects outside this block

    logger.info("GET /orm/devices – returning %d devices", len(result))
    return _json_response(result, 200)


# ---------------------------------------------------------------------------
# 5. Map locations — GET /orm/locations
# ---------------------------------------------------------------------------

def _metrics_from_snapshot(snapshot) -> dict[str, float]:
    """Extract Cold Water Shock Risk and Alert Count from snapshot metrics (same schema as PC/YouTube)."""
    out = {"Cold Water Shock Risk": 0.0, "Alert Count": 0}
    for sm in snapshot.snapshot_metrics or []:
        name = sm.metric_type.name if sm.metric_type else ""
        if name == "Cold Water Shock Risk":
            out["Cold Water Shock Risk"] = float(sm.value)
        elif name == "Alert Count":
            out["Alert Count"] = int(sm.value)
    return out


@orm_bp.route("/locations", methods=["GET"])
def orm_list_locations():
    """
    GET /orm/locations — list locations for map markers.
    Locations come from SEED_LOCATIONS (local). Metrics (cold_water_shock_risk_score, alert_count)
    come from the latest snapshot for device_id = mobile:{loc_id} in Postgres.
    """
    from .db_seed import SEED_LOCATIONS

    with get_session() as session:
        result = []
        for loc_id, name, county, lat, lng in SEED_LOCATIONS:
            device_id_str = f"{MOBILE_DEVICE_ID_PREFIX}{loc_id}"
            snapshot_stmt = (
                select(Snapshot)
                .options(
                    selectinload(Snapshot.snapshot_metrics).joinedload(SnapshotMetric.metric_type),
                )
                .join(Snapshot.device)
                .where(Device.device_id == device_id_str)
                .order_by(Snapshot.id.desc())
                .limit(1)
            )
            snapshot = session.scalars(snapshot_stmt).first()
            if snapshot:
                metrics = _metrics_from_snapshot(snapshot)
                risk = metrics["Cold Water Shock Risk"]
                alerts = metrics["Alert Count"]
            else:
                risk = 0.0
                alerts = 0
            result.append({
                "id": loc_id,
                "name": name,
                "county": county,
                "lat": lat,
                "lng": lng,
                "cold_water_shock_risk_score": risk,
                "alert_count": alerts,
            })
    logger.info("GET /orm/locations – returning %d locations (from SEED_LOCATIONS, metrics from Postgres)", len(result))
    return _json_response(result, 200)


# ---------------------------------------------------------------------------
# 6. Danger thresholds for gauges — GET /orm/thresholds
# ---------------------------------------------------------------------------

@orm_bp.route("/thresholds", methods=["GET"])
def orm_get_thresholds():
    """GET /orm/thresholds — danger thresholds (and warning_fraction) for gauge green/yellow/red zones."""
    cfg = current_app.config.get(APP_CONFIG_KEY)
    if cfg is not None:
        th = asdict(cfg.danger_thresholds)
    else:
        th = FALLBACK_THRESHOLDS
    result = {
        "thread_count": th["thread_count"],
        "ram_percent": th["ram_percent"],
        "disk_usage_percent": th["disk_usage_percent"],
        "warning_fraction": 0.8,
    }
    return _json_response(result, 200)
