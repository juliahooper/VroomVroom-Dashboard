"""
Collect mobile data using existing MobileDataCollector and mobile_snapshot_bridge,
then POST to the same Aggregator API (one DB) via /orm/upload_snapshot.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from ._upload import upload_snapshot

logger = logging.getLogger(__name__)

# Default location when no locations from Firestore
DEFAULT_LOCATION_ID = "loc_lough_dan"


def collect_and_upload(
    api_base_url: str,
    config_path: str | None = None,
) -> None:
    """
    Load mobile config, fetch data with MobileDataCollector, build snapshot(s)
    via mobile_snapshot_bridge, POST each to api_base_url (same DB as PC/YouTube).
    """
    from ..configlib import load_mobile_config
    from ..mobile_collector import MobileDataCollector, init_firebase
    from ..mobile_snapshot_bridge import mobile_to_snapshot

    path = config_path or os.environ.get("VROOMVROOM_CONFIG", str(Path("config") / "config.json"))
    mobile_config = load_mobile_config(path)
    if mobile_config is None or not mobile_config.enabled:
        logger.info("Mobile not configured or disabled; skipping mobile upload.")
        return
    if not init_firebase(mobile_config):
        logger.warning("Firebase init failed; skipping mobile upload.")
        return
    collector = MobileDataCollector(mobile_config)
    locations = collector.list_locations()
    location_ids = [loc.id for loc in locations] if locations else [DEFAULT_LOCATION_ID]
    for location_id in location_ids:
        try:
            series = collector.get_time_series(location_id)
            latest_point = series[-1] if series else None
            count_results = []
            for src in mobile_config.count_sources:
                cr = collector.get_count(location_id, metric_id=src.metric_id)
                if cr:
                    count_results.append(cr)
            snapshot = mobile_to_snapshot(location_id, latest_point, count_results)
            dto = {
                "device_id": snapshot.device_id,
                "timestamp_utc": snapshot.timestamp_utc.isoformat(),
                "metrics": [
                    {"name": m.name, "value": m.value, "unit": m.unit, "status": m.status}
                    for m in snapshot.metrics
                ],
            }
            upload_snapshot(api_base_url, dto)
            logger.info("Mobile upload: device_id=%s metrics=%d", snapshot.device_id, len(snapshot.metrics))
        except Exception as e:
            logger.exception("Mobile upload failed for location %s: %s", location_id, e)
