"""Which account role may enter which app.

packages/contracts Role: customer, retailer, admin.
apps/backend/auth/contract.py uses the same three strings.
customer is ParkPe (apps/parkpe). retailer is PaySwap (apps/payswap).
admin stays on apps/backend/auth/console and is not a context here.
"""

from __future__ import annotations

PARKPE = "parkpe"
PAYSWAP = "payswap"
CONTEXTS = frozenset({PARKPE, PAYSWAP})

ROLE_FOR_CONTEXT = {
    PARKPE: "customer",
    PAYSWAP: "retailer",
}


class BadContext(Exception):
    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


def parse_context(value: str | None) -> str:
    if value is None or not str(value).strip():
        raise BadContext("Send X-App-Context.")
    cleaned = str(value).strip().lower()
    if cleaned not in CONTEXTS:
        raise BadContext("X-App-Context must be parkpe or payswap.")
    return cleaned
