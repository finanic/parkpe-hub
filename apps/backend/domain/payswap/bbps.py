"""Record a BBPS collection.

Not mounted. The routed PaySwap call is POST /api/v1/payswap/vouchers/order
(domain/payswap/vouchers.py, api/v1/routes/payswap.py).
App caller: apps/payswap/features/bbps, context payswap, role retailer.
Downstream: integrations/bbps.py. Does not import domain/parkpe.
"""

from __future__ import annotations

from decimal import Decimal

from integrations.bbps import submit_bill


def collect(*, biller: str, account: str, amount: Decimal) -> dict:
    reference = submit_bill(biller=biller, account=account, amount=amount)
    return {
        "biller": biller,
        "account": account,
        "amount": f"{amount:.2f}",
        "reference": reference,
        "state": "accepted",
    }
