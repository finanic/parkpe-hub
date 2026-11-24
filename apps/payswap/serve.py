#!/usr/bin/env python3
"""PaySwap retailer app. Its own static server, separate from ParkPe (apps/parkpe/serve.py, :4310).

Serves this directory no matter which folder the process was started from.
Start it with `make payswap` from the repo root. The API is `make hub`.
"""

import os
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HOST = "127.0.0.1"
PORT = 4500


class Handler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


if __name__ == "__main__":
    os.chdir(Path(__file__).resolve().parent)
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"PaySwap http://{HOST}:{PORT}/", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()
