# VroomVroom-Dashboard docs

| Doc | Purpose |
|-----|--------|
| [API_DESIGN.md](API_DESIGN.md) | Bulk vs granular API, versioning, security, client/server trade-offs. |
| [BACKUP_AND_FAILED_REPLAY.md](BACKUP_AND_FAILED_REPLAY.md) | Snapshot backup log, retries, failed-snapshot replay, concurrent writes (no queue). |
| [DATA_MODEL.md](DATA_MODEL.md) | Four layers: DB, ORM, domain, DTO; timestamps UTC ISO 8601. |
| [DATABASE_CLOUD.md](DATABASE_CLOUD.md) | PostgreSQL on VM: create DB, user, set `DATABASE_URL`. |
| [EXECUTION_ORDER.md](EXECUTION_ORDER.md) | Execution order for main and web app. |
| [GETTING_STARTED.md](GETTING_STARTED.md) | Step-by-step setup: env, config, DB, web app, collector, verify. |
| [ONE_DATABASE_AND_FRONTEND.md](ONE_DATABASE_AND_FRONTEND.md) | One DB for PC, YouTube, mobile; how to run collectors and populate the front end. |
| [SCHEMA_DESIGN.md](SCHEMA_DESIGN.md) | Normalised schema, tables, indexes, referential integrity. |
