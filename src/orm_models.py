"""
SQLAlchemy ORM models for VroomVroom — same four tables as database.py.

Use get_session() for RAII; use joinedload/selectinload in queries to avoid N+1.

When DATABASE_URL is set (PostgreSQL on our VM), the app uses that DB;
otherwise it uses local SQLite (data/vroomvroom.db).
"""
from __future__ import annotations

import contextlib
import logging
import os
from pathlib import Path
from typing import Iterator

from sqlalchemy import (
    CheckConstraint,
    Float,
    ForeignKey,
    Integer,
    String,
    create_engine,
    event,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Session,
    mapped_column,
    relationship,
    sessionmaker,
)

logger = logging.getLogger(__name__)

# Step 5 – enable SQL logging to inspect generated queries (set VROOMVROOM_SQL_ECHO=1)
_SQL_ECHO = os.environ.get("VROOMVROOM_SQL_ECHO", "").lower() in ("1", "true", "yes")

_DATABASE_URL: str | None = os.environ.get("DATABASE_URL")
_DEFAULT_DB_PATH = str(Path(__file__).parent.parent / "data" / "vroomvroom.db")
_DB_PATH: str = os.environ.get("VROOMVROOM_DB", _DEFAULT_DB_PATH)

if _DATABASE_URL:
    # PostgreSQL on our VM: use postgresql+psycopg2:// so SQLAlchemy uses the right driver
    _url = _DATABASE_URL
    if _url.startswith("postgresql://") and "postgresql+" not in _url:
        _url = _url.replace("postgresql://", "postgresql+psycopg2://", 1)
    _engine = create_engine(_url, echo=_SQL_ECHO)
else:
    # Local SQLite
    _SQLITE_TIMEOUT = 15
    _engine = create_engine(
        f"sqlite:///{_DB_PATH}",
        echo=_SQL_ECHO,
        connect_args={"timeout": _SQLITE_TIMEOUT},
    )

    @event.listens_for(_engine, "connect")
    def _set_sqlite_pragma(dbapi_conn, _):
        dbapi_conn.execute("PRAGMA foreign_keys = ON")

# Session factory – call _SessionFactory() to get a new Session
_SessionFactory = sessionmaker(bind=_engine)


# ---------------------------------------------------------------------------
# ORM Models  (mapped to the same tables as database.py)
# ---------------------------------------------------------------------------

class Base(DeclarativeBase):
    """Shared declarative base — all models inherit from this."""


class Device(Base):
    """
    Maps to the 'device' table.
    One row per monitored machine.
    Relationship: one Device → many Snapshots.
    """
    __tablename__ = "device"

    id:         Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id:  Mapped[str] = mapped_column(String, nullable=False, unique=True)
    label:      Mapped[str] = mapped_column(String, nullable=False, default="")
    first_seen: Mapped[str] = mapped_column(String, nullable=False)

    # Relationship: one Device → many Snapshots. Default lazy="select" (load on access).
    snapshots: Mapped[list[Snapshot]] = relationship(
        "Snapshot",
        back_populates="device",
        cascade="all, delete-orphan",
        lazy="select",  # lazy load: query when device.snapshots is first accessed
    )
    commands: Mapped[list[DeviceCommand]] = relationship(
        "DeviceCommand",
        back_populates="device",
        cascade="all, delete-orphan",
        lazy="select",
    )

    def __repr__(self) -> str:
        return f"<Device id={self.id} device_id={self.device_id!r} label={self.label!r}>"


class MetricType(Base):
    """
    Maps to the 'metric_type' table.
    Defines what can be measured (e.g. 'CPU Usage', '%').
    Relationship: one MetricType appears in many SnapshotMetric rows.
    """
    __tablename__ = "metric_type"

    id:   Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    unit: Mapped[str] = mapped_column(String, nullable=False)

    # One-to-many: MetricType → SnapshotMetric (lazy load unless eager-loaded).
    snapshot_metrics: Mapped[list[SnapshotMetric]] = relationship(
        "SnapshotMetric", back_populates="metric_type", lazy="select"
    )

    def __repr__(self) -> str:
        return f"<MetricType id={self.id} name={self.name!r} unit={self.unit!r}>"


class Snapshot(Base):
    """
    Maps to the 'snapshot' table.
    One row per reading event (when metrics were collected).
    Relationships:
        device          – the machine this reading came from (many-to-one)
        snapshot_metrics – the individual metric values (one-to-many)
    """
    __tablename__ = "snapshot"

    id:            Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id:     Mapped[int] = mapped_column(ForeignKey("device.id"), nullable=False)
    timestamp_utc: Mapped[str] = mapped_column(String, nullable=False)

    # Many-to-one: Snapshot → Device. Lazy load by default.
    device: Mapped[Device] = relationship("Device", back_populates="snapshots", lazy="select")
    # One-to-many: Snapshot → SnapshotMetric list. Use joinedload/selectinload in queries to eager load.
    snapshot_metrics: Mapped[list[SnapshotMetric]] = relationship(
        "SnapshotMetric",
        back_populates="snapshot",
        cascade="all, delete-orphan",
        lazy="select",
    )

    def __repr__(self) -> str:
        return f"<Snapshot id={self.id} device_id={self.device_id} ts={self.timestamp_utc}>"


