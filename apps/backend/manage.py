#!/usr/bin/env python3
"""Django entry for the unified API. Makefile `hub` does not call this file.

`make hub` still runs apps/backend/run.py (apps/backend/auth/server.py on port 4600).
Start this process separately:

  python apps/backend/manage.py runserver 127.0.0.1:4610
"""

from __future__ import annotations

import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(APP_DIR))

if __name__ == "__main__":
    import os

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)
