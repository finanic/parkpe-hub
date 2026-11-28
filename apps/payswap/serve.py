#!/usr/bin/env python3
"""PaySwap retailer app. Its own static server, separate from ParkPe (apps/parkpe/serve.py, :4310).

Serves this directory no matter which folder the process was started from.
Start it with `make payswap` from the repo root. Auth is `make hub` (:4600); Django is `make api` (:4610).
"""

import os
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HOST = "127.0.0.1"
PORT = 4500


# Fonts are loaded from Google. Hub calls go to auth :4600 and Django :4610.
CSP = (
    "default-src 'self'; "
    "style-src 'self' https://fonts.googleapis.com; "
    "font-src https://fonts.gstatic.com; "
    "img-src 'self' data: https://static.mobikwik.com https://www.google.com https://*.gstatic.com; "
    "script-src 'self'; "
    "connect-src 'self' http://127.0.0.1:4600 http://127.0.0.1:4610 http://localhost:4600 http://localhost:4610; "
    "base-uri 'none'; frame-ancestors 'none'"
)


class Handler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Security-Policy", CSP)
        self.send_header("X-Content-Type-Options", "nosniff")
        super().end_headers()


if __name__ == "__main__":
    os.chdir(Path(__file__).resolve().parent)
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"PaySwap http://{HOST}:{PORT}/", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()