class SnapshotMetric(Base):
    """
    Maps to the 'snapshot_metric' junction table.
    One row = one metric value in one snapshot.
    Composite primary key: (snapshot_id, metric_type_id).
    Relationships:
        snapshot     – the reading event this value belongs to
        metric_type  – what was measured (name + unit)
    """
    __tablename__ = "snapshot_metric"
    __table_args__ = (
        CheckConstraint("status IN ('normal', 'warning', 'danger')", name="chk_status"),
    )

    snapshot_id:    Mapped[int]   = mapped_column(ForeignKey("snapshot.id"),      primary_key=True)
    metric_type_id: Mapped[int]   = mapped_column(ForeignKey("metric_type.id"),   primary_key=True)
    value:          Mapped[float] = mapped_column(Float, nullable=False)
    status:         Mapped[str]   = mapped_column(String, nullable=False)

    # Navigate to parent Snapshot and MetricType (lazy load unless eager-loaded in query).
    snapshot: Mapped[Snapshot] = relationship("Snapshot", back_populates="snapshot_metrics", lazy="select")
    metric_type: Mapped[MetricType] = relationship("MetricType", back_populates="snapshot_metrics", lazy="select")

    def __repr__(self) -> str:
        return f"<SnapshotMetric snap={self.snapshot_id} type={self.metric_type_id} value={self.value}>"


class DeviceCommand(Base):
    """
    Maps to the 'device_command' table.
    Stretch goal: server sends commands to devices (e.g. play_alert = open YouTube when threshold breached).
    Agent polls GET /orm/commands/pending and executes; acks via POST /orm/commands/<id>/ack.
    """
    __tablename__ = "device_command"
    __table_args__ = (
        CheckConstraint("status IN ('pending', 'executed', 'failed')", name="chk_device_command_status"),
    )

    id:         Mapped[int]   = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id:  Mapped[int]   = mapped_column(ForeignKey("device.id"), nullable=False)
    command:    Mapped[str]  = mapped_column(String, nullable=False)
    status:    Mapped[str]  = mapped_column(String, nullable=False)
    created_at: Mapped[str] = mapped_column(String, nullable=False)

    device: Mapped[Device] = relationship("Device", back_populates="commands", lazy="select")

    def __repr__(self) -> str:
        return f"<DeviceCommand id={self.id} device_id={self.device_id} command={self.command!r} status={self.status!r}>"


class Location(Base):
    """
    Maps to the 'location' table.
    Map markers (e.g. Irish locations) with id, name, county, lat, lng, cold_water_shock_risk_score, alert_count.
    """
    __tablename__ = "location"

    id:                         Mapped[str]  = mapped_column(String, primary_key=True)
    name:                       Mapped[str]  = mapped_column(String, nullable=False)
    county:                     Mapped[str]  = mapped_column(String, nullable=False)
    lat:                        Mapped[float] = mapped_column(Float, nullable=False)
    lng:                        Mapped[float] = mapped_column(Float, nullable=False)
    cold_water_shock_risk_score: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    alert_count:                 Mapped[int]   = mapped_column(Integer, nullable=False, default=0)

    def __repr__(self) -> str:
        return f"<Location id={self.id!r} name={self.name!r} lat={self.lat} lng={self.lng}>"


# ---------------------------------------------------------------------------
# Session management (RAII context manager)
# ---------------------------------------------------------------------------

@contextlib.contextmanager
def get_session() -> Iterator[Session]:
    """
    RAII context manager for SQLAlchemy sessions.

    Usage:
        with get_session() as session:
            devices = session.scalars(select(Device)).all()

    Lifecycle:
        __enter__ → open session
        normal exit → commit
        exception  → rollback  (changes are never partially applied)
        __exit__   → close session  (always, even on exception)

    IMPORTANT: Keep the session open while accessing lazy-loaded relationships.
    If the session is closed before you read snapshot.device, SQLAlchemy raises
    DetachedInstanceError. This context manager keeps it open for the duration
    of the with block.
    """
    session = _SessionFactory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def create_session() -> Session:
    """
    Return a new Session without the context manager. Caller must call
    session.close() when done. Use for demos/tests that need manual
    commit/rollback (e.g. demonstrating session.rollback()).
    """
    return _SessionFactory()


# ---------------------------------------------------------------------------
# Cloud DB init (PostgreSQL) – create tables and seed metric_type
# ---------------------------------------------------------------------------

def init_pg_db() -> None:
    """
    Create all tables and seed metric_type. Call when DATABASE_URL is set
    Safe to call on every startup (CREATE TABLE IF NOT EXISTS;
    INSERT ON CONFLICT DO NOTHING; UPDATE for units).
    Locations for the map are hardcoded from SEED_LOCATIONS; GET /orm/locations uses them.
    """
    from sqlalchemy import text

    from .db_seed import SEED_METRIC_TYPES

    Base.metadata.create_all(_engine)
    with _engine.connect() as conn:
        with conn.begin():
            for name, unit in SEED_METRIC_TYPES:
                conn.execute(
                    text(
                        "INSERT INTO metric_type (name, unit) VALUES (:name, :unit) "
                        "ON CONFLICT (name) DO NOTHING"
                    ),
                    {"name": name, "unit": unit},
                )
                conn.execute(
                    text("UPDATE metric_type SET unit = :unit WHERE name = :name"),
                    {"unit": unit, "name": name},
                )
            # Remove Lough Owel from location table if present (no longer in SEED_LOCATIONS)
            conn.execute(
                text("DELETE FROM location WHERE id IN ('loc_lough_owel', 'loc_lough_owell')")
            )
    logger.info("PostgreSQL database initialised (DATABASE_URL)")
