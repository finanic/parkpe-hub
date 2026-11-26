"""Mode-aware commission / fee split + TDS + GST."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from domain.payswap.economics._money import HUNDRED, PAISE, d, to_paise
from domain.payswap.economics.catalogue import resolve_rate_row
from domain.payswap.economics.fee import resolve_fee_paise
from domain.payswap.economics.policy import get_or_create_service_policy
from models.models import RetailerServiceOverride, ServiceEconomicsPolicy


def vendor_commission_paise(*, amount_paise: int, rate: dict[str, Any] | None) -> int:
    if not rate:
        return 0
    if int(amount_paise) < int(rate.get("min_txn_paise") or 0):
        return 0
    value = d(rate.get("rate_value"))
    if value <= 0:
        return 0
    if str(rate.get("rate_type") or "") == "percent":
        rupees = Decimal(int(amount_paise)) / PAISE
        return to_paise(rupees * value / HUNDRED)
    return to_paise(value)


def compute_economics(
    *,
    service: str,
    amount_paise: int,
    external_id: str = "",
    category: str = "",
    retailer_id: str = "",
    has_gstin: bool = False,
    policy: ServiceEconomicsPolicy | None = None,
    vendor_paise: int | None = None,
) -> dict[str, Any]:
    policy = policy or get_or_create_service_policy(service)
    mode = str(policy.monetization_mode or "vendor_share")

    if mode == "service_charge":
        fee = resolve_fee_paise(service=service, amount_paise=amount_paise, external_id=external_id, category=category)
        retailer_gross = int(fee["retailer_commission_paise"])
        admin_revenue = int(fee["admin_revenue_paise"])
        service_charge = int(fee["service_charge_paise"])
        vendor = 0
        rate_source = fee.get("source", "none")
        rate_snap = {"mode": mode, **{k: fee[k] for k in fee if k != "source"}, "source": rate_source}
    else:
        override = None
        if retailer_id:
            override = RetailerServiceOverride.objects.filter(
                user_id=retailer_id, service=service, active=True
            ).first()
        from domain.payswap.commission import effective_retailer_admin_bps

        admin_bps, share_source = effective_retailer_admin_bps(
            override,
            external_id=external_id,
            category=category,
            policy_bps=int(policy.admin_share_bps),
        )
        if vendor_paise is not None:
            # Mobikwik discountprice is the commission actually given, including below the sheet minimum.
            vendor = max(0, int(vendor_paise))
            rate_source = "vendor_discount"
            rate_snap = {
                "mode": mode,
                "rate": {
                    "external_id": external_id,
                    "category": category,
                    "rate_value": "0",
                    "rate_type": "",
                    "min_txn_paise": 0,
                    "source": rate_source,
                    "vendor_paise": vendor,
                },
                "admin_share_bps": admin_bps,
                "share_source": share_source,
            }
        else:
            rate = resolve_rate_row(
                service=service,
                external_id=external_id,
                category=category,
                retailer_id=retailer_id,
            )
            vendor = vendor_commission_paise(amount_paise=amount_paise, rate=rate)
            rate_source = (rate or {}).get("source", "none")
            rate_snap = {
                "mode": mode,
                "rate": {
                    "external_id": (rate or {}).get("external_id", external_id),
                    "category": (rate or {}).get("category", category),
                    "rate_value": str((rate or {}).get("rate_value", "0")),
                    "rate_type": (rate or {}).get("rate_type", ""),
                    "min_txn_paise": int((rate or {}).get("min_txn_paise") or 0),
                    "source": rate_source,
                },
                "admin_share_bps": admin_bps,
                "share_source": share_source,
            }
        admin_revenue = int(
            (Decimal(vendor) * Decimal(admin_bps) / Decimal(10000)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        )
        retailer_gross = max(0, vendor - admin_revenue)
        service_charge = 0

    gst_paise = 0
    if has_gstin and retailer_gross > 0 and int(policy.gst_rate_bps) > 0:
        gst_paise = int(
            (Decimal(retailer_gross) * Decimal(int(policy.gst_rate_bps)) / Decimal(10000)).quantize(
                Decimal("1"), rounding=ROUND_HALF_UP
            )
        )
    from domain.payswap.commission import resolve_tds_rate

    decision = resolve_tds_rate(
        retailer_id=retailer_id,
        policy_rate_bps=int(policy.tds_rate_bps),
        withhold=bool(policy.withhold_tds_always),
    )
    tds_rate = int(decision["tds_rate_bps"])
    tds_paise = 0
    if retailer_gross > 0 and tds_rate > 0:
        tds_paise = int(
            (Decimal(retailer_gross) * Decimal(tds_rate) / Decimal(10000)).quantize(
                Decimal("1"), rounding=ROUND_HALF_UP
            )
        )
    net = max(0, retailer_gross - tds_paise)
    rate_snap["tds_rate_bps"] = tds_rate
    rate_snap["tds_basis"] = decision["tds_basis"]
    rate_snap["tds_section"] = decision["tds_section"]
    rate_snap["gst_rate_bps"] = int(policy.gst_rate_bps) if has_gstin else 0
    rate_snap["has_gstin"] = bool(has_gstin)
    return {
        "monetization_mode": mode,
        "vendor_commission_paise": vendor,
        "admin_revenue_paise": admin_revenue,
        "retailer_commission_paise": retailer_gross,
        "service_charge_paise": service_charge,
        "tds_paise": tds_paise,
        "tds_rate_bps": tds_rate,
        "tds_basis": decision["tds_basis"],
        "tds_section": decision["tds_section"],
        "gst_paise": gst_paise,
        "net_to_retailer_paise": net,
        "net_credit_paise": net,  # alias for wallet capture
        "fee_paise": service_charge if mode == "service_charge" else 0,
        "rate_source": rate_source,
        "snapshot": rate_snap,
    }
