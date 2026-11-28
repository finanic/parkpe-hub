"""Start a PaySwap brand-voucher order.

HTTP caller: POST /api/v1/payswap/vouchers/order in api/v1/routes/payswap.py.
App caller: apps/payswap/features/vouchers, via packages/sdk-client with
X-App-Context: payswap. The account is the signed-in retailer.
Does not import domain/parkpe. No brand host is called from here.
Audit shape: domain/common/audit.py.
The service line is core/actions.py action domain.payswap.voucher.order.
"""

from __future__ import annotations

import json
import secrets
import time
from decimal import Decimal

from core.actions import elapsed_ms, log_action
from domain.common.audit import audit_entry
from domain.common.scope import PAYSWAP


def order_voucher(*, user_id: str, brand: str, amount: Decimal) -> dict:
    started = time.perf_counter()
    reference = f"vch-{secrets.token_hex(8)}"
    log_action(
        action="domain.payswap.voucher.order",
        outcome="ok",
        status=201,
        duration_ms=elapsed_ms(started),
        target_id=reference,
        request=json.dumps({"brand": brand, "amount": f"{amount:.2f}"}),
        response=json.dumps({"reference": reference, "brand": brand, "amount": f"{amount:.2f}", "state": "ordered"}),
    )
    return {
        "brand": brand,
        "amount": f"{amount:.2f}",
        "reference": reference,
        "state": "ordered",
        "audit": audit_entry(
            app_context=PAYSWAP,
            user_id=user_id,
            action="voucher.order",
            reference=reference,
        ),
    }
