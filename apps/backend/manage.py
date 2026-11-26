#!/usr/bin/env python3
"""Django entry for the unified API on port 4610.

`make hub` still runs apps/backend/run.py (auth on port 4600).
`make api` and `python3 dev.py` start this process:

  python apps/backend/manage.py runserver --noreload 127.0.0.1:4610
"""

from __future__ import annotations

import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(APP_DIR))

if __name__ == "__main__":
    import os

    from integrations.bbps import load_local_env as load_bbps_env

    load_bbps_env()
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)
