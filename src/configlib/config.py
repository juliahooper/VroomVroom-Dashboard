"""
Configuration loading and validation.

Reads app settings from a JSON file (e.g. config/config.json), checks that all
required fields are present and valid, and returns an AppConfig object.
Raises ConfigError if something is missing or wrong.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


# Raised when the config file is missing a key, has wrong types, or invalid values
class ConfigError(Exception):
    pass


# Thresholds above which we consider metrics "in danger"
@dataclass(frozen=True)
class DangerThresholds:
    thread_count: int
    ram_percent: int
    disk_read_mb_s: int


# Defaults for optional TCP settings (used when not in config JSON)
DEFAULT_SERVER_PORT = 54545
DEFAULT_SERVER_HOST = "127.0.0.1"

# Fallbacks when the Flask app has no config (e.g. test or import-time). Not for production.
# Use these instead of hardcoding thresholds or device_id in routes.
FALLBACK_DEVICE_ID = "unknown"
FALLBACK_THRESHOLDS = {"thread_count": 300, "ram_percent": 85, "disk_read_mb_s": 50}


# Immutable dataclass representing all settings the app needs. Loaded once from JSON and passed around.
@dataclass(frozen=True)
class AppConfig:
    app_name: str
    device_id: str
    read_interval_seconds: int
    log_level: str
    log_file_path: str
    danger_thresholds: DangerThresholds
    server_port: int = DEFAULT_SERVER_PORT
    server_host: str = DEFAULT_SERVER_HOST
    sql_echo: bool = False  # if True, SQLAlchemy logs every SQL statement (for debugging)


# Names of required keys at the top level of the config JSON
_REQUIRED_TOP_LEVEL_KEYS = (
    "app_name",
    "device_id",
    "read_interval_seconds",
    "log_level",
    "log_file_path",
    "danger_thresholds",
)

# These keys must exist inside the danger_thresholds object in the JSON
_REQUIRED_DANGER_KEYS = ("thread_count", "ram_percent", "disk_read_mb_s")


def _require_key(obj: Mapping[str, Any], key: str, *, context: str) -> Any:
    """If the key is missing we raise ConfigError; otherwise return its value."""
    if key not in obj:
        raise ConfigError(f"Missing required key '{key}' in {context}.")
    return obj[key]


def _require_int(obj: Mapping[str, Any], key: str, *, context: str) -> int:
    """Same as _require_key but we also check the value is an integer (not a bool)."""
    value = _require_key(obj, key, context=context)
    if type(value) is not int:
        raise ConfigError(f"Key '{key}' in {context} must be an integer.")
    return value


def _require_str(obj: Mapping[str, Any], key: str, *, context: str) -> str:
    """Same as _require_key but we also check the value is a non-empty string."""
    value = _require_key(obj, key, context=context)
    if not isinstance(value, str):
        raise ConfigError(f"Key '{key}' in {context} must be a string.")
    if value.strip() == "":
        raise ConfigError(f"Key '{key}' in {context} must be non-empty.")
    return value


def load_config(config_path: str | Path) -> AppConfig:
    """
    Read the config file from disk, parse the JSON, check all required keys exist
    and have the right types, then build and return an AppConfig. Raises ConfigError
    if anything is wrong; raises OSError if the file can't be read.
    """
    path = Path(config_path)
    try:
        raw_text = path.read_text(encoding="utf-8")
    except OSError as e:
        raise ConfigError(f"Unable to read config file at '{path}': {e}") from e

    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as e:
        raise ConfigError(f"Invalid JSON in config file '{path}': {e}") from e

    if not isinstance(data, dict):
        raise ConfigError(f"Config root must be a JSON object in '{path}'.")

    # Check every required top-level key exists
    for key in _REQUIRED_TOP_LEVEL_KEYS:
        _require_key(data, key, context="config root")

    # danger_thresholds must be an object with thread_count, ram_percent, disk_read_mb_s
    danger = _require_key(data, "danger_thresholds", context="config root")
    if not isinstance(danger, dict):
        raise ConfigError("Key 'danger_thresholds' must be an object in config root.")

    for key in _REQUIRED_DANGER_KEYS:
        _require_key(danger, key, context="danger_thresholds")

    # Optional: TCP server port and host for client (defaults if missing)
    server_port = data.get("server_port", DEFAULT_SERVER_PORT)
    if type(server_port) is not int or not (1 <= server_port <= 65535):
        raise ConfigError("Key 'server_port' must be an integer between 1 and 65535.")
    server_host = data.get("server_host", DEFAULT_SERVER_HOST)
    if not isinstance(server_host, str) or not server_host.strip():
        raise ConfigError("Key 'server_host' must be a non-empty string.")

    # Optional: SQLAlchemy echo (log every SQL statement)
    sql_echo = data.get("sql_echo", False)
    if not isinstance(sql_echo, bool):
        raise ConfigError("Key 'sql_echo' must be a boolean.")

    # Build the immutable config object from validated values
    cfg = AppConfig(
        app_name=_require_str(data, "app_name", context="config root"),
        device_id=_require_str(data, "device_id", context="config root"),
        read_interval_seconds=_require_int(data, "read_interval_seconds", context="config root"),
        log_level=_require_str(data, "log_level", context="config root"),
        log_file_path=_require_str(data, "log_file_path", context="config root"),
        danger_thresholds=DangerThresholds(
            thread_count=_require_int(danger, "thread_count", context="danger_thresholds"),
            ram_percent=_require_int(danger, "ram_percent", context="danger_thresholds"),
            disk_read_mb_s=_require_int(danger, "disk_read_mb_s", context="danger_thresholds"),
        ),
        server_port=server_port,
        server_host=server_host.strip(),
        sql_echo=sql_echo,
    )

    # Extra check: read interval must be positive
    if cfg.read_interval_seconds <= 0:
        raise ConfigError("Key 'read_interval_seconds' must be > 0.")

    return cfg
