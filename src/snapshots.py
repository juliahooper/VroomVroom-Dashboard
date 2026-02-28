"""
RESTful CRUD for snapshots (raw SQL). Rows mapped to business objects; INNER/LEFT JOIN as needed.

Endpoints: POST/GET /snapshots, GET /snapshots/<id>, PUT /devices/<id>, DELETE /snapshots/<id>.
"""
from __future__ import annotations

import logging
import sqlite3
from dataclasses import asdict, dataclass

from flask import Blueprint, request

from .configlib import FALLBACK_DEVICE_ID, FALLBACK_THRESHOLDS
from .database import get_db, TransactionManager
from .datasnapshot import create_snapshot
from .metrics_reader import MetricsError, read_metrics
from .web_app import _json_response

logger = logging.getLogger(__name__)

snapshots_bp = Blueprint("snapshots", __name__)


# ---------------------------------------------------------------------------
# Business objects  (typed representations of database rows)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MetricRecord:
    """One metric value from a snapshot — mapped from snapshot_metric JOIN metric_type."""
    name: str
    unit: str
    value: float
    status: str


@dataclass(frozen=True)
class SnapshotSummary:
    """
    Lightweight snapshot used in list responses.
    Mapped from snapshot INNER JOIN device LEFT JOIN snapshot_metric (with COUNT).
    """
    id: int
    device_id: str
    timestamp_utc: str
    metric_count: int


@dataclass(frozen=True)
class SnapshotDetail:
    """
    Full snapshot with all metrics.
    Mapped from a single LEFT JOIN query; metrics list may be empty.
    """
    id: int
    device_id: str
    timestamp_utc: str
    metrics: list[MetricRecord]


@dataclass(frozen=True)
class DeviceRecord:
    """One device row — mapped from the device table."""
    id: int
    device_id: str
    label: str
    first_seen: str


# ---------------------------------------------------------------------------
# Row → business object mapping functions
# ---------------------------------------------------------------------------

def _row_to_metric(row: sqlite3.Row) -> MetricRecord:
    """Map one sqlite3.Row from snapshot_metric JOIN metric_type to a MetricRecord."""
    return MetricRecord(
        name=row["name"],
        unit=row["unit"],
        value=row["value"],
        status=row["status"],
    )


def _row_to_summary(row: sqlite3.Row) -> SnapshotSummary:
    """
    Map one sqlite3.Row from the summary query to a SnapshotSummary.
    The row comes from: snapshot INNER JOIN device LEFT JOIN snapshot_metric (COUNT).
    """
    return SnapshotSummary(
        id=row["id"],
        device_id=row["device_id"],
        timestamp_utc=row["timestamp_utc"],
        metric_count=row["metric_count"],
    )


def _rows_to_detail(rows: list[sqlite3.Row]) -> SnapshotDetail | None:
    """
    Map a list of JOIN rows to one SnapshotDetail with a list of MetricRecords.

    A single LEFT JOIN between snapshot, device, and snapshot_metric produces
    one row per metric (or one row with NULL metric columns if there are none).
    This function collects all rows into a single SnapshotDetail, creating the
    parent object exactly once and appending MetricRecord children as needed.

    Returns None if rows is empty (snapshot not found).

    Avoids duplicate instantiation: even if there are 10 metric rows, the
    SnapshotDetail is constructed only once.
    """
    if not rows:
        return None

    # All rows share the same snapshot header — read it from the first row only.
    # This is the "avoid duplicate instantiation" requirement: we do NOT create
    # a new SnapshotDetail per row, only one for the whole group.
    first = rows[0]
    metrics: list[MetricRecord] = []

    for row in rows:
        # LEFT JOIN: metric columns are NULL when the snapshot has no metrics yet
        if row["metric_name"] is not None:
            metrics.append(MetricRecord(
                name=row["metric_name"],
                unit=row["metric_unit"],
                value=row["value"],
                status=row["status"],
            ))

    return SnapshotDetail(
        id=first["snap_id"],
        device_id=first["device_id"],
        timestamp_utc=first["timestamp_utc"],
        metrics=metrics,
    )


def _row_to_device(row: sqlite3.Row) -> DeviceRecord:
    """Map one sqlite3.Row from the device table to a DeviceRecord."""
    return DeviceRecord(
        id=row["id"],
        device_id=row["device_id"],
        label=row["label"],
        first_seen=row["first_seen"],
    )


