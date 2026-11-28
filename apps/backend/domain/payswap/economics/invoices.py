"""Monthly GST invoices from ServiceSettlement (all services)."""

from __future__ import annotations

import json
import secrets
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from core.actions import log_action
from django.db.models import Sum
from django.utils import timezone
from domain.payswap.economics._money import paise_to_rupees_str
from domain.payswap.economics.policy import get_or_create_service_policy
from models.models import CommissionInvoice, ServiceSettlement


def previous_calendar_month(today=None) -> str:
    day = today or timezone.localdate()
    year, month = day.year, day.month
    if month == 1:
        return f"{year - 1}-12"
    return f"{year}-{month - 1:02d}"


def create_monthly_invoice(
    *,
    user_id: str,
    month: str,
    gstin: str,
    actor: str = "",
    place_of_supply_same_state: bool = True,
    service: str = "all",
) -> dict[str, Any]:
    month = month or timezone.localdate().strftime("%Y-%m")
    existing = CommissionInvoice.objects.filter(user_id=user_id, month=month).first()
    if existing:
        return serialize_invoice(existing)

    qs = ServiceSettlement.objects.filter(
        user_id=user_id,
        state="settled",
        created_at__year=int(month[:4]),
        created_at__month=int(month[5:7]),
        retailer_commission_paise__gt=0,
    ).order_by("created_at")
    if service and service != "all":
        qs = qs.filter(service=service.strip().lower())
    if not qs.exists():
        raise ValueError("No commission rows for this retailer/month.")

    lines = []
    taxable = 0
    for row in qs:
        taxable += int(row.retailer_commission_paise)
        lines.append(
            {
                "service": row.service,
                "reference": row.reference,
                "amount": paise_to_rupees_str(int(row.amount_paise)),
                "commission": paise_to_rupees_str(int(row.retailer_commission_paise)),
                "tds": paise_to_rupees_str(int(row.tds_paise)),
            }
        )
    policy = get_or_create_service_policy("bbps")
    gst = int(
        (Decimal(taxable) * Decimal(int(policy.gst_rate_bps)) / Decimal(10000)).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        )
    )
    if place_of_supply_same_state:
        half = gst // 2
        cgst, sgst, igst = half, gst - half, 0
    else:
        cgst, sgst, igst = 0, 0, gst

    inv = CommissionInvoice.objects.create(
        invoice_id="inv-" + secrets.token_hex(8),
        invoice_no=f"PS-{month.replace('-', '')}-{secrets.token_hex(3).upper()}",
        user_id=user_id,
        gstin=(gstin or "").strip().upper()[:20],
        month=month,
        taxable_paise=taxable,
        cgst_paise=cgst,
        sgst_paise=sgst,
        igst_paise=igst,
        total_paise=taxable + gst,
        lines=lines,
        status="draft",
        created_by=actor or "",
    )
    log_action(
        action="domain.payswap.economics.invoice",
        outcome="ok",
        status=200,
        duration_ms=0,
        target_id=inv.invoice_no,
        request=json.dumps({"user_id": user_id, "month": month}),
        response=json.dumps({"invoice_no": inv.invoice_no, "taxable": taxable, "gst": gst}),
    )
    return serialize_invoice(inv)


def serialize_invoice(row: CommissionInvoice) -> dict[str, Any]:
    return {
        "invoice_id": row.invoice_id,
        "invoice_no": row.invoice_no,
        "user_id": row.user_id,
        "gstin": row.gstin,
        "month": row.month,
        "taxable": paise_to_rupees_str(int(row.taxable_paise)),
        "cgst": paise_to_rupees_str(int(row.cgst_paise)),
        "sgst": paise_to_rupees_str(int(row.sgst_paise)),
        "igst": paise_to_rupees_str(int(row.igst_paise)),
        "total": paise_to_rupees_str(int(row.total_paise)),
        "lines": list(row.lines or []),
        "status": row.status,
        "created_at": row.created_at.isoformat() if row.created_at else "",
        "html": invoice_html(row),
    }


