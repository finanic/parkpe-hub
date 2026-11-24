"""Hold a parking bay. Not wired to any /api/v1 route.

The mounted ParkPe call is POST /api/v1/parkpe/sessions/initiate
(domain/parkpe/sessions.py, api/v1/routes/parkpe.py).
App caller: apps/parkpe/features/parking, context parkpe, role customer.
Downstream: integrations/parking.py. Does not import domain/payswap.
"""

from __future__ import annotations

import time
from decimal import Decimal

from core.actions import elapsed_ms, log_action
from integrations.parking import reserve_parking_bay


def hold_bay(*, bay: str, amount: Decimal) -> dict:
    started = time.perf_counter()
    reference = reserve_parking_bay(bay=bay, amount=amount)
    log_action(
        action="domain.parkpe.parking.hold",
        outcome="ok",
        status=200,
        duration_ms=elapsed_ms(started),
        target_id=reference,
    )
    return {
        "bay": bay,
        "amount": f"{amount:.2f}",
        "reference": reference,
        "state": "held",
    }
