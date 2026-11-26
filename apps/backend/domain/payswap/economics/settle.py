"""Write ServiceSettlement + TdsAccrual; optional BBPS dual-write."""

from __future__ import annotations

import json
import secrets
import time
from typing import Any

from core.actions import elapsed_ms, log_action
from django.utils import timezone
from domain.payswap.economics.catalogue import ensure_catalogue
from domain.payswap.economics.split import compute_economics
from models.models import BbpsTransaction, ServiceRateRow, ServiceSettlement, TdsAccrual


def settle_success(
    *,
    service: str,
    reference: str,
    user_id: str,
    amount_paise: int,
    external_id: str = "",
    category: str = "",
    has_gstin: bool = False,
    bbps_tx: BbpsTransaction | None = None,
    vendor_paise: int | None = None,
) -> dict[str, Any]:
    """Idempotent per (service, reference). Returns ledger instructions for the caller."""
    started = time.perf_counter()
    svc = (service or "bbps").strip().lower()
    ref = str(reference or "").strip()
    if not ref or not user_id:
        return {"applied": False, "reason": "missing_ref_or_user", "net_credit_paise": 0, "fee_paise": 0}

    existing = ServiceSettlement.objects.filter(service=svc, reference=ref).first()
    if existing:
        return {
            "applied": False,
            "reason": "already_settled",
            "net_credit_paise": int(existing.net_to_retailer_paise),
            "fee_paise": int(existing.service_charge_paise),
            "settlement_id": existing.settlement_id,
            "tds_paise": int(existing.tds_paise),
            "vendor_commission_paise": int(existing.vendor_commission_paise),
            "admin_revenue_paise": int(existing.admin_revenue_paise),
            "retailer_commission_paise": int(existing.retailer_commission_paise),
            "gst_paise": int(existing.gst_paise),
            "service_charge_paise": int(existing.service_charge_paise),
            "net_to_retailer_paise": int(existing.net_to_retailer_paise),
            "snapshot": existing.rate_snapshot or {},
        }

    if svc == "bbps" and not ServiceRateRow.objects.filter(service="bbps").exists():
        ensure_catalogue(service="bbps", actor="settle")

    split = compute_economics(
        service=svc,
        amount_paise=int(amount_paise),
        external_id=external_id,
        category=category,
        retailer_id=user_id,
        has_gstin=has_gstin,
        vendor_paise=vendor_paise,
    )
    settlement = ServiceSettlement.objects.create(
        settlement_id="stl-" + secrets.token_hex(10),
        service=svc,
        reference=ref,
        user_id=user_id,
        amount_paise=int(amount_paise),
        vendor_commission_paise=split["vendor_commission_paise"],
        admin_revenue_paise=split["admin_revenue_paise"],
        retailer_commission_paise=split["retailer_commission_paise"],
        service_charge_paise=split["service_charge_paise"],
        tds_paise=split["tds_paise"],
        gst_paise=split["gst_paise"],
        net_to_retailer_paise=split["net_to_retailer_paise"],
        rate_snapshot=split["snapshot"],
        state="settled",
    )

    if split["tds_paise"] > 0 and not TdsAccrual.objects.filter(service=svc, reference=ref).exists():
        TdsAccrual.objects.create(
            accrual_id="tds-" + secrets.token_hex(10),
            user_id=user_id,
            service=svc,
            reference=ref,
            month=timezone.localdate().strftime("%Y-%m"),
            tds_paise=split["tds_paise"],
            tds_paise_withheld=split["tds_paise"],
            commission_paise=split["retailer_commission_paise"],
            tds_rate_bps=int(split.get("tds_rate_bps") or 0),
            tds_basis=str(split.get("tds_basis") or "194h")[:16],
            status="open",
        )

    if bbps_tx is not None:
        bbps_tx.vendor_commission_paise = split["vendor_commission_paise"]
        bbps_tx.admin_revenue_paise = split["admin_revenue_paise"]
        bbps_tx.retailer_commission_paise = split["retailer_commission_paise"]
        bbps_tx.tds_paise = split["tds_paise"]
        bbps_tx.gst_paise = split["gst_paise"]
        bbps_tx.commission_paise = split["net_to_retailer_paise"]
        bbps_tx.commission_rate_snapshot = split["snapshot"]
        bbps_tx.save(
            update_fields=[
                "vendor_commission_paise",
                "admin_revenue_paise",
                "retailer_commission_paise",
                "tds_paise",
                "gst_paise",
                "commission_paise",
                "commission_rate_snapshot",
                "updated_at",
            ]
        )

    log_action(
        action="domain.payswap.economics.settle",
        outcome="ok",
        status=200,
        duration_ms=elapsed_ms(started),
        target_id=ref,
        request=json.dumps({"service": svc, "external_id": external_id, "amount_paise": int(amount_paise)}),
        response=json.dumps(
            {
                "vendor": split["vendor_commission_paise"],
                "admin": split["admin_revenue_paise"],
                "retailer": split["retailer_commission_paise"],
                "fee": split["service_charge_paise"],
                "tds": split["tds_paise"],
                "net": split["net_to_retailer_paise"],
                "rate_source": split["rate_source"],
            }
        ),
    )
    return {
        "applied": True,
        "settlement_id": settlement.settlement_id,
        **split,
    }


