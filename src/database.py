"""
SQLite database for VroomVroom. Schema (normalised): docs/SCHEMA_DESIGN.md.

Tables: device, metric_type, snapshot, snapshot_metric. RAII via get_db();
parameterized queries only (no string formatting for user input).
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

-- location: map markers (e.g. Irish locations). id matches mobile location_id (e.g. loc_lough_dan).
-- cold_water_shock_risk_score: 0–100 or similar scale; alert_count: number of active alerts.
CREATE TABLE IF NOT EXISTS location (
    id                         TEXT  PRIMARY KEY,
    name                       TEXT  NOT NULL,
    county                     TEXT  NOT NULL,
    lat                        REAL  NOT NULL,
    lng                        REAL  NOT NULL,
    cold_water_shock_risk_score REAL NOT NULL DEFAULT 0,
    alert_count                 INTEGER NOT NULL DEFAULT 0
);
"""

# ---------------------------------------------------------------------------
# Indexes: foreign keys and frequently filtered/sorted columns (Step 1 – indexing)
# ---------------------------------------------------------------------------
# SQLite does not auto-create indexes on FK columns. Explicit indexes speed up
# JOINs, WHERE on device_id/timestamp, and ORDER BY. Use EXPLAIN QUERY PLAN to verify.
_INDEXES_SQL = """
CREATE INDEX IF NOT EXISTS idx_snapshot_device_id
    ON snapshot(device_id);
CREATE INDEX IF NOT EXISTS idx_snapshot_timestamp_utc
    ON snapshot(timestamp_utc);
CREATE INDEX IF NOT EXISTS idx_snapshot_metric_snapshot_id
    ON snapshot_metric(snapshot_id);
CREATE INDEX IF NOT EXISTS idx_snapshot_metric_metric_type_id
    ON snapshot_metric(metric_type_id);
"""

# Seed list lives in db_seed.py so ORM and raw SQL stay in sync.
from .db_seed import SEED_METRIC_TYPES as _SEED_METRIC_TYPES

# Irish locations for the map (id, name, county, lat, lng). Add more rows to seed further markers.
_SEED_LOCATIONS = [
    ("loc_lough_dan", "Lough Dan", "Wicklow", 53.09, -6.12),
    ("loc_dublin", "Dublin", "Dublin", 53.3498, -6.2603),
    ("loc_cork", "Cork", "Cork", 51.8985, -8.4756),
    ("loc_galway", "Galway", "Galway", 53.2707, -9.0518),
]

# Per-location live metrics: (id, cold_water_shock_risk_score 0–100, alert_count). Updated on seed.
_SEED_LOCATION_METRICS = [
    ("loc_lough_dan", 72.0, 2),
    ("loc_dublin", 35.0, 0),
    ("loc_cork", 58.0, 1),
    ("loc_galway", 45.0, 1),
]


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------

def init_db() -> None:
    """
    Create the data/ directory, all tables, and seed metric_type rows.
    Safe to call every time the app starts (CREATE TABLE IF NOT EXISTS /
    INSERT OR IGNORE ensures no duplicate setup).
    When DATABASE_URL is set, use PostgreSQL (ORM init) instead of local SQLite.
    """
    if os.environ.get("DATABASE_URL"):
        from .orm_models import init_pg_db
        init_pg_db()
        return

    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)

    # RAII: contextlib.closing guarantees conn.close() is called
    with contextlib.closing(sqlite3.connect(DB_PATH)) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        with conn:  # transaction – commit on success, rollback on exception
            conn.executescript(_SCHEMA_SQL)
            conn.executescript(_INDEXES_SQL)

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

            # Step 3: Seed location table for map markers (Ireland).
            conn.executemany(
                "INSERT OR IGNORE INTO location (id, name, county, lat, lng) VALUES (?, ?, ?, ?, ?)",
                _SEED_LOCATIONS,
            )
            # Step 3b: Ensure location table has metric columns (migration for existing DBs).
            for col_def in [
                "ALTER TABLE location ADD COLUMN cold_water_shock_risk_score REAL NOT NULL DEFAULT 0",
                "ALTER TABLE location ADD COLUMN alert_count INTEGER NOT NULL DEFAULT 0",
            ]:
                try:
                    conn.execute(col_def)
                except sqlite3.OperationalError as e:
                    if "duplicate column name" not in str(e).lower():
                        raise
            # Step 3c: Update seeded locations with live metrics.
            conn.executemany(
                "UPDATE location SET cold_water_shock_risk_score = ?, alert_count = ? WHERE id = ?",
                [(score, count, loc_id) for loc_id, score, count in _SEED_LOCATION_METRICS],
            )

    logger.info("Database initialised at %s", DB_PATH)


# ---------------------------------------------------------------------------
# Transaction manager (Step 3 – RAII: explicit BEGIN / COMMIT / ROLLBACK)
# ---------------------------------------------------------------------------

class TransactionManager:
    """
    RAII context manager for explicit transaction boundaries.

    - __enter__: runs BEGIN (transaction starts).
    - __exit__(normal): runs COMMIT.
    - __exit__(exception): runs ROLLBACK, then re-raises.

    Use with get_db(): open a connection, then run multi-step work inside
    a single transaction. If any step raises, the whole transaction is rolled back.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def __enter__(self) -> TransactionManager:
        self._conn.execute("BEGIN")
        return self

    def __exit__(self, exc_type: type | None, exc_val: BaseException | None, exc_tb: object) -> None:
        if exc_type is not None:
            self._conn.rollback()
            logger.debug("Transaction rolled back due to %s", exc_type.__name__)
            return None  # re-raise
        self._conn.commit()
        return None

    @property
    def conn(self) -> sqlite3.Connection:
        """The underlying connection for executing statements within this transaction."""
        return self._conn


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
        - For explicit transaction boundaries use TransactionManager(conn): BEGIN on enter,
          COMMIT on success, ROLLBACK on exception.
        - timeout=15 so concurrent writers wait for the lock instead of failing with BUSY.
    """
    conn = sqlite3.connect(DB_PATH, timeout=15.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
    finally:
        conn.close()  # always executed, even if caller raises
