"""Per-service economics policy (monetization mode, TDS/GST shares)."""

from __future__ import annotations

import json
from typing import Any

from core.actions import log_action
from domain.payswap.economics._money import paise_to_rupees_str
from models.models import ServiceEconomicsPolicy

KNOWN_SERVICES = ("bbps", "aeps", "dmt", "recharge", "vouchers")


def _company_tds() -> dict[str, Any]:
    """TAN and the 206AA rate live once on CommissionPolicy, not on each service."""
    from models.models import CommissionPolicy

    row = CommissionPolicy.objects.filter(key="payswap_default").first()
    tan = ""
    no_pan = 2000
    if row is not None:
        tan = str(getattr(row, "deductor_tan", "") or "").strip().upper()
        no_pan = int(getattr(row, "no_pan_tds_rate_bps", 2000) or 2000)
    return {
        "deductor_tan": tan,
        "no_pan_tds_rate_bps": no_pan,
        "no_pan_tds_rate_percent": round(no_pan / 100, 2),
    }


def get_or_create_service_policy(service: str = "bbps") -> ServiceEconomicsPolicy:
    svc = (service or "bbps").strip().lower() or "bbps"
    row, _ = ServiceEconomicsPolicy.objects.get_or_create(
        service=svc,
        defaults={
            "monetization_mode": "service_charge" if svc == "vouchers" else "vendor_share",
            "admin_share_bps": 3000,
            "tds_rate_bps": 200,
            "gst_rate_bps": 1800,
            "tds_threshold_paise": 2_000_000,
            "withhold_tds_always": True,
            "active": True,
        },
    )
    return row


def serialize_service_policy(row: ServiceEconomicsPolicy | None = None, *, service: str = "bbps") -> dict[str, Any]:
    row = row or get_or_create_service_policy(service)
    return {
        "service": row.service,
        "monetization_mode": row.monetization_mode,
        "admin_share_bps": int(row.admin_share_bps),
        "admin_share_percent": round(int(row.admin_share_bps) / 100, 2),
        "retailer_share_percent": round((10000 - int(row.admin_share_bps)) / 100, 2),
        "tds_rate_bps": int(row.tds_rate_bps),
        "tds_rate_percent": round(int(row.tds_rate_bps) / 100, 2),
        "gst_rate_bps": int(row.gst_rate_bps),
        "gst_rate_percent": round(int(row.gst_rate_bps) / 100, 2),
        "tds_threshold_paise": int(row.tds_threshold_paise),
        "tds_threshold": paise_to_rupees_str(int(row.tds_threshold_paise)),
        "withhold_tds_always": bool(row.withhold_tds_always),
        **_company_tds(),
        "rates_file_mtime": float(row.rates_file_mtime or 0),
        "rates_imported_at": row.rates_imported_at.isoformat() if row.rates_imported_at else "",
        "active": bool(row.active),
        "updated_by": row.updated_by,
        "updated_at": row.updated_at.isoformat() if row.updated_at else "",
    }


def update_service_policy(service: str = "bbps", *, actor: str = "", **fields: Any) -> dict[str, Any]:
    row = get_or_create_service_policy(service)
    if "monetization_mode" in fields and fields["monetization_mode"] is not None:
        mode = str(fields["monetization_mode"]).strip()
        if mode in {"vendor_share", "service_charge"}:
            row.monetization_mode = mode
    if "admin_share_bps" in fields and fields["admin_share_bps"] is not None:
        row.admin_share_bps = max(0, min(10000, int(fields["admin_share_bps"])))
    if "tds_rate_bps" in fields and fields["tds_rate_bps"] is not None:
        row.tds_rate_bps = max(0, min(10000, int(fields["tds_rate_bps"])))
    if "gst_rate_bps" in fields and fields["gst_rate_bps"] is not None:
        row.gst_rate_bps = max(0, min(10000, int(fields["gst_rate_bps"])))
    if "tds_threshold_paise" in fields and fields["tds_threshold_paise"] is not None:
        row.tds_threshold_paise = max(0, int(fields["tds_threshold_paise"]))
    if "withhold_tds_always" in fields and fields["withhold_tds_always"] is not None:
        row.withhold_tds_always = bool(fields["withhold_tds_always"])
    if "active" in fields and fields["active"] is not None:
        row.active = bool(fields["active"])
    row.updated_by = actor or row.updated_by
    row.save()
    out = serialize_service_policy(row)
    log_action(
        action="domain.payswap.economics.policy",
        outcome="ok",
        status=200,
        duration_ms=0,
        target_id=row.service,
        request=json.dumps({k: fields[k] for k in fields if fields[k] is not None}),
        response=json.dumps(out),
    )
    return out


def list_service_policies() -> dict[str, Any]:
    rows = []
    for svc in KNOWN_SERVICES:
        rows.append(serialize_service_policy(service=svc))
    return {"services": rows}
