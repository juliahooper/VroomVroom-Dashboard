"""
Lightweight backup and failed-snapshot log for snapshot uploads.

- On successful persist: append DTO to data/snapshot_backup.jsonl (one JSON object per line).
- On persist failure after retries: append DTO + error to data/failed_snapshots.jsonl for replay.

No queue server; just append-only files so data is not lost and can be replayed if needed.
"""
from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

_DATA_DIR = Path(__file__).parent.parent / "data"
BACKUP_FILE = _DATA_DIR / "snapshot_backup.jsonl"
FAILED_FILE = _DATA_DIR / "failed_snapshots.jsonl"
_LOCK = threading.Lock()


def _ensure_data_dir() -> None:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)


def append_backup(dto: dict) -> None:
    """Append a snapshot DTO (one JSON line) to snapshot_backup.jsonl. Safe to call from any thread."""
    with _LOCK:
        try:
            _ensure_data_dir()
            line = json.dumps(dto, ensure_ascii=False) + "\n"
            with open(BACKUP_FILE, "a", encoding="utf-8") as f:
                f.write(line)
        except OSError as e:
            logger.warning("Backup append failed (non-fatal): %s", e)


def append_failed(dto: dict, error: str) -> None:
    """Append a failed DTO and error to failed_snapshots.jsonl for later replay."""
    with _LOCK:
        try:
            _ensure_data_dir()
            record = {
                "dto": dto,
                "error": error,
                "ts": datetime.now(timezone.utc).isoformat(),
            }
            line = json.dumps(record, ensure_ascii=False) + "\n"
            with open(FAILED_FILE, "a", encoding="utf-8") as f:
                f.write(line)
            logger.info("Appended failed snapshot to %s for replay", FAILED_FILE)
        except OSError as e:
            logger.warning("Failed-snapshot log append failed: %s", e)
