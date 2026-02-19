"""
BlockTimer – RAII-style timing for critical or timed blocks.

Use it like:  with BlockTimer("my_step"): ... do work ...
When you enter the block we start a timer; when you leave we log how long it took.
"""
from __future__ import annotations

import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)


class BlockTimer:
    """
    RAII-style context manager that times a block of code.

    - __enter__: starts a high-resolution timer (perf_counter).
    - __exit__: computes elapsed time and logs it.

    Use to time metric serialisation, transmission, or loop execution.
    """

    def __init__(self, label: str = "block", log_level: int = logging.DEBUG):
        # What to call this timer in the log message (e.g. "create_snapshot")
        self.label = label
        # Whether to log at DEBUG, INFO, etc.
        self.log_level = log_level
        # When we entered the block (set in __enter__)
        self._start: Optional[float] = None
        # How long the block took (set in __exit__)
        self._elapsed_seconds: Optional[float] = None

    def __enter__(self) -> BlockTimer:
        # Start the stopwatch as soon as we enter the "with" block
        self._start = time.perf_counter()
        return self

    def __exit__(self, exc_type: type | None, exc_val: BaseException | None, exc_tb: object) -> None:
        # When we leave the block (normally or by exception), compute elapsed time and log it
        self._elapsed_seconds = time.perf_counter() - (self._start or 0)
        logger.log(
            self.log_level,
            "BlockTimer [%s]: %.6f s",
            self.label,
            self._elapsed_seconds,
        )

    @property
    def elapsed_seconds(self) -> float:
        """How many seconds the block took (0 if we haven't exited yet)."""
        return self._elapsed_seconds if self._elapsed_seconds is not None else 0.0
