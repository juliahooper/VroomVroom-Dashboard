#!/usr/bin/env python3
"""
Step 2 – Performance testing: full table scan vs B-tree index search.

Demonstrates:
  • Query WITHOUT index → full table scan (SCAN) — O(n) rows examined.
  • Query WITH index    → B-tree search (SEARCH) — O(log n) lookups.
Measures execution time using BlockTimer, logs the difference, and explains
O(n) vs O(log n) behaviour.

Run from project root: python scripts/performance_scan_vs_search.py [--iterations N]
Uses VROOMVROOM_DB or data/vroomvroom.db. Leaves DB with indexes restored.
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

# Project root on sys.path so we can import src
_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from src.blocktimer import BlockTimer
from src.database import get_db, init_db

# Configure logging so BlockTimer messages are visible
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Query used for both scenarios: lookup snapshots by device (FK).
# With idx_snapshot_device_id: SEARCH using index (B-tree). Without: SCAN snapshot.
QUERY_BY_DEVICE = "SELECT id, device_id, timestamp_utc FROM snapshot WHERE device_id = ?"
INDEX_NAME = "idx_snapshot_device_id"


def run_explain(conn, sql: str, params: tuple, label: str) -> None:
    """Print EXPLAIN QUERY PLAN so user sees SCAN vs SEARCH."""
    cursor = conn.execute(f"EXPLAIN QUERY PLAN {sql}", params)
    rows = cursor.fetchall()
    print(f"  {label}:")
    for row in rows:
        line = " ".join(str(c) for c in row)
        print(f"    {line}")
    print()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Step 2: Compare full table scan vs index search using BlockTimer.",
    )
    parser.add_argument(
        "--iterations", "-n", type=int, default=500,
        help="Number of query executions per scenario (default 500)",
    )
    args = parser.parse_args()
    n = args.iterations

    init_db()

    with get_db() as conn:
        # Resolve a valid device_id (FK) to use in WHERE
        row = conn.execute("SELECT id FROM device WHERE device_id = ?", ("pc-01",)).fetchone()
        if not row:
            conn.execute("INSERT OR IGNORE INTO device (device_id) VALUES (?)", ("pc-01",))
            row = conn.execute("SELECT id FROM device WHERE device_id = ?", ("pc-01",)).fetchone()
        device_pk = row["id"]
        count_snapshots = conn.execute("SELECT COUNT(*) FROM snapshot").fetchone()[0]
        logger.info("Snapshot table row count: %d (device_id=%s used for WHERE)", count_snapshots, device_pk)

        print("=== EXPLAIN QUERY PLAN (scan vs search) ===\n")

        # 1) With index: B-tree search
        run_explain(conn, QUERY_BY_DEVICE, (device_pk,), "With index (B-tree SEARCH)")

        # 2) Drop index so the same query becomes a full table scan
        conn.execute(f"DROP INDEX IF EXISTS {INDEX_NAME}")
        conn.commit()

    # Fresh connection so planner sees schema without index; EXPLAIN shows SCAN
    with get_db() as conn2:
        run_explain(conn2, QUERY_BY_DEVICE, (device_pk,), "Without index (full table SCAN)")

        # 3) Restore index for the timed runs (we want to measure “with index” first, then “without”)
        print("=== Execution time (BlockTimer) ===\n")

        # Scenario A: WITHOUT index — full table scan, O(n) (index already dropped)
        start = time.perf_counter()
        with BlockTimer("query_without_index_full_table_scan", log_level=logging.INFO):
            for _ in range(n):
                conn2.execute(QUERY_BY_DEVICE, (device_pk,)).fetchall()
        elapsed_without = time.perf_counter() - start

        # Scenario B: WITH index — B-tree search, O(log n). Restore index then time.
        conn2.execute("""
            CREATE INDEX IF NOT EXISTS idx_snapshot_device_id ON snapshot(device_id)
        """)
        conn2.commit()

        start = time.perf_counter()
        with BlockTimer("query_with_index_B_tree_search", log_level=logging.INFO):
            for _ in range(n):
                conn2.execute(QUERY_BY_DEVICE, (device_pk,)).fetchall()
        elapsed_with = time.perf_counter() - start

        # Log performance difference and O(n) vs O(log n)
        ratio = elapsed_without / elapsed_with if elapsed_with > 0 else 0
        print()
        print("=== Performance difference and O(n) vs O(log n) ===\n")
        logger.info(
            "Total time (n=%d runs): WITH index=%.4f s, WITHOUT index=%.4f s → ratio %.2fx",
            n, elapsed_with, elapsed_without, ratio,
        )
        print("""
  • WITH index (B-tree SEARCH): SQLite uses idx_snapshot_device_id to find rows by device_id.
    Cost is O(log n) in the index: each step halves the search space. Only matching rows are read.

  • WITHOUT index (full table SCAN): SQLite scans the entire snapshot table row by row.
    Cost is O(n): every row is examined, so time grows linearly with table size.

  As the snapshot table grows, full-table-scan time grows roughly linearly with row count;
  index lookup time grows only logarithmically. The ratio you see above illustrates why
  indexing foreign keys and filtered columns matters for performance.

  (With a small table the ratio may be ≤1 because scan overhead is tiny; add more rows
  via POST /snapshots to see the scan get slower relative to index search.)
""")


if __name__ == "__main__":
    sys.exit(main())
