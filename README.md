# VroomVroom-Dashboard

PoC monitor: reads OS metrics, builds a structured snapshot, and serialises to JSON. Includes a TCP client/server for sending metrics, RAII/BlockTimer, and a Flask web app (/hello, /health, /metrics).

## Requirements

Python packages (see `requirements.txt`): **psutil** (OS metrics), **flask** (web app), **gunicorn** (production WSGI), **sqlalchemy** (ORM). Install once in a venv so the app can run locally and on the VM.

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

   After adding packages: `pip freeze > requirements.txt` so the VM stays in sync.

## How to run

**Always run from the project root** (`VroomVroom-Dashboard`) so `config/config.json` and `logs/` are found.

- **Main app** (read metrics, build snapshot, serialise to JSON, verify round-trip):

  ```bash
  python -m src.main
  ```

- **TCP server** (listens for metric data; start this first):

  ```bash
  python -m src.tcp_server
  ```

  Listens on the port in config (default 54545). Stop with Ctrl+C.

- **TCP client** (sends one JSON metric snapshot to the server):

  ```bash
  python -m src.tcp_client
  ```

  Connects to `server_host` and `server_port` in config (default 127.0.0.1:54545). Start the server in another terminal first.

- **Web app — development** (Flask dev server, local only):

  ```bash
  python -m src.web_app
  ```

  Then open: `http://127.0.0.1:5000/hello`, `/health`, or `/metrics`.

- **Web app — production** (gunicorn, e.g. on VM):

  ```bash
  gunicorn wsgi:application --bind 0.0.0.0:5000 --workers 2
  ```

Optional: `VROOMVROOM_CONFIG` for config path; `VROOMVROOM_DB` for DB path.

**Local vs production:** `wsgi.py` loads config, logging, and `create_app()` the same way as `python -m src.web_app`, so gunicorn and the dev server behave identically.

## Network connectivity

The app is **network-reachable** when run with `--bind 0.0.0.0` (gunicorn) or when the Flask dev server listens on `0.0.0.0` (default in this project), so it accepts requests from other machines, not only localhost.

**How to test connectivity:**

| What | How |
|------|-----|
| HTTP health | `curl http://<host>:5000/health` → `OK` and 200 |
| REST CRUD (raw SQL) | `curl -X POST http://<host>:5000/snapshots` → 201 and snapshot id; `curl http://<host>:5000/snapshots` → 200 and list |
| REST CRUD (ORM) | `curl -X POST http://<host>:5000/orm/snapshots` → 201; `curl http://<host>:5000/orm/devices` → 200 |
| TCP metrics | Start `python -m src.tcp_server`, then `python -m src.tcp_client`; client uses `server_host` and `server_port` from config |

From another machine, use the VM IP (e.g. `http://200.69.13.70:5000/health`) instead of `127.0.0.1`.

## Deploying to the VM

### VM details
- **IP:** 200.69.13.70
- **User:** student
- **SSH port:** 2210
- **Key file:** `C:\Users\user\.ssh\juliapk`

### Step 1 — Connect to the VM (run on your PC)

```bash
ssh -i "C:\Users\user\.ssh\juliapk" -p 2210 student@200.69.13.70
```

### Step 2 — First time setup (only needed once, on the VM)

```bash
cd VroomVroom-Dashboard
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
sudo ufw allow 5000/tcp
```

### Step 3 — Run the web server

**Development (Flask):**
```bash
cd VroomVroom-Dashboard
source venv/bin/activate
python -m src.web_app
```

**Production (gunicorn — recommended on VM):**
```bash
cd VroomVroom-Dashboard
source venv/bin/activate
gunicorn wsgi:application --bind 0.0.0.0:5000 --workers 2
```

### Step 4 — Keep it running after logout (tmux)

```bash
cd VroomVroom-Dashboard
source venv/bin/activate
tmux new -s vroomvroom
gunicorn wsgi:application --bind 0.0.0.0:5000 --workers 2
```

Press **Ctrl+B then D** to detach. To reconnect: `tmux attach -t vroomvroom`

### Step 5 — Update code on the VM (after pushing from PC)

```bash
cd VroomVroom-Dashboard
git pull
source venv/bin/activate
gunicorn wsgi:application --bind 0.0.0.0:5000 --workers 2
```

### Step 6 — Test in browser

```
http://200.69.13.70:5000/hello
http://200.69.13.70:5000/health
http://200.69.13.70:5000/metrics
```

### Terminal tips
- **Paste in SSH terminal:** Ctrl+Shift+V
- **Copy in SSH terminal:** Ctrl+Shift+C

