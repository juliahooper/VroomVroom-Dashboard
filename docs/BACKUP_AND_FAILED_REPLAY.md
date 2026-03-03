# Snapshot backup and failed-snapshot protection

Lightweight data protection without a separate queue server: append-only logs and retries.

---

## 1. What’s in place

| Mechanism | Purpose |
|-----------|--------|
| **Success backup** | Every snapshot that is successfully written to the DB is appended to `data/snapshot_backup.jsonl` (one JSON object per line). Gives a chronological backup you can use to restore or audit. |
| **Retry on persist** | When `POST /orm/upload_snapshot` fails to write to the DB, the request is retried up to 3 times with a short delay. Reduces loss from transient DB lock or I/O errors. |
| **Failed log** | If all retries fail, the snapshot DTO (and error) is appended to `data/failed_snapshots.jsonl`. Data is not dropped; it can be replayed later. |
| **Replay script** | `python scripts/replay_failed_snapshots.py` reads `failed_snapshots.jsonl`, persists each DTO to the DB, and removes successfully replayed lines from the file. |

---

## 2. Files (under `data/`)

- **`snapshot_backup.jsonl`** – One JSON line per successfully stored snapshot (full DTO). Append-only; not cleared by the app.
- **`failed_snapshots.jsonl`** – One JSON line per failed attempt: `{"dto": {...}, "error": "...", "ts": "..."}`. Cleared only by the replay script for lines that were replayed.

---

## 3. Replaying failed snapshots

With the app running (or stopped, if you prefer to avoid load):

```bash
cd /path/to/VroomVroom-Dashboard
python scripts/replay_failed_snapshots.py
```

The script persists each `dto` in `failed_snapshots.jsonl` into the DB and overwrites the file with only the lines that still fail (if any). You can run it on a schedule (e.g. cron) or after fixing DB/disk issues.

---

## 4. No separate queue

There is no Redis, RabbitMQ, or in-process queue. Collectors POST directly to the API. Protection is:

- **Retries** – Transient failures are retried.
- **Backup log** – Successful writes are logged to disk.
- **Failed log** – Persistent failures are logged and can be replayed.

This keeps the system simple while still covering basic backup and “don’t lose data on failure” behaviour.

---

## 5. Concurrent writes (no queue)

When PC, YouTube, and mobile all POST at once:

- **Per-process serialization:** The ORM upload path holds a single lock per Flask process so only one `upload_snapshot` persist runs at a time. Concurrent POSTs to `/orm/upload_snapshot` wait for the lock, then run one after the other. No queue server; just a short in-process wait.
- **SQLite timeout:** Both the ORM engine and the raw SQL `get_db()` use a **15 second** busy timeout. If the DB is locked (e.g. another thread or the raw SQL path is writing), the waiting connection waits up to 15 seconds instead of failing immediately with `SQLITE_BUSY`. After that it fails and our retry + failed log applies.
- **Result:** Writes are serialized (one at a time per process, or by SQLite when both ORM and raw paths are used). No corruption; requests may take a bit longer under load but succeed, or after retries they are logged to `failed_snapshots.jsonl` for replay.
