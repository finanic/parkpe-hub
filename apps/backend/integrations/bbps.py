"""BBPS submit for domain/payswap/bbps.py.

No biller host is configured, and no credential is read here. The reference
is local. apps/payswap/js/services.js bills() is still the screen that runs today.
apps/payswap/features/bbps is the caller once that screen moves.
The call line is core/actions.py action integration.bbps.submit.
The account number stays out of that line.
"""

from __future__ import annotations

import hashlib
import time
from decimal import Decimal

from core.actions import elapsed_ms, log_action


def submit_bill(*, biller: str, account: str, amount: Decimal) -> str:
    started = time.perf_counter()
    digest = hashlib.sha256(f"{biller}|{account}|{amount:.2f}".encode()).hexdigest()[:12]
    reference = f"bbps-{digest}"
    log_action(
        action="integration.bbps.submit",
        outcome="ok",
        status=200,
        duration_ms=elapsed_ms(started),
        target_id=reference,
    )
    return reference
