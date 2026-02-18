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

Run from the project root so `config/config.json` and `logs/` resolve correctly.

## Project layout

```
VroomVroom-Dashboard/
├── config/
│   └── config.json       # App config (no hardcoded values in code)
├── src/
│   ├── __init__.py
│   ├── main.py           # Entry point, logging setup, exit codes
│   ├── config.py         # Load and validate config
│   ├── metrics_reader.py # Read OS metrics (CPU, RAM, disk)
│   └── models.py         # Data models, JSON serialisation, status
├── logs/                 # Created at runtime (log_file_path in config)
└── README.md
```