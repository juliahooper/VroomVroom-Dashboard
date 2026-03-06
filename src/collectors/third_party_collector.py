"""
3rd party data collector: YouTube (view count + like count).
Fetches via YouTube Data API v3 when YOUTUBE_API_KEY is set; otherwise uses stub env vars.
POSTs to the same Aggregator API (one DB) with 2 metrics for the YouTube device.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

from ._upload import upload_snapshot

logger = logging.getLogger(__name__)

DEVICE_ID = "youtube-vroom-vroom"


def collect_and_upload(api_base_url: str) -> None:
    """Fetch YouTube stats (views + likes), build snapshot DTO, POST to Aggregator API."""
    stub_views = os.environ.get("VROOMVROOM_YOUTUBE_STREAM_COUNT")
    if stub_views is not None:
        try:
            view_count = float(stub_views)
        except ValueError:
            view_count = 0.0
        like_count = 0.0
    else:
        try:
            from ..youtube_fetcher import YouTubeFetcherError, get_video_statistics
            stats = get_video_statistics()
            view_count = float(stats["view_count"])
            like_count = float(stats["like_count"])
        except Exception as e:
            logger.warning("YouTube API not available: %s. Set YOUTUBE_API_KEY or VROOMVROOM_YOUTUBE_STREAM_COUNT.", e)
            view_count = 0.0
            like_count = 0.0

    timestamp_utc = datetime.now(timezone.utc).isoformat()
    dto = {
        "device_id": DEVICE_ID,
        "timestamp_utc": timestamp_utc,
        "metrics": [
            {"name": "total_streams", "value": view_count, "unit": "count", "status": "normal"},
            {"name": "Like Count", "value": like_count, "unit": "count", "status": "normal"},
        ],
    }
    upload_snapshot(api_base_url, dto)
    logger.info("3rd party collector uploaded views=%.0f likes=%.0f for device_id=%s", view_count, like_count, DEVICE_ID)
