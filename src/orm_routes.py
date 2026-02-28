"""
ORM-backed snapshot endpoints (SQLAlchemy). Same DB as snapshots.py; compare approaches.

Routes: POST/GET /orm/snapshots, GET /orm/snapshots/<id>, GET /orm/devices.
"""
from __future__ import annotations

import logging
from dataclasses import asdict
from datetime import datetime, timezone

from flask import Blueprint, request
from sqlalchemy import func, select
from sqlalchemy.orm import joinedload

from .configlib import FALLBACK_DEVICE_ID, FALLBACK_THRESHOLDS
from .datasnapshot import create_snapshot
from .metrics_reader import MetricsError, read_metrics
from .orm_models import Device, MetricType, Snapshot, SnapshotMetric, get_session
from .web_app import _json_response

logger = logging.getLogger(__name__)

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

    # --- ORM: build and persist objects ---
    with get_session() as session:
        # Find or create the Device object
        device = session.scalars(
            select(Device).where(Device.device_id == device_id)
        ).first()

        if device is None:
            device = Device(
                device_id=device_id,
                label="",
                first_seen=datetime.now(timezone.utc).isoformat(),
            )
            session.add(device)  # stage the new Device for INSERT
            session.flush()      # assigns device.id without committing the transaction

        # Build Snapshot object — SQLAlchemy will INSERT this on commit
        new_snap = Snapshot(
            device_id=device.id,
            timestamp_utc=snapshot_obj.timestamp_utc.isoformat(),
        )
        session.add(new_snap)  # stage for INSERT
        session.flush()        # assigns new_snap.id

        # Build SnapshotMetric objects for each metric
        for metric in snapshot_obj.metrics:
            metric_type = session.scalars(
                select(MetricType).where(MetricType.name == metric.name)
            ).first()
            if metric_type is None:
                logger.warning("ORM: Unknown metric '%s' – skipping", metric.name)
                continue

            sm = SnapshotMetric(
                snapshot_id=new_snap.id,
                metric_type_id=metric_type.id,
                value=metric.value,
                status=metric.status,
            )
            session.add(sm)  # stage for INSERT

        # session.commit() is called by get_session() on clean exit
        snapshot_id = new_snap.id

    logger.info("POST /orm/snapshots – stored id=%d", snapshot_id)
    return _json_response(
        {
            "id": snapshot_id,
            "device_id": device_id,
            "timestamp_utc": snapshot_obj.timestamp_utc.isoformat(),
            "metric_count": len(snapshot_obj.metrics),
            "stored_via": "sqlalchemy_orm",
        },
        201,
    )


# ---------------------------------------------------------------------------
# 2. Query filtering — GET /orm/snapshots?device=pc-01&limit=10
# ---------------------------------------------------------------------------

@orm_bp.route("/snapshots", methods=["GET"])
def orm_list_snapshots():
    """GET /orm/snapshots — list snapshots (optional ?device=, ?limit=). Uses joinedload to avoid N+1."""
    device_filter = request.args.get("device")
    try:
        limit = min(int(request.args.get("limit", 50)), 200)
    except ValueError:
        limit = 50

    with get_session() as session:
        # Build the base query
        stmt = (
            select(Snapshot)
            # joinedload: fetch Device in the same query — prevents N+1 problem
            .options(joinedload(Snapshot.device))
            .order_by(Snapshot.id.desc())
            .limit(limit)
        )

        # Demonstrate query filtering — add WHERE clause if ?device= supplied
        if device_filter:
            stmt = stmt.join(Snapshot.device).where(Device.device_id == device_filter)

        snapshots = session.scalars(stmt).all()

        # Relationship navigation: snapshot.device.device_id — no extra query
        result = [
            {
                "id":            s.id,
                "device_id":     s.device.device_id,    # ← navigates Device relationship
                "device_label":  s.device.label,         # ← second attribute, same object
                "timestamp_utc": s.timestamp_utc,
                "metric_count":  len(s.snapshot_metrics),
            }
            for s in snapshots
        ]

    logger.info(
        "GET /orm/snapshots – returning %d snapshots (filter=%r)",
        len(result), device_filter,
    )
    return _json_response(result, 200)


# ---------------------------------------------------------------------------
# 3. Relationship navigation — GET /orm/snapshots/<id>
# ---------------------------------------------------------------------------

@orm_bp.route("/snapshots/<int:snapshot_id>", methods=["GET"])
def orm_get_snapshot(snapshot_id: int):
    """GET /orm/snapshots/<id> — full detail with metrics via selectinload (avoids N+1)."""
    from sqlalchemy.orm import selectinload

    with get_session() as session:
        snapshot = session.scalars(
            select(Snapshot)
            # selectinload: fetch all snapshot_metrics + their metric_type in 2 queries
            # instead of 1 + N queries (one per metric)
            .options(
                joinedload(Snapshot.device),
                selectinload(Snapshot.snapshot_metrics).joinedload(SnapshotMetric.metric_type),
            )
            .where(Snapshot.id == snapshot_id)
        ).first()

        if snapshot is None:
            return _json_response({"error": f"Snapshot {snapshot_id} not found"}, 404)

        # Relationship navigation — no SQL here, data already loaded
        metrics = [
            {
                "name":   sm.metric_type.name,    # ← navigate to MetricType object
                "unit":   sm.metric_type.unit,    # ← same MetricType, no extra query
                "value":  sm.value,
                "status": sm.status,
            }
            for sm in snapshot.snapshot_metrics   # ← navigate to SnapshotMetric list
        ]

        result = {
            "id":            snapshot.id,
            "device_id":     snapshot.device.device_id,   # ← navigate to Device
            "device_label":  snapshot.device.label,
            "timestamp_utc": snapshot.timestamp_utc,
            "metrics":       metrics,
            "retrieved_via": "sqlalchemy_orm",
        }

    logger.info(
        "GET /orm/snapshots/%d – found (%d metrics)", snapshot_id, len(metrics)
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

        # Session is still open here — safe to read row values
        result = [
            {
                "id":             row.id,
                "device_id":      row.device_id,
                "label":          row.label,
                "first_seen":     row.first_seen,
                "snapshot_count": row.snapshot_count,
            }
            for row in rows
        ]
    # Session is closed here — don't access ORM objects outside this block

    logger.info("GET /orm/devices – returning %d devices", len(result))
    return _json_response(result, 200)
