"""Hold a parking bay.

HTTP caller: api/v1/routes/parkpe.py ParkingHoldView (POST /api/v1/parkpe/parking/holds/).
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
