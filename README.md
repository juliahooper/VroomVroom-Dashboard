# VroomVroom-Dashboard

PoC monitor: reads OS metrics, builds a structured snapshot, and serialises to JSON. Includes a TCP client/server for sending metrics, RAII/BlockTimer, and a small web app (Hello World and health endpoints).

## Requirements (what are they?)

**Requirements** are the extra Python packages this project depends on (beyond the standard library). They’re listed in `requirements.txt`. You install them once so the code can import things like `psutil` (for CPU/RAM/disk) and `flask` (for the web server).

## Setup

1. Install Python (e.g. from [python.org](https://www.python.org/downloads/) or `winget install Python.Python.3.12`).
2. From the project root, install the requirements:

   ```bash
   cd VroomVroom-Dashboard
   python -m pip install -r requirements.txt
   ```

   If `pip` isn’t found, use `python -m pip` so the correct Python is used.

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

- **Web app** (Flask server with GET /hello and GET /health):

  ```bash
  python -m src.web_app
  ```

  Then open in a browser: `http://127.0.0.1:5000/hello` or `http://127.0.0.1:5000/health`.

Optional: set `VROOMVROOM_CONFIG` to a different config file path, or `VROOMVROOM_WEB_PORT` (e.g. `8080`) to change the web app port.

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
| Hello World endpoint works in cloud environment | Copy the project to the VM, run `python -m src.web_app` (or gunicorn), then open `http://<VM_IP>:5000/hello` in a browser. |

## Project layout

```
VroomVroom-Dashboard/
├── config/
│   └── config.json       # App config (no hardcoded values in code)
├── requirements.txt      # Python packages to install (psutil, flask)
├── src/
│   ├── __init__.py
│   ├── main.py           # Entry point, logging setup, exit codes
│   ├── config.py         # Load and validate config (includes server_port, server_host)
│   ├── metrics_reader.py # Read OS metrics (CPU, RAM, disk)
│   ├── models.py         # Data models, JSON serialisation, status
│   ├── protocol.py       # 4-byte length header + payload (stream vs message)
│   ├── tcp_server.py     # TCP server: listen, accept, reconstruct messages, RAII
│   ├── tcp_client.py     # TCP client: send JSON metrics, BlockTimer, RAII
│   ├── block_timer.py    # RAII timing (perf_counter, log duration)
│   ├── raii.py           # Context manager helpers (e.g. closing sockets)
│   └── web_app.py        # Flask: GET /hello, GET /health
├── logs/                 # Created at runtime (log_file_path in config)
└── README.md
```