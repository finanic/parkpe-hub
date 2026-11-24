"""Record a BBPS collection.

HTTP caller: api/v1/routes/payswap.py BbpsPaymentView (POST /api/v1/payswap/bbps/payments/).
App caller: apps/payswap/features/bbps, context payswap, role retailer.
Downstream: integrations/bbps.py. Does not import domain/parkpe.
The Idempotency-Key is applied by the view via core/idempotency.py, before this runs.
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
