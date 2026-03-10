"""
Fix mobile device snapshots that have wrong metrics (e.g. total_streams instead of Cold Water Shock Risk).

Run when mobile historic charts show empty/wrong data due to stale or misconfigured uploads.
Deletes snapshots for mobile devices that don't have location metrics (Cold Water Shock Risk, Water Temp).
After running, the mobile collector will upload fresh correct data on its next run.

Usage: python scripts/fix_mobile_snapshots.py [--dry-run]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select, delete
from sqlalchemy.orm import selectinload

from src.orm_models import Device, Snapshot, SnapshotMetric, get_session

MOBILE_PREFIX = "mobile:"
EXPECTED_METRIC_NAMES = {"Cold Water Shock Risk", "Water Temp"}


def main() -> int:
    parser = argparse.ArgumentParser(description="Remove mobile snapshots with wrong metrics")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be deleted without deleting")
    args = parser.parse_args()

    with get_session() as session:
        devices = session.scalars(
            select(Device).where(Device.device_id.like(f"{MOBILE_PREFIX}%"))
        ).all()
        if not devices:
            print("No mobile devices found.")
            return 0

        total_deleted = 0
        for dev in devices:
            snapshots = session.scalars(
                select(Snapshot)
                .where(Snapshot.device_id == dev.id)
                .options(selectinload(Snapshot.snapshot_metrics).joinedload(SnapshotMetric.metric_type))
            ).all()

            for snap in snapshots:
                metric_names = {
                    sm.metric_type.name
                    for sm in snap.snapshot_metrics
                    if sm.metric_type
                }
                has_expected = bool(metric_names & EXPECTED_METRIC_NAMES)
                if not has_expected:
                    print(f"  Would delete snapshot {snap.id} ({dev.device_id}): metrics={list(metric_names)}")
                    if not args.dry_run:
                        session.execute(delete(SnapshotMetric).where(SnapshotMetric.snapshot_id == snap.id))
                        session.execute(delete(Snapshot).where(Snapshot.id == snap.id))
                        total_deleted += 1

        if args.dry_run:
            print("Dry run – no changes made. Run without --dry-run to apply.")
        elif total_deleted > 0:
            print(f"Deleted {total_deleted} invalid snapshot(s).")

    return 0


if __name__ == "__main__":
    sys.exit(main())
