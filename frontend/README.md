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

With the Flask API running on port 5000:

```bash
npm run dev
```

Open http://localhost:5173/dashboard/ — Vite proxies `/orm` and `/dashboard/assets` to Flask.

## Production build

```bash
npm run build
```

Then run the Flask app; it serves the built app from `dist/` at `/dashboard/` and `/dashboard`.

## Background image

`public/finalBackground.svg` is copied into the build. To update it, replace `frontend/public/finalBackground.svg` (e.g. copy from `../assets/finalBackground.svg`).
