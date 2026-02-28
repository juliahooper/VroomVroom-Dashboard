"""
configlib – Configuration loading and logging setup.

Exposes: AppConfig, ConfigError, DangerThresholds, load_config, setup_logging,
defaults (server port/host), and fallbacks for when config is absent (FALLBACK_*).
"""
from .config import (
    DEFAULT_SERVER_HOST,
    DEFAULT_SERVER_PORT,
    AppConfig,
    ConfigError,
    DangerThresholds,
    FALLBACK_DEVICE_ID,
    FALLBACK_THRESHOLDS,
    load_config,
)
from .logging_setup import setup_logging

__all__ = [
    "DEFAULT_SERVER_HOST",
    "DEFAULT_SERVER_PORT",
    "AppConfig",
    "ConfigError",
    "DangerThresholds",
    "FALLBACK_DEVICE_ID",
    "FALLBACK_THRESHOLDS",
    "load_config",
    "setup_logging",
]
