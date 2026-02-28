# VroomVroom-Dashboard

PoC monitor: reads OS metrics, builds a structured snapshot, and serialises to JSON. Includes a TCP client/server for sending metrics, RAII/BlockTimer, and a Flask web app (/hello, /health, /metrics).

## Requirements (what are they?)

**Requirements** are the extra Python packages this project depends on (beyond the standard library). They're listed in `requirements.txt`. You install them once so the code can import things like `psutil` (for CPU/RAM/disk) and `flask` (for the web server).

## Setup

### 1. Install Python
Download from [python.org](https://www.python.org/downloads/) or run `winget install Python.Python.3.12`.

### 2. Create a virtual environment

A virtual environment isolates this project's packages from the rest of the system.
Run once from the project root:

```bash
cd VroomVroom-Dashboard
python -m venv venv
```

Activate it (required every time you open a new terminal):

```bash
# Windows
venv\Scripts\activate

# Linux / macOS (and on the VM)
source venv/bin/activate
```

Your prompt will show `(venv)` when active.

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

`requirements.txt` pins three packages:
- `psutil` — reads CPU, RAM, disk from the OS
- `flask` — web framework for /hello, /health, /metrics
- `gunicorn` — production WSGI server (used on the VM instead of the Flask dev server)

### 4. Freeze dependencies after adding new packages

```bash
pip freeze > requirements.txt
```

Run this whenever you `pip install` something new so the VM stays in sync.

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

- **Web app — production** (gunicorn + wsgi.py, used on the VM):

  ```bash
  gunicorn wsgi:application --bind 0.0.0.0:5000 --workers 2
  ```

  `wsgi.py` at the project root is the WSGI entry point. It loads config, sets up logging, builds the Flask app, and exposes it as `application` — the name gunicorn looks for.

Optional: set `VROOMVROOM_CONFIG` to a different config file path.

## WSGI configuration

`wsgi.py` (project root) bridges gunicorn and the Flask app:

1. Adds the project root to `sys.path` so `src` is importable.
2. Loads `config/config.json` (or `VROOMVROOM_CONFIG` env var).
3. Calls `setup_logging(config)`.
4. Calls `create_app(config)` → attaches `MetricsCache` → calls `register_routes(app)`.
5. Exposes the result as `application` (the WSGI callable gunicorn expects).

This means gunicorn and `python -m src.web_app` do exactly the same initialisation — config, logging, app, routes — so local and cloud behaviour are consistent.

## Local vs cloud consistency

| Step | Local (`python -m src.web_app`) | Cloud (gunicorn + wsgi.py) |
|------|----------------------------------|----------------------------|
| Config loaded | `src/web_app.py main()` | `wsgi.py` module level |
| Logging set up | `src/web_app.py main()` | `wsgi.py` module level |
| App created | `create_app(config)` | `create_app(config)` |
| Cache attached | `MetricsCache(ttl_seconds=30)` | `MetricsCache(ttl_seconds=30)` |
| Routes registered | `register_routes(app)` | `register_routes(app)` |
| Entry point | `__main__` guard | `wsgi:application` |

Both use the same `config/config.json`, the same `create_app()` and `register_routes()` functions, and the same `MetricsCache` — so `/metrics`, `/hello`, and `/health` behave identically in both environments.

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
├── config/
│   └── config.json           # App config (no hardcoded values in code)
├── requirements.txt           # Python packages (psutil, flask, gunicorn)
├── wsgi.py                    # WSGI entry point for gunicorn (production)
├── src/
│   ├── __init__.py
│   ├── main.py                # CLI entry point with argparse (-s/-c/-a modes)
│   ├── web_app.py             # Flask app: /hello, /health, /metrics
│   ├── metrics_cache.py       # Thread-safe TTL cache for /metrics
│   ├── metrics_reader.py      # Read OS metrics (CPU, RAM, disk) via psutil
│   ├── protocol.py            # 4-byte length header + payload (stream vs message)
│   ├── tcp_server.py          # TCP server: listen, accept, reconstruct messages
│   ├── tcp_client.py          # TCP client: send JSON metrics with BlockTimer
│   ├── raii.py                # RAII helpers (closing sockets)
│   ├── blocktimer/            # RAII timing (perf_counter, log duration)
│   ├── configlib/             # Config loading, validation, logging setup
│   └── datasnapshot/          # Metric/Snapshot models, JSON serialisation, status
├── logs/                      # Created at runtime (log_file_path in config)
└── README.md
```
