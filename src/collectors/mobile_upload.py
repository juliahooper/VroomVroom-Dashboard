"""
Collect mobile data using existing MobileDataCollector and mobile_snapshot_bridge,
then POST to the same Aggregator API (one DB) via /orm/upload_snapshot.

- Locations: each run, ensures every Firestore location has a device row in PostgreSQL
  (diffs list_locations() vs GET /orm/devices; uploads minimal snapshot for any missing).
- Time-series: incremental sync — only queries Firestore for documents newer than last sync,
  only appends to the DB when there is new data. Sync state in data/mobile_sync_state.json.

If Firestore returns an index error for the time-series query, create the
composite index it suggests (location_field + timestamp_field).
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from ._upload import upload_snapshot

logger = logging.getLogger(__name__)

MOBILE_DEVICE_ID_PREFIX = "mobile:"

# Default location when no locations from Firestore
DEFAULT_LOCATION_ID = "loc_lough_dan"

# Sync state: { "location_id": { "metric_id": timestamp_millis }, ... }
_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
_SYNC_STATE_FILE = _DATA_DIR / "mobile_sync_state.json"


def _load_sync_state() -> dict[str, dict[str, int]]:
    """Load last-sync timestamps from data/mobile_sync_state.json."""
    if not _SYNC_STATE_FILE.exists():
        return {}
    try:
        with open(_SYNC_STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Could not load mobile sync state: %s; starting fresh.", e)
        return {}


def _save_sync_state(state: dict[str, dict[str, int]]) -> None:
    """Persist sync state to data/mobile_sync_state.json."""
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(_SYNC_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def _fetch_mobile_device_ids(api_base_url: str) -> set[str]:
    """GET /orm/devices and return set of device_ids that start with mobile:."""
    import urllib.request
    url = api_base_url.rstrip("/") + "/orm/devices"
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return {d["device_id"] for d in data if (d.get("device_id") or "").startswith(MOBILE_DEVICE_ID_PREFIX)}


def _ensure_locations_in_db(
    api_base_url: str,
    location_ids: list[str],
    existing_mobile_device_ids: set[str],
) -> None:
    """
    For each location_id not yet in PostgreSQL (no device mobile:location_id),
    upload a minimal snapshot so the device is created. Runs every collect.
    """
    for location_id in location_ids:
        device_id = f"{MOBILE_DEVICE_ID_PREFIX}{location_id}"
        if device_id in existing_mobile_device_ids:
            continue
        dto = {
            "device_id": device_id,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "metrics": [
                {"name": "total_streams", "value": 0.0, "unit": "count", "status": "normal"}
            ],
        }
        try:
            upload_snapshot(api_base_url, dto)
            logger.info("Mobile: ensured device for location %s (new)", location_id)
        except Exception as e:
            logger.warning("Mobile: could not ensure device for %s: %s", location_id, e)


def collect_and_upload(
    api_base_url: str,
    config_path: str | None = None,
) -> None:
    """
    Load mobile config, fetch only NEW time-series data from Firestore (since last sync),
    build snapshot(s) via mobile_snapshot_bridge, POST each to api_base_url.
    Only appends to the DB when Firebase has new documents. Updates sync state after upload.
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

    # Automated: ensure every Firestore location has a device row in PostgreSQL
    try:
        existing_mobile = _fetch_mobile_device_ids(api_base_url)
        _ensure_locations_in_db(api_base_url, location_ids, existing_mobile)
    except Exception as e:
        logger.warning("Mobile: could not ensure locations in DB: %s", e)

    state = _load_sync_state()
    state_updated = False

    for location_id in location_ids:
        for src in mobile_config.time_series_sources:
            metric_id = src.metric_id
            last_sync = (state.get(location_id) or {}).get(metric_id)

            try:
                series = collector.get_time_series(
                    location_id,
                    metric_id=metric_id,
                    since_timestamp_millis=last_sync,
                )
            except Exception as e:
                logger.exception("Mobile get_time_series failed for %s/%s: %s", location_id, metric_id, e)
                continue

            if not series:
                continue

            latest_point = series[-1]
            count_results = []
            for count_src in mobile_config.count_sources:
                try:
                    cr = collector.get_count(location_id, metric_id=count_src.metric_id)
                    if cr:
                        count_results.append(cr)
                except Exception as e:
                    logger.debug("Count fetch failed for %s/%s: %s", location_id, count_src.metric_id, e)

            try:
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
                logger.info(
                    "Mobile upload: device_id=%s metrics=%d (new since %s)",
                    snapshot.device_id, len(snapshot.metrics),
                    "last_sync" if last_sync else "first_run",
                )
            except Exception as e:
                logger.exception("Mobile upload failed for location %s: %s", location_id, e)
                continue

            if location_id not in state:
                state[location_id] = {}
            state[location_id][metric_id] = latest_point.timestamp_millis
            state_updated = True

    if state_updated:
        _save_sync_state(state)
