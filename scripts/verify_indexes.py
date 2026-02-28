#!/usr/bin/env python3
"""
Verify index usage and compare query times (Step 1 – indexing).

Run from project root: python scripts/verify_indexes.py [--iterations N]
Uses VROOMVROOM_DB or data/vroomvroom.db. Ensures database and indexes exist via init_db().

For each representative query:
  1. Prints EXPLAIN QUERY PLAN so you can confirm indexes are used (e.g. SEARCH ... USING INDEX).
  2. Runs the query N times and reports total and mean time in milliseconds.

Compare runs: with indexes (default after init_db) vs without (temporarily drop indexes) to see improvement.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

# Project root on sys.path so we can import src
_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from src.database import get_db, init_db


def run_explain(conn, name: str, sql: str, params: tuple = ()) -> None:
    """Run EXPLAIN QUERY PLAN and print lines with 'SEARCH' or 'SCAN' to show index usage."""
    cursor = conn.execute(f"EXPLAIN QUERY PLAN {sql}", params)
    rows = cursor.fetchall()
    print(f"  [{name}] EXPLAIN QUERY PLAN:")
    for row in rows:
        line = " ".join(str(c) for c in row)
        print(f"    {line}")
    print()


def run_timed(conn, sql: str, params: tuple = (), iterations: int = 100) -> tuple[float, float]:
    """Execute query N times; return (total_ms, mean_ms)."""
    conn.execute(sql, params)
    conn.execute(sql, params)  # warm-up
    start = time.perf_counter()
    for _ in range(iterations):
        conn.execute(sql, params).fetchall()
    total_ms = (time.perf_counter() - start) * 1000
    return total_ms, total_ms / iterations


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify indexes: EXPLAIN QUERY PLAN + query timing.")
    parser.add_argument(
        "--iterations", "-n", type=int, default=200,
        help="Number of times to run each query for timing (default 200)",
    )
    args = parser.parse_args()
    n = args.iterations

    # Ensure DB and indexes exist
    init_db()

    with get_db() as conn:
        print("=== EXPLAIN QUERY PLAN (check for USING INDEX / SEARCH) ===\n")

        # 1. List snapshots (JOIN device + LEFT JOIN snapshot_metric, GROUP BY, ORDER BY)
        q_list = """
            SELECT s.id, d.device_id, s.timestamp_utc, COUNT(sm.metric_type_id) AS metric_count
            FROM   snapshot s
            JOIN   device d ON d.id = s.device_id
            LEFT JOIN snapshot_metric sm ON sm.snapshot_id = s.id
            GROUP  BY s.id
            ORDER  BY s.id DESC
        """
        run_explain(conn, "GET /snapshots (list)", q_list.strip())

        # 2. Get snapshot by id (JOIN device, LEFT JOIN snapshot_metric + metric_type, WHERE s.id = ?)
        q_detail = """
            SELECT s.id AS snap_id, d.device_id, s.timestamp_utc,
                   mt.name AS metric_name, mt.unit AS metric_unit, sm.value, sm.status
            FROM   snapshot s
            JOIN   device d ON d.id = s.device_id
            LEFT JOIN snapshot_metric sm ON sm.snapshot_id = s.id
            LEFT JOIN metric_type mt ON mt.id = sm.metric_type_id
            WHERE  s.id = ?
            ORDER  BY mt.name
        """
        # Use a likely id (1) for EXPLAIN; planner doesn't depend on value
        run_explain(conn, "GET /snapshots/<id> (detail)", q_detail.strip(), (1,))

        # 3. Lookup device by device_id (used in POST /snapshots and ORM filter)
        q_device = "SELECT id FROM device WHERE device_id = ?"
        run_explain(conn, "Device lookup by device_id", q_device, ("pc-01",))

        # 4. Filter snapshot by device_id (e.g. ?device= in list)
        q_by_device = """
            SELECT s.id, d.device_id, s.timestamp_utc, COUNT(sm.metric_type_id)
            FROM   snapshot s
            JOIN   device d ON d.id = s.device_id
            LEFT JOIN snapshot_metric sm ON sm.snapshot_id = s.id
            WHERE  d.device_id = ?
            GROUP  BY s.id
            ORDER  BY s.id DESC
        """
        run_explain(conn, "List snapshots by device_id", q_by_device.strip(), ("pc-01",))

        print("=== Query timing (ms) ===\n")

        # Get a valid snapshot id for detail query
        row = conn.execute("SELECT id FROM snapshot ORDER BY id DESC LIMIT 1").fetchone()
        snap_id = row["id"] if row else 1
        device_id = "pc-01"

        total_list, mean_list = run_timed(conn, q_list.strip(), (), n)
        total_detail, mean_detail = run_timed(conn, q_detail.strip(), (snap_id,), n)
        total_device, mean_device = run_timed(conn, q_device, (device_id,), n)
        total_by_device, mean_by_device = run_timed(conn, q_by_device.strip(), (device_id,), n)

        print(f"  List snapshots (JOIN+GROUP+ORDER)     total={total_list:.2f} ms  mean={mean_list:.4f} ms  (n={n})")
        print(f"  Get snapshot by id (JOIN+WHERE)      total={total_detail:.2f} ms  mean={mean_detail:.4f} ms  (n={n})")
        print(f"  Device lookup by device_id           total={total_device:.2f} ms  mean={mean_device:.4f} ms  (n={n})")
        print(f"  List by device_id (WHERE+GROUP)     total={total_by_device:.2f} ms  mean={mean_by_device:.4f} ms  (n={n})")
        print()
        print("To compare: run once with indexes (default), then drop indexes and run again to see slowdown.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
