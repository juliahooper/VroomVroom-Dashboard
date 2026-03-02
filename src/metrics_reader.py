"""
Metrics reading and processing module.

Reads the current number of running threads, RAM usage %, and disk usage % from
the operating system (using the psutil library) and returns them as a dictionary.
If psutil isn't installed or a read fails we raise MetricsError.
"""
from __future__ import annotations

import logging
import os
import time

try:
    import psutil
except ImportError:
    psutil = None

logger = logging.getLogger(__name__)


class MetricsError(Exception):
    """Exception raised when metric reading fails."""
    pass


def read_metrics() -> dict[str, float]:
    """
    Read system metrics (thread count, RAM %, and disk read speed).
    
    Returns:
        Dictionary with 'thread_count', 'ram_percent', and 'disk_read_mb_s' keys.
        
    Raises:
        MetricsError: If metrics cannot be read (e.g., psutil not installed or system error).
    """
    if psutil is None:
        raise MetricsError("psutil library is not installed. Install it with: pip install psutil")
    
    logger.info("Reading system metrics")
    
    metrics: dict[str, float] = {}
    
    try:
        # Read total number of running threads across all processes.
        # This replaces CPU percentage as a load indicator.
        thread_count = 0
        for proc in psutil.process_iter(attrs=["num_threads"]):
            try:
                info = proc.info
                thread_count += int(info.get("num_threads") or 0)
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
        if thread_count < 0:
            raise MetricsError(f"Invalid thread count value: {thread_count}")
        metrics["thread_count"] = float(thread_count)
        logger.debug(f"Thread count: {thread_count}")
        
    except Exception as e:
        raise MetricsError(f"Failed to read thread count: {e}") from e
    
    try:
        # Read RAM percentage (Fuel Level equivalent)
        memory = psutil.virtual_memory()
        ram_percent = memory.percent
        if ram_percent < 0 or ram_percent > 100:
            raise MetricsError(f"Invalid RAM percentage value: {ram_percent}")
        metrics["ram_percent"] = round(ram_percent, 2)
        logger.debug(f"RAM percentage: {ram_percent}%")
        
    except Exception as e:
        raise MetricsError(f"Failed to read RAM percentage: {e}") from e
    
    try:
        # Approximate disk read throughput (MB/s) using a 1s sampling window.
        io_before = psutil.disk_io_counters()
        time.sleep(1.0)
        io_after = psutil.disk_io_counters()
        read_bytes = io_after.read_bytes - io_before.read_bytes
        if read_bytes < 0:
            raise MetricsError(f"Invalid disk read bytes delta: {read_bytes}")
        disk_read_mb_s = read_bytes / (1024 * 1024)
        metrics["disk_read_mb_s"] = round(disk_read_mb_s, 2)
        logger.debug(f"Disk read speed: {disk_read_mb_s:.2f} MB/s")
        
    except Exception as e:
        raise MetricsError(f"Failed to read disk read speed: {e}") from e
    
    logger.info(
        "Metrics read successfully - Threads: %s, RAM: %s%%, Disk read: %s MB/s",
        metrics["thread_count"],
        metrics["ram_percent"],
        metrics["disk_read_mb_s"],
    )
    return metrics
