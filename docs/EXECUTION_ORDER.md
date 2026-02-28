# Execution Order Awareness

This document describes how Python execution order applies in this project and where it is demonstrated.

## Code executes top-to-bottom, depth-first

- When a module is run or imported, Python executes statements from the top of the file downward.
- When a function is called, execution goes into that function (depth-first) and returns when the function finishes.
- **Example:** In `main.py`, `main()` runs in order: load config → setup logging → read metrics → create snapshot → serialize to JSON → verify integrity → return. Each step runs completely before the next.

## Modules execute once per process

- Importing a module (e.g. `from .configlib import load_config`) runs that module’s top-level code once per process.
- Subsequent imports of the same module reuse the same loaded module object; top-level code is not re-run.
- **Example:** `configlib`, `datasnapshot`, `metrics_reader` are imported once when `main.py` runs; their module-level constants and function definitions exist for the life of the process.

## `__name__ == '__main__'` defines entry point

- When you run a file with `python -m src.main`, Python sets `__name__` to `'__main__'` for that file only.
- Code under `if __name__ == '__main__':` runs only when the file is the program entry point, not when the file is imported.
- **Examples:**
  - `src/main.py`: `if __name__ == '__main__': sys.exit(main())` — run the CLI when executed as `python -m src.main`.
  - `src/web_app.py`: same pattern for `python -m src.web_app`.
  - `src/tcp_client.py` / `src/tcp_server.py`: same pattern for TCP client and server scripts.

## Web apps initialise once, then respond to events

- The web server is started once: load config, create app, register routes, then call `app.run(...)`.
- After that, the process stays alive and does not re-run the startup code; it only reacts to incoming HTTP requests.
- Each request is handled by the registered view functions (e.g. `/hello`, `/health`, `/metrics`); those run in response to events (incoming requests), not in startup order.
- **Example:** In `web_app.py`, `main()` runs once: config load → logging setup → `create_app(config)` → `register_routes(app)` → `app.run(...)`. Later, a request to GET `/metrics` triggers the `metrics()` view; the app does not re-initialise for each request.
