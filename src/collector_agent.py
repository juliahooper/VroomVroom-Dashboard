"""
Long-running collector agent: continuous timing loop, read metrics, upload via API.

- Collects PC metrics, YouTube view count, and mobile (Firebase) data at the same interval.
- Start-based scheduling: next run at (loop_start + interval) to avoid drift.
- Error retry: upload retries with exponential backoff.
- Graceful shutdown: SIGTERM/SIGINT set a flag; loop exits after current iteration.
"""
from __future__ import annotations

import json
import logging
import signal
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

from dataclasses import asdict

from .configlib import AppConfig
from .datasnapshot import create_snapshot
from .metrics_reader import MetricsError, read_metrics

logger = logging.getLogger(__name__)

_DEFAULT_API_URL = "http://127.0.0.1:5000"
_UPLOAD_PATH = "/orm/upload_snapshot"


def _upload_snapshot_once(api_base_url: str, dto: dict) -> None:
    """POST snapshot DTO to API. Raises on HTTP or connection error."""
    url = api_base_url.rstrip("/") + _UPLOAD_PATH
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


def upload_snapshot_with_retry(
    api_base_url: str,
    dto: dict,
    max_attempts: int = 3,
    base_delay: float = 1.0,
) -> None:
    """
    Upload snapshot DTO to API with retries. Exponential backoff: base_delay * 2**attempt.
    Raises after all attempts fail.
    """
    last_error: Exception | None = None
    for attempt in range(max_attempts):
        try:
            _upload_snapshot_once(api_base_url, dto)
            if attempt > 0:
                logger.info("Upload succeeded on attempt %d", attempt + 1)
            return
        except (urllib.error.URLError, urllib.error.HTTPError, OSError, RuntimeError) as e:
            last_error = e
            logger.warning(
                "Upload attempt %d/%d failed: %s",
                attempt + 1, max_attempts, e,
            )
            if attempt < max_attempts - 1:
                delay = base_delay * (2 ** attempt)
                logger.info("Retrying in %.1f s", delay)
                time.sleep(delay)
    if last_error:
        raise last_error


def run_agent(
    config: AppConfig,
    interval_seconds: int = 30,
    api_base_url: str | None = None,
    config_path: str | None = None,
) -> None:
    """
    Run the collector agent loop: every interval_seconds, read PC metrics, YouTube,
    and mobile (Firebase) data, upload to API. Start-based scheduling (sleep until
    loop_start + interval). Handles SIGTERM/SIGINT for graceful shutdown.
    """
    api = (api_base_url or "").strip() or _DEFAULT_API_URL
    thresholds = asdict(config.danger_thresholds)
    device_id = config.device_id

    shutdown_requested = False

    def _signal_handler(_signum: int, _frame: object) -> None:
        nonlocal shutdown_requested
        shutdown_requested = True
        logger.info("Shutdown requested (signal), will exit after current iteration")

    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)

    logger.info(
        "Collector agent starting: interval=%ds, api=%s, device_id=%s",
        interval_seconds, api, device_id,
    )
    logger.info(
        "Scheduling: start-based (next run at loop_start + %ds) to avoid drift",
        interval_seconds,
    )

    cycle = 0
    while not shutdown_requested:
        cycle += 1
        loop_start = time.monotonic()

        try:
            metrics_dict = read_metrics()
            snapshot = create_snapshot(
                device_id=device_id,
                metrics_dict=metrics_dict,
                thresholds=thresholds,
            )
            dto = {
                "device_id": snapshot.device_id,
                "timestamp_utc": snapshot.timestamp_utc.isoformat(),
                "metrics": [
                    {"name": m.name, "value": m.value, "unit": m.unit, "status": m.status}
                    for m in snapshot.metrics
                ],
            }
            upload_snapshot_with_retry(api, dto)
            logger.info(
                "Cycle %d: uploaded snapshot %s (%d metrics)",
                cycle, snapshot.timestamp_utc.isoformat(), len(snapshot.metrics),
            )

            # YouTube: same interval (view count + like count = 2 metrics for 3rd party)
            try:
                from .youtube_fetcher import YouTubeFetcherError, get_video_statistics
                stats = get_video_statistics()
                youtube_dto = {
                    "device_id": "youtube-vroom-vroom",
                    "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                    "metrics": [
                        {"name": "total_streams", "value": float(stats["view_count"]), "unit": "count", "status": "normal"},
                        {"name": "Like Count", "value": float(stats["like_count"]), "unit": "count", "status": "normal"},
                    ],
                }
                upload_snapshot_with_retry(api, youtube_dto)
                logger.info("Cycle %d: uploaded YouTube snapshot (views=%s, likes=%s)", cycle, stats["view_count"], stats["like_count"])
            except YouTubeFetcherError as e:
                logger.warning("Cycle %d: YouTube fetch skipped: %s", cycle, e)

            # Mobile (Firebase): same interval; no-op if mobile not configured or disabled
            try:
                from .collectors.mobile_upload import collect_and_upload
                collect_and_upload(api, config_path=config_path)
            except Exception as e:
                logger.warning("Cycle %d: mobile collect/upload skipped: %s", cycle, e)
        except MetricsError as e:
            logger.error("Cycle %d: failed to read metrics: %s", cycle, e, exc_info=True)
        except Exception as e:
            logger.error(
                "Cycle %d: upload failed after retries: %s",
                cycle, e, exc_info=True,
            )

        if shutdown_requested:
            break

        # Start-based: sleep until loop_start + interval (avoids drift from end-based)
        sleep_until = loop_start + interval_seconds
        now = time.monotonic()
        sleep_duration = sleep_until - now
        if sleep_duration > 0:
            time.sleep(sleep_duration)
        else:
            logger.warning(
                "Cycle %d overran interval by %.1f s (next run delayed)",
                cycle, -sleep_duration,
            )

    logger.info("Collector agent shutting down gracefully (cycle %d)", cycle)
