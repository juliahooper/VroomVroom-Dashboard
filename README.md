# VroomVroom-Dashboard

PoC monitor: reads OS metrics, builds a structured snapshot, and serialises to JSON.

## Project layout

```
VroomVroom-Dashboard/
├── config/
│   └── config.json       # App config (no hardcoded values in code)
├── src/
│   ├── main.py           # Entry point, logging setup, exit codes
│   ├── config.py         # Load and validate config
│   ├── metrics_reader.py # Read OS metrics (CPU, RAM, disk)
│   └── models.py         # Data models, JSON serialisation, status
├── logs/                 # Created at runtime (log_file_path in config)
└── README.md
```