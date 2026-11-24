"""JSON bodies for api/v1/routes.

Field names and error codes match packages/contracts. apps/parkpe and
apps/payswap consume that package through packages/sdk-client, not a
private copy of these shapes. Role and path constants that already ship
are in apps/backend/auth/contract.py.

SessionInitiateSerializer is POST /api/v1/parkpe/sessions/initiate.
VoucherOrderSerializer is POST /api/v1/payswap/vouchers/order.
"""

from schemas.serializers import (
    BbpsPaymentSerializer,
    ParkingHoldSerializer,
    SessionInitiateSerializer,
    VoucherOrderSerializer,
)

__all__ = [
    "BbpsPaymentSerializer",
    "ParkingHoldSerializer",
    "SessionInitiateSerializer",
    "VoucherOrderSerializer",
]
