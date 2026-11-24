"""BBPS submit for domain/payswap/bbps.py.

No biller host is configured, and no credential is read here. The reference
is local. apps/payswap/js/services.js bills() is still the screen that runs today.
apps/payswap/features/bbps is the caller once that screen moves.
"""

from __future__ import annotations

import hashlib
from decimal import Decimal


def submit_bill(*, biller: str, account: str, amount: Decimal) -> str:
    digest = hashlib.sha256(f"{biller}|{account}|{amount:.2f}".encode()).hexdigest()[:12]
    return f"bbps-{digest}"