---

## PoC 4.0 Definition of Done – checklist

| Criterion | How it is met | How to verify |
|-----------|----------------|---------------|
| **REST endpoints persist data in SQLite** | POST/GET/PUT/DELETE in `snapshots.py` and `orm_routes.py` use `get_db()` / `get_session()` and write to `data/vroomvroom.db`. | Run app, `curl -X POST http://127.0.0.1:5000/snapshots`, then `curl http://127.0.0.1:5000/snapshots` — list includes new snapshot. |
| **CRUD operations function correctly** | Create: POST /snapshots, POST /orm/snapshots. Read: GET /snapshots, GET /snapshots/<id>, GET /orm/snapshots, GET /orm/snapshots/<id>, GET /orm/devices. Update: PUT /devices/<id>. Delete: DELETE /snapshots/<id>. | POST → 201; GET list → 200; GET by id → 200 or 404; PUT label → 200; DELETE → 204 or 404. |
| **ORM maps tables to objects** | `orm_models.py`: Device, MetricType, Snapshot, SnapshotMetric map to tables; `orm_routes.py` uses them with relationships (joinedload, selectinload). | GET /orm/snapshots and /orm/snapshots/<id> return data built from ORM objects; GET /orm/devices returns device list with counts. |
| **Cloud-hosted app works publicly** | Gunicorn started with `--bind 0.0.0.0:5000`; firewall allows 5000/tcp. | On VM: run gunicorn, open `http://200.69.13.70:5000/health` from a browser on your PC. |
| **Schema normalised and integrity enforced** | `docs/SCHEMA_DESIGN.md` documents 1NF/2NF/3NF; FKs, UNIQUE, CHECK, `PRAGMA foreign_keys = ON` in `database.py`. | See SCHEMA_DESIGN.md; DB Browser or SQLite can confirm constraints. |
| **No hardcoded magic values in SQL or API** | All SQL uses `?` placeholders. Port, device_id, thresholds, TCP host/port come from config (config.json) or from named constants in configlib (FALLBACK_* only when config absent). | Grep for literal numbers in routes: only fallbacks from configlib. Config holds device_id, danger_thresholds, server_host, server_port. |
| **Network connectivity understood and testable** | Health endpoint and curl examples above; TCP client/server use config; bind 0.0.0.0 documented. | Use "Network connectivity" section: health, REST, and TCP tests. |

## PoC 2.0 Definition of Done – checklist

**Before you have the VM** (do these now on your machine):

| Item | How to verify |
|------|----------------|
| Client successfully sends JSON metric data | Run `python -m src.tcp_server` in one terminal, then `python -m src.tcp_client` in another. Client sends one JSON snapshot. |
| Server correctly reconstructs full messages | Same as above – server logs the full JSON message (device_id, timestamp, metrics). |
| No socket leaks occur | Code uses `closing()` for all sockets; no extra step – just run server + client. |
| RAII BlockTimer logs timing information | Same run – client logs lines like `BlockTimer [create_snapshot]: 0.000053 s`. |

**When you have the VM** (do this after you get the ISE VM):

| Item | How to verify |
|------|----------------|
| Hello World endpoint works in cloud environment | Clone repo on VM, activate venv, run gunicorn, open `http://200.69.13.70:5000/hello` in a browser. |

## Project layout

```
VroomVroom-Dashboard/
├── config/config.json
├── requirements.txt
├── wsgi.py                    # Gunicorn entry point
├── docs/
│   ├── EXECUTION_ORDER.md
│   └── SCHEMA_DESIGN.md       # Normalised schema (Step 7)
├── src/
│   ├── main.py                # CLI (-s/-c/-a), metrics pipeline
│   ├── web_app.py             # Flask: /hello, /health, /metrics, route registration
│   ├── database.py            # SQLite schema, get_db(), init_db()
│   ├── snapshots.py           # Raw SQL CRUD (POST/GET/PUT/DELETE snapshots, devices)
│   ├── orm_models.py          # SQLAlchemy models, get_session()
│   ├── orm_routes.py          # ORM endpoints (/orm/snapshots, /orm/devices)
│   ├── metrics_cache.py       # TTL cache for /metrics
│   ├── metrics_reader.py      # psutil CPU/RAM/disk
│   ├── protocol.py            # Length-prefixed TCP messages
│   ├── tcp_server.py
│   ├── tcp_client.py
│   ├── raii.py
│   ├── blocktimer/
│   ├── configlib/
│   └── datasnapshot/
├── data/                      # vroomvroom.db (created at runtime)
├── logs/
└── README.md
```
