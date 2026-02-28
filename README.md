# VroomVroom-Dashboard

PoC monitor: reads OS metrics, builds a structured snapshot, and serialises to JSON. Includes a TCP client/server for sending metrics, RAII/BlockTimer, and a Flask web app with REST CRUD and SQLite persistence.

## Requirements

Python packages (see `requirements.txt`): **psutil** (OS metrics), **flask** (web app), **gunicorn** (production WSGI), **sqlalchemy** (ORM). Install once in a venv.

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

## How to run

**Always run from the project root** so `config/config.json` and `logs/` are found.

- **Main app** (read metrics, build snapshot, serialise to JSON):

  ```bash
  python -m src.main
  ```

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

  Then open `http://127.0.0.1:5000/hello`, `/health`, or `/metrics`.

- **Web app — production** (e.g. on VM):

  ```bash
  gunicorn wsgi:application --bind 0.0.0.0:5000 --workers 2
  ```

Optional env: `VROOMVROOM_CONFIG` (config path), `VROOMVROOM_DB` (DB path). Optional: `"sql_echo": true` in config for SQLAlchemy SQL logging.

**Local vs production:** `wsgi.py` and `python -m src.web_app` load config and create the app the same way; gunicorn and the dev server behave identically.

## Network connectivity

The app accepts connections from other machines when bound to `0.0.0.0` (Flask default here; gunicorn use `--bind 0.0.0.0:5000`).

| What | How |
|------|-----|
| HTTP health | `curl http://<host>:5000/health` → 200 |
| REST CRUD (raw SQL) | `curl -X POST http://<host>:5000/snapshots` → 201; `curl http://<host>:5000/snapshots` → list; `curl http://<host>:5000/devices` → devices (paginated) |
| Snapshots (filter/sort/page) | `curl "http://<host>:5000/snapshots?device_id=pc-01&limit=100&offset=0&sort=timestamp_desc"` → `{ "items", "total", "limit", "offset" }` |
| REST CRUD (ORM) | `curl -X POST http://<host>:5000/orm/snapshots` → 201; `curl http://<host>:5000/orm/devices` → 200 |
| Upload snapshot (JSON DTO) | `curl -X POST -H "Content-Type: application/json" -d '{"device_id":"pc-01","timestamp_utc":"2025-02-28T12:00:00Z","metrics":[...]}' http://<host>:5000/orm/upload_snapshot` → 201 |
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

`http://200.69.13.70:5000/hello` · `http://200.69.13.70:5000/health` · `http://200.69.13.70:5000/metrics`

**Terminal tips:** Paste in SSH: Ctrl+Shift+V. Copy: Ctrl+Shift+C.

---

## Architecture and features

- **Flask web app:** `/hello`, `/health`, `/metrics` (cached). REST CRUD in `snapshots.py` and `orm_routes.py`. **Granular API:** GET /devices (sort, limit, offset); GET /snapshots (device_id filter, sort, limit, offset). Responses include `items`, `total`, `limit`, `offset` for pagination awareness. POST /orm/upload_snapshot accepts JSON DTO, validates, persists, returns structured JSON.
- **Data model (four layers):** Database (normalized tables), ORM (`orm_models.py`), server domain (`datasnapshot/models.py`, `snapshots.py` view types), DTO (wire JSON). Timestamps UTC ISO 8601. See `docs/DATA_MODEL.md`.
- **SQLite:** Normalised schema in `src/database.py`. Indexes on FKs and timestamp. Multi-step writes use `TransactionManager`. See `docs/SCHEMA_DESIGN.md`.
- **ORM:** SQLAlchemy models in `orm_models.py`; relationships and eager loading (joinedload/selectinload) in `orm_routes.py`.
- **TCP client/server:** Length-prefixed JSON messages (`src.protocol`). Server buffers and parses; client sends one snapshot per run. Config: `server_host`, `server_port`.
- **Config:** `config/config.json` (device_id, thresholds, log level, TCP host/port). Optional `sql_echo` for SQL logging. Env overrides: `VROOMVROOM_CONFIG`, `VROOMVROOM_DB`.
- **RAII / BlockTimer:** Sockets and timing in `tcp_client`, `web_app` metrics handler; `src/blocktimer/` for block timing.

## Project layout

```
VroomVroom-Dashboard/
├── config/config.json
├── requirements.txt
├── wsgi.py                    # Gunicorn entry point
├── docs/
│   ├── DATA_MODEL.md          # Four layers: DB, ORM, domain, DTO; UTC & UUID
│   ├── EXECUTION_ORDER.md
│   └── SCHEMA_DESIGN.md
├── src/
│   ├── main.py                # CLI, metrics pipeline
│   ├── web_app.py             # Flask app, routes, /hello, /health, /metrics
│   ├── database.py             # SQLite schema, get_db(), init_db(), TransactionManager
│   ├── snapshots.py           # Raw SQL CRUD (snapshots, devices)
│   ├── orm_models.py          # SQLAlchemy models
│   ├── orm_dto.py             # ORM ↔ DTO mapping (to_dict/from_dict, datetime/UUID)
│   ├── orm_routes.py          # ORM endpoints (/orm/snapshots, /orm/devices)
│   ├── metrics_cache.py       # TTL cache for /metrics
│   ├── metrics_reader.py      # psutil CPU/RAM/disk
│   ├── protocol.py            # Length-prefixed TCP messages
│   ├── tcp_server.py
│   ├── tcp_client.py
│   ├── blocktimer/
│   ├── configlib/
│   └── datasnapshot/
├── data/                      # vroomvroom.db (created at runtime)
├── scripts/
│   ├── verify_indexes.py
│   └── performance_scan_vs_search.py
├── logs/
└── README.md
```
