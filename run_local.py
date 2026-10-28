"""CloudPort Local Development Runner.

Starts both the backend Cloud Function API (port 8080) and frontend static web server (port 3000)
concurrently for local development and testing.

Usage:
    python run_local.py
"""
import http.server
import json
import os
import socketserver
import sys
import threading
import time

# Ensure backend directory is in Python path
BACKEND_DIR = os.path.join(os.path.dirname(__file__), "backend")
FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "frontend")
sys.path.insert(0, BACKEND_DIR)

# Enable Local Dev mode
os.environ["LOCAL_DEV"] = "true"
os.environ["ALLOWED_ORIGINS"] = "http://localhost:3000,http://127.0.0.1:3000,http://localhost:8080,http://127.0.0.1:8080"
os.environ["PROJECT_ID"] = "cloudport-local-dev"
os.environ["COLLECTION"] = "registrations"

import main
from flask import Flask, request

# Create Flask runner for Cloud Function
backend_app = Flask("cloudport-local-backend")


@backend_app.route("/", methods=["GET", "POST", "OPTIONS"])
@backend_app.route("/register_user", methods=["GET", "POST", "OPTIONS"])
@backend_app.route("/<path:path>", methods=["GET", "POST", "OPTIONS"])
def handle_request(path=None):
    return main.register_user(request)


def run_backend():
    print("[BACKEND] Starting Cloud Function API on http://127.0.0.1:8080 ...")
    backend_app.run(host="127.0.0.1", port=8080, debug=False, use_reloader=False)


class FrontendHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=FRONTEND_DIR, **kwargs)

    def log_message(self, format, *args):
        # Quieter static logs
        pass


def run_frontend():
    print("[FRONTEND] Serving static website on http://127.0.0.1:3000 ...")
    with socketserver.TCPServer(("127.0.0.1", 3000), FrontendHandler) as httpd:
        httpd.serve_forever()


def update_frontend_config():
    """Ensure frontend/config.js points to the local backend endpoint."""
    config_path = os.path.join(FRONTEND_DIR, "config.js")
    content = """/**
 * CloudPort Frontend Local Configuration
 */
window.CLOUDPORT_CONFIG = {
  ENDPOINT: "http://127.0.0.1:8080"
};
"""
    with open(config_path, "w", encoding="utf-8") as f:
        f.write(content)


if __name__ == "__main__":
    update_frontend_config()

    print("=" * 70)
    print("  CloudPort &bull; Local Development Environment")
    print("  Engineer: Aaryan Kumar")
    print("=" * 70)
    print("  Frontend UI : http://127.0.0.1:3000")
    print("  Backend API : http://127.0.0.1:8080")
    print("  Mode        : Local Offline Emulation (Zero GCP Credentials Needed)")
    print("=" * 70)
    print("Press Ctrl+C to terminate both servers.\n")

    # Start backend in a background daemon thread
    backend_thread = threading.Thread(target=run_backend, daemon=True)
    backend_thread.start()

    time.sleep(0.5)

    # Start frontend in main thread
    try:
        run_frontend()
    except KeyboardInterrupt:
        print("\n[SHUTDOWN] Stopping local servers.")
        sys.exit(0)
