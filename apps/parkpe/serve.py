#!/usr/bin/env python3
"""ParkPe static app. Separate process from PaySwap (apps/payswap/serve.py, :4500).

Auth allowlists this origin in apps/backend/auth/server.py (default
http://127.0.0.1:4310). Start it with `make parkpe` from the repo root.
"""

import os
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HOST = "127.0.0.1"
PORT = 4310


# Fonts are loaded from Google. Hub calls go to auth :4600 and Django :4610.
CSP = (
    "default-src 'self'; "
    "style-src 'self' https://fonts.googleapis.com; "
    "font-src https://fonts.gstatic.com; "
    "img-src 'self' data:; "
    "script-src 'self'; "
    "connect-src 'self' http://127.0.0.1:4600 http://127.0.0.1:4610 http://localhost:4600 http://localhost:4610; "
    "base-uri 'none'; frame-ancestors 'none'"
)


class Handler(SimpleHTTPRequestHandler):
    def end_headers(self):
        # Dashboard JS is edited in place; a cached copy hides the change.
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Security-Policy", CSP)
        self.send_header("X-Content-Type-Options", "nosniff")
        super().end_headers()


if __name__ == "__main__":
    os.chdir(Path(__file__).resolve().parent)
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"ParkPe http://{HOST}:{PORT}/", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()
