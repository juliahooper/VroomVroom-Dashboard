"""
configlib – Configuration loading and logging setup.

Exposes: AppConfig, ConfigError, DangerThresholds, load_config, setup_logging,
and default constants for server port/host.
"""
from .config import (
    DEFAULT_SERVER_HOST,
    DEFAULT_SERVER_PORT,
    AppConfig,
    ConfigError,
    DangerThresholds,
    load_config,
)
from .logging_setup import setup_logging

__all__ = [
    "DEFAULT_SERVER_HOST",
    "DEFAULT_SERVER_PORT",
    "AppConfig",
    "ConfigError",
    "DangerThresholds",
    "load_config",
    "setup_logging",
]
