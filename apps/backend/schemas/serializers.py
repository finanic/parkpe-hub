"""Request bodies for /api/v1 money writes.

Field names are the ones packages/contracts will carry for these calls.
Error code on failure is validation (config/exceptions.py).
ParkPe hold: apps/parkpe/features/parking.
PaySwap bill: apps/payswap/features/bbps.
"""

from __future__ import annotations

from decimal import Decimal

from rest_framework import serializers


class SessionInitiateSerializer(serializers.Serializer):
    """POST /api/v1/parkpe/sessions/initiate. Caller: apps/parkpe features/qr-connect."""

    site_code = serializers.RegexField(r"^[A-Za-z0-9][A-Za-z0-9-]{1,31}$")
    bay = serializers.RegexField(r"^[A-Za-z0-9][A-Za-z0-9-]{0,15}$")
    vehicle = serializers.RegexField(r"^[A-Za-z0-9]{4,16}$")


class VoucherOrderSerializer(serializers.Serializer):
    """POST /api/v1/payswap/vouchers/order. Caller: apps/payswap features/vouchers."""

    brand = serializers.RegexField(r"^[A-Za-z0-9][A-Za-z0-9 .&-]{1,40}$")
    amount = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=Decimal("1.00"),
        max_value=Decimal("500000.00"),
    )


class ParkingHoldSerializer(serializers.Serializer):
    bay = serializers.RegexField(r"^[A-Za-z0-9][A-Za-z0-9-]{0,15}$")
    amount = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=Decimal("1.00"),
        max_value=Decimal("500000.00"),
    )


class BbpsPaymentSerializer(serializers.Serializer):
    biller = serializers.CharField(min_length=2, max_length=80, trim_whitespace=True)
    account = serializers.RegexField(r"^[A-Za-z0-9]{4,32}$")
    amount = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=Decimal("1.00"),
        max_value=Decimal("500000.00"),
    )
