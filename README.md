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

## Deploy to VM (Hello World in the cloud)

Assumes a **new VM with nothing installed** (e.g. a minimal Linux image).

1. **Copy the project to the VM** (from your machine). Examples:
   - **SCP:** `scp -r VroomVroom-Dashboard user@<VM_IP>:~`
   - **rsync:** `rsync -avz VroomVroom-Dashboard/ user@<VM_IP>:~/VroomVroom-Dashboard/`
   - Or on the VM: install git (`sudo apt install git`), then `git clone <repo-url> VroomVroom-Dashboard && cd VroomVroom-Dashboard`

2. **On the VM, install Python.** You need Python 3, pip, and venv (Debian/Ubuntu use an “externally managed” Python, so we use a virtual environment):
   ```bash
   sudo apt update
   sudo apt install -y python3 python3-pip python3-venv
   ```
   (On RHEL/Fedora: `sudo dnf install python3 python3-pip`. Amazon Linux: `sudo yum install python3 python3-pip`. Then use `python3 -m venv venv`; if that fails, install the distro’s `python3-venv` or equivalent.)

3. **Create a virtual environment and install dependencies** (from the project root):
   ```bash
   cd ~/VroomVroom-Dashboard
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```
   Leave the venv activated for the next step. (If you open a new terminal later, run `cd ~/VroomVroom-Dashboard` and `source venv/bin/activate` again.)

4. **Run the web app** (with the venv still activated). Run **only one** of these:
   - **Flask dev server:**  
     `python3 -m src.web_app`
   - **Gunicorn (production-style):**  
     `gunicorn -w 1 -b 0.0.0.0:5000 "src.web_app:app"`  
     (For another port: `gunicorn -w 1 -b 0.0.0.0:<port> "src.web_app:app"`.)

5. **Open in a browser:**  
// replace ur VM IP adress with 'localhost' if your running it like 5000:localhost:5000
   `http://<VM_IP>:5000/hello`  
   (Replace `<VM_IP>` with the VM’s public or private IP.)

   Also try `http://<VM_IP>:5000/health` to confirm the app is up.

**Note:** The app binds to `0.0.0.0`, so it accepts connections from outside the VM. If you can’t reach it, check the VM’s firewall/security group allows inbound TCP on port 5000 (or your chosen port).

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