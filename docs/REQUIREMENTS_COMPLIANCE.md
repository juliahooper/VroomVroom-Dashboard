# Project Functional Requirements – Compliance

This document maps the project functional requirements to the VroomVroom Dashboard implementation.

---

## 1. System-Monitoring Tool with Cloud Dashboards

**Requirement:** A System-Monitoring Tool that Provides Cloud Dashboards for PC, Mobile Device & 3rd Party Data and History.

| Source | Implementation |
|--------|-----------------|
| **PC** | Collector agent (`python -m src.main --agent`) reads OS metrics via `psutil`; gauges show live data; historic charts show trends. |
| **Mobile** | Firebase Firestore; config-driven (`mobile` in `config.json`); locations, cold water shock risk, alerts, water temp; map markers. |
| **3rd Party** | YouTube Data API v3 (views, likes for Vroom Vroom video). |
| **Cloud** | PostgreSQL (or SQLite) on VM; Flask REST API; React dashboard served at `/dashboard/`. |
| **History** | `snapshot` and `snapshot_metric` tables; historic charts for last 7 days. |

---

## 2. Min 2 Metrics per Device

**Requirement:** Min 2 Metrics per Device. E.g. #Running Threads, #Open Processes, RAM Usage…

| Device | Metrics | Count |
|--------|---------|-------|
| **PC** (`pc-01`) | Running Threads, RAM Usage, Disk Usage | 3 |
| **Mobile** (per location) | Cold Water Shock Risk, Alert Count, Water Temp | 3 |
| **3rd Party** (`youtube-vroom-vroom`) | Total Streams (views), Like Count | 2 |

---

## 3. Values That Change Reasonably Regularly

**Requirement:** Choose Values that Change Reasonably Regularly but not at Sub-Second Frequency.

| Metric | Change Frequency | Notes |
|--------|------------------|-------|
| Running Threads | Minutes | Process count varies with workload |
| RAM Usage | Minutes | Memory usage fluctuates |
| Disk Usage | Hours/days | Grows slowly |
| Cold Water Shock Risk | Per reading | Firestore time-series |
| Alert Count | Per event | Firestore count |
| Water Temp | Per reading | Firestore time-series |
| YouTube Views/Likes | Hours | API rate limits apply |

---

## 4. Gather Information from PC, Mobile & 3rd Party

**Requirement:** Gather information from PC, Mobile Device & 3rd Party Service.

| Source | How | Module |
|--------|-----|--------|
| **PC** | `psutil` (threads, RAM, disk) | `metrics_reader.py`, `collector_agent.py` |
| **Mobile** | Firebase Firestore (config-driven) | `mobile_collector.py`, `collectors/mobile_upload.py` |
| **3rd Party** | YouTube Data API v3 | `youtube_fetcher.py`, `collectors/third_party_collector.py` |

---

## 5. Report to Cloud Server

**Requirement:** Report that Information to a Cloud based Server.

| Mechanism | Endpoint | Used By |
|-----------|----------|---------|
| REST API | `POST /orm/upload_snapshot` | Collector agent, backfill, mobile upload |
| DTO | `{ device_id, timestamp_utc, metrics: [{ name, value, unit, status }] }` | All collectors |

---

## 6. Store History on Cloud Server

**Requirement:** Store a History of Information on the Cloud Server.

| Storage | Tables | Notes |
|---------|--------|-------|
| PostgreSQL | `device`, `snapshot`, `snapshot_metric`, `metric_type`, `device_command` | When `DATABASE_URL` set |
| SQLite | Same schema | Default when `DATABASE_URL` unset |

- `snapshot` stores each upload with timestamp
- `snapshot_metric` stores per-metric values
- Historic queries use `since` and `limit` params

---

## 7. Dashboard UI with Live and Historic Data

**Requirement:** Present a Dashboard UI showing Live and Historic Data.

| UI | Implementation |
|----|----------------|
| **Live** | Gauges (PC), badges (YouTube, location), map with markers |
| **Historic** | Toggle to Historic view; charts for PC, YouTube, mobile; last 7 days |
| **Tech** | React, Vite, Recharts, Leaflet; served at `/dashboard/` |

---

## 8. Stretch – Send Messages Back to Device

**Requirement:** Send messages back to the Device (e.g. Restart App).

### Why it counts

The stretch goal requires the **server to send a message to a device** and the **device to receive and act on it**. The implementation satisfies this as follows:

1. **Server receives a request** – User clicks "Yes" on the dashboard; frontend sends `POST /orm/commands` with `{ device_id: "pc-01", command: "play_alert" }`.

2. **Server stores the command** – Backend creates a row in `device_command` with `status: "pending"`. The server has now "sent" the message (queued it for the device).

3. **Device polls for commands** – The collector agent (the "device" for `pc-01`) runs a background thread that polls `GET /orm/commands/pending?device_id=pc-01` every 10 seconds.

4. **Device receives the message** – The API returns the pending command. The collector has received the message from the server.

5. **Device executes** – The collector runs `webbrowser.open(url)` for `play_alert`. On a headless VM this has no visible effect; on a machine with a display it would open the browser. The UX improvement: the frontend also opens the video in the user's browser when they click "Yes", so the user sees the action on the device they are using.

**Architecture:** Server → command queue → device polls → device executes. The "message back" is the command in the queue; the device fetches it and acts on it. The stretch goal is satisfied by this flow.

| Component | Implementation |
|-----------|----------------|
| **Frontend** | Danger popup → "Yes" sends `POST /orm/commands`; opens video in user's browser |
| **Backend** | `device_command` table; `POST /orm/commands`, `GET /orm/commands/pending`, `POST /orm/commands/<id>/ack` |
| **Collector** | Polls for pending commands; executes `play_alert` (webbrowser.open) |
