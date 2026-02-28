"""
In-memory cache for metrics response with TTL and thread-safe access.

Logic table: Cache empty vs populated, expired vs valid, updater alive vs stalled.
Only one thread updates the cache; other threads serve cached data (or stale on stall).
RAII lock management and decision logging for debugging.
"""
from __future__ import annotations

import copy
import logging
import threading
import time
from typing import Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


# Logic-table state labels for decision logging
class _State:
    EMPTY = "empty"
    POPULATED_VALID = "populated_valid"
    POPULATED_EXPIRED_NO_UPDATER = "populated_expired_no_updater"
    POPULATED_EXPIRED_UPDATER_ALIVE = "populated_expired_updater_alive"
    UPDATER_STALLED = "updater_stalled"


class _Action:
    SERVE_CACHED = "serve_cached"
    SERVE_STALE = "serve_stale"
    BECOME_UPDATER = "become_updater"
    WAIT_THEN_SERVE_CACHED = "wait_then_serve_cached"


class MetricsCache:
    """
    Thread-safe cache with TTL invalidation and logic-table behaviour.

    States:
    - Cache: empty | populated
    - Validity: valid (within TTL) | expired
    - Updater: none | alive (thread in provider) | stalled (wait timeout exceeded)

    RAII: all lock access via context managers or try/finally release.
    """

    def __init__(
        self,
        ttl_seconds: float = 30.0,
        stall_timeout_seconds: float = 10.0,
    ):
        self._ttl_seconds = ttl_seconds
        self._stall_timeout_seconds = stall_timeout_seconds
        self._data: T | None = None
        self._last_refresh: float = 0.0
        self._updating: bool = False
        self._lock = threading.Lock()
        self._update_lock = threading.Lock()

    def _is_valid(self) -> bool:
        """True if cache has data and has not exceeded TTL. Call under _lock."""
        if self._data is None:
            return False
        return (time.time() - self._last_refresh) <= self._ttl_seconds

    def _is_populated(self) -> bool:
        """True if cache has data. Call under _lock."""
        return self._data is not None

    def get(self) -> T | None:
        """
        Return a deep copy of the cached value if valid, else None.
        Safe for concurrent callers; does not perform updates.
        """
        with self._lock:
            if self._is_valid():
                logger.debug(
                    "cache decision state=%s action=%s",
                    _State.POPULATED_VALID,
                    _Action.SERVE_CACHED,
                )
                return copy.deepcopy(self._data)
            return None

    def set(self, value: T) -> None:
        """Store a deep copy of value and set last refresh timestamp. Thread-safe."""
        with self._lock:
            self._data = copy.deepcopy(value)
            self._last_refresh = time.time()

    def get_or_compute(self, provider: Callable[[], T]) -> T:
        """
        Logic table: empty/populated × valid/expired × updater alive/stalled.
        One thread updates when cache is empty or expired with no updater;
        others serve cached (valid) or wait then serve; on stall timeout, serve stale.
        RAII: locks released via with or finally. Decision logging at DEBUG.
        """
        need_wait = False
        need_update = False
        can_serve_stale = False  # True if we have data to serve on stall timeout

        # --- Under _lock: classify state (logic table) and decide action ---
        with self._lock:
            populated = self._is_populated()
            valid = self._is_valid()
            updating = self._updating

            if not populated:
                logger.debug(
                    "cache decision state=%s action=%s",
                    _State.EMPTY,
                    _Action.BECOME_UPDATER,
                )
                need_update = True
                can_serve_stale = False
            elif valid:
                logger.debug(
                    "cache decision state=%s action=%s",
                    _State.POPULATED_VALID,
                    _Action.SERVE_CACHED,
                )
                return copy.deepcopy(self._data)  # type: ignore[return-value]
            elif updating:
                logger.debug(
                    "cache decision state=%s (will wait or serve_stale on timeout)",
                    _State.POPULATED_EXPIRED_UPDATER_ALIVE,
                )
                need_wait = True
                can_serve_stale = True
            else:
                logger.debug(
                    "cache decision state=%s action=%s (or serve_stale on timeout)",
                    _State.POPULATED_EXPIRED_NO_UPDATER,
                    _Action.BECOME_UPDATER,
                )
                need_update = True
                can_serve_stale = True

        # --- Wait for current updater (with timeout); then re-check or become updater ---
        if need_wait:
            acquired = self._update_lock.acquire(
                timeout=self._stall_timeout_seconds
            )
            if not acquired:
                with self._lock:
                    logger.debug(
                        "cache decision state=%s action=%s",
                        _State.UPDATER_STALLED,
                        _Action.SERVE_STALE,
                    )
                    if self._data is not None:
                        return copy.deepcopy(self._data)  # type: ignore[return-value]
                # Defensive: no data, must become updater
                self._update_lock.acquire(blocking=True)
            else:
                with self._lock:
                    if self._is_valid():
                        logger.debug(
                            "cache decision after wait action=%s",
                            _Action.WAIT_THEN_SERVE_CACHED,
                        )
                        result = copy.deepcopy(self._data)  # type: ignore[return-value]
                        self._update_lock.release()
                        return result
                # Still expired; we hold _update_lock, fall through to updater path
                need_update = False  # already have lock, skip acquire below

        # --- Acquire update lock if we need to become updater (empty or expired, no one updating) ---
        if need_update:
            if can_serve_stale:
                acquired = self._update_lock.acquire(
                    timeout=self._stall_timeout_seconds
                )
                if not acquired:
                    with self._lock:
                        logger.debug(
                            "cache decision state=%s action=%s",
                            _State.UPDATER_STALLED,
                            _Action.SERVE_STALE,
                        )
                        if self._data is not None:
                            return copy.deepcopy(self._data)  # type: ignore[return-value]
                    self._update_lock.acquire(blocking=True)
            else:
                self._update_lock.acquire(blocking=True)

        # --- Updater path: we hold _update_lock; RAII release in finally ---
        try:
            with self._lock:
                if self._is_valid():
                    logger.debug(
                        "cache decision (double-check) action=%s",
                        _Action.SERVE_CACHED,
                    )
                    return copy.deepcopy(self._data)  # type: ignore[return-value]
                self._updating = True

            try:
                new_value = provider()
            finally:
                with self._lock:
                    self._updating = False

            with self._lock:
                self._data = copy.deepcopy(new_value)
                self._last_refresh = time.time()

            return copy.deepcopy(new_value)
        finally:
            try:
                self._update_lock.release()
            except RuntimeError:
                pass  # already released (e.g. released in wait path)
