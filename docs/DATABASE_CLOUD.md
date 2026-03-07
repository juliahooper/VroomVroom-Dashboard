# Using PostgreSQL on our VM

When the team needs to share one database, we use **PostgreSQL hosted on our own VM** instead of a local SQLite file. The app connects via the `DATABASE_URL` environment variable.

---

## 1. Create the `.env` file (once per machine)

The app reads secrets from a file named **`.env`** in the project root. The repo only has **`.env.example`** (so secrets are not committed). Create your own `.env`:

1. In the project root (same folder as `config/` and `src/`), copy the example:
   - **Windows (PowerShell):** `Copy-Item .env.example .env`
   - **Linux / VM:** `cp .env.example .env`
2. Open **`.env`** and fill in any values you need (e.g. `YOUTUBE_API_KEY`, `DATABASE_URL`).

If you already have a `.env` file, you can skip this step.

---

## 2. Install PostgreSQL on the VM

On the VM (Ubuntu/Debian):

```bash
sudo apt update
sudo apt install -y postgresql postgresql-contrib
sudo systemctl start postgresql
sudo systemctl enable postgresql
```

---

## 3. Create the database and user

```bash
sudo -u postgres psql
```

At the `postgres=#` prompt, run (use your own password instead of `yourpassword`):

```sql
CREATE USER vroomvroom WITH PASSWORD 'yourpassword';
CREATE DATABASE vroomvroom OWNER vroomvroom;
\q
```

---

## 4. Point the app at PostgreSQL

In the project root, open **`.env`** and set:

```env
DATABASE_URL=postgresql://vroomvroom:yourpassword@localhost:5432/vroomvroom
```

Use the **same password** you set in step 3. We run the app and PostgreSQL on the **same VM**, so **`localhost`** is correct; no firewall or remote-access setup is needed.

---

## 5. Install the PostgreSQL driver and run the app

From the project root:

```bash
pip install -r requirements.txt
python -m src.web_app
```

You should see: **`PostgreSQL database initialised (DATABASE_URL)`**. Tables and metric types are created automatically on first run.

---

## Sharing with the team

- **One database user:** Everyone uses the same `vroomvroom` user and password in `DATABASE_URL` (the app connects as this user; you don’t create a separate PostgreSQL user per person).
- **Same `.env` on the server:** If the app runs only on the VM, only that VM needs `.env` with `DATABASE_URL`. The others use the dashboard at `http://<VM-IP>:5000`.
- **Everyone runs the app:** If each of you runs the app and points at the same VM database, each machine needs a `.env` with the **same** `DATABASE_URL` (same user/password/host/dbname).

---

## Behaviour when `DATABASE_URL` is set

- The app uses **PostgreSQL** instead of the local `data/vroomvroom.db` file.
- Tables are created and metric types are seeded automatically on startup.
- Only the **ORM** routes are used (`/orm/snapshots`, `/orm/devices`, `/orm/upload_snapshot`). The raw SQL blueprint is disabled. The frontend and collector already use the ORM endpoints.

---

## Viewing data on the VM

- **From the app:** Open `http://<VM-IP>:5000/orm/devices` or `http://<VM-IP>:5000/orm/snapshots` in a browser.
- **Directly in PostgreSQL:** On the VM, run `psql -U vroomvroom -d vroomvroom` (it will ask for the password), then e.g. `\dt` to list tables, `SELECT * FROM device;` to see devices.
