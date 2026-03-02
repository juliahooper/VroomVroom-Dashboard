"""
configlib – Configuration loading and logging setup.

Exposes: AppConfig, ConfigError, DangerThresholds, load_config, setup_logging,
mobile config (load_mobile_config, MobileConfig, TimeSeriesSource, CountSource),
defaults (server port/host), and fallbacks for when config is absent (FALLBACK_*).
"""
from .config import (
    DEFAULT_SERVER_HOST,
    DEFAULT_SERVER_PORT,
    AppConfig,
    ConfigError,
    CountSource,
    DangerThresholds,
    FALLBACK_DEVICE_ID,
    FALLBACK_THRESHOLDS,
    MobileConfig,
    TimeSeriesSource,
    load_config,
    load_mobile_config,
)
from .logging_setup import setup_logging

__all__ = [
    "DEFAULT_SERVER_HOST",
    "DEFAULT_SERVER_PORT",
    "AppConfig",
    "ConfigError",
    "CountSource",
    "DangerThresholds",
    "FALLBACK_DEVICE_ID",
    "FALLBACK_THRESHOLDS",
    "MobileConfig",
    "TimeSeriesSource",
    "load_config",
    "load_mobile_config",
    "setup_logging",
]
