"""
Logging setup – console and file handlers from config.

Configures the root logger with level and handlers (stdout + file) using AppConfig.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

from .config import AppConfig


def setup_logging(config: AppConfig) -> None:
    """
    Set up logging so messages go to both the console and a log file.
    Log level and file path come from config.
    """
    log_level_map = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
        "CRITICAL": logging.CRITICAL,
    }
    log_level = log_level_map.get(config.log_level.upper(), logging.INFO)

    log_path = Path(config.log_file_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger()
    logger.setLevel(log_level)
    logger.handlers.clear()

    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File handler
    file_handler = logging.FileHandler(log_path, encoding='utf-8')
    file_handler.setLevel(log_level)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
