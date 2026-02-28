"""
RESTful CRUD API for VroomVroom snapshots – backed by SQLite.

A "snapshot" is one reading event: the app reads CPU/RAM/Disk from the OS,
pairs each value with its danger status, and stores everything in the database.

Endpoints:

    POST   /snapshots           Read live OS metrics and store a new snapshot  → 201
    GET    /snapshots           List all stored snapshots (summary)             → 200
    GET    /snapshots/<id>      Full snapshot with every metric value           → 200 / 404
    PUT    /devices/<id>        Update the human-readable label of a device     → 200 / 404
    DELETE /snapshots/<id>      Delete a snapshot (cascades to snapshot_metric) → 204 / 404

SQL operations used:
    SELECT  – list snapshots, fetch one snapshot, JOIN with metric_type
    INSERT  – store a new device, snapshot, and snapshot_metric rows
    UPDATE  – update a device label
    DELETE  – remove a snapshot (FK ON DELETE CASCADE removes its metrics)

Safety:
    - All queries use ? placeholders – no string formatting in SQL, no injection.
    - Every connection is opened inside `with get_db() as conn:` (RAII)
      and is always closed when the block exits.
"""
from __future__ import annotations

import logging
from dataclasses import asdict

from flask import Blueprint, request

from .database import get_db
from .datasnapshot import create_snapshot
from .metrics_reader import MetricsError, read_metrics
from .web_app import _json_response

logger = logging.getLogger(__name__)

