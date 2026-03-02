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


# Percentages above which we consider CPU, RAM, or disk "in danger"
@dataclass(frozen=True)
class DangerThresholds:
    cpu_percent: int
    ram_percent: int
    disk_percent: int


# Defaults for optional TCP settings (used when not in config JSON)
DEFAULT_SERVER_PORT = 54545
DEFAULT_SERVER_HOST = "127.0.0.1"

# Fallbacks when the Flask app has no config (e.g. test or import-time). Not for production.
# Use these instead of hardcoding thresholds or device_id in routes.
FALLBACK_DEVICE_ID = "unknown"
FALLBACK_THRESHOLDS = {"cpu_percent": 80, "ram_percent": 85, "disk_percent": 90}


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
_REQUIRED_DANGER_KEYS = ("cpu_percent", "ram_percent", "disk_percent")


# ---------------------------------------------------------------------------
# Optional mobile (Firebase/Firestore) config – flexible data flow
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TimeSeriesSource:
    """One time-series metric source: collection + field mapping. Add new metrics by adding entries in config."""
    metric_id: str
    collection_key: str  # key into mobile.collections
    location_field: str
    timestamp_field: str
    value_fields: tuple[str, ...]  # Firestore field names to expose (e.g. risk_score, water_temp)
    limit: int


@dataclass(frozen=True)
class CountSource:
    """One count metric source (e.g. alerts per location). Add new count metrics by adding entries in config."""
    metric_id: str
    collection_key: str
    location_field: str


@dataclass(frozen=True)
class MobileConfig:
    """
    Mobile data source config (Firestore). All collection names and metric definitions
    come from config so new services/devices/metrics can be added without code changes.
    """
    enabled: bool
    firebase_credentials_path: str | None  # None = use GOOGLE_APPLICATION_CREDENTIALS env
    collections: tuple[tuple[str, str], ...]  # (logical_key, firestore_collection_name)
    time_series_sources: tuple[TimeSeriesSource, ...]
    count_sources: tuple[CountSource, ...]

    def collection_name(self, logical_key: str) -> str | None:
        """Resolve logical key (e.g. 'water_temp') to Firestore collection name."""
        for k, v in self.collections:
            if k == logical_key:
                return v
        return None


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

    # danger_thresholds must be an object with cpu_percent, ram_percent, disk_percent
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
            cpu_percent=_require_int(danger, "cpu_percent", context="danger_thresholds"),
            ram_percent=_require_int(danger, "ram_percent", context="danger_thresholds"),
            disk_percent=_require_int(danger, "disk_percent", context="danger_thresholds"),
        ),
        server_port=server_port,
        server_host=server_host.strip(),
        sql_echo=sql_echo,
    )

    # Extra check: read interval must be positive
    if cfg.read_interval_seconds <= 0:
        raise ConfigError("Key 'read_interval_seconds' must be > 0.")

    return cfg


def load_mobile_config(config_path: str | Path) -> MobileConfig | None:
    """
    Load optional mobile (Firebase/Firestore) config from the same config file.
    Returns None if "mobile" is missing or mobile.enabled is false.
    Raises ConfigError if "mobile" is present but invalid.
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

    mobile = data.get("mobile")
    if mobile is None:
        return None
    if not isinstance(mobile, dict):
        raise ConfigError("Key 'mobile' must be an object.")

    enabled = mobile.get("enabled", False)
    if not isinstance(enabled, bool):
        raise ConfigError("Key 'mobile.enabled' must be a boolean.")
    if not enabled:
        return None

    creds_path = mobile.get("firebase_credentials_path")
    if creds_path is not None and not (isinstance(creds_path, str) and creds_path.strip()):
        raise ConfigError("Key 'mobile.firebase_credentials_path' must be a non-empty string or omitted.")

    collections_raw = mobile.get("collections")
    if not isinstance(collections_raw, dict):
        raise ConfigError("Key 'mobile.collections' must be an object (logical_key -> Firestore collection name).")
    collections = tuple((k, str(v).strip()) for k, v in collections_raw.items() if v)
    if not collections:
        raise ConfigError("Key 'mobile.collections' must have at least one entry.")

    time_series_raw = mobile.get("time_series_sources", [])
    if not isinstance(time_series_raw, list):
        raise ConfigError("Key 'mobile.time_series_sources' must be an array.")
    time_series_sources: list[TimeSeriesSource] = []
    for i, entry in enumerate(time_series_raw):
        if not isinstance(entry, dict):
            raise ConfigError(f"mobile.time_series_sources[{i}] must be an object.")
        metric_id = _require_str(entry, "metric_id", context=f"mobile.time_series_sources[{i}]")
        collection_key = _require_str(entry, "collection_key", context=f"mobile.time_series_sources[{i}]")
        location_field = _require_str(entry, "location_field", context=f"mobile.time_series_sources[{i}]")
        timestamp_field = _require_str(entry, "timestamp_field", context=f"mobile.time_series_sources[{i}]")
        vf = entry.get("value_fields")
        if not isinstance(vf, list) or not all(isinstance(x, str) for x in vf):
            raise ConfigError(f"mobile.time_series_sources[{i}].value_fields must be an array of strings.")
        value_fields = tuple(vf)
        limit = entry.get("limit", 200)
        if type(limit) is not int or limit < 1:
            raise ConfigError(f"mobile.time_series_sources[{i}].limit must be a positive integer.")
        time_series_sources.append(TimeSeriesSource(
            metric_id=metric_id,
            collection_key=collection_key,
            location_field=location_field,
            timestamp_field=timestamp_field,
            value_fields=value_fields,
            limit=limit,
        ))

    count_raw = mobile.get("count_sources", [])
    if not isinstance(count_raw, list):
        raise ConfigError("Key 'mobile.count_sources' must be an array.")
    count_sources: list[CountSource] = []
    for i, entry in enumerate(count_raw):
        if not isinstance(entry, dict):
            raise ConfigError(f"mobile.count_sources[{i}] must be an object.")
        metric_id = _require_str(entry, "metric_id", context=f"mobile.count_sources[{i}]")
        collection_key = _require_str(entry, "collection_key", context=f"mobile.count_sources[{i}]")
        location_field = _require_str(entry, "location_field", context=f"mobile.count_sources[{i}]")
        count_sources.append(CountSource(metric_id=metric_id, collection_key=collection_key, location_field=location_field))

    return MobileConfig(
        enabled=True,
        firebase_credentials_path=creds_path.strip() if creds_path else None,
        collections=collections,
        time_series_sources=tuple(time_series_sources),
        count_sources=tuple(count_sources),
    )
