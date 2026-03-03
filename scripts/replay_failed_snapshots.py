"""
Replay failed snapshots from data/failed_snapshots.jsonl into the DB.
Run with web app stopped or from a separate process; uses ORM to persist.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.orm_dto import snapshot_from_dto
from src.orm_models import get_session
from src.snapshot_backup import FAILED_FILE


def main() -> int:
    if not FAILED_FILE.exists():
        print("No failed_snapshots.jsonl found. Nothing to replay.")
        return 0
    replayed = 0
    remaining_lines = []
    with open(FAILED_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
                dto = record.get("dto")
                if not dto:
                    remaining_lines.append(line)
                    continue
                with get_session() as session:
                    snapshot_from_dto(dto, session)
                replayed += 1
            except Exception as e:
                print(f"Replay error: {e}", file=sys.stderr)
                remaining_lines.append(line)
    FAILED_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(FAILED_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(remaining_lines) + ("\n" if remaining_lines else ""))
    print(f"Replayed {replayed} snapshot(s). {len(remaining_lines)} line(s) left in {FAILED_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