def apply_vendor_discount(*, reference: str, vendor_paise: int, actor: str = "system") -> dict[str, Any]:
    """Fill a zero BBPS settlement from Mobikwik's actual discount and credit the retailer once."""
    from domain.payswap.wallet import credit_commission

    ref = str(reference or "").strip()
    vendor = int(vendor_paise)
    if vendor <= 0 or not ref:
        return {"applied": False, "reason": "no_discount", "net_credit_paise": 0}
    settlement = ServiceSettlement.objects.filter(service="bbps", reference=ref).first()
    tx = BbpsTransaction.objects.filter(reference=ref).first()
    if settlement is None or tx is None:
        return {"applied": False, "reason": "missing", "net_credit_paise": 0}
    if int(settlement.vendor_commission_paise or 0) > 0:
        paid = credit_commission(tx.user_id, amount_paise=int(settlement.net_to_retailer_paise or 0), reference=ref, actor=actor)
        return {"applied": False, "reason": "already_settled", "net_credit_paise": int(settlement.net_to_retailer_paise or 0), "credited_paise": paid}
    from domain.payswap.commission import retailer_has_gstin

    split = compute_economics(
        service="bbps",
        amount_paise=int(tx.amount_paise),
        external_id=tx.operator_id,
        category=tx.category,
        retailer_id=tx.user_id,
        has_gstin=retailer_has_gstin(tx.user_id),
        vendor_paise=vendor,
    )
    settlement.vendor_commission_paise = split["vendor_commission_paise"]
    settlement.admin_revenue_paise = split["admin_revenue_paise"]
    settlement.retailer_commission_paise = split["retailer_commission_paise"]
    settlement.tds_paise = split["tds_paise"]
    settlement.gst_paise = split["gst_paise"]
    settlement.net_to_retailer_paise = split["net_to_retailer_paise"]
    settlement.rate_snapshot = split["snapshot"]
    settlement.save(
        update_fields=[
            "vendor_commission_paise",
            "admin_revenue_paise",
            "retailer_commission_paise",
            "tds_paise",
            "gst_paise",
            "net_to_retailer_paise",
            "rate_snapshot",
            "updated_at",
        ]
    )
    tx.vendor_commission_paise = split["vendor_commission_paise"]
    tx.admin_revenue_paise = split["admin_revenue_paise"]
    tx.retailer_commission_paise = split["retailer_commission_paise"]
    tx.tds_paise = split["tds_paise"]
    tx.gst_paise = split["gst_paise"]
    tx.commission_paise = split["net_to_retailer_paise"]
    tx.commission_rate_snapshot = split["snapshot"]
    tx.save(
        update_fields=[
            "vendor_commission_paise",
            "admin_revenue_paise",
            "retailer_commission_paise",
            "tds_paise",
            "gst_paise",
            "commission_paise",
            "commission_rate_snapshot",
            "updated_at",
        ]
    )
    if split["tds_paise"] > 0 and not TdsAccrual.objects.filter(service="bbps", reference=ref).exists():
        TdsAccrual.objects.create(
            accrual_id="tds-" + secrets.token_hex(10),
            user_id=tx.user_id,
            service="bbps",
            reference=ref,
            month=timezone.localdate().strftime("%Y-%m"),
            tds_paise=split["tds_paise"],
            tds_paise_withheld=split["tds_paise"],
            commission_paise=split["retailer_commission_paise"],
            tds_rate_bps=int(split.get("tds_rate_bps") or 0),
            tds_basis=str(split.get("tds_basis") or "194h")[:16],
            status="open",
        )
    paid = credit_commission(tx.user_id, amount_paise=int(split["net_to_retailer_paise"]), reference=ref, actor=actor)
    log_action(
        action="domain.payswap.economics.settle.discount",
        outcome="ok",
        status=200,
        duration_ms=0,
        target_id=ref,
        request=json.dumps({"vendor_paise": vendor, "actor": actor}),
        response=json.dumps({"net": split["net_to_retailer_paise"], "credited_paise": paid, "tds": split["tds_paise"]}),
    )
    return {"applied": True, "credited_paise": paid, **split}
