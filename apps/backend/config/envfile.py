"""Load apps/backend/.env into os.environ (setdefault only).

Auth (run.py / auth.server.main) and Django (manage.py / settings) call
load_backend_env before provider helpers. Existing process env wins.
Does not print or log values. Legacy data/*.env files remain optional fallbacks
in kaleyra, mail, cashfree, and bbps loaders.
"""

from __future__ import annotations

import os
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_ENV = _BACKEND_ROOT / ".env"
_LOADED = False


def backend_root() -> Path:
    return _BACKEND_ROOT


def load_backend_env(path: Path | None = None) -> Path:
    """Parse KEY=VALUE lines from the backend .env file into os.environ."""
    global _LOADED
    file = path or _DEFAULT_ENV
    try:
        text = file.read_text(encoding="utf-8")
    except OSError:
        _LOADED = True
        return file
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        name = name.strip()
        if not name or not name.replace("_", "").isalnum():
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        os.environ.setdefault(name, value)
    _LOADED = True
    return file


def ensure_backend_env() -> None:
    if not _LOADED:
        load_backend_env()
