"""Hold a parking bay. Not wired to any /api/v1 route.

The mounted ParkPe call is POST /api/v1/parkpe/sessions/initiate
(domain/parkpe/sessions.py, api/v1/routes/parkpe.py).
App caller: apps/parkpe/features/parking, context parkpe, role customer.
Downstream: integrations/parking.py. Does not import domain/payswap.
"""

from __future__ import annotations

from decimal import Decimal

from integrations.parking import reserve_parking_bay


def hold_bay(*, bay: str, amount: Decimal) -> dict:
    reference = reserve_parking_bay(bay=bay, amount=amount)
    return {
        "bay": bay,
        "amount": f"{amount:.2f}",
        "reference": reference,
        "state": "held",
    }
