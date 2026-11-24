"""Record a BBPS collection. Not wired to any /api/v1 route.

The mounted PaySwap call is POST /api/v1/payswap/vouchers/order
(domain/payswap/vouchers.py, api/v1/routes/payswap.py).
App caller: apps/payswap/features/bbps, context payswap, role retailer.
Downstream: integrations/bbps.py. Does not import domain/parkpe.
"""

from __future__ import annotations

import time
from decimal import Decimal

from core.actions import elapsed_ms, log_action
from integrations.bbps import submit_bill


def collect(*, biller: str, account: str, amount: Decimal) -> dict:
    started = time.perf_counter()
    reference = submit_bill(biller=biller, account=account, amount=amount)
    log_action(
        action="domain.payswap.bbps.collect",
        outcome="ok",
        status=200,
        duration_ms=elapsed_ms(started),
        target_id=reference,
    )
    return {
        "biller": biller,
        "account": account,
        "amount": f"{amount:.2f}",
        "reference": reference,
        "state": "accepted",
    }
