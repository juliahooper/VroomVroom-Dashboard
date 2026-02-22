"""
blocktimer – RAII-style timing for code blocks.

Exposes BlockTimer for use as:  with BlockTimer("label"): ... do work ...
"""
from .timer import BlockTimer

__all__ = ["BlockTimer"]
