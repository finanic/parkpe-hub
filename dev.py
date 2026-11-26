#!/usr/bin/env python3
"""Start auth, the Django API, and both frontends. Ctrl+C stops all four.

  ParkPe   apps/parkpe/serve.py              http://127.0.0.1:4310
  PaySwap  apps/payswap/serve.py             http://127.0.0.1:4500
  Auth     apps/backend/run.py               http://127.0.0.1:4600
  API      apps/backend/manage.py runserver  http://127.0.0.1:4610

Auth allowlists both frontend origins (apps/backend/auth/server.py AUTH_ORIGINS).
"""

from __future__ import annotations

import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent

SERVICES = (
    ("auth", [sys.executable, str(ROOT / "apps" / "backend" / "run.py")], ROOT / "apps" / "backend"),
    (
        "api",
        [sys.executable, str(ROOT / "apps" / "backend" / "manage.py"), "runserver", "--noreload", "127.0.0.1:4610"],
        ROOT,
    ),
    ("parkpe", [sys.executable, str(ROOT / "apps" / "parkpe" / "serve.py")], ROOT / "apps" / "parkpe"),
    ("payswap", [sys.executable, str(ROOT / "apps" / "payswap" / "serve.py")], ROOT / "apps" / "payswap"),
)


def main() -> int:
    children: list[tuple[str, subprocess.Popen[bytes]]] = []
    stopping = False

    def stop(_signum: int | None = None, _frame: object = None) -> None:
        nonlocal stopping
        if stopping:
            return
        stopping = True
        for _name, proc in children:
            if proc.poll() is None:
                proc.terminate()

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)

    for name, command, cwd in SERVICES:
        children.append((name, subprocess.Popen(command, cwd=cwd)))

    print("ParkPe   http://127.0.0.1:4310/", flush=True)
    print("PaySwap  http://127.0.0.1:4500/", flush=True)
    print("Auth     http://127.0.0.1:4600/", flush=True)
    print("API      http://127.0.0.1:4610/", flush=True)
    print("Ctrl+C stops all four.", flush=True)

    exit_code = 0
    while not stopping:
        for name, proc in children:
            code = proc.poll()
            if code is not None:
                print(f"{name} stopped ({code}). Shutting down the rest.", flush=True)
                exit_code = code or exit_code
                stop()
                break
        else:
            time.sleep(0.25)
            continue
        break

    for _name, proc in children:
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
