# VroomVroom Dashboard (React)

React + Vite frontend for the VroomVroom dashboard. Boat-themed gauges (tachometer, speedometer, fuel) for PC metrics; Ireland map with swim-spot markers; historic time-series charts. Uses the Flask API (`/orm/snapshots/latest`, `/orm/snapshots`, `/orm/locations`, etc.).

## Features

- **Live gauges:** Running Threads (RPM), Disk Usage (%), RAM Usage (Fuel). Thresholds from backend.
- **Ireland map:** Swim spots with markers; click to select and filter historic data.
- **Historic charts:** PC metrics (threads, disk, RAM) or location metrics (Cold Water Shock Risk, Alert Count, Water Temp) when a location is selected.
- **YouTube badge:** View/like count from `youtube-vroom-vroom` device.

## Setup

```bash
cd frontend
npm install
```

## Development

Run the frontend dev server with hot reload. API requests are proxied to the backend.

**1. Start the backend** (Flask) somewhere — locally or on your VM:
```bash
python -m src.web_app
# or however you run it on the VM
```

**2. Start the frontend dev server:**
```bash
cd frontend
npm run dev
```

**3. Open** http://localhost:5176/dashboard/

Vite proxies `/orm` and `/health` to the backend. **No restart needed** — frontend changes (React, CSS) hot-reload instantly.

**Backend on a VM?** Set `VITE_API_PROXY` to your backend URL before starting the dev server:
```bash
# Windows (PowerShell)
$env:VITE_API_PROXY="http://192.168.1.100:5000"; npm run dev

# Or create frontend/.env with:
# VITE_API_PROXY=http://your-vm-ip:5000
```

## Production build

```bash
npm run build
```

Then run the Flask app; it serves the built app from `dist/` at `/dashboard/` and `/dashboard`.

## Background image

`public/finalBackground.svg` is copied into the build. To update it, replace `frontend/public/finalBackground.svg` (e.g. copy from `../assets/finalBackground.svg`).
