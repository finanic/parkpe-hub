"""Parking-bay reservation for domain/parkpe/parking.py.

No issuer host is configured. The reference is local so a retry can be
compared without a second booking. A live call, when one exists, stays in
this module. apps/parkpe does not call the issuer itself.
The call line is core/actions.py action integration.parking.reserve.
The bay and amount stay out of that line.
"""

from __future__ import annotations

import hashlib
import time
from decimal import Decimal

from core.actions import elapsed_ms, log_action


def reserve_parking_bay(*, bay: str, amount: Decimal) -> str:
    started = time.perf_counter()
    digest = hashlib.sha256(f"{bay}|{amount:.2f}".encode()).hexdigest()[:12]
    reference = f"park-{digest}"
    log_action(
        action="integration.parking.reserve",
        outcome="ok",
        status=200,
        duration_ms=elapsed_ms(started),
        target_id=reference,
    )
    return reference
