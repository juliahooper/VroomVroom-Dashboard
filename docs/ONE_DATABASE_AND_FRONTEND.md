# One Database for All Sources and Front End

All data from **Device 1 (PC)**, **3rd party (YouTube stream count)**, and **mobile (Firebase)** is stored in the **same SQLite database** (`data/vroomvroom.db`). The front end can read from one place.

---

## 1. Data flow (matches target architecture)

| Source | Collector | How it gets into the DB |
|--------|-----------|-------------------------|
| **Device 1 (PC)** | PC Data Collector | Cron or agent: `POST /snapshots` or `POST /orm/upload_snapshot` → Aggregator API writes to DB. |
| **3rd party (YouTube)** | 3rd Party Data Collector | `src.collectors.third_party_collector.collect_and_upload(api_url)` → same `POST /orm/upload_snapshot` → same DB. |
| **Mobile (Firebase)** | Mobile Data Collector | Uses existing `src.mobile_collector` + `mobile_snapshot_bridge`; `src.collectors.mobile_upload.collect_and_upload(api_url)` → same `POST /orm/upload_snapshot` → same DB. |

There is **one Aggregator API** (Flask) and **one DB**. No separate database per source.

---

## 2. Device IDs in the same DB

- **PC:** `device_id` from config (e.g. `pc-01`).
- **YouTube:** `device_id = "youtube"`.
- **Mobile:** `device_id = "mobile:<location_id>"` (e.g. `mobile:loc_lough_dan`), one per location from Firestore.

Same tables (`device`, `snapshot`, `snapshot_metric`, `metric_type`). Filter by `device_id` to get per-source data.

---

## 3. Metric types (all in one DB)

Seeded in `src/database.py`:

- **PC:** CPU Usage, RAM Usage, Disk Usage (or Running Threads, RAM Usage, Disk Read Speed if you switched).
- **3rd party:** Stream Count.
- **Mobile:** Water Temp, Risk Score, Alerts Count.

All are in `metric_type`; `snapshot_metric` links snapshots to these by `metric_type_id`.

---

## 4. How to run the collectors

**Web app must be running** (e.g. `python -m src.web_app`). Then:

**YouTube (3rd party) – once or on a schedule:**

```bash
# Stub value (no API key):
export VROOMVROOM_YOUTUBE_STREAM_COUNT=42
python -c "
from src.collectors import third_party_collect_and_upload
third_party_collect_and_upload('http://127.0.0.1:5000')
"
```

**Mobile (Firebase):** Uses existing `src.mobile_collector` (config-driven Firestore). Run from project root with mobile enabled in config:

```bash
export GOOGLE_APPLICATION_CREDENTIALS=config/firebase-service-account.json  # if needed
python -c "
from src.collectors import mobile_collect_and_upload
mobile_collect_and_upload('http://127.0.0.1:5000')
"
# Or: python scripts/run_all_collectors.py
```

Add these to cron (or a scheduler) like the PC snapshot so all three sources keep writing to the same DB.

---

## 5. Populating the front end from the one database

Use the **Reporting API** (same Flask app):

- **GET /orm/snapshots?device=pc-01** – PC snapshots.
- **GET /orm/snapshots?device=youtube** – YouTube (stream count) snapshots.
- **GET /orm/snapshots?device=mobile:loc_lough_dan** – Mobile snapshots for a location.
- **GET /orm/snapshots** – All snapshots (optional `limit=`, default 50).
- **GET /orm/devices** – All devices (pc-01, youtube, mobile:loc_..., etc.).
- **GET /orm/snapshots/<id>** – One snapshot with all metrics.

Front end can call these endpoints and combine results (e.g. dashboard with Device 1 metrics, Stream Count, and mobile metrics). All data comes from the single DB behind the Reporting API.
