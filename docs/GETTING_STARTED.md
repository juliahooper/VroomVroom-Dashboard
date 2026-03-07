# VroomVroom Dashboard – Step by step

Get the database, web app, and collector agent running so the dashboard is populated with PC, YouTube, and (optionally) mobile data.

---

## 1. Environment and dependencies

```bash
cd VroomVroom-Dashboard
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate    # Linux/macOS
pip install -r requirements.txt
```

---

## 2. Configuration

**Config file** (`config/config.json`) – already present; adjust if needed:

- `device_id`: e.g. `"pc-01"` (this machine’s name in the dashboard).
- `read_interval_seconds`: how often the collector runs (e.g. `300` = 5 min).
- `mobile.enabled`: set to `false` if you’re not using Firebase/mobile yet.

**Environment** (`.env` in the project root):

```bash
copy .env.example .env          # Windows
# cp .env.example .env          # Linux/macOS
```

Edit `.env`:

- **YouTube (views + likes):** set `YOUTUBE_API_KEY=` to your YouTube Data API v3 key (from Google Cloud Console). Leave blank to skip YouTube or use stub later.
- **Database:**
  - **SQLite (default):** do not set `DATABASE_URL`. Data goes to `data/vroomvroom.db`.
  - **PostgreSQL:** set e.g.  
    `DATABASE_URL=postgresql://USER:PASSWORD@localhost:5432/vroomvroom`  
    (See `docs/DATABASE_CLOUD.md` for creating the DB and user.)

---

## 3. Database (if using PostgreSQL)

Only if you set `DATABASE_URL`:

- Ensure PostgreSQL is running.
- Create database and user, then run migrations/init from the app (step 5 runs `init_db()` on first web app start and creates tables + seeds metric types).

---

## 4. Optional: Mobile (Firebase)

If `config/config.json` has `"mobile": { "enabled": true, ... }`:

- Place your Firebase service account JSON at the path in `firebase_credentials_path` (e.g. `config/firebase-service-account.json`).
- Firestore must have the collections and structure your config expects; otherwise disable mobile or fix config.

---

## 5. Start the web app

This creates tables and seeds metric types (e.g. `total_streams`, `Like Count`) on first run, and exposes the API the collector will use.

```bash
python -m src.web_app
```

Default: `http://0.0.0.0:5000`. Override port with:

```bash
set VROOMVROOM_WEB_PORT=5001
python -m src.web_app
```

Check: open `http://localhost:5000/health` → should return `OK`.

---

## 6. Start the collector agent

In a **second** terminal (same project, venv activated):

```bash
cd VroomVroom-Dashboard
.venv\Scripts\activate          # Windows
python -m src.main --agent
```

The agent will:

- Use `read_interval_seconds` from config (or `--interval SECONDS` to override).
- POST PC metrics to `http://127.0.0.1:5000` by default. If the web app is on another host/port, set:
  ```bash
  set VROOMVROOM_API_URL=http://localhost:5000
  python -m src.main --agent
  ```

Every interval it will:

1. Read PC metrics and upload a snapshot (device = your `device_id`).
2. Fetch YouTube view + like count (if `YOUTUBE_API_KEY` is set) and upload a snapshot (device = `youtube-vroom-vroom`).
3. If mobile is enabled, fetch from Firestore and upload snapshots (devices = `mobile:<location_id>`).

Leave this running; the database will fill with data over time.

---

## 7. Verify data

- **Health:** `http://localhost:5000/health`
- **Devices:** `http://localhost:5000/orm/devices`
- **Snapshots (e.g. latest):** `http://localhost:5000/orm/snapshots?limit=5` or your frontend/dashboard.

---

## 8. Frontend (optional)

The React dashboard is served by Flask at `/dashboard/` when `frontend/dist` exists. For development with hot reload:

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5176/dashboard/`. Vite proxies `/orm` and `/health` to the backend. See `frontend/README.md` for details (proxy config when backend runs on VM).

---

## Quick reference

| Step | Command / action |
|------|-------------------|
| 1 | `pip install -r requirements.txt` |
| 2 | Copy `.env.example` → `.env`, set `YOUTUBE_API_KEY` and optionally `DATABASE_URL` |
| 3 | (PostgreSQL only) DB created and running |
| 4 | (Optional) Firebase creds in place if mobile enabled |
| 5 | `python -m src.web_app` → leave running |
| 6 | In another terminal: `python -m src.main --agent` → leave running |
| 7 | Check `/health`, `/orm/devices`, `/orm/snapshots` |
| 8 | (Optional) `cd frontend && npm install && npm run dev` → `http://localhost:5176/dashboard/` |

Once the web app and agent are both running, the database will keep being populated with PC, YouTube, and (if enabled) mobile data.

---

## Stretch goal: threshold alert (open YouTube)

When a PC metric (threads, RAM, disk) reaches **danger** threshold, the dashboard shows a popup: "Begin emergency recovery mode?" with **Yes** and **Cancel**. If you click **Yes**, the frontend sends a `play_alert` command to the server; the collector agent polls for it and opens the Vroom Vroom music video on the PC. If you click **Cancel**, nothing happens. To test: temporarily lower thresholds in `config/config.json` (e.g. `"thread_count": 50`) so you hit danger quickly.
