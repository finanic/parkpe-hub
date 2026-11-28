"""Resolve service_charge fees from ServiceFeeRule."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from domain.payswap.economics._money import HUNDRED, PAISE, d, to_paise
from models.models import ServiceFeeRule


def resolve_fee_paise(
    *,
    service: str,
    amount_paise: int,
    external_id: str = "",
    category: str = "",
) -> dict[str, Any]:
    svc = (service or "").strip().lower()
    op = str(external_id or "").strip()
    cat = str(category or "").strip()
    qs = ServiceFeeRule.objects.filter(service=svc, active=True)
    rule = None
    if op:
        rule = qs.filter(match_key=op).first()
    if not rule and cat:
        rule = qs.filter(category__iexact=cat).first()
    if not rule:
        rule = qs.filter(match_key__in=["", "*"]).order_by("id").first()
    if not rule:
        return {
            "service_charge_paise": 0,
            "admin_revenue_paise": 0,
            "retailer_commission_paise": 0,
            "who_pays": "wallet",
            "source": "none",
        }

    value = d(rule.fee_value)
    if rule.fee_type == "percent":
        fee = to_paise((Decimal(int(amount_paise)) / PAISE) * value / HUNDRED)
    else:
        fee = to_paise(value)
    fee = max(int(rule.min_fee_paise or 0), fee)
    if int(rule.max_fee_paise or 0) > 0:
        fee = min(fee, int(rule.max_fee_paise))
    retain_bps = max(0, min(10000, int(rule.admin_retain_bps or 10000)))
    admin = int((Decimal(fee) * Decimal(retain_bps) / Decimal(10000)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    retailer = max(0, fee - admin)
    return {
        "service_charge_paise": fee,
        "admin_revenue_paise": admin,
        "retailer_commission_paise": retailer,
        "who_pays": rule.who_pays or "wallet",
        "source": "fee_rule",
        "fee_type": rule.fee_type,
        "fee_value": str(rule.fee_value),
    }
