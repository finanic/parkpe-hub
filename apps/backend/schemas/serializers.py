"""Request bodies for /api/v1.

Mounted on Django: SessionInitiateSerializer
(POST /api/v1/parkpe/sessions/initiate, api/v1/routes/parkpe.py) and
VoucherOrderSerializer
(POST /api/v1/payswap/vouchers/order, api/v1/routes/payswap.py).
Field names line up with packages/contracts. A bad body is code validation
through config/exceptions.py.

ParkingHoldSerializer and BbpsPaymentSerializer are not wired to any
/api/v1 route. domain/parkpe/parking.py and domain/payswap/bbps.py are
the same: present, unmounted.
"""

from __future__ import annotations

from decimal import Decimal

from rest_framework import serializers


class SessionInitiateSerializer(serializers.Serializer):
    """POST /api/v1/parkpe/sessions/initiate.

    Route: api/v1/routes/parkpe.py. Caller: apps/parkpe/js/hub.js.
    """

    site_code = serializers.RegexField(r"^[A-Za-z0-9][A-Za-z0-9-]{1,31}$")
    bay = serializers.RegexField(r"^[A-Za-z0-9][A-Za-z0-9-]{0,15}$")
    vehicle = serializers.RegexField(r"^[A-Za-z0-9]{4,16}$")


class VoucherOrderSerializer(serializers.Serializer):
    """POST /api/v1/payswap/vouchers/order.

    Route: api/v1/routes/payswap.py. Caller: apps/payswap/js/hub.js.
    """

    brand = serializers.RegexField(r"^[A-Za-z0-9][A-Za-z0-9 .&-]{1,40}$")
    amount = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=Decimal("1.00"),
        max_value=Decimal("500000.00"),
    )


class ParkingHoldSerializer(serializers.Serializer):
    """Not wired to /api/v1. Kept beside domain/parkpe/parking.py."""

    bay = serializers.RegexField(r"^[A-Za-z0-9][A-Za-z0-9-]{0,15}$")
    amount = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=Decimal("1.00"),
        max_value=Decimal("500000.00"),
    )


class BbpsPaymentSerializer(serializers.Serializer):
    """Not wired to /api/v1. Kept beside domain/payswap/bbps.py."""

    biller = serializers.CharField(min_length=2, max_length=80, trim_whitespace=True)
    account = serializers.RegexField(r"^[A-Za-z0-9]{4,32}$")
    amount = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=Decimal("1.00"),
        max_value=Decimal("500000.00"),
    )
