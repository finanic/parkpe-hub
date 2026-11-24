"""Parking-bay reservation for domain/parkpe/parking.py.

No issuer host is configured. The reference is local so a retry can be
compared without a second booking. A live call, when one exists, stays in
this module. apps/parkpe does not call the issuer itself.
"""

from __future__ import annotations

import hashlib
from decimal import Decimal


def reserve_parking_bay(*, bay: str, amount: Decimal) -> str:
    digest = hashlib.sha256(f"{bay}|{amount:.2f}".encode()).hexdigest()[:12]
    return f"park-{digest}"
