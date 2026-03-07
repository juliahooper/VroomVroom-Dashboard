# VroomVroom Dashboard (React)

React + Vite frontend for the VroomVroom dashboard. Uses the same Flask API (`/orm/snapshots/latest`, `/orm/snapshots?expand=metrics`, etc.).

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