snapshots_bp = Blueprint("snapshots", __name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_or_create_device(conn, device_id: str) -> int:
    """
    Return the integer PK for device_id, inserting the device row if it does
    not exist yet.  All in one connection so no separate open/close needed.

    SQL: INSERT OR IGNORE … then SELECT id
    """
    # INSERT OR IGNORE: does nothing if device_id already exists (UNIQUE constraint)
    conn.execute(
        "INSERT OR IGNORE INTO device (device_id) VALUES (?)",
        (device_id,),
    )
    row = conn.execute(
        "SELECT id FROM device WHERE device_id = ?", (device_id,)
    ).fetchone()
    return row["id"]


def _store_snapshot(conn, device_pk: int, snapshot) -> int:
    """
    INSERT a snapshot row and return its auto-assigned id.

    SQL: INSERT INTO snapshot (device_id, timestamp_utc) VALUES (?, ?)
    """
    cursor = conn.execute(
        "INSERT INTO snapshot (device_id, timestamp_utc) VALUES (?, ?)",
        (device_pk, snapshot.timestamp_utc.isoformat()),
    )
    return cursor.lastrowid


def _store_metrics(conn, snapshot_id: int, snapshot) -> None:
    """
    INSERT one snapshot_metric row per Metric in the snapshot.

    Uses executemany with a list of tuples – all parameterised, never string-formatted.

    SQL: INSERT INTO snapshot_metric (snapshot_id, metric_type_id, value, status)
         SELECT ?, id, ?, ? FROM metric_type WHERE name = ?
    """
    for metric in snapshot.metrics:
        # Look up the metric_type by name (seeded at init_db)
        row = conn.execute(
            "SELECT id FROM metric_type WHERE name = ?", (metric.name,)
        ).fetchone()
        if row is None:
            logger.warning("Unknown metric name '%s' – skipping", metric.name)
            continue
        conn.execute(
            """INSERT INTO snapshot_metric
               (snapshot_id, metric_type_id, value, status)
               VALUES (?, ?, ?, ?)""",
            (snapshot_id, row["id"], metric.value, metric.status),
        )


# ---------------------------------------------------------------------------
# POST /snapshots  –  read live metrics and store
# ---------------------------------------------------------------------------

@snapshots_bp.route("/snapshots", methods=["POST"])
def create_snapshot_endpoint():
    """
    POST /snapshots
    Read OS metrics now, build a Snapshot, store it in the database.

    SQL: INSERT INTO device (if new), snapshot, snapshot_metric rows
    Returns 201 Created with the stored snapshot id and summary.
    Returns 503 if OS metrics cannot be read.
    """
    # Read live data – same pipeline as the metrics cache
    cfg = None
    try:
        from flask import current_app
        from .web_app import APP_CONFIG_KEY
        cfg = current_app.config.get(APP_CONFIG_KEY)
    except RuntimeError:
        pass  # outside app context (tests) – cfg stays None

    try:
        metrics_dict = read_metrics()
    except MetricsError as e:
        logger.error("POST /snapshots – metrics read failed: %s", e)
        return _json_response({"error": f"Could not read OS metrics: {e}"}, 503)

    # Build the Snapshot object with status computed from config thresholds
    if cfg is not None:
        thresholds = asdict(cfg.danger_thresholds)
        device_id = cfg.device_id
    else:
        # Fallback when config is not attached (e.g. direct test run)
        thresholds = {"cpu_percent": 80, "ram_percent": 85, "disk_percent": 90}
        device_id = "unknown"

    snapshot = create_snapshot(
        device_id=device_id,
        metrics_dict=metrics_dict,
        thresholds=thresholds,
    )

    # Persist to SQLite – all INSERTs in one transaction
    with get_db() as conn:
        with conn:  # transaction: commit on success, rollback on exception
            device_pk = _get_or_create_device(conn, snapshot.device_id)
            snapshot_id = _store_snapshot(conn, device_pk, snapshot)
            _store_metrics(conn, snapshot_id, snapshot)

    logger.info(
        "POST /snapshots – stored snapshot id=%d for device '%s' (%d metrics)",
        snapshot_id, snapshot.device_id, len(snapshot.metrics),
    )
    return _json_response(
        {
            "id": snapshot_id,
            "device_id": snapshot.device_id,
            "timestamp_utc": snapshot.timestamp_utc.isoformat(),
            "metric_count": len(snapshot.metrics),
        },
        201,
    )


# ---------------------------------------------------------------------------
# GET /snapshots  –  list all (summary rows)
# ---------------------------------------------------------------------------

@snapshots_bp.route("/snapshots", methods=["GET"])
def list_snapshots():
    """
    GET /snapshots
    Return a summary list of every stored snapshot.

    SQL:
        SELECT s.id, d.device_id, s.timestamp_utc, COUNT(sm.metric_type_id)
        FROM snapshot s
        JOIN device d ON d.id = s.device_id
        LEFT JOIN snapshot_metric sm ON sm.snapshot_id = s.id
        GROUP BY s.id
        ORDER BY s.id DESC

    Returns 200 OK with [] if no snapshots exist yet.
    """
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT s.id,
                   d.device_id,
                   s.timestamp_utc,
                   COUNT(sm.metric_type_id) AS metric_count
            FROM snapshot s
            JOIN device          d  ON d.id  = s.device_id
            LEFT JOIN snapshot_metric sm ON sm.snapshot_id = s.id
            GROUP BY s.id
            ORDER BY s.id DESC
            """
        ).fetchall()

    result = [
        {
            "id": r["id"],
            "device_id": r["device_id"],
            "timestamp_utc": r["timestamp_utc"],
            "metric_count": r["metric_count"],
        }
        for r in rows
    ]
    logger.info("GET /snapshots – returning %d snapshots", len(result))
    return _json_response(result, 200)


# ---------------------------------------------------------------------------
# GET /snapshots/<id>  –  full snapshot with all metric values
# ---------------------------------------------------------------------------

@snapshots_bp.route("/snapshots/<int:snapshot_id>", methods=["GET"])
def get_snapshot(snapshot_id: int):
    """
    GET /snapshots/<id>
    Return one snapshot with all its metric rows joined from snapshot_metric.

    SQL:
        SELECT snapshot + JOIN device + JOIN snapshot_metric + JOIN metric_type
    Returns 200 OK or 404 Not Found.
    """
    with get_db() as conn:
        # Parameterised SELECT by primary key – no injection possible
        snap_row = conn.execute(
            """
            SELECT s.id, d.device_id, s.timestamp_utc
            FROM snapshot s
            JOIN device d ON d.id = s.device_id
            WHERE s.id = ?
            """,
            (snapshot_id,),
        ).fetchone()

        if snap_row is None:
            return _json_response(
                {"error": f"Snapshot {snapshot_id} not found"}, 404
            )

        # JOIN snapshot_metric with metric_type to get name + unit
        metric_rows = conn.execute(
            """
            SELECT mt.name, mt.unit, sm.value, sm.status
            FROM snapshot_metric sm
            JOIN metric_type mt ON mt.id = sm.metric_type_id
            WHERE sm.snapshot_id = ?
            ORDER BY mt.name
            """,
            (snapshot_id,),
        ).fetchall()

    metrics = [
        {
            "name": m["name"],
            "value": m["value"],
            "unit": m["unit"],
            "status": m["status"],
        }
        for m in metric_rows
    ]

    logger.info("GET /snapshots/%d – found (%d metrics)", snapshot_id, len(metrics))
    return _json_response(
        {
            "id": snap_row["id"],
            "device_id": snap_row["device_id"],
            "timestamp_utc": snap_row["timestamp_utc"],
            "metrics": metrics,
        },
        200,
    )


# ---------------------------------------------------------------------------
# PUT /devices/<id>  –  update device label  (demonstrates SQL UPDATE)
# ---------------------------------------------------------------------------

@snapshots_bp.route("/devices/<int:device_pk>", methods=["PUT"])
def update_device_label(device_pk: int):
    """
    PUT /devices/<id>
    Update the human-readable label of a device.

    Request body (JSON): { "label": "My Gaming PC" }

    SQL: UPDATE device SET label = ? WHERE id = ?
    Returns 200 OK with the updated device row or 404 Not Found.
    """
    body = request.get_json(silent=True)
    if body is None or not isinstance(body.get("label"), str):
        return _json_response(
            {"error": "'label' is required and must be a string"}, 400
        )

    label = body["label"].strip()

    with get_db() as conn:
        # Check the device exists first
        row = conn.execute(
            "SELECT id, device_id, label FROM device WHERE id = ?", (device_pk,)
        ).fetchone()

        if row is None:
            return _json_response({"error": f"Device {device_pk} not found"}, 404)

        with conn:  # transaction
            conn.execute(
                "UPDATE device SET label = ? WHERE id = ?",
                (label, device_pk),
            )

        updated = conn.execute(
            "SELECT id, device_id, label, first_seen FROM device WHERE id = ?",
            (device_pk,),
        ).fetchone()

    logger.info("PUT /devices/%d – label updated to '%s'", device_pk, label)
    return _json_response(
        {
            "id": updated["id"],
            "device_id": updated["device_id"],
            "label": updated["label"],
            "first_seen": updated["first_seen"],
        },
        200,
    )


# ---------------------------------------------------------------------------
# DELETE /snapshots/<id>  –  remove a snapshot
# ---------------------------------------------------------------------------

@snapshots_bp.route("/snapshots/<int:snapshot_id>", methods=["DELETE"])
def delete_snapshot(snapshot_id: int):
    """
    DELETE /snapshots/<id>
    Remove a snapshot row.  The ON DELETE CASCADE foreign key automatically
    removes all matching snapshot_metric rows.

    SQL: DELETE FROM snapshot WHERE id = ?
    Returns 204 No Content on success or 404 Not Found.
    """
    with get_db() as conn:
        with conn:  # transaction
            cursor = conn.execute(
                "DELETE FROM snapshot WHERE id = ?", (snapshot_id,)
            )
            deleted = cursor.rowcount  # 1 if deleted, 0 if id did not exist

    if deleted == 0:
        logger.info("DELETE /snapshots/%d – not found", snapshot_id)
        return _json_response(
            {"error": f"Snapshot {snapshot_id} not found"}, 404
        )

    logger.info("DELETE /snapshots/%d – deleted (cascade removed its metrics)", snapshot_id)
    return "", 204  # 204 No Content – success, no body
