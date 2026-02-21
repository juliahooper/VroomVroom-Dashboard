"""
Web enabling – Hello World and health endpoints (WSGI).

What this does: runs a small web server (using Flask) that answers two URLs.
- GET /hello  → returns the text "Hello World"
- GET /health → returns "OK" and status 200 (used to check if the app is running)

To run it locally: use the command  python -m src.web_app  (that starts Flask’s
built-in server). For deployment on a VM you run the same command there, or use
gunicorn; then open http://<VM_IP>:5000/hello from a browser.
"""
from __future__ import annotations

import os
import sys

from flask import Flask

# Create the Flask app. Routes below tell it what to do for each URL.
app = Flask(__name__)


@app.route("/hello")
def hello() -> str:
    """When someone visits /hello we return this string."""
    return "Hello World"


@app.route("/health")
def health() -> tuple[str, int]:
    """When someone visits /health we return 'OK' and HTTP status 200 (success)."""
    return "OK", 200


def main() -> int:
    """Start the web server. Listens on all interfaces (0.0.0.0) so the VM can be reached from outside."""
    port = int(os.environ.get("VROOMVROOM_WEB_PORT", "5000"))
    # host="0.0.0.0" means "accept connections from any machine", not just this one
    app.run(host="0.0.0.0", port=port, debug=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
