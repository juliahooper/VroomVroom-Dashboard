"""
Main entry point for the application.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from config import ConfigError, load_config

def main():
    """Main function."""
    config_path = os.environ.get("VROOMVROOM_CONFIG", str(Path("config") / "config.json"))
    try:
        _ = load_config(config_path)
    except ConfigError as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        return 2
    return 0

if __name__ == '__main__':
    sys.exit(main())
