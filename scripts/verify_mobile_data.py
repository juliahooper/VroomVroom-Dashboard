"""
Verify mobile data in the database after backfill.

Run from project root:
    python scripts/verify_mobile_data.py

Checks:
- snapshot table: count by device
- snapshot_metric table: count and sample
- metric_type: required names for mobile
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# Must load env before orm_models (DATABASE_URL)
from sqlalchemy import text

from src.orm_models import _engine

REQUIRED_METRIC_NAMES = ["Cold Water Shock Risk", "Alert Count", "Water Temp"]


def main():
    print("=== Mobile data verification ===\n")

    with _engine.connect() as conn:
        # 1. metric_type
        print("1. metric_type table (required for mobile):")
        result = conn.execute(
            text("SELECT id, name, unit FROM metric_type ORDER BY id")
        )
        rows = result.fetchall()
        for r in rows:
            print(f"   id={r[0]} name={r[1]!r} unit={r[2]!r}")
        found = {r[1] for r in rows}
        missing = set(REQUIRED_METRIC_NAMES) - found
        if missing:
            print(f"   WARNING: Missing metric types: {missing}")
            print("   Run the web app once so init_db/init_pg_db seeds metric_type.")
        else:
            print("   OK: All required metric types present.\n")

        # 2. snapshot count by device
        print("2. snapshot count by device (mobile:*):")
        result = conn.execute(
            text("""
                SELECT d.device_id, COUNT(s.id) AS cnt
                FROM device d
                LEFT JOIN snapshot s ON s.device_id = d.id
                WHERE d.device_id LIKE 'mobile:%'
                GROUP BY d.id, d.device_id
                ORDER BY d.device_id
            """)
        )
        rows = result.fetchall()
        if not rows:
            print("   No mobile devices found. Backfill creates devices on first upload.")
        for r in rows:
            print(f"   {r[0]}: {r[1]} snapshots")
        print()

        # 3. snapshot_metric count
        print("3. snapshot_metric rows (for mobile devices):")
        result = conn.execute(
            text("""
                SELECT COUNT(sm.id) AS cnt
                FROM snapshot_metric sm
                JOIN snapshot s ON s.id = sm.snapshot_id
                JOIN device d ON d.id = s.device_id
                WHERE d.device_id LIKE 'mobile:%'
            """)
        )
        cnt = result.scalar()
        print(f"   Total: {cnt} rows")
        if cnt == 0 and rows:
            print("   WARNING: Snapshots exist but no snapshot_metric rows.")
            print("   Likely cause: metric names in upload don't match metric_type.name")
            print("   Check web app logs for 'skipping metric' warnings.")
        elif cnt > 0:
            # Sample
            result = conn.execute(
                text("""
                    SELECT d.device_id, mt.name, sm.value
                    FROM snapshot_metric sm
                    JOIN snapshot s ON s.id = sm.snapshot_id
                    JOIN device d ON d.id = s.device_id
                    JOIN metric_type mt ON mt.id = sm.metric_type_id
                    WHERE d.device_id LIKE 'mobile:%'
                    ORDER BY s.id DESC
                    LIMIT 6
                """)
            )
            print("   Sample (latest):")
            for r in result.fetchall():
                print(f"     {r[0]} | {r[1]}: {r[2]}")

    print("\n=== Done ===")


if __name__ == "__main__":
    main()
