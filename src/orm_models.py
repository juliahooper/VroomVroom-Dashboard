"""
SQLAlchemy ORM models for VroomVroom Monitor.

Maps the same four database tables as database.py to Python classes so that
rows can be read and written as objects rather than raw SQL strings.

HOW ORM DIFFERS FROM RAW SQL
─────────────────────────────
Raw SQL (snapshots.py)          ORM (this file)
─────────────────────────────   ─────────────────────────────────────────
conn.execute("SELECT ...")      session.scalars(select(Snapshot).where(...))
dict / sqlite3.Row result       Python object with typed attributes
Manual JOIN + grouping          Relationship navigation: snapshot.device.label
Explicit transaction control    session.commit() / session.rollback()

BENEFITS OF ORM
─────────────────────────────
• Type-safe access to columns (snapshot.timestamp_utc, not row["timestamp_utc"])
• Relationship navigation without writing JOINs (snapshot.device, snapshot.metrics)
• SQLAlchemy tracks changes — modify an object and commit, no UPDATE query needed
• Identity map: two queries for the same row return the SAME Python object (no duplicates)

HIDDEN COMPLEXITY (things ORM abstracts that can catch you out)
─────────────────────────────
• N+1 query problem: accessing snapshot.device in a loop fires one extra SELECT per row
  → Fix: use joinedload() or selectinload() in the query
• Lazy loading: by default, relationships are fetched on first access. If the session
  is closed first, you get a DetachedInstanceError
• Session lifetime: you must keep the session open while navigating relationships
• Implicit queries: obj.relationship_field looks like a property access but runs SQL
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
    UniqueConstraint,
    create_engine,
    event,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Session,
    joinedload,
    mapped_column,
    relationship,
    sessionmaker,
)

logger = logging.getLogger(__name__)

# Use the same database file as the raw SQL layer
_DEFAULT_DB_PATH = str(Path(__file__).parent.parent / "data" / "vroomvroom.db")
_DB_PATH: str = os.environ.get("VROOMVROOM_DB", _DEFAULT_DB_PATH)

# SQLAlchemy engine – connects to the same SQLite file as raw SQL
_engine = create_engine(f"sqlite:///{_DB_PATH}", echo=False)

# Enable foreign key enforcement for every SQLite connection opened by the engine
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

    # Relationship: navigate from a Device to all its Snapshots without writing a JOIN
    snapshots: Mapped[list[Snapshot]] = relationship(
        "Snapshot",
        back_populates="device",
        cascade="all, delete-orphan",  # deleting a Device deletes its Snapshots
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

    # Relationship: navigate from MetricType to all recorded values
    snapshot_metrics: Mapped[list[SnapshotMetric]] = relationship(
        "SnapshotMetric", back_populates="metric_type"
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

    # Relationship navigation (no JOIN needed in application code)
    device:           Mapped[Device]              = relationship("Device", back_populates="snapshots")
    snapshot_metrics: Mapped[list[SnapshotMetric]] = relationship(
        "SnapshotMetric",
        back_populates="snapshot",
        cascade="all, delete-orphan",  # deleting a Snapshot deletes its metrics
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

    # Relationship navigation — traverse to sibling objects without extra queries
    snapshot:    Mapped[Snapshot]    = relationship("Snapshot",    back_populates="snapshot_metrics")
    metric_type: Mapped[MetricType]  = relationship("MetricType",  back_populates="snapshot_metrics")

    def __repr__(self) -> str:
        return f"<SnapshotMetric snap={self.snapshot_id} type={self.metric_type_id} value={self.value}>"


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
