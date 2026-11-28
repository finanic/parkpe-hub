"""Keep local auth and ledger files readable only by this user."""

from __future__ import annotations

import os
from pathlib import Path


def restrict_private(path: Path) -> None:
    try:
        if path.is_dir():
            os.chmod(path, 0o700)
        elif path.is_file():
            os.chmod(path, 0o600)
    except OSError:
        return
