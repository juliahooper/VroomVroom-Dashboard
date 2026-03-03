"""
3rd party data collector: YouTube stream count.
Fetches current stream count and POSTs to the same Aggregator API (one DB).
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

from ._upload import upload_snapshot

logger = logging.getLogger(__name__)

DEVICE_ID = "youtube"


def fetch_stream_count() -> float:
    """
    Fetch current YouTube stream count.
    Set VROOMVROOM_YOUTUBE_STREAM_COUNT for a stub value (no API key).
    """
    stub = os.environ.get("VROOMVROOM_YOUTUBE_STREAM_COUNT")
    if stub is not None:
        try:
            return float(stub)
        except ValueError:
            pass
    logger.warning(
        "YouTube stream count not configured; using 0. Set VROOMVROOM_YOUTUBE_STREAM_COUNT or implement API."
    )
    return 0.0


def collect_and_upload(api_base_url: str) -> None:
    """Fetch stream count, build snapshot DTO, POST to Aggregator API."""
    value = fetch_stream_count()
    timestamp_utc = datetime.now(timezone.utc).isoformat()
    dto = {
        "device_id": DEVICE_ID,
        "timestamp_utc": timestamp_utc,
        "metrics": [
            {"name": "Stream Count", "value": value, "unit": "count", "status": "normal"},
        ],
    }
    upload_snapshot(api_base_url, dto)
    logger.info("3rd party collector uploaded stream_count=%.0f for device_id=%s", value, DEVICE_ID)
