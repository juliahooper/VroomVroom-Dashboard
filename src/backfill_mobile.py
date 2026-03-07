"""
One-time backfill: read all historical mobile data from Firebase into the DB.

Run once before starting the normal collector. After backfill, run the collector
normally (cron/scheduler) to ingest only new readings.

Usage:
    python -m src.backfill_mobile

Requires:
    - mobile.enabled: true in config
    - Firebase credentials configured
    - Backend API running (for POST /orm/upload_snapshot)
    - VROOMVROOM_API env var or default http://127.0.0.1:5000
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

# Limit for Firestore query (max points per location per time-series source)
BACKFILL_LIMIT = 10_000

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def main() -> int:
    from dotenv import load_dotenv

    _project_root = Path(__file__).resolve().parent.parent
    load_dotenv(_project_root / ".env")

    config_path = os.environ.get("VROOMVROOM_CONFIG", str(_project_root / "config" / "config.json"))
    api_base = os.environ.get("VROOMVROOM_API", "http://127.0.0.1:5000").rstrip("/")

    from .configlib import load_mobile_config
    from .mobile_collector import MobileDataCollector, init_firebase
    from .mobile_snapshot_bridge import mobile_to_snapshot
    from .collectors._upload import upload_snapshot

    mobile_config = load_mobile_config(config_path)
    if mobile_config is None or not mobile_config.enabled:
        logger.error("Mobile not configured or disabled. Set mobile.enabled: true in config.")
        return 1
    if not init_firebase(mobile_config):
        logger.error("Firebase init failed. Check firebase_credentials_path.")
        return 1

    collector = MobileDataCollector(mobile_config)
    locations = collector.list_locations()
    if not locations:
        logger.warning("No locations from Firestore; using default.")
        location_ids = ["loc_lough_dan"]
    else:
        location_ids = [loc.id for loc in locations]

    logger.info("Backfilling %d locations to %s", len(location_ids), api_base)
    total_uploaded = 0
    total_skipped = 0

    for location_id in location_ids:
        try:
            series = collector.get_time_series(location_id, limit_override=BACKFILL_LIMIT)
            count_results = []
            for src in mobile_config.count_sources:
                cr = collector.get_count(location_id, metric_id=src.metric_id)
                if cr:
                    count_results.append(cr)

            if not series:
                logger.info("  %s: no time-series data, skipping", location_id)
                continue

            logger.info("  %s: %d points", location_id, len(series))
            for i, point in enumerate(series):
                try:
                    snapshot = mobile_to_snapshot(location_id, point, count_results)
                    dto = {
                        "device_id": snapshot.device_id,
                        "timestamp_utc": snapshot.timestamp_utc.isoformat(),
                        "metrics": [
                            {"name": m.name, "value": m.value, "unit": m.unit, "status": m.status}
                            for m in snapshot.metrics
                        ],
                    }
                    upload_snapshot(api_base, dto)
                    total_uploaded += 1
                    if (i + 1) % 100 == 0:
                        logger.info("    uploaded %d/%d", i + 1, len(series))
                except Exception as e:
                    logger.warning("    skipped point %d: %s", i, e)
                    total_skipped += 1

        except Exception as e:
            logger.exception("Backfill failed for location %s: %s", location_id, e)
            return 1

    logger.info("Backfill complete. Uploaded %d snapshots, skipped %d.", total_uploaded, total_skipped)
    return 0


if __name__ == "__main__":
    sys.exit(main())