# ---------------------------------------------------------------------------
# Write helpers  (INSERT)
# ---------------------------------------------------------------------------

def _get_or_create_device(conn, device_id: str) -> int:
    """
    Return the integer PK for device_id, inserting a new row if needed.
    SQL: INSERT OR IGNORE + SELECT
    """
    conn.execute(
        "INSERT OR IGNORE INTO device (device_id) VALUES (?)", (device_id,)
    )
    row = conn.execute(
        "SELECT id FROM device WHERE device_id = ?", (device_id,)
    ).fetchone()
    return row["id"]


def _store_snapshot(conn, device_pk: int, snapshot) -> int:
    """INSERT a snapshot row and return its AUTOINCREMENT id."""
    cursor = conn.execute(
        "INSERT INTO snapshot (device_id, timestamp_utc) VALUES (?, ?)",
        (device_pk, snapshot.timestamp_utc.isoformat()),
    )
    return cursor.lastrowid


def _store_metrics(conn, snapshot_id: int, snapshot) -> None:
    """INSERT one snapshot_metric row per Metric — all parameterised."""
    for metric in snapshot.metrics:
        row = conn.execute(
            "SELECT id FROM metric_type WHERE name = ?", (metric.name,)
        ).fetchone()
        if row is None:
            logger.warning("Unknown metric name '%s' – skipping", metric.name)
            continue
        conn.execute(
            "INSERT INTO snapshot_metric (snapshot_id, metric_type_id, value, status) "
            "VALUES (?, ?, ?, ?)",
            (snapshot_id, row["id"], metric.value, metric.status),
        )


# ---------------------------------------------------------------------------
# POST /snapshots
# ---------------------------------------------------------------------------

@snapshots_bp.route("/snapshots", methods=["POST"])
def create_snapshot_endpoint():
    """
    POST /snapshots — read live OS metrics, store, return 201 with SnapshotSummary.
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
        logger.error("POST /snapshots – metrics read failed: %s", e)
        return _json_response({"error": f"Could not read OS metrics: {e}"}, 503)

    if cfg is not None:
        thresholds = asdict(cfg.danger_thresholds)
        device_id = cfg.device_id
    else:
        thresholds = FALLBACK_THRESHOLDS
        device_id = FALLBACK_DEVICE_ID

    snapshot = create_snapshot(
        device_id=device_id,
        metrics_dict=metrics_dict,
        thresholds=thresholds,
    )

    # Multi-step insert in a single transaction (RAII: BEGIN → COMMIT or ROLLBACK)
    with get_db() as conn:
        with TransactionManager(conn) as tx:
            device_pk = _get_or_create_device(tx.conn, snapshot.device_id)
            snapshot_id = _store_snapshot(tx.conn, device_pk, snapshot)
            _store_metrics(tx.conn, snapshot_id, snapshot)

    logger.info(
        "POST /snapshots – stored id=%d device='%s' metrics=%d",
        snapshot_id, snapshot.device_id, len(snapshot.metrics),
    )
    # Map to business object before returning — never return raw SQL data
    summary = SnapshotSummary(
        id=snapshot_id,
        device_id=snapshot.device_id,
        timestamp_utc=snapshot.timestamp_utc.isoformat(),
        metric_count=len(snapshot.metrics),
    )
    return _json_response(asdict(summary), 201)


# ---------------------------------------------------------------------------
# GET /snapshots  –  INNER JOIN + LEFT JOIN, mapped to SnapshotSummary list
# ---------------------------------------------------------------------------

@snapshots_bp.route("/snapshots", methods=["GET"])
def list_snapshots():
    """
    GET /snapshots — return list of SnapshotSummary objects.

    INNER JOIN device: only snapshots that have a matching device appear.
    LEFT JOIN snapshot_metric: snapshots with zero metrics still appear (count = 0).

    Each row is mapped to a SnapshotSummary — no raw dicts returned to the caller.
    """
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT s.id,
                   d.device_id,
                   s.timestamp_utc,
                   COUNT(sm.metric_type_id) AS metric_count
            FROM   snapshot        s
            -- INNER JOIN: snapshot must have a device (FK enforces this anyway)
            JOIN   device          d  ON d.id = s.device_id
            -- LEFT JOIN: include snapshots that have no metrics yet (count = 0)
            LEFT JOIN snapshot_metric sm ON sm.snapshot_id = s.id
            GROUP  BY s.id
            ORDER  BY s.id DESC
            """
        ).fetchall()

    # Map every row to a SnapshotSummary — the route never touches raw columns
    summaries = [_row_to_summary(r) for r in rows]
    logger.info("GET /snapshots – returning %d summaries", len(summaries))
    return _json_response([asdict(s) for s in summaries], 200)