def invoice_html(row: CommissionInvoice) -> str:
    lines = "".join(
        f"<tr><td>{item.get('service','')}</td><td>{item.get('reference','')}</td>"
        f"<td>{item.get('amount','')}</td><td>{item.get('commission','')}</td></tr>"
        for item in (row.lines or [])
    )
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>{row.invoice_no}</title>
<style>body{{font-family:system-ui,sans-serif;padding:24px}} table{{border-collapse:collapse;width:100%}}
td,th{{border:1px solid #ccc;padding:6px 8px;text-align:left}} h1{{margin:0 0 8px}}</style></head>
<body><h1>Commission tax invoice (draft)</h1>
<p>Invoice <strong>{row.invoice_no}</strong> · Month {row.month}<br>
Retailer {row.user_id}<br>GSTIN {row.gstin or '—'}</p>
<table><thead><tr><th>Service</th><th>Ref</th><th>Txn</th><th>Commission</th></tr></thead>
<tbody>{lines}</tbody></table>
<p>Taxable ₹{paise_to_rupees_str(int(row.taxable_paise))} ·
CGST ₹{paise_to_rupees_str(int(row.cgst_paise))} ·
SGST ₹{paise_to_rupees_str(int(row.sgst_paise))} ·
IGST ₹{paise_to_rupees_str(int(row.igst_paise))}<br>
<strong>Total ₹{paise_to_rupees_str(int(row.total_paise))}</strong></p>
<p><small>Draft for books — confirm with CA before filing.</small></p></body></html>"""


def generate_monthly_invoices(*, month: str = "", actor: str = "cron") -> dict[str, Any]:
    from domain.payswap.commission import retailer_gstin

    month = (month or "").strip() or previous_calendar_month()
    user_ids = (
        ServiceSettlement.objects.filter(
            state="settled",
            created_at__year=int(month[:4]),
            created_at__month=int(month[5:7]),
            retailer_commission_paise__gt=0,
        )
        .values_list("user_id", flat=True)
        .distinct()
    )
    created, reused, skipped = [], [], []
    for user_id in user_ids:
        gstin = retailer_gstin(user_id)
        if not gstin:
            skipped.append({"user_id": user_id, "reason": "no_gstin"})
            continue
        existing = CommissionInvoice.objects.filter(user_id=user_id, month=month).first()
        try:
            inv = create_monthly_invoice(user_id=user_id, month=month, gstin=gstin, actor=actor)
        except ValueError as exc:
            skipped.append({"user_id": user_id, "reason": str(exc)})
            continue
        bucket = reused if existing else created
        bucket.append({"user_id": user_id, "invoice_no": inv["invoice_no"]})
    out = {
        "month": month,
        "created": len(created),
        "reused": len(reused),
        "skipped": skipped,
        "invoices": created + reused,
    }
    log_action(
        action="domain.payswap.economics.invoice.batch",
        outcome="ok",
        status=200,
        duration_ms=0,
        target_id=month,
        request=json.dumps({"month": month, "actor": actor}),
        response=json.dumps({"created": out["created"], "reused": out["reused"], "skipped": len(skipped)}),
    )
    return out


def retailer_settlement_summary(*, user_id: str, month: str = "", service: str = "all") -> dict[str, Any]:
    month = month or timezone.localdate().strftime("%Y-%m")
    qs = ServiceSettlement.objects.filter(
        user_id=user_id,
        state="settled",
        created_at__year=int(month[:4]),
        created_at__month=int(month[5:7]),
    )
    if service and service != "all":
        qs = qs.filter(service=service.strip().lower())
    agg = qs.aggregate(
        retailer=Sum("retailer_commission_paise"),
        tds=Sum("tds_paise"),
        net=Sum("net_to_retailer_paise"),
        gst=Sum("gst_paise"),
        fee=Sum("service_charge_paise"),
    )
    invoices = [
        serialize_invoice(row)
        for row in CommissionInvoice.objects.filter(user_id=user_id).order_by("-month")[:12]
    ]
    from domain.payswap.commission import retailer_has_gstin, retailer_tds_position

    position = retailer_tds_position(user_id)
    return {
        "month": month,
        "service": service or "all",
        "txn_count": qs.count(),
        "commission": paise_to_rupees_str(int(agg["retailer"] or 0)),
        "tds": paise_to_rupees_str(int(agg["tds"] or 0)),
        "net_credited": paise_to_rupees_str(int(agg["net"] or 0)),
        "gst": paise_to_rupees_str(int(agg["gst"] or 0)),
        "service_charge": paise_to_rupees_str(int(agg["fee"] or 0)),
        "has_gstin": retailer_has_gstin(user_id),
        "pan_on_file": bool(position.get("pan_on_file")),
        "tds_section": position.get("tds_section") or "194H",
        "tds_rate_percent": position.get("tds_rate_percent"),
        "tds_rule": position.get("rule") or "",
        "invoices": invoices,
    }


def settlement_set_view(snapshot: dict | None) -> dict[str, str]:
    """Configured rate versus the money that later settled. Blank sheet values stay 'No sheet rate'."""
    snap = snapshot if isinstance(snapshot, dict) else {}
    rate = snap.get("rate") if isinstance(snap.get("rate"), dict) else {}
    source = str(rate.get("source") or snap.get("source") or "none")
    value = str(rate.get("rate_value") or "").strip()
    kind = str(rate.get("rate_type") or "")
    share = ""
    bps = snap.get("admin_share_bps")
    if bps is not None:
        try:
            share = f"{int(bps) / 100:g}%"
        except (TypeError, ValueError):
            share = ""
    blank = {"", "0", "0.0", "0.00", "0.000", "0.000000"}
    if source == "vendor_discount":
        label = "Discount price"
    elif kind == "percent" and value not in blank:
        label = f"{value}%"
    elif value not in blank:
        label = f"₹{value}"
    else:
        label = "No sheet rate"
    return {"set_label": label, "set_share": share, "set_source": source}


def revenue_report(*, month: str = "", service: str = "all", limit: int = 50) -> dict[str, Any]:
    qs = ServiceSettlement.objects.filter(state="settled")
    if service and service != "all":
        qs = qs.filter(service=service.strip().lower())
    if month:
        qs = qs.filter(created_at__year=int(month[:4]), created_at__month=int(month[5:7]))
    agg = qs.aggregate(
        volume=Sum("amount_paise"),
        vendor=Sum("vendor_commission_paise"),
        admin=Sum("admin_revenue_paise"),
        retailer=Sum("retailer_commission_paise"),
        tds=Sum("tds_paise"),
        gst=Sum("gst_paise"),
        net=Sum("net_to_retailer_paise"),
        fee=Sum("service_charge_paise"),
    )
    recent = list(qs.order_by("-created_at")[: max(1, min(int(limit), 200))])
    return {
        "month": month or timezone.localdate().strftime("%Y-%m"),
        "service": service or "all",
        "totals": {
            "txn_count": qs.count(),
            "volume": paise_to_rupees_str(int(agg["volume"] or 0)),
            "vendor_commission": paise_to_rupees_str(int(agg["vendor"] or 0)),
            "admin_revenue": paise_to_rupees_str(int(agg["admin"] or 0)),
            "retailer_commission": paise_to_rupees_str(int(agg["retailer"] or 0)),
            "tds": paise_to_rupees_str(int(agg["tds"] or 0)),
            "gst": paise_to_rupees_str(int(agg["gst"] or 0)),
            "net_credited": paise_to_rupees_str(int(agg["net"] or 0)),
            "service_charge": paise_to_rupees_str(int(agg["fee"] or 0)),
        },
        "recent": [
            {
                "service": r.service,
                "reference": r.reference,
                "user_id": r.user_id,
                "amount": paise_to_rupees_str(int(r.amount_paise)),
                "vendor_commission": paise_to_rupees_str(int(r.vendor_commission_paise)),
                "admin_revenue": paise_to_rupees_str(int(r.admin_revenue_paise)),
                "retailer_commission": paise_to_rupees_str(int(r.retailer_commission_paise)),
                "tds": paise_to_rupees_str(int(r.tds_paise)),
                "service_charge": paise_to_rupees_str(int(r.service_charge_paise)),
                "net_credit": paise_to_rupees_str(int(r.net_to_retailer_paise)),
                "created_at": r.created_at.isoformat() if r.created_at else "",
                **settlement_set_view(r.rate_snapshot),
            }
            for r in recent
        ],
    }
