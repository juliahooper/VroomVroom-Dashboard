# VroomVroom-Dashboard

PoC monitor: reads OS metrics, builds a structured snapshot, and serialises to JSON.

## Setup

1. **Install Python** (if needed) from [python.org](https://www.python.org/downloads/) or with `winget install Python.Python.3.12`. Do not use `pip install python` — pip is included with Python.
2. **Install dependencies** (from the project root):
   ```bash
   python -m pip install -r requirements.txt
   ```
   If `pip` is not found, use `python -m pip` so the correct Python’s pip is used.

## Run

From the project root:

```bash
python -m src.main
```

(Not `python main.py` — the entry point is in `src/`.)

Run from the project root so `config/config.json` and `logs/` resolve correctly.

### TCP server (Step 1 – IPC)

```bash
python -m src.tcp_server
```

Listens on the port in config (`server_port`, default 54545). Buffers incoming bytes and only processes complete protocol messages (4-byte length + payload); logs each JSON message. Stop with Ctrl+C.

### TCP client (Step 2 – metric transmission)

```bash
python -m src.tcp_client
```

Connects to `server_host` and `server_port` from config (default 127.0.0.1:54545). Logs local and remote socket info, sends one JSON metric payload (device_id, timestamp, metrics with status), then closes the socket. Start the server first in another terminal.

### Protocol (Step 3 – stream vs message)

Messages use a **4-byte length header** (big-endian, payload length) **+ payload** (JSON UTF-8). The server buffers incoming bytes and only processes complete messages; the client sends each payload with `encode_message()` from `src.protocol`.

## Project layout

```
VroomVroom-Dashboard/
├── config/
│   └── config.json       # App config (no hardcoded values in code)
├── src/
│   ├── __init__.py
│   ├── main.py           # Entry point, logging setup, exit codes
│   ├── tcp_server.py     # TCP server (buffer, process complete messages)
│   ├── tcp_client.py     # TCP client (connect, send length-prefixed JSON)
│   ├── protocol.py       # 4-byte header + payload (stream vs message)
│   ├── config.py         # Load and validate config
│   ├── metrics_reader.py # Read OS metrics (CPU, RAM, disk)
│   └── models.py         # Data models, JSON serialisation, status
├── logs/                 # Created at runtime (log_file_path in config)
└── README.md
```