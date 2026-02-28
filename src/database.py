"""
SQLite database setup and connection management for VroomVroom Monitor.

Normalised schema – four tables:

    device          – one row per monitored machine
                      PRIMARY KEY id, unique device_id string, optional label

    metric_type     – defines the available metric names and units
                      PRIMARY KEY id, unique name (e.g. "CPU Usage"), unit (e.g. "%")
                      Seeded once at init_db() with the three standard metrics.

    snapshot        – one row per reading event
                      PRIMARY KEY id
                      FOREIGN KEY device_id → device(id)  ON DELETE CASCADE

    snapshot_metric – junction table  (many-to-many: snapshot ↔ metric_type)
                      Each row = one metric value recorded in one snapshot.
                      COMPOSITE PRIMARY KEY (snapshot_id, metric_type_id)
                      FOREIGN KEY snapshot_id    → snapshot(id)     ON DELETE CASCADE
                      FOREIGN KEY metric_type_id → metric_type(id)

Relationships:
    device     1──* snapshot           (one device, many snapshots)
    snapshot   *──* metric_type        (via snapshot_metric)
                   ↑ many-to-many with composite PK junction table

RAII:
    All connections are opened inside context managers so they are always
    closed – even if an exception is raised mid-query.

No SQL injection:
    Every query that accepts external input uses ? placeholders, never
    string formatting.
"""
from __future__ import annotations

import contextlib
import logging
import os
import sqlite3
from pathlib import Path
from typing import Iterator

logger = logging.getLogger(__name__)

# Default database file – stored in data/ next to the project root.
# Override at runtime with the VROOMVROOM_DB environment variable.
_DEFAULT_DB_PATH = str(Path(__file__).parent.parent / "data" / "vroomvroom.db")
DB_PATH: str = os.environ.get("VROOMVROOM_DB", _DEFAULT_DB_PATH)

# ---------------------------------------------------------------------------
# Schema DDL
# ---------------------------------------------------------------------------

_SCHEMA_SQL = """
-- device: one row per monitored machine.
-- device_id is the string identifier from config (e.g. "pc-01").
-- label is an optional human-readable name (can be updated via PUT /devices/<id>).
CREATE TABLE IF NOT EXISTS device (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id  TEXT    NOT NULL UNIQUE,
    label      TEXT    NOT NULL DEFAULT '',
    first_seen TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- metric_type: the fixed set of metric definitions (what can be measured).
-- name is unique so "CPU Usage" cannot be registered twice.
-- unit stores the display unit, e.g. "%".
CREATE TABLE IF NOT EXISTS metric_type (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT    NOT NULL UNIQUE,
    unit TEXT    NOT NULL
);

-- snapshot: one row per reading event on a device.
-- ON DELETE CASCADE: deleting a device removes all its snapshots automatically.
CREATE TABLE IF NOT EXISTS snapshot (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id     INTEGER NOT NULL REFERENCES device(id) ON DELETE CASCADE,
    timestamp_utc TEXT    NOT NULL
);

-- snapshot_metric: junction table (many-to-many between snapshot and metric_type).
-- Each row records one metric value measured in one snapshot.
-- Composite PK prevents duplicate (snapshot, metric_type) pairs.
-- ON DELETE CASCADE: deleting a snapshot removes its metric rows automatically.
CREATE TABLE IF NOT EXISTS snapshot_metric (
    snapshot_id    INTEGER NOT NULL REFERENCES snapshot(id)     ON DELETE CASCADE,
    metric_type_id INTEGER NOT NULL REFERENCES metric_type(id),
    value          REAL    NOT NULL,
    status         TEXT    NOT NULL CHECK (status IN ('normal', 'warning', 'danger')),
    PRIMARY KEY (snapshot_id, metric_type_id)
);
"""

# The three standard metric types – inserted once when the DB is first created.
_SEED_METRIC_TYPES = [
    ("CPU Usage",  "%"),
    ("RAM Usage",  "%"),
    ("Disk Usage", "%"),
]


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------

def init_db() -> None:
    """
    Create the data/ directory, all tables, and seed metric_type rows.
    Safe to call every time the app starts (CREATE TABLE IF NOT EXISTS /
    INSERT OR IGNORE ensures no duplicate setup).
    """
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)

    # RAII: contextlib.closing guarantees conn.close() is called
    with contextlib.closing(sqlite3.connect(DB_PATH)) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        with conn:  # transaction – commit on success, rollback on exception
            conn.executescript(_SCHEMA_SQL)

            # Step 1: Insert any metric_type rows that don't exist yet.
            # Adding a new entry to _SEED_METRIC_TYPES is all that's needed —
            # the new row will appear in the database on the next startup.
            conn.executemany(
                "INSERT OR IGNORE INTO metric_type (name, unit) VALUES (?, ?)",
                _SEED_METRIC_TYPES,
            )

            # Step 2: Keep the unit in sync with _SEED_METRIC_TYPES.
            # If you change a unit (e.g. "%" → "percent"), it is updated automatically.
            # We update by name so the id (referenced by snapshot_metric FK) never changes.
            conn.executemany(
                "UPDATE metric_type SET unit = ? WHERE name = ?",
                [(unit, name) for name, unit in _SEED_METRIC_TYPES],
            )

    logger.info("Database initialised at %s", DB_PATH)


# ---------------------------------------------------------------------------
# Connection context manager (RAII)
# ---------------------------------------------------------------------------

@contextlib.contextmanager
def get_db() -> Iterator[sqlite3.Connection]:
    """
    RAII context manager – open a SQLite connection, yield it, always close it.

    Usage:
        with get_db() as conn:
            rows = conn.execute("SELECT * FROM snapshot").fetchall()

    Features:
        - Foreign keys enabled per-connection (SQLite requires this).
        - row_factory = sqlite3.Row so columns can be accessed by name: row["id"].
        - Caller wraps mutations in `with conn:` for automatic commit/rollback.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
    finally:
        conn.close()  # always executed, even if caller raises
