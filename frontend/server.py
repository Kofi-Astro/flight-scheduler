#!/usr/bin/env python3
"""Tiny static file server for the frontend.

Why not just ``python -m http.server``? Two reasons:

1. **Runtime config injection.** The frontend needs to know the backend's URL,
   which differs between local dev and each deployment. Baking it into the JS at
   build time is brittle. Instead this server generates a small ``/env.js`` file
   on the fly from the ``API_BASE_URL`` environment variable, and ``index.html``
   loads it before anything else:

       window.__CONFIG__ = { API_BASE_URL: "https://api.example.com" }

2. **Sensible defaults + caching headers** for a single-page app.

No third-party dependencies — this is the Python standard library only, so the
Railway build is instant.

Local dev:   python server.py            (serves on :5173)
Production:  Railway runs `python server.py`, PORT is injected.
"""

from __future__ import annotations

import http.server
import json
import os
import socketserver
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _load_dotenv(path: Path) -> None:
    """Minimal .env loader (no dependency on python-dotenv).

    Lets `cp .env.example .env && python server.py` work locally. In production
    Railway injects real environment variables and there is no .env file.
    """
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv(HERE / ".env")

# The backend base URL the browser should call. Overridden per environment.
API_BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8000")

# Railway injects PORT; default matches the Vite convention for familiarity.
PORT = int(os.environ.get("PORT", "5173"))


class Handler(http.server.SimpleHTTPRequestHandler):
    """Serves ./ with one special route: /env.js (generated, never cached)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(HERE), **kwargs)

    # --- generated runtime config -------------------------------------
    def do_GET(self) -> None:  # noqa: N802 (stdlib naming)
        if self.path.split("?")[0] in ("/env.js", "/js/env.js"):
            self._serve_env_js()
            return
        super().do_GET()

    def _serve_env_js(self) -> None:
        config = {"API_BASE_URL": API_BASE_URL.rstrip("/")}
        body = f"window.__CONFIG__ = {json.dumps(config)};\n".encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/javascript; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        # Never cache — the value can change on redeploy.
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    # --- caching: long for hashed assets, short for html -------------
    def end_headers(self) -> None:
        path = self.path.split("?")[0]
        if path.endswith((".css", ".js", ".svg", ".woff2", ".png", ".webp")):
            self.send_header("Cache-Control", "public, max-age=3600")
        elif path.endswith(".html") or path == "/":
            self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def log_message(self, fmt: str, *args) -> None:
        # Compact one-line logs.
        print(f"[frontend] {self.address_string()} {fmt % args}")


def main() -> None:
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.ThreadingTCPServer(("0.0.0.0", PORT), Handler) as httpd:
        print(f"[frontend] serving {HERE} on http://0.0.0.0:{PORT}")
        print(f"[frontend] API_BASE_URL = {API_BASE_URL}")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n[frontend] bye")


if __name__ == "__main__":
    main()
