"""Request bodies for /api/v1.

Mounted on Django: SessionInitiateSerializer
(POST /api/v1/parkpe/sessions/initiate, api/v1/routes/parkpe.py),
VoucherOrderSerializer
(POST /api/v1/payswap/vouchers/order, api/v1/routes/payswap.py), and
BbpsFetchBillSerializer / BbpsPaymentSerializer
(POST /api/v1/payswap/bbps/fetch-bill and /api/v1/payswap/bbps/pay).
Field names line up with packages/contracts. A bad body is code validation
through config/exceptions.py.

ParkingHoldSerializer is not wired to any /api/v1 route.
domain/parkpe/parking.py is present, unmounted.
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


class BbpsFetchBillSerializer(serializers.Serializer):
    """POST /api/v1/payswap/bbps/fetch-bill.

    Route: api/v1/routes/payswap.py. Caller: apps/payswap/js/hub.js.
    """

    biller = serializers.CharField(min_length=1, max_length=80, trim_whitespace=True)
    account = serializers.RegexField(r"^[A-Za-z0-9._/@ -]{2,64}$")
    circle = serializers.CharField(required=False, allow_blank=True, max_length=32, default="")
    payment_mode = serializers.CharField(required=False, allow_blank=True, max_length=32, default="")
    ad_params = serializers.DictField(
        child=serializers.CharField(allow_blank=True, max_length=120),
        required=False,
        default=dict,
    )


class BbpsPaymentSerializer(serializers.Serializer):
    """POST /api/v1/payswap/bbps/pay.

    Route: api/v1/routes/payswap.py. Caller: apps/payswap/js/hub.js.
    """

    biller = serializers.CharField(min_length=1, max_length=80, trim_whitespace=True)
    account = serializers.RegexField(r"^[A-Za-z0-9._/@ -]{2,64}$")
    amount = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=Decimal("1.00"),
        max_value=Decimal("500000.00"),
    )
    circle = serializers.CharField(required=False, allow_blank=True, max_length=32, default="")
    customer_mobile = serializers.RegexField(r"^(\d{10})?$", required=False, allow_blank=True, default="")
    remitter_name = serializers.CharField(required=False, allow_blank=True, max_length=80, default="")
    payment_mode = serializers.CharField(required=False, allow_blank=True, max_length=32, default="Cash")
    payment_rail = serializers.ChoiceField(choices=["wallet", "pg"], required=False, default="wallet")
    wallet_pin = serializers.CharField(required=False, allow_blank=True, max_length=12, default="")
    ad_params = serializers.DictField(
        child=serializers.CharField(allow_blank=True, max_length=120),
        required=False,
        default=dict,
    )


class WalletTopupRequestSerializer(serializers.Serializer):
    amount = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=Decimal("1.00"),
        max_value=Decimal("500000.00"),
    )
    mode = serializers.ChoiceField(choices=["BANK_TRANSFER", "UPI"], default="BANK_TRANSFER")
    utr = serializers.CharField(min_length=6, max_length=64, trim_whitespace=True)
    remarks = serializers.CharField(required=False, allow_blank=True, max_length=200, default="")


class WalletPinSerializer(serializers.Serializer):
    new_pin = serializers.RegexField(r"^\d{4,6}$")
    current_pin = serializers.CharField(required=False, allow_blank=True, max_length=12, default="")


class PgOrderCreateSerializer(serializers.Serializer):
    amount = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=Decimal("1.00"),
        max_value=Decimal("500000.00"),
    )
    customer_phone = serializers.RegexField(r"^(\d{10})?$", required=False, allow_blank=True, default="")


class PgOrderVerifySerializer(serializers.Serializer):
    pg_order_id = serializers.RegexField(r"^[A-Za-z0-9_-]{6,64}$")


class VehicleAddSerializer(serializers.Serializer):
    registration = serializers.RegexField(r"^[A-Za-z0-9 -]{4,20}$")
    make_model = serializers.CharField(required=False, allow_blank=True, max_length=80, default="")
    color = serializers.CharField(required=False, allow_blank=True, max_length=40, default="")
    fastag_linked = serializers.BooleanField(required=False, default=False)
