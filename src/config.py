"""
Configuration management module.
"""

# Enables postponed evaluation of type annotations (PEP 563)
# Allows using modern type syntax like str | Path without quotes
from __future__ import annotations
# Standard library for parsing and generating JSON data
import json
# Decorator that automatically generates __init__, __repr__, __eq__ methods for classes
from dataclasses import dataclass
# Object-oriented path handling for file system operations (replaces os.path)
from pathlib import Path
# Type hints: Any allows any type, Mapping is abstract base class for dict-like objects
from typing import Any, Mapping


# Custom exception class for configuration-related errors (missing keys, invalid values, etc.)
class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class DangerThresholds:
    cpu_percent: int
    ram_percent: int
    disk_percent: int


# Default TCP server port (used when server_port is omitted from config)
DEFAULT_SERVER_PORT = 54545

# Immutable dataclass representing the full validated application configuration
@dataclass(frozen=True)
class AppConfig:
    app_name: str
    device_id: str
    read_interval_seconds: int
    log_level: str
    log_file_path: str
    danger_thresholds: DangerThresholds
    server_port: int = DEFAULT_SERVER_PORT


# Names of required keys at the top level of the config JSON
_REQUIRED_TOP_LEVEL_KEYS = (
    "app_name",
    "device_id",
    "read_interval_seconds",
    "log_level",
    "log_file_path",
    "danger_thresholds",
)

# Names of required keys inside the nested danger_thresholds object
_REQUIRED_DANGER_KEYS = ("cpu_percent", "ram_percent", "disk_percent")

 # Helper to ensure a required key exists in a mapping, otherwise raise a ConfigError
def _require_key(obj: Mapping[str, Any], key: str, *, context: str) -> Any:
    if key not in obj:
        raise ConfigError(f"Missing required key '{key}' in {context}.")
    return obj[key]


# Helper to ensure a required key exists and its value is an integer, otherwise raise ConfigError
def _require_int(obj: Mapping[str, Any], key: str, *, context: str) -> int:
    value = _require_key(obj, key, context=context)
    # Use type() instead of isinstance() to exclude bool (which is a subclass of int)
    if type(value) is not int:
        raise ConfigError(f"Key '{key}' in {context} must be an integer.")
    return value


# Helper to ensure a required key exists and its value is a non-empty string, otherwise raise ConfigError
def _require_str(obj: Mapping[str, Any], key: str, *, context: str) -> str:
    value = _require_key(obj, key, context=context)
    if not isinstance(value, str):
        raise ConfigError(f"Key '{key}' in {context} must be a string.")
    if value.strip() == "":
        raise ConfigError(f"Key '{key}' in {context} must be non-empty.")
    return value


def load_config(config_path: str | Path) -> AppConfig:
    """
    Load configuration from JSON file and validate required keys.

    Raises ConfigError for missing/invalid config and OSError for IO issues.
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

    for key in _REQUIRED_TOP_LEVEL_KEYS:
        _require_key(data, key, context="config root")

    danger = _require_key(data, "danger_thresholds", context="config root")
    if not isinstance(danger, dict):
        raise ConfigError("Key 'danger_thresholds' must be an object in config root.")

    for key in _REQUIRED_DANGER_KEYS:
        _require_key(danger, key, context="danger_thresholds")

    # Optional: TCP server port (default 54545)
    server_port = data.get("server_port", DEFAULT_SERVER_PORT)
    if type(server_port) is not int or not (1 <= server_port <= 65535):
        raise ConfigError("Key 'server_port' must be an integer between 1 and 65535.")

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
    )

    if cfg.read_interval_seconds <= 0:
        raise ConfigError("Key 'read_interval_seconds' must be > 0.")

    return cfg
