# VroomVroom-Dashboard

PoC monitor: reads OS metrics, builds a structured snapshot, and serialises to JSON. Includes a TCP client/server for sending metrics, RAII/BlockTimer, and a Flask web app with REST CRUD and SQLite persistence.

## Requirements

Python packages (see `requirements.txt`): **psutil** (OS metrics), **flask** (web app), **gunicorn** (production WSGI), **sqlalchemy** (ORM), **requests** (YouTube API), **python-dotenv** (.env loading). Install once in a venv.

## Setup

1. **Python** — [python.org](https://www.python.org/downloads/) or `winget install Python.Python.3.12`.

2. **Virtual environment** (once, from project root):

   ```bash
   cd VroomVroom-Dashboard
   python -m venv venv
   ```

   Activate (each new terminal): **Windows** `venv\Scripts\activate` · **Linux/macOS** `source venv/bin/activate`. Prompt shows `(venv)`.

3. **Dependencies:**

   ```bash
   pip install -r requirements.txt
   ```

4. **Configuring the YouTube API (.env)** — required only if you use `/youtube/vroom-vroom`:

   - In the project root there is a file **`.env.example`**. Copy it to a new file named **`.env`** (same folder as `.env.example`).
   - One teammate with access to the YouTube Data API v3 key should share it securely (e.g. team chat or password manager). Each developer then pastes the key into their own **`.env`** file:
     ```bash
     # .env (do not commit this file — it is in .gitignore)
     YOUTUBE_API_KEY=your_actual_key_here
     ```
   - The app loads `.env` automatically when you run `python -m src.web_app` or `gunicorn wsgi:application`, so you do **not** need to set `YOUTUBE_API_KEY` in the terminal each time.
   - **Important:** Never commit `.env` or put the real key in `.env.example`. The repo already ignores `.env`; only the variable names live in `.env.example` for reference.

## How to run

**Always run from the project root** so `config/config.json` and `logs/` are found.

- **Main app** (read metrics, build snapshot, serialise to JSON):

  ```bash
  python -m src.main
  ```

- **Collector agent** (long-running: read metrics every N seconds, upload to API). Start-based scheduling (no drift); retry on upload failure; graceful shutdown on Ctrl+C or SIGTERM:

  ```bash
  python -m src.main --agent
  ```
  Optional: `--interval 30` (default: `read_interval_seconds` from config). Set `VROOMVROOM_API_URL` (default `http://127.0.0.1:5000`) if the API is elsewhere. Run the web app first so `/orm/upload_snapshot` is available.

- **TCP server** (listens for metric data; start first):

  ```bash
  python -m src.tcp_server
  ```

  Listens on port in config (default 54545). Stop with Ctrl+C.

- **TCP client** (sends one JSON snapshot to the server):

  ```bash
  python -m src.tcp_client
  ```

  Connects to `server_host` and `server_port` in config. Start the server in another terminal first.

- **Web app — development:**

  ```bash
  python -m src.web_app
  ```

  Then open `http://127.0.0.1:5000/hello`, `/health`, `/metrics`, or `/youtube/vroom-vroom`.

- **Web app — production** (e.g. on VM):

  ```bash
  gunicorn wsgi:application --bind 0.0.0.0:5000 --workers 2
  ```

Optional env: `VROOMVROOM_CONFIG` (config path), `VROOMVROOM_DB` (DB path). Optional: `"sql_echo": true` in config for SQLAlchemy SQL logging. For **YouTube Vroom Vroom**: use a `.env` file (see “Configuring the YouTube API (.env)” above); you can also set `YOUTUBE_API_KEY` or `YOUTUBE_VIDEO_ID` in the shell if you prefer.

**Local vs production:** `wsgi.py` and `python -m src.web_app` load config and create the app the same way; gunicorn and the dev server behave identically.

## Mobile data (Firestore)

Metrics can be pulled from a Firestore backend (e.g. SwimScape) with **no hardcoded collection or field names**. Everything is driven by the optional `mobile` section in `config/config.json`. New services, devices, and metrics can be added by editing config only. Mobile data is also exposed as a **unified snapshot** (same `device_id` / `timestamp_utc` / `metrics` shape as PC snapshots) so the rest of CoC and dashboards can consume one format for all sources.

### Enabling and configuring

1. In `config/config.json`, add or edit the `mobile` block (see example below). Set `"enabled": true` when you want to use Firestore.
2. **Credentials (Python backend):** Place your Firebase service account JSON file somewhere readable (e.g. `config/firebase-service-account.json`). Set either:
   - `mobile.firebase_credentials_path` in config (e.g. `"config/firebase-service-account.json"`), or
   - the environment variable `GOOGLE_APPLICATION_CREDENTIALS` to that file path.
3. **Collections:** Under `mobile.collections`, map logical keys to exact Firestore collection names. Use the names as they appear in the Firebase console (e.g. `water_temp` → `"water_temperature_readings"` if that is the full name).
4. **Time-series metrics:** Each entry in `mobile.time_series_sources` defines one metric: `metric_id`, `collection_key` (must match a key in `collections`), `location_field`, `timestamp_field`, `value_fields` (array of field names to expose), and optional `limit`.
5. **Count metrics:** Each entry in `mobile.count_sources` defines a count per location: `metric_id`, `collection_key`, `location_field`. Count is all-time unless you extend the collector later.

To add a new time-series or count metric, add another object to `time_series_sources` or `count_sources` and ensure the referenced collection exists in `collections`. No code changes are required.

### Endpoints (when mobile is enabled)

| Endpoint | Description |
|----------|-------------|
| `GET /mobile/locations` | List locations (id, name, county). |
| `GET /mobile/metrics/latest?locationId=loc_lough_dan` | Latest time-series point, count metrics, and a **unified snapshot** (same shape as PC `/metrics`). |
| `GET /mobile/metrics/history?locationId=loc_lough_dan&metricId=water_readings` | Time-series points for graphing (timestamp_millis, values). |
| `GET /mobile/snapshot?locationId=loc_lough_dan` | **Unified snapshot only**: `device_id`, `timestamp_utc`, `metrics` (same as PC snapshots; `device_id` is `mobile:&lt;locationId&gt;`). Use this when the dashboard consumes one format for all sources. |

### Firestore indexes

If you see an error that a composite index is required, create it in the Firebase console (Firestore → Indexes). Typical indexes:

- **Time-series query** (location + timestamp): collection = your time-series collection, fields: `location_field` (Ascending), `timestamp_field` (Ascending).
- **Count query** (location only): no composite index needed for a single `where`; if you add ordering later, add an index with `location_field` and the order field.

The error message in the logs will state the required fields; add those to the README for your project if needed.

## Network connectivity

The app accepts connections from other machines when bound to `0.0.0.0` (Flask default here; gunicorn use `--bind 0.0.0.0:5000`).

| What | How |
|------|-----|
| HTTP health | `curl http://<host>:5000/health` → 200 |
| REST CRUD (raw SQL) | `curl -X POST http://<host>:5000/snapshots` → 201; `curl http://<host>:5000/snapshots` → list; `curl http://<host>:5000/devices` → devices (paginated) |
| Snapshots (filter/sort/page) | `curl "http://<host>:5000/snapshots?device_id=pc-01&limit=100&offset=0&sort=timestamp_desc"` → `{ "items", "total", "limit", "offset" }` |
| REST CRUD (ORM) | `curl -X POST http://<host>:5000/orm/snapshots` → 201; `curl http://<host>:5000/orm/devices` → 200 |
| Upload snapshot (JSON DTO) | `curl -X POST -H "Content-Type: application/json" -d '{"device_id":"pc-01","timestamp_utc":"2025-02-28T12:00:00Z","metrics":[...]}' http://<host>:5000/orm/upload_snapshot` → 201 |
| YouTube Vroom Vroom (on-demand) | Configure `.env` with `YOUTUBE_API_KEY` (see Setup); `curl http://<host>:5000/youtube/vroom-vroom` → 200 with `timestamp_utc`, `total_streams`, `metrics` (and stores a snapshot) |
| TCP | Start `python -m src.tcp_server`, then `python -m src.tcp_client` (uses config for host/port) |

**Troubleshooting:** `curl -v http://<host>:5000/health` — connection refused means nothing listening or firewall. Server must listen on `0.0.0.0` for external access. On VM: `sudo ufw allow 5000/tcp` then `sudo ufw reload` if needed.

## Deploying to the VM

### VM details

- **IP:** 200.69.13.70  
- **User:** student  
- **SSH port:** 2210  
- **Key file:** `C:\Users\user\.ssh\juliapk`

### Connect (from your PC)

```bash
ssh -i "C:\Users\user\.ssh\juliapk" -p 2210 student@200.69.13.70
```

### First-time setup (on VM, once)

```bash
cd VroomVroom-Dashboard
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
sudo ufw allow 5000/tcp
```

### Build the dashboard (on VM, after pulling frontend changes)

Flask serves the built React app at `/dashboard/` if `frontend/dist` exists. Build it on the VM (requires Node.js):

```bash
cd frontend
npm install
npm run build
cd ..
```

If Node.js is not installed: `sudo apt install nodejs npm` (or use nvm).

### Run the web server

**Development:** `python -m src.web_app`

**Production (recommended):** `gunicorn wsgi:application --bind 0.0.0.0:5000 --workers 2`

### Keep running after logout (tmux)

```bash
cd VroomVroom-Dashboard
source venv/bin/activate
tmux new -s vroomvroom
gunicorn wsgi:application --bind 0.0.0.0:5000 --workers 2
```

Press **Ctrl+B then D** to detach. Reconnect: `tmux attach -t vroomvroom`.

### Test in browser

- **API:** `http://200.69.13.70:5000/hello` · `http://200.69.13.70:5000/health` · `http://200.69.13.70:5000/metrics`
- **Dashboard (gauges, charts):** `http://200.69.13.70:5000/dashboard/` (requires `frontend/dist` to exist; run `npm run build` in `frontend/` first)
- **YouTube:** `http://200.69.13.70:5000/youtube/vroom-vroom` (requires `YOUTUBE_API_KEY` on the server)

**Terminal tips:** Paste in SSH: Ctrl+Shift+V. Copy: Ctrl+Shift+C.

---

## Architecture and features

- **Flask web app:** `/hello`, `/health`, `/metrics` (cached), `/youtube/vroom-vroom` (on-demand: fetch view count, store snapshot, return JSON). REST CRUD in `snapshots.py` and `orm_routes.py`. **Granular API:** GET /devices (sort, limit, offset); GET /snapshots (device_id filter, sort, limit, offset). POST /orm/upload_snapshot accepts JSON DTO, validates, persists. API design (bulk vs granular, versioning, security, client/server trade-offs): `docs/API_DESIGN.md`.
- **Data model (four layers):** Database (normalized tables), ORM (`orm_models.py`), server domain (`datasnapshot/models.py`, `snapshots.py` view types), DTO (wire JSON). Timestamps UTC ISO 8601. See `docs/DATA_MODEL.md`.
- **SQLite:** Normalised schema in `src/database.py`. Indexes on FKs and timestamp. Multi-step writes use `TransactionManager`. See `docs/SCHEMA_DESIGN.md`.
- **ORM:** SQLAlchemy models in `orm_models.py`; relationships and eager loading (joinedload/selectinload) in `orm_routes.py`.
- **TCP client/server:** Length-prefixed JSON messages (`src.protocol`). Server buffers and parses; client sends one snapshot per run. Config: `server_host`, `server_port`.
- **Config:** `config/config.json` (device_id, thresholds, log level, TCP host/port). Optional `sql_echo` for SQL logging. Env overrides: `VROOMVROOM_CONFIG`, `VROOMVROOM_DB`.
- **RAII / BlockTimer:** Sockets and timing in `tcp_client`, `web_app` metrics handler; `src/blocktimer/` for block timing.

## Project layout

```
VroomVroom-Dashboard/
├── config/
│   └── config.json
├── .env.example               # Copy to .env and add YOUTUBE_API_KEY (see Setup)
├── requirements.txt
├── wsgi.py                    # Gunicorn entry point
├── docs/
│   ├── README.md              # Docs index
│   ├── API_DESIGN.md
│   ├── BACKUP_AND_FAILED_REPLAY.md   # Backup log, retries, concurrent writes, replay script
│   ├── DATA_MODEL.md
│   ├── EXECUTION_ORDER.md
│   ├── ONE_DATABASE_AND_FRONTEND.md   # One DB for PC, YouTube, mobile; front-end APIs
│   └── SCHEMA_DESIGN.md
├── src/
│   ├── main.py                # CLI (-c, -a/--agent, -i/--interval)
│   ├── web_app.py             # Flask app, routes, /hello, /health, /metrics, /youtube/vroom-vroom
│   ├── collector_agent.py     # Long-running PC collector: loop, upload API, retry
│   ├── database.py            # SQLite schema, get_db(), init_db(), TransactionManager
│   ├── snapshots.py            # Raw SQL CRUD (snapshots, devices)
│   ├── orm_models.py          # SQLAlchemy models
│   ├── orm_dto.py             # ORM ↔ DTO mapping
│   ├── orm_routes.py          # ORM endpoints, POST /orm/upload_snapshot (retry, backup, lock)
│   ├── snapshot_backup.py     # Append-only backup + failed log (no queue server)
│   ├── metrics_reader.py
│   ├── metrics_cache.py
│   ├── protocol.py            # Length-prefixed TCP messages
│   ├── raii.py
│   ├── tcp_server.py
│   ├── tcp_client.py
│   ├── youtube_fetcher.py     # YouTube Data API v3 (YOUTUBE_API_KEY)
│   ├── mobile_models.py       # Mobile/Firestore data types
│   ├── mobile_collector.py    # Firestore reader (config-driven)
│   ├── mobile_routes.py       # GET /mobile/locations, /mobile/snapshot, etc.
│   ├── mobile_snapshot_bridge.py   # Mobile → unified Snapshot shape
│   ├── blocktimer/
│   ├── configlib/             # Config + logging
│   ├── datasnapshot/          # Snapshot domain model + JSON
│   └── collectors/            # 3rd party + mobile upload to same API
│       ├── _upload.py
│       ├── third_party_collector.py   # YouTube stream count
│       └── mobile_upload.py   # Mobile (Firestore) → POST /orm/upload_snapshot
├── data/                      # vroomvroom.db, snapshot_backup.jsonl, failed_snapshots.jsonl (runtime)
├── scripts/
│   ├── run_all_collectors.py  # Run YouTube + mobile collectors once (web app must be up)
│   ├── replay_failed_snapshots.py    # Replay data/failed_snapshots.jsonl into DB
│   ├── verify_indexes.py
│   └── performance_scan_vs_search.py
├── logs/
└── README.md
```

### Scripts (run from project root)

| Script | Purpose |
|--------|--------|
| `python scripts/run_all_collectors.py` | Run 3rd party (YouTube) and mobile (Firebase) collectors once; web app must be running. |
| `python scripts/replay_failed_snapshots.py` | Replay `data/failed_snapshots.jsonl` into the DB after fixing transient failures. See `docs/BACKUP_AND_FAILED_REPLAY.md`. |
| `python scripts/verify_indexes.py` | Ensure DB and indexes exist (init_db). |
| `python scripts/performance_scan_vs_search.py` | Index vs search performance check; leaves DB with indexes restored. |

**Docs:** See `docs/README.md` for an index of all design and runbook docs.
