"""
Metrics reading and processing module.
"""
from __future__ import annotations

import logging
import os

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
    Read system metrics (CPU %, RAM %, and Disk %).
    
    Returns:
        Dictionary with 'cpu_percent', 'ram_percent', and 'disk_percent' keys.
        
    Raises:
        MetricsError: If metrics cannot be read (e.g., psutil not installed or system error).
    """
    if psutil is None:
        raise MetricsError("psutil library is not installed. Install it with: pip install psutil")
    
    logger.info("Reading system metrics")
    
    metrics = {}
    
    try:
        # Read CPU percentage (Engine RPM equivalent)
        # interval=1.0 means we wait 1 second to get an accurate CPU reading
        cpu_percent = psutil.cpu_percent(interval=1.0)
        if cpu_percent < 0 or cpu_percent > 100:
            raise MetricsError(f"Invalid CPU percentage value: {cpu_percent}")
        metrics['cpu_percent'] = round(cpu_percent, 2)
        logger.debug(f"CPU percentage: {cpu_percent}%")
        
    except Exception as e:
        raise MetricsError(f"Failed to read CPU percentage: {e}") from e
    
    try:
        # Read RAM percentage (Fuel Level equivalent)
        memory = psutil.virtual_memory()
        ram_percent = memory.percent
        if ram_percent < 0 or ram_percent > 100:
            raise MetricsError(f"Invalid RAM percentage value: {ram_percent}")
        metrics['ram_percent'] = round(ram_percent, 2)
        logger.debug(f"RAM percentage: {ram_percent}%")
        
    except Exception as e:
        raise MetricsError(f"Failed to read RAM percentage: {e}") from e
    
    try:
        # Read Disk percentage (cross-platform root path)
        # On Windows, use the root of the current drive; on Unix-like systems, use '/'
        if os.name == 'nt':  # Windows
            root_path = os.path.splitdrive(os.getcwd())[0] + os.sep
        else:  # Unix-like (Linux, macOS)
            root_path = '/'
        disk = psutil.disk_usage(root_path)
        disk_percent = disk.percent
        if disk_percent < 0 or disk_percent > 100:
            raise MetricsError(f"Invalid disk percentage value: {disk_percent}")
        metrics['disk_percent'] = round(disk_percent, 2)
        logger.debug(f"Disk percentage: {disk_percent}%")
        
    except Exception as e:
        raise MetricsError(f"Failed to read disk percentage: {e}") from e
    
    logger.info(
        f"Metrics read successfully - CPU: {metrics['cpu_percent']}%, "
        f"RAM: {metrics['ram_percent']}%, Disk: {metrics['disk_percent']}%"
    )
    return metrics
