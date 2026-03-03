"""
Shared upload: POST snapshot DTO to Aggregator API (same DB as PC collector).
Used by 3rd party (YouTube) and Firebase (mobile) collectors.
"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request

logger = logging.getLogger(__name__)

UPLOAD_PATH = "/orm/upload_snapshot"


def upload_snapshot(api_base_url: str, dto: dict) -> None:
    """
    POST snapshot DTO to api_base_url + UPLOAD_PATH.
    dto: { "device_id": str, "timestamp_utc": str (ISO 8601), "metrics": [ { "name", "value", "unit", "status" }, ... ] }
    Raises on HTTP or connection error.
    """
    url = api_base_url.rstrip("/") + UPLOAD_PATH
    body = json.dumps(dto).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        if resp.status not in (200, 201):
            raise RuntimeError(f"Upload returned status {resp.status}")
    logger.debug("Uploaded snapshot device_id=%s to %s", dto.get("device_id"), url)
