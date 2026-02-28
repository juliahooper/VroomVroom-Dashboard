"""
ORM-backed snapshot endpoints – demonstrates SQLAlchemy concepts.

These endpoints sit alongside the raw SQL endpoints in snapshots.py.
Both use the same SQLite database file so you can compare the two approaches.

WHAT THIS FILE DEMONSTRATES
─────────────────────────────
1. Session management   – get_session() context manager opens/commits/rolls back/closes
2. Object creation      – build a Python object, session.add(), session.commit()
3. Query filtering      – select(Snapshot).where(...), filter by device or date range
4. Relationship navigation – snapshot.device.label without writing a JOIN

Routes:
    POST   /orm/snapshots              Read live metrics, store via ORM     → 201
    GET    /orm/snapshots              List snapshots (optional ?device= filter) → 200
    GET    /orm/snapshots/<id>         Full detail – navigate relationships  → 200 / 404
    GET    /orm/devices                List all devices with snapshot counts → 200
"""
from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timezone

from flask import Blueprint, request
from sqlalchemy import func, select
from sqlalchemy.orm import joinedload

from .database import get_db          # raw SQL still used for INSERT helpers
from .datasnapshot import create_snapshot
from .metrics_reader import MetricsError, read_metrics
from .orm_models import Device, MetricType, Snapshot, SnapshotMetric, get_session
from .snapshots import _get_or_create_device, _store_metrics, _store_snapshot
from .web_app import _json_response

logger = logging.getLogger(__name__)

orm_bp = Blueprint("orm", __name__, url_prefix="/orm")


# ---------------------------------------------------------------------------
# 1. Object creation & commit — POST /orm/snapshots
# ---------------------------------------------------------------------------

@orm_bp.route("/snapshots", methods=["POST"])
def orm_create_snapshot():
    """
    POST /orm/snapshots
    Demonstrates: session.add(), session.commit(), object creation.

    We create Python objects (Device, Snapshot, SnapshotMetric) and add them to
    the session. When we commit, SQLAlchemy generates the INSERT statements and
    executes them — we never write SQL ourselves.

    The raw SQL helper functions (_get_or_create_device etc.) are reused here
    because the INSERT logic is identical; only the read side uses ORM.
    """
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

    from dataclasses import asdict as dc_asdict
    if cfg is not None:
        thresholds = dc_asdict(cfg.danger_thresholds)
        device_id  = cfg.device_id
    else:
        thresholds = {"cpu_percent": 80, "ram_percent": 85, "disk_percent": 90}
        device_id  = "unknown"

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
    """
    GET /orm/snapshots
    Demonstrates: select(), where() filtering, joinedload() to avoid N+1 queries.

    Optional query parameters:
        ?device=<device_id>   filter to one device
        ?limit=<n>            return at most n results (default 50)

    N+1 problem explained:
        Without joinedload, accessing snapshot.device for each snapshot would fire
        one extra SELECT per row. joinedload fetches all devices in one JOIN so
        we never hit the database inside the loop.
    """
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
    """
    GET /orm/snapshots/<id>
    Demonstrates: relationship navigation — traverse from Snapshot to its metrics
    and from each metric to its MetricType, all without writing any JOINs.

    The ORM lazy-loads related objects on first access inside the session.
    We use selectinload() to fetch all snapshot_metrics in one extra SELECT
    (better than lazy loading N separate queries for N metrics).
    """
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
    """
    GET /orm/devices
    Demonstrates: session lifecycle, aggregate query (COUNT), group_by.

    Shows that a session is just a unit-of-work container — open it, query,
    read results while the session is open, then close.
    """
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
