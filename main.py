"""
Launcher so 'python main.py' works from the project root.
Delegates to src.main.
"""
import sys
from pathlib import Path

# Ensure src is on path when running from repo root
_root = Path(__file__).resolve().parent
_src = _root / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from main import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
