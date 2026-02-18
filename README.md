# VroomVroom-Dashboard

PoC monitor: reads OS metrics, builds a structured snapshot, and serialises to JSON.

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