# ---------------------------------------------------------------------------
# GET /snapshots/<id>  –  single LEFT JOIN, grouped into one SnapshotDetail
# ---------------------------------------------------------------------------

@snapshots_bp.route("/snapshots/<int:snapshot_id>", methods=["GET"])
def get_snapshot(snapshot_id: int):
    """
    GET /snapshots/<id> — return one SnapshotDetail with all MetricRecord children.

    Uses a single LEFT JOIN query that produces one row per metric.
    _rows_to_detail() groups those rows into one SnapshotDetail object,
    creating the parent exactly once (no duplicate instantiation).

    LEFT JOIN snapshot_metric: the snapshot is returned even if it has no metrics.
    INNER JOIN metric_type: only metrics with a valid type are included.
    """
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT s.id          AS snap_id,
                   d.device_id,
                   s.timestamp_utc,
                   mt.name       AS metric_name,
                   mt.unit       AS metric_unit,
                   sm.value,
                   sm.status
            FROM   snapshot        s
            -- INNER JOIN: snapshot must have a device
            JOIN   device          d  ON d.id  = s.device_id
            -- LEFT JOIN: include the snapshot even if it has no metrics
            LEFT JOIN snapshot_metric sm ON sm.snapshot_id  = s.id
            LEFT JOIN metric_type    mt ON mt.id = sm.metric_type_id
            WHERE  s.id = ?
            ORDER  BY mt.name
            """,
            (snapshot_id,),
        ).fetchall()

    # _rows_to_detail groups multiple metric rows into ONE SnapshotDetail
    detail = _rows_to_detail(rows)
    if detail is None:
        return _json_response({"error": f"Snapshot {snapshot_id} not found"}, 404)

    logger.info("GET /snapshots/%d – found (%d metrics)", snapshot_id, len(detail.metrics))
    return _json_response(asdict(detail), 200)


# ---------------------------------------------------------------------------
# PUT /devices/<id>  –  UPDATE, mapped to DeviceRecord
# ---------------------------------------------------------------------------

@snapshots_bp.route("/devices/<int:device_pk>", methods=["PUT"])
def update_device_label(device_pk: int):
    """
    PUT /devices/<id> — update device label, return updated DeviceRecord.
    SQL: UPDATE device SET label = ? WHERE id = ?
    """
    body = request.get_json(silent=True)
    if body is None or not isinstance(body.get("label"), str):
        return _json_response({"error": "'label' is required and must be a string"}, 400)

    label = body["label"].strip()

    with get_db() as conn:
        exists = conn.execute(
            "SELECT 1 FROM device WHERE id = ?", (device_pk,)
        ).fetchone()

        if exists is None:
            return _json_response({"error": f"Device {device_pk} not found"}, 404)

        with conn:
            conn.execute(
                "UPDATE device SET label = ? WHERE id = ?", (label, device_pk)
            )

        # Re-fetch and map to DeviceRecord — never return raw SQL row
        row = conn.execute(
            "SELECT id, device_id, label, first_seen FROM device WHERE id = ?",
            (device_pk,),
        ).fetchone()

    device = _row_to_device(row)
    logger.info("PUT /devices/%d – label updated to '%s'", device_pk, label)
    return _json_response(asdict(device), 200)


# ---------------------------------------------------------------------------
# DELETE /snapshots/<id>
# ---------------------------------------------------------------------------

@snapshots_bp.route("/snapshots/<int:snapshot_id>", methods=["DELETE"])
def delete_snapshot(snapshot_id: int):
    """
    DELETE /snapshots/<id>
    ON DELETE CASCADE removes snapshot_metric rows automatically.
    Returns 204 No Content or 404 Not Found.
    """
    with get_db() as conn:
        with conn:
            cursor = conn.execute(
                "DELETE FROM snapshot WHERE id = ?", (snapshot_id,)
            )
            deleted = cursor.rowcount

    if deleted == 0:
        logger.info("DELETE /snapshots/%d – not found", snapshot_id)
        return _json_response({"error": f"Snapshot {snapshot_id} not found"}, 404)

    logger.info("DELETE /snapshots/%d – deleted (cascade removed metrics)", snapshot_id)
    return "", 204
