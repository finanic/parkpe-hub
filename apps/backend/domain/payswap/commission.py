"""BBPS vendor commission split, TDS (194H), and GST helpers for PaySwap.

Admin policy + Mobikwik Excel rates live in hub_models. BBPS success in
domain/payswap/bbps.py calls settle_commission() to credit net commission
and open a TdsAccrual row. Desk routes expose policy/rates/revenue/TDS.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import sqlite3
import sys
import time
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any

from core.actions import elapsed_ms, log_action
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from models.models import (
    BbpsTransaction,
    CommissionInvoice,
    CommissionPolicy,
    RetailerCommissionOverride,
    RetailerTdsCertificate,
    TdsAccrual,
    VendorCommissionRate,
)

POLICY_KEY = "payswap_default"
TDS_SECTION = "194H"
NO_PAN_TDS_BPS = 2000  # 20% u/s 206AA
CERT_RE = re.compile(r"^[A-Z0-9][A-Z0-9./-]{4,39}$")
TAN_RE = re.compile(r"^[A-Z]{4}[0-9]{5}[A-Z]$")
PAN_RE = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")
MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
BSR_RE = re.compile(r"^\d{7}$")
SERIAL_RE = re.compile(r"^\d{1,10}$")
ZERO = Decimal("0")
HUNDRED = Decimal("100")
PAISE = Decimal("100")
DEFAULT_SHEET = Path(__file__).resolve().parents[2] / "data" / "mobikwik" / "commission-b2b.xlsx"


def default_commission_sheet_path() -> Path:
    return DEFAULT_SHEET


def retailer_has_gstin(user_id: str) -> bool:
    """Best-effort GSTIN lookup from auth.sqlite account_profiles (role=retailer)."""
    import os
    import sqlite3
    from pathlib import Path

    custom = os.environ.get("AUTH_DATA_DIR", "").strip()
    root = Path(custom) if custom else Path(__file__).resolve().parents[2] / "data"
    db = root / "auth.sqlite"
    if not db.is_file():
        return False
    try:
        with sqlite3.connect(str(db)) as conn:
            row = conn.execute(
                "SELECT gstin FROM account_profiles WHERE user_id = ? AND role = 'retailer' LIMIT 1",
                (user_id,),
            ).fetchone()
        return bool(row and str(row[0] or "").strip())
    except sqlite3.Error:
        return False


def retailer_gstin(user_id: str) -> str:
    import os
    import sqlite3
    from pathlib import Path

    custom = os.environ.get("AUTH_DATA_DIR", "").strip()
    root = Path(custom) if custom else Path(__file__).resolve().parents[2] / "data"
    db = root / "auth.sqlite"
    if not db.is_file():
        return ""
    try:
        with sqlite3.connect(str(db)) as conn:
            row = conn.execute(
                "SELECT gstin FROM account_profiles WHERE user_id = ? AND role = 'retailer' LIMIT 1",
                (user_id,),
            ).fetchone()
        return str(row[0] or "").strip().upper() if row else ""
    except sqlite3.Error:
        return ""


def _auth_sqlite_for_tds() -> Path | None:
    """Developer auth.sqlite stays out of manage.py test unless the test sets AUTH_DATA_DIR."""
    if "test" in sys.argv and not os.environ.get("AUTH_DATA_DIR", "").strip():
        return None
    return _auth_sqlite()


def _auth_sqlite() -> Path | None:
    custom = os.environ.get("AUTH_DATA_DIR", "").strip()
    root = Path(custom) if custom else Path(__file__).resolve().parents[2] / "data"
    db = root / "auth.sqlite"
    return db if db.is_file() else None


def fiscal_period(month: str) -> dict[str, str]:
    """Indian FY quarter for a YYYY-MM credit month. April opens Q1."""
    text = str(month or "").strip()
    if not MONTH_RE.fullmatch(text):
        return {"section": TDS_SECTION, "quarter": "", "financial_year": ""}
    year = int(text[0:4])
    mon = int(text[5:7])
    if mon >= 4:
        start = year
        quarter = ((mon - 4) // 3) + 1
    else:
        start = year - 1
        quarter = 4
    return {
        "section": TDS_SECTION,
        "quarter": f"Q{quarter}",
        "financial_year": f"{start}-{str(start + 1)[-2:]}",
    }


def _mask_pan(pan: str) -> str:
    if not PAN_RE.fullmatch(pan):
        return ""
    return pan[:5] + "····" + pan[-1]


def retailer_tax_identity(user_id: str) -> dict[str, Any]:
    """Deductee name and PAN for a TDS row.

    TdsAccrual.user_id is the retailer email. account_profiles.user_id is the
    auth user id, so this joins users.email. Full PAN stays in the desk
    response and is not written to the action log. found is false when the
    account cannot be read, so a missing file does not become a 206AA rate.
    """
    email = str(user_id or "").strip().lower()
    empty = {"email": email, "name": "", "pan": "", "pan_mask": "", "found": False}
    db = _auth_sqlite_for_tds()
    if not db or not email:
        return empty
    try:
        with sqlite3.connect(str(db)) as conn:
            row = conn.execute(
                """SELECT IFNULL(p.display_name, ''), IFNULL(p.pan_name, ''),
                          IFNULL(p.pan_name_hint, ''), IFNULL(p.pan, ''),
                          IFNULL(p.pan_mask, '')
                   FROM users u
                   LEFT JOIN account_profiles p
                     ON p.user_id = u.id AND p.role = 'retailer'
                   WHERE lower(u.email) = ? OR u.id = ?
                   LIMIT 1""",
                (email, user_id),
            ).fetchone()
            if row is None:
                row = conn.execute(
                    """SELECT IFNULL(display_name, ''), IFNULL(pan_name, ''),
                              IFNULL(pan_name_hint, ''), IFNULL(pan, ''),
                              IFNULL(pan_mask, '')
                       FROM account_profiles
                       WHERE role = 'retailer' AND lower(user_id) = ?
                       LIMIT 1""",
                    (email,),
                ).fetchone()
    except sqlite3.Error:
        return empty
    if not row:
        return empty
    name = next((str(part or "").strip() for part in row[:3] if str(part or "").strip()), "")
    pan = str(row[3] or "").strip().upper()
    if not PAN_RE.fullmatch(pan):
        pan = ""
    mask = str(row[4] or "").strip() or _mask_pan(pan)
    return {"email": email, "name": name, "pan": pan, "pan_mask": mask, "found": True}


def _certificate_for(user_id: str, on_date: date) -> RetailerTdsCertificate | None:
    email = str(user_id or "").strip().lower()
    if not email:
        return None
    row = (
        RetailerTdsCertificate.objects.filter(
            user_id=email, section=TDS_SECTION, status="approved", active=True
        )
        .order_by("-approved_at", "-id")
        .first()
    )
    if row is None or row.valid_from is None or row.valid_to is None:
        return None
    if row.valid_from <= on_date <= row.valid_to:
        return row
    return None


def resolve_tds_rate(
    *,
    retailer_id: str = "",
    policy_rate_bps: int = 200,
    withhold: bool = True,
    on_date: date | None = None,
) -> dict[str, Any]:
    """194H for a known PAN, 197 only for that certificate, 206AA when PAN is missing.

    An account that cannot be read keeps the 194H rate. A lower-deduction
    certificate applies only when that retailer has a PAN and the credit date
    sits inside the certificate.
    """
    policy_rate = max(0, min(10000, int(policy_rate_bps or 0)))
    if not withhold:
        return {"tds_rate_bps": 0, "tds_basis": "194h", "tds_section": TDS_SECTION}
    who = retailer_tax_identity(retailer_id) if retailer_id else {"found": False, "pan": ""}
    today = on_date or timezone.localdate()
    if who.get("found") and not who.get("pan"):
        no_pan = int(get_or_create_policy().no_pan_tds_rate_bps or NO_PAN_TDS_BPS)
        return {
            "tds_rate_bps": max(policy_rate, no_pan),
            "tds_basis": "206aa",
            "tds_section": "206AA",
        }
    cert = _certificate_for(retailer_id, today) if who.get("pan") else None
    if cert is not None:
        return {
            "tds_rate_bps": min(policy_rate, int(cert.rate_bps)),
            "tds_basis": "197",
            "tds_section": "197",
        }
    return {"tds_rate_bps": policy_rate, "tds_basis": "194h", "tds_section": TDS_SECTION}


def _basis_label(basis: str) -> str:
    return {"206aa": "206AA", "197": "197"}.get(str(basis or "194h"), "194H")


def _serialize_certificate(row: RetailerTdsCertificate | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "id": row.id,
        "user_id": row.user_id,
        "section": row.section,
        "status": row.status,
        "active": bool(row.active and row.status == "approved"),
        "certificate_no": row.certificate_no,
        "rate_bps": int(row.rate_bps),
        "rate_percent": round(int(row.rate_bps) / 100, 2),
        "valid_from": row.valid_from.isoformat() if row.valid_from else "",
        "valid_to": row.valid_to.isoformat() if row.valid_to else "",
        "reject_reason": row.reject_reason or "",
        "refunded": paise_to_rupees_str(int(row.refunded_paise or 0)),
    }


def _certificate_fields(fields: dict[str, Any]) -> tuple[str, int, date, date]:
    number = str(fields.get("certificate_no") or "").strip().upper()
    if not CERT_RE.fullmatch(number):
        raise ValueError("Certificate number must be 5 to 40 letters, digits, or . / -.")
    try:
        rate_bps = max(0, min(10000, int(fields.get("rate_bps"))))
    except (TypeError, ValueError) as exc:
        raise ValueError("Certificate TDS rate is required.") from exc
    policy_rate = int(get_or_create_policy().tds_rate_bps)
    if rate_bps > policy_rate:
        raise ValueError("Certificate rate cannot be higher than the Section 194H rate.")
    try:
        valid_from = date.fromisoformat(str(fields.get("valid_from") or "").strip())
        valid_to = date.fromisoformat(str(fields.get("valid_to") or "").strip())
    except ValueError as exc:
        raise ValueError("Certificate dates must be YYYY-MM-DD.") from exc
    if valid_from > valid_to:
        raise ValueError("Certificate valid from must be on or before valid to.")
    return number, rate_bps, valid_from, valid_to


def retailer_tds_position(user_id: str) -> dict[str, Any]:
    """What this retailer is deducted at right now, plus their certificate states."""
    email = str(user_id or "").strip().lower()
    who = retailer_tax_identity(email)
    policy = get_or_create_policy()
    decision = resolve_tds_rate(
        retailer_id=email,
        policy_rate_bps=int(policy.tds_rate_bps),
        withhold=bool(policy.withhold_tds_always),
    )
    pending = (
        RetailerTdsCertificate.objects.filter(user_id=email, section=TDS_SECTION, status="pending")
        .order_by("-id")
        .first()
    )
    approved = _certificate_for(email, timezone.localdate())
    rejected = (
        RetailerTdsCertificate.objects.filter(user_id=email, section=TDS_SECTION, status="rejected")
        .order_by("-id")
        .first()
    )
    if who.get("found") and not who.get("pan"):
        rule = "PAN is not on this account, so each commission credit withholds Section 206AA from this moment."
    elif decision["tds_basis"] == "197":
        rule = "An approved Section 197 certificate sets this retailer's rate. Other retailers stay on 194H."
    else:
        rule = "Section 194H applies. A lower rate starts only after admin approves a certificate."
    return {
        "user_id": email,
        "pan_on_file": bool(who.get("pan")),
        "account_found": bool(who.get("found")),
        "tds_basis": decision["tds_basis"],
        "tds_section": decision["tds_section"],
        "tds_rate_bps": int(decision["tds_rate_bps"]),
        "tds_rate_percent": round(int(decision["tds_rate_bps"]) / 100, 2),
        "rule": rule,
        "pending": _serialize_certificate(pending),
        "approved": _serialize_certificate(approved),
        "rejected": _serialize_certificate(rejected),
    }


def submit_tds_certificate(*, user_id: str, actor: str = "", **fields: Any) -> dict[str, Any]:
    """Retailer files a Section 197 certificate. It does not change TDS until admin approves it."""
    email = str(user_id or "").strip().lower()
    if "@" not in email or len(email) > 320:
        raise ValueError("Retailer email is required.")
    if RetailerTdsCertificate.objects.filter(user_id=email, section=TDS_SECTION, status="pending").exists():
        raise ValueError("A certificate is already waiting for admin approval.")
    number, rate_bps, valid_from, valid_to = _certificate_fields(fields)
    row = RetailerTdsCertificate.objects.create(
        user_id=email,
        section=TDS_SECTION,
        certificate_no=number,
        rate_bps=rate_bps,
        valid_from=valid_from,
        valid_to=valid_to,
        status="pending",
        active=False,
        submitted_at=timezone.now(),
        updated_by=actor or email,
    )
    log_action(
        action="domain.payswap.commission.tds.certificate.submit",
        outcome="ok",
        status=200,
        duration_ms=0,
        target_id=email,
        request=json.dumps(
            {
                "user_id": email,
                "certificate_no": number,
                "rate_bps": rate_bps,
                "valid_from": valid_from.isoformat(),
                "valid_to": valid_to.isoformat(),
            }
        ),
        response=json.dumps({"id": row.id, "status": "pending"}),
    )
    return retailer_tds_position(email)


def _tds_at_rate(commission_paise: int, rate_bps: int) -> int:
    if commission_paise <= 0 or rate_bps <= 0:
        return 0
    return int(
        (Decimal(int(commission_paise)) * Decimal(int(rate_bps)) / Decimal(10000)).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        )
    )


def _credit_date(row: TdsAccrual) -> date | None:
    if not isinstance(row.created_at, datetime):
        return None
    return timezone.localtime(row.created_at).date()


def _apply_certificate_refunds(cert: RetailerTdsCertificate, *, actor: str) -> tuple[int, int]:
    """Reprice accruals inside the certificate window and credit only the extra TDS already taken.

    A later approval never debits the retailer. Money already returned stays returned.
    """
    from domain.payswap.wallet import credit_tds_refund
    from models.models import ServiceSettlement

    credited = 0
    rows_touched = 0
    accruals = list(TdsAccrual.objects.filter(user_id=cert.user_id))
    for row in accruals:
        on = _credit_date(row)
        if on is None or cert.valid_from is None or cert.valid_to is None:
            continue
        if not (cert.valid_from <= on <= cert.valid_to):
            continue
        original = int(row.tds_paise_withheld or row.tds_paise or 0)
        if int(row.tds_paise_withheld or 0) == 0 and original:
            row.tds_paise_withheld = original
        already = int(row.refund_paise or 0)
        calculated = _tds_at_rate(int(row.commission_paise or 0), int(cert.rate_bps))
        target_remaining = min(original, calculated)
        current_remaining = max(0, original - already)
        paid = 0
        if target_remaining < current_remaining:
            extra = current_remaining - target_remaining
            paid = credit_tds_refund(
                cert.user_id,
                amount_paise=extra,
                reference=f"tds197-{row.accrual_id}"[:80],
                actor=actor,
            )
            row.refund_paise = already + paid
            credited += paid
            target_remaining = max(0, original - int(row.refund_paise))
        else:
            target_remaining = current_remaining
        row.tds_paise = target_remaining
        row.tds_rate_bps = int(cert.rate_bps)
        row.tds_basis = "197"
        row.save(
            update_fields=[
                "tds_paise",
                "tds_paise_withheld",
                "refund_paise",
                "tds_rate_bps",
                "tds_basis",
            ]
        )
        settlement = ServiceSettlement.objects.filter(service=row.service, reference=row.reference).first()
        if settlement is not None:
            settlement.tds_paise = target_remaining
            if paid:
                settlement.net_to_retailer_paise = int(settlement.net_to_retailer_paise or 0) + paid
            settlement.save(update_fields=["tds_paise", "net_to_retailer_paise", "updated_at"])
        bbps = BbpsTransaction.objects.filter(reference=row.reference, user_id=cert.user_id).first()
        if bbps is not None:
            bbps.tds_paise = target_remaining
            if paid:
                bbps.commission_paise = int(bbps.commission_paise or 0) + paid
            bbps.save(update_fields=["tds_paise", "commission_paise", "updated_at"])
        rows_touched += 1
    cert.refunded_paise = int(cert.refunded_paise or 0) + credited
    cert.save(update_fields=["refunded_paise", "updated_at"])
    return credited, rows_touched


def approve_tds_certificate(*, certificate_id: int, actor: str = "") -> dict[str, Any]:
    """Approve one pending certificate and credit back TDS above that rate."""
    try:
        cert_id = int(certificate_id)
    except (TypeError, ValueError) as exc:
        raise ValueError("Certificate id is required.") from exc
    with transaction.atomic():
        cert = RetailerTdsCertificate.objects.select_for_update().filter(pk=cert_id).first()
        if cert is None:
            raise ValueError("Certificate was not found.")
        if cert.status != "pending":
            raise ValueError("Only a pending certificate can be approved.")
        who = retailer_tax_identity(cert.user_id)
        if not who.get("found") or not who.get("pan"):
            raise ValueError("PAN must be on the account before this certificate can apply. Section 206AA stays in force.")
        RetailerTdsCertificate.objects.filter(
            user_id=cert.user_id, section=TDS_SECTION, status="approved", active=True
        ).exclude(pk=cert.pk).update(active=False)
        now = timezone.now()
        cert.status = "approved"
        cert.active = True
        cert.approved_at = now
        cert.updated_by = actor or cert.updated_by
        cert.save(update_fields=["status", "active", "approved_at", "updated_by", "updated_at"])
        credited, rows_touched = _apply_certificate_refunds(cert, actor=actor or "")
    log_action(
        action="domain.payswap.commission.tds.certificate.approve",
        outcome="ok",
        status=200,
        duration_ms=0,
        target_id=cert.user_id,
        request=json.dumps({"id": cert.id, "actor": actor}),
        response=json.dumps({"refunded_paise": credited, "rows": rows_touched}),
    )
    position = retailer_tds_position(cert.user_id)
    position["refunded_paise"] = credited
    position["refunded"] = paise_to_rupees_str(credited)
    position["rows"] = rows_touched
    return position


def reject_tds_certificate(*, certificate_id: int, actor: str = "", reason: str = "") -> dict[str, Any]:
    try:
        cert_id = int(certificate_id)
    except (TypeError, ValueError) as exc:
        raise ValueError("Certificate id is required.") from exc
    cert = RetailerTdsCertificate.objects.filter(pk=cert_id).first()
    if cert is None:
        raise ValueError("Certificate was not found.")
    if cert.status != "pending":
        raise ValueError("Only a pending certificate can be rejected.")
    cert.status = "rejected"
    cert.active = False
    cert.reject_reason = str(reason or "").strip()[:200]
    cert.updated_by = actor or cert.updated_by
    cert.save(update_fields=["status", "active", "reject_reason", "updated_by", "updated_at"])
    log_action(
        action="domain.payswap.commission.tds.certificate.reject",
        outcome="ok",
        status=200,
        duration_ms=0,
        target_id=cert.user_id,
        request=json.dumps({"id": cert.id, "reason": cert.reject_reason}),
        response=json.dumps({"status": "rejected"}),
    )
    return retailer_tds_position(cert.user_id)


def list_tds_certificates() -> dict[str, Any]:
    rows = RetailerTdsCertificate.objects.order_by("-id")[:100]
    items = []
    for row in rows:
        item = _serialize_certificate(row) or {}
        who = retailer_tax_identity(row.user_id)
        item["pan_on_file"] = bool(who.get("pan"))
        item["name"] = who.get("name") or ""
        items.append(item)
    return {"certificates": items}


def _d(value: Any) -> Decimal:
    try:
        return Decimal(str(value).strip())
    except Exception:
        return ZERO


def _paise(rupees: Decimal | str | float | int) -> int:
    return int((_d(rupees) * PAISE).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def paise_to_rupees_str(paise: int) -> str:
    return f"{(Decimal(int(paise)) / PAISE):.2f}"


def get_or_create_policy() -> CommissionPolicy:
    row, _ = CommissionPolicy.objects.get_or_create(
        key=POLICY_KEY,
        defaults={
            "admin_share_bps": 3000,
            "tds_rate_bps": 200,
            "gst_rate_bps": 1800,
            "tds_threshold_paise": 2_000_000,
            "withhold_tds_always": True,
            "no_pan_tds_rate_bps": NO_PAN_TDS_BPS,
        },
    )
    return row


def serialize_policy(row: CommissionPolicy | None = None) -> dict[str, Any]:
    row = row or get_or_create_policy()
    return {
        "key": row.key,
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
        "deductor_tan": str(row.deductor_tan or "").strip().upper(),
        "no_pan_tds_rate_bps": int(row.no_pan_tds_rate_bps or NO_PAN_TDS_BPS),
        "no_pan_tds_rate_percent": round(int(row.no_pan_tds_rate_bps or NO_PAN_TDS_BPS) / 100, 2),
        "rates_file_mtime": float(row.rates_file_mtime or 0),
        "rates_imported_at": row.rates_imported_at.isoformat() if row.rates_imported_at else "",
        "rates_count": VendorCommissionRate.objects.count(),
        "updated_by": row.updated_by,
        "updated_at": row.updated_at.isoformat() if row.updated_at else "",
    }


def update_policy(*, actor: str = "", sync_bbps: bool = True, **fields: Any) -> dict[str, Any]:
    row = get_or_create_policy()
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
    if "deductor_tan" in fields and fields["deductor_tan"] is not None:
        tan = str(fields["deductor_tan"] or "").strip().upper()
        if tan and not TAN_RE.fullmatch(tan):
            raise ValueError("TAN must be 4 letters, 5 digits, and 1 letter.")
        if tan:
            row.deductor_tan = tan
    if "no_pan_tds_rate_bps" in fields and fields["no_pan_tds_rate_bps"] is not None:
        no_pan = max(0, min(10000, int(fields["no_pan_tds_rate_bps"])))
        if no_pan < int(row.tds_rate_bps):
            raise ValueError("No-PAN rate must be at least the Section 194H rate.")
        row.no_pan_tds_rate_bps = no_pan
    row.updated_by = actor or row.updated_by
    row.save()
    if sync_bbps:
        try:
            from domain.payswap.economics.policy import update_service_policy

            update_service_policy(
                "bbps",
                actor=actor,
                admin_share_bps=row.admin_share_bps,
                tds_rate_bps=row.tds_rate_bps,
                gst_rate_bps=row.gst_rate_bps,
                tds_threshold_paise=row.tds_threshold_paise,
                withhold_tds_always=row.withhold_tds_always,
            )
        except Exception:
            pass
    log_action(
        action="domain.payswap.commission.policy",
        outcome="ok",
        status=200,
        duration_ms=0,
        target_id=row.key,
        request=json.dumps({k: fields[k] for k in fields if fields[k] is not None}),
        response=json.dumps(serialize_policy(row)),
    )
    return serialize_policy(row)


def serialize_rate(row: VendorCommissionRate) -> dict[str, Any]:
    return {
        "operator_id": row.operator_id,
        "operator_name": row.operator_name,
        "category": row.category,
        "rate_value": str(row.rate_value),
        "rate_type": row.rate_type,
        "min_txn_paise": int(row.min_txn_paise),
        "min_txn": paise_to_rupees_str(int(row.min_txn_paise)),
        "bbps_enabled": bool(row.bbps_enabled),
        "source_file": row.source_file,
        "updated_at": row.updated_at.isoformat() if row.updated_at else "",
    }


def list_rates(*, category: str = "", q: str = "", limit: int = 200, service: str = "bbps") -> dict[str, Any]:
    from domain.payswap.economics.catalogue import list_rate_rows

    # Policy + split preview come from ServiceEconomicsPolicy (do not overwrite with legacy).
    return list_rate_rows(service=service or "bbps", category=category, q=q, limit=limit)


def update_rate(*, service: str = "bbps", actor: str = "", **fields: Any) -> dict[str, Any]:
    from domain.payswap.economics.catalogue import update_rate_row

    return update_rate_row(service=service or "bbps", actor=actor, **fields)


def models_q_operator_name_or_id(needle: str):
    from django.db.models import Q

    return Q(operator_name__icontains=needle) | Q(operator_id__icontains=needle) | Q(category__icontains=needle)


def _normalize_rate_type(raw: str) -> str:
    text = str(raw or "").strip().lower()
    if "percent" in text or text in {"%", "pct", "percentage"}:
        return "percent"
    return "flat"


def import_vendor_sheet(path: str | Path, *, actor: str = "") -> dict[str, Any]:
    """Shim → Mobikwik importer into ServiceRateRow (+ legacy VendorCommissionRate mirror)."""
    from domain.payswap.economics.importers.bbps_mobikwik import import_bbps_mobikwik_sheet

    return import_bbps_mobikwik_sheet(path, actor=actor)


def _running_under_tests() -> bool:
    import sys

    return any(arg == "test" or arg.startswith("test") for arg in sys.argv) or "pytest" in sys.modules


def ensure_commission_catalogue(
    *,
    path: str | Path | None = None,
    force: bool = False,
    actor: str = "boot",
) -> dict[str, Any]:
    """Shim → economics.ensure_catalogue(service=bbps)."""
    from domain.payswap.economics.catalogue import ensure_catalogue

    return ensure_catalogue(service="bbps", path=path, force=force, actor=actor)


def previous_calendar_month(today=None) -> str:
    day = today or timezone.localdate()
    year, month = day.year, day.month
    if month == 1:
        return f"{year - 1}-12"
    return f"{year}-{month - 1:02d}"


def generate_monthly_invoices(*, month: str = "", actor: str = "cron") -> dict[str, Any]:
    from domain.payswap.economics.invoices import generate_monthly_invoices as _gen

    return _gen(month=month, actor=actor)


def get_retailer_override(user_id: str) -> RetailerCommissionOverride | None:
    return RetailerCommissionOverride.objects.filter(user_id=user_id, active=True).first()


COMMISSION_SHEET_SERVICES = ("bbps", "recharge", "vouchers", "dmt", "aeps")
COMMISSION_SHEET_LABELS = {
    "bbps": "Bill Pay (BBPS)",
    "recharge": "Mobile & DTH Recharges",
    "vouchers": "Gift Vouchers",
    "dmt": "Domestic Money Transfer (DMT)",
    "aeps": "AEPS Cash Withdrawal",
}


def match_share_override(items, external_id: str, category: str = "") -> int | None:
    """Biller row share. Category-specific match wins over a row saved without a category."""
    op = str(external_id or "").strip()
    cat = str(category or "").strip().lower()
    if not op:
        return None
    loose = None
    for item in items or []:
        if not isinstance(item, dict) or item.get("admin_share_bps") is None:
            continue
        if str(item.get("external_id") or "").strip() != op:
            continue
        item_cat = str(item.get("category") or "").strip().lower()
        if item_cat and cat and item_cat != cat:
            continue
        try:
            bps = max(0, min(10000, int(item["admin_share_bps"])))
        except (TypeError, ValueError):
            continue
        if item_cat and cat and item_cat == cat:
            return bps
        if not item_cat:
            loose = bps
    return loose


def effective_retailer_admin_bps(override, *, external_id: str = "", category: str = "", policy_bps: int = 0) -> tuple[int, str]:
    """Biller share, then the service override, then the Economics policy."""
    policy = max(0, min(10000, int(policy_bps)))
    if override is not None and getattr(override, "active", True):
        hit = match_share_override(getattr(override, "share_overrides", None), external_id, category)
        if hit is not None:
            return hit, "biller"
        if getattr(override, "admin_share_bps", None) is not None:
            return max(0, min(10000, int(override.admin_share_bps))), "service"
    return policy, "policy"


def _pct_from_bps(bps: int | None) -> float | None:
    if bps is None:
        return None
    return round(int(bps) / 100, 2)


def _sample_split(admin_bps: int, *, sample: Decimal = Decimal("2.25")) -> dict[str, str]:
    admin_bps = max(0, min(10000, int(admin_bps)))
    admin_keeps = (sample * Decimal(admin_bps) / Decimal(10000)).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
    retailer_gets = (sample - admin_keeps).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
    return {
        "sample_vendor": f"{sample:.2f}",
        "sample_admin": f"{admin_keeps:.3f}",
        "sample_retailer": f"{retailer_gets:.3f}",
    }


def retailer_commission_sheet(user_id: str, *, enabled_services: list[str] | None = None) -> dict[str, Any]:
    """Per-retailer commission sheet: default vs override for each earning service."""
    from domain.payswap.economics.policy import serialize_service_policy
    from models.models import RetailerServiceOverride

    uid = str(user_id or "").strip().lower()
    enabled = {str(s).strip().lower() for s in (enabled_services or []) if str(s).strip()}
    if not enabled and uid:
        try:
            from domain.payswap.entitlements import resolve_retailer_entitlements

            enabled = {str(s).strip().lower() for s in (resolve_retailer_entitlements(uid).get("enabled_services") or [])}
        except Exception:
            enabled = set()

    overrides = {
        str(row.service): row
        for row in RetailerServiceOverride.objects.filter(user_id=uid, service__in=COMMISSION_SHEET_SERVICES)
    }
    rows: list[dict[str, Any]] = []
    for svc in COMMISSION_SHEET_SERVICES:
        policy = serialize_service_policy(service=svc)
        default_bps = int(policy["admin_share_bps"])
        ov = overrides.get(svc)
        override_bps = None
        if ov and ov.active and ov.admin_share_bps is not None:
            override_bps = int(ov.admin_share_bps)
        effective_bps = override_bps if override_bps is not None else default_bps
        sample = _sample_split(effective_bps)
        rows.append(
            {
                "service": svc,
                "label": COMMISSION_SHEET_LABELS.get(svc, svc.upper()),
                "enabled": svc in enabled,
                "monetization_mode": policy["monetization_mode"],
                "default_admin_share_bps": default_bps,
                "default_admin_share_percent": _pct_from_bps(default_bps),
                "default_retailer_share_percent": _pct_from_bps(10000 - default_bps),
                "override_admin_share_bps": override_bps,
                "override_admin_share_percent": _pct_from_bps(override_bps),
                "effective_admin_share_bps": effective_bps,
                "effective_admin_share_percent": _pct_from_bps(effective_bps),
                "effective_retailer_share_percent": _pct_from_bps(10000 - effective_bps),
                "inherits": override_bps is None,
                "updated_by": (ov.updated_by if ov else "") or "",
                "updated_at": ov.updated_at.isoformat() if ov and ov.updated_at else "",
                **sample,
            }
        )
    return {"user_id": uid, "rows": rows}


def update_retailer_service_share(
    user_id: str,
    service: str,
    *,
    actor: str = "",
    admin_share_bps: int | None = None,
    clear_share: bool = False,
) -> dict[str, Any]:
    """Save or clear one service's admin-share override for a retailer."""
    from models.models import RetailerServiceOverride

    uid = str(user_id or "").strip().lower()
    svc = str(service or "").strip().lower()
    if not uid:
        raise ValueError("email is required.")
    if svc not in COMMISSION_SHEET_SERVICES:
        raise ValueError(f"Unknown commission service: {svc}")

    row, _ = RetailerServiceOverride.objects.get_or_create(user_id=uid, service=svc)
    if clear_share:
        row.admin_share_bps = None
    elif admin_share_bps is not None:
        row.admin_share_bps = max(0, min(10000, int(admin_share_bps)))
    else:
        raise ValueError("Send admin_share_bps or clear_share.")
    row.active = True
    row.updated_by = actor or row.updated_by
    row.save()

    # Keep legacy BBPS RetailerCommissionOverride aligned for older readers.
    if svc == "bbps":
        legacy, _ = RetailerCommissionOverride.objects.get_or_create(user_id=uid)
        legacy.admin_share_bps = row.admin_share_bps
        legacy.active = True
        legacy.updated_by = actor or legacy.updated_by
        legacy.save()

    out = retailer_commission_sheet(uid)
    log_action(
        action="domain.payswap.commission.retailer_service_share",
        outcome="ok",
        status=200,
        duration_ms=0,
        target_id=f"{uid}:{svc}",
        request=json.dumps(
            {
                "service": svc,
                "clear_share": bool(clear_share),
                "admin_share_bps": None if clear_share else row.admin_share_bps,
            }
        ),
        response=json.dumps({"service": svc, "admin_share_bps": row.admin_share_bps}),
    )
    return out


def retailer_service_catalogue(
    user_id: str,
    service: str,
    *,
    category: str = "",
    query: str = "",
    limit: int = 200,
) -> dict[str, Any]:
    """One service sheet for one retailer: Economics rate, plus this account's share on each row."""
    from domain.payswap.economics.catalogue import list_rate_rows
    from models.models import RetailerServiceOverride

    uid = str(user_id or "").strip().lower()
    svc = str(service or "").strip().lower()
    if svc not in COMMISSION_SHEET_SERVICES:
        raise ValueError(f"Unknown commission service: {svc}")
    listed = list_rate_rows(service=svc, category=category, q=query, limit=limit)
    policy = listed.get("policy") or {}
    policy_bps = int(policy.get("admin_share_bps") or 0)
    override = RetailerServiceOverride.objects.filter(user_id=uid, service=svc, active=True).first()
    rows = []
    for item in listed.get("rates") or []:
        external_id = str(item.get("external_id") or item.get("operator_id") or "")
        row_category = str(item.get("category") or item.get("bbps_category") or "")
        bps, source = effective_retailer_admin_bps(
            override,
            external_id=external_id,
            category=row_category,
            policy_bps=policy_bps,
        )
        fallback_bps = policy_bps
        if override is not None and override.admin_share_bps is not None:
            fallback_bps = int(override.admin_share_bps)
        rows.append(
            {
                **item,
                "default_admin_share_percent": _pct_from_bps(policy_bps),
                "default_retailer_share_percent": _pct_from_bps(10000 - policy_bps),
                "fallback_admin_share_percent": _pct_from_bps(fallback_bps),
                "retailer_admin_share_percent": _pct_from_bps(bps) if source == "biller" else None,
                "effective_admin_share_percent": _pct_from_bps(bps),
                "effective_retailer_share_percent": _pct_from_bps(10000 - bps),
                "share_source": source,
            }
        )
    return {
        "user_id": uid,
        "service": svc,
        "label": COMMISSION_SHEET_LABELS.get(svc, svc.upper()),
        "total": int(listed.get("total") or len(rows)),
        "rows": rows,
        "policy": policy,
    }


def update_retailer_biller_share(
    user_id: str,
    service: str,
    external_id: str,
    category: str = "",
    *,
    actor: str = "",
    admin_share_bps: int | None = None,
    clear_share: bool = False,
) -> dict[str, Any]:
    """Save or clear the admin share for one sheet row. Other billers stay unchanged."""
    from models.models import RetailerServiceOverride

    uid = str(user_id or "").strip().lower()
    svc = str(service or "").strip().lower()
    op = str(external_id or "").strip()
    cat = str(category or "").strip()
    if not uid:
        raise ValueError("email is required.")
    if svc not in COMMISSION_SHEET_SERVICES:
        raise ValueError(f"Unknown commission service: {svc}")
    if not op:
        raise ValueError("external_id is required.")
    if not clear_share and admin_share_bps is None:
        raise ValueError("Send admin_share_bps or clear_share.")

    row, _ = RetailerServiceOverride.objects.get_or_create(user_id=uid, service=svc)
    kept = []
    for item in row.share_overrides or []:
        if not isinstance(item, dict):
            continue
        same_id = str(item.get("external_id") or "").strip() == op
        same_cat = str(item.get("category") or "").strip().lower() == cat.lower()
        if same_id and same_cat:
            continue
        kept.append(item)
    saved_bps = None
    if not clear_share:
        saved_bps = max(0, min(10000, int(admin_share_bps)))
        kept.append({"external_id": op, "category": cat, "admin_share_bps": saved_bps})
    row.share_overrides = kept
    row.active = True
    row.updated_by = actor or row.updated_by
    row.save()
    log_action(
        action="domain.payswap.commission.retailer_biller_share",
        outcome="ok",
        status=200,
        duration_ms=0,
        target_id=f"{uid}:{svc}:{op}",
        request=json.dumps({"service": svc, "external_id": op, "category": cat, "clear_share": bool(clear_share)}),
        response=json.dumps({"admin_share_bps": saved_bps}),
    )
    return retailer_service_catalogue(uid, svc, category=cat, query=op, limit=20)


def serialize_retailer_override(row: RetailerCommissionOverride | None, *, user_id: str = "") -> dict[str, Any]:
    policy = serialize_policy()
    uid = str((row.user_id if row else user_id) or "").strip().lower()
    sheet = retailer_commission_sheet(uid)
    if not row:
        return {
            "user_id": uid,
            "active": False,
            "admin_share_bps": None,
            "admin_share_percent": None,
            "inherits_admin_share_bps": policy["admin_share_bps"],
            "operator_overrides": [],
            "sheet": sheet,
        }
    return {
        "user_id": row.user_id,
        "active": bool(row.active),
        "admin_share_bps": row.admin_share_bps,
        "admin_share_percent": None if row.admin_share_bps is None else round(int(row.admin_share_bps) / 100, 2),
        "inherits_admin_share_bps": policy["admin_share_bps"],
        "operator_overrides": list(row.operator_overrides or []),
        "updated_by": row.updated_by,
        "updated_at": row.updated_at.isoformat() if row.updated_at else "",
        "sheet": sheet,
    }


def update_retailer_override(
    user_id: str,
    *,
    actor: str = "",
    admin_share_bps: int | None = None,
    operator_overrides: list | None = None,
    active: bool | None = None,
    clear_share: bool = False,
) -> dict[str, Any]:
    row, _ = RetailerCommissionOverride.objects.get_or_create(user_id=user_id)
    if clear_share:
        row.admin_share_bps = None
    elif admin_share_bps is not None:
        row.admin_share_bps = max(0, min(10000, int(admin_share_bps)))
    if operator_overrides is not None:
        cleaned = []
        for item in operator_overrides:
            if not isinstance(item, dict):
                continue
            op = str(item.get("operator_id") or "").strip()
            if not op:
                continue
            cleaned.append(
                {
                    "operator_id": op,
                    "category": str(item.get("category") or "").strip()[:80],
                    "rate_value": str(_d(item.get("rate_value"))),
                    "rate_type": _normalize_rate_type(str(item.get("rate_type") or "flat")),
                    "min_txn_paise": int(item.get("min_txn_paise") or 0),
                }
            )
        row.operator_overrides = cleaned
    if active is not None:
        row.active = bool(active)
    row.updated_by = actor or row.updated_by
    row.save()
    try:
        from models.models import RetailerServiceOverride

        rate_overrides = [
            {
                "external_id": item.get("operator_id") or item.get("external_id"),
                "category": item.get("category") or "",
                "rate_value": item.get("rate_value"),
                "rate_type": item.get("rate_type") or "flat",
                "min_txn_paise": int(item.get("min_txn_paise") or 0),
            }
            for item in (row.operator_overrides or [])
            if isinstance(item, dict)
        ]
        RetailerServiceOverride.objects.update_or_create(
            user_id=user_id,
            service="bbps",
            defaults={
                "admin_share_bps": row.admin_share_bps,
                "rate_overrides": rate_overrides,
                "active": bool(row.active),
                "updated_by": actor or "",
            },
        )
    except Exception:
        pass
    return serialize_retailer_override(row)


def _find_catalogue_rate(operator_id: str, category: str) -> VendorCommissionRate | None:
    op = str(operator_id or "").strip()
    cat = str(category or "").strip()
    if not op:
        return None
    if cat:
        row = VendorCommissionRate.objects.filter(operator_id=op, category__iexact=cat).first()
        if row:
            return row
    return VendorCommissionRate.objects.filter(operator_id=op).order_by("id").first()


def resolve_rate(*, operator_id: str, category: str, retailer_id: str = "") -> dict[str, Any] | None:
    """Return effective rate dict from ServiceRateRow / retailer override (BBPS)."""
    from domain.payswap.economics.catalogue import resolve_rate_row

    return resolve_rate_row(
        service="bbps",
        external_id=operator_id,
        category=category,
        retailer_id=retailer_id,
    )


def vendor_commission_paise(*, amount_paise: int, rate: dict[str, Any] | None) -> int:
    if not rate:
        return 0
    if int(amount_paise) < int(rate.get("min_txn_paise") or 0):
        return 0
    value = _d(rate.get("rate_value"))
    if value <= 0:
        return 0
    if rate.get("rate_type") == "percent":
        rupees = Decimal(int(amount_paise)) / PAISE
        return _paise(rupees * value / HUNDRED)
    return _paise(value)


def compute_split(
    *,
    vendor_paise: int,
    retailer_id: str = "",
    has_gstin: bool = False,
    policy: CommissionPolicy | None = None,
) -> dict[str, Any]:
    """Split vendor commission into admin revenue, retailer gross, TDS, GST, net credit."""
    policy = policy or get_or_create_policy()
    override = get_retailer_override(retailer_id) if retailer_id else None
    admin_bps = int(override.admin_share_bps) if (override and override.admin_share_bps is not None) else int(policy.admin_share_bps)
    admin_bps = max(0, min(10000, admin_bps))
    vendor = max(0, int(vendor_paise))
    admin_revenue = int((Decimal(vendor) * Decimal(admin_bps) / Decimal(10000)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    retailer_gross = max(0, vendor - admin_revenue)
    gst_paise = 0
    if has_gstin and retailer_gross > 0 and int(policy.gst_rate_bps) > 0:
        gst_paise = int(
            (Decimal(retailer_gross) * Decimal(int(policy.gst_rate_bps)) / Decimal(10000)).quantize(
                Decimal("1"), rounding=ROUND_HALF_UP
            )
        )
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
    net_credit = max(0, retailer_gross - tds_paise)
    return {
        "vendor_commission_paise": vendor,
        "admin_revenue_paise": admin_revenue,
        "retailer_commission_paise": retailer_gross,
        "tds_paise": tds_paise,
        "gst_paise": gst_paise,
        "net_credit_paise": net_credit,
        "admin_share_bps": admin_bps,
        "tds_rate_bps": tds_rate,
        "tds_basis": decision["tds_basis"],
        "tds_section": decision["tds_section"],
        "gst_rate_bps": int(policy.gst_rate_bps) if has_gstin else 0,
    }


def settle_commission(
    tx: BbpsTransaction,
    *,
    has_gstin: bool = False,
    vendor_paise: int | None = None,
) -> dict[str, Any]:
    """BBPS shim: delegates to economics.settle_success and dual-writes BbpsTransaction."""
    if tx.state != "success":
        return {"applied": False, "reason": "not_success"}
    if int(tx.vendor_commission_paise or 0) > 0 or int(tx.retailer_commission_paise or 0) > 0:
        return {
            "applied": False,
            "reason": "already_settled",
            "net_credit_paise": int(tx.commission_paise or 0),
            "tds_paise": int(tx.tds_paise or 0),
        }
    from domain.payswap.economics.settle import settle_success

    out = settle_success(
        service="bbps",
        reference=tx.reference,
        user_id=tx.user_id,
        amount_paise=int(tx.amount_paise),
        external_id=tx.operator_id,
        category=tx.category,
        has_gstin=has_gstin,
        bbps_tx=tx,
        vendor_paise=vendor_paise,
    )
    if "snapshot" not in out and out.get("rate_snapshot"):
        out["snapshot"] = out["rate_snapshot"]
    return out


def revenue_report(*, month: str = "", limit: int = 50, service: str = "all") -> dict[str, Any]:
    from domain.payswap.economics.invoices import revenue_report as _rev

    return _rev(month=month, service=service or "all", limit=limit)


def _challan_label(bucket: dict[str, Any]) -> dict[str, str]:
    seen = bucket.get("challans") or []
    if len(seen) != 1:
        blank = {"challan_bsr": "mixed" if seen else "", "challan_serial": "", "challan_date": "", "challan_amount": ""}
        return blank
    bsr, serial, on, amount = seen[0]
    return {
        "challan_bsr": bsr,
        "challan_serial": serial,
        "challan_date": on,
        "challan_amount": paise_to_rupees_str(amount) if amount else "",
    }


def tds_month_report(*, month: str = "") -> dict[str, Any]:
    """Month pack the Economics → TDS desk needs before a 194H deposit.

    Company TAN, deductee name and PAN, credit dates, quarter, and the challan
    already saved on deposited rows. PAN is for that admin screen only.
    """
    month = month or timezone.localdate().strftime("%Y-%m")
    period = fiscal_period(month)
    tan = str(get_or_create_policy().deductor_tan or "").strip().upper()
    qs = TdsAccrual.objects.filter(month=month)
    by_user: dict[str, dict[str, Any]] = {}
    for row in qs:
        bucket = by_user.setdefault(
            row.user_id,
            {
                "user_id": row.user_id,
                "tds_paise": 0,
                "commission_paise": 0,
                "open_paise": 0,
                "deposited_paise": 0,
                "count": 0,
                "credited_from": "",
                "credited_to": "",
                "challans": [],
                "bases": [],
            },
        )
        bucket["tds_paise"] += int(row.tds_paise)
        bucket["commission_paise"] += int(row.commission_paise)
        bucket["count"] += 1
        label = _basis_label(row.tds_basis)
        if label not in bucket["bases"]:
            bucket["bases"].append(label)
        credited = ""
        if isinstance(row.created_at, datetime):
            credited = timezone.localtime(row.created_at).date().isoformat()
        if credited:
            if not bucket["credited_from"] or credited < bucket["credited_from"]:
                bucket["credited_from"] = credited
            if not bucket["credited_to"] or credited > bucket["credited_to"]:
                bucket["credited_to"] = credited
        if row.status == "deposited":
            bucket["deposited_paise"] += int(row.tds_paise)
            stamp = (
                str(row.challan_bsr or ""),
                str(row.challan_serial or ""),
                row.challan_on.isoformat() if row.challan_on else "",
                int(row.challan_amount_paise or 0),
            )
            if stamp not in bucket["challans"]:
                bucket["challans"].append(stamp)
        else:
            bucket["open_paise"] += int(row.tds_paise)
    missing: list[str] = []
    if not tan:
        missing.append("Company TAN is not saved.")
    retailers = []
    for bucket in sorted(by_user.values(), key=lambda item: item["user_id"]):
        who = retailer_tax_identity(bucket["user_id"])
        if int(bucket["open_paise"]) > 0 and not who["pan"]:
            missing.append(f"{bucket['user_id']} has no PAN on the account file. New credits use Section 206AA.")
        if int(bucket["open_paise"]) > 0 and not who["name"]:
            missing.append(f"{bucket['user_id']} has no name on the account file.")
        challan = _challan_label(bucket)
        retailers.append(
            {
                "user_id": bucket["user_id"],
                "name": who["name"],
                "pan": who["pan"],
                "pan_mask": who["pan_mask"],
                "pan_on_file": bool(who["pan"]),
                "section": TDS_SECTION,
                "tds_basis_label": bucket["bases"][0] if len(bucket["bases"]) == 1 else ("mixed" if bucket["bases"] else "194H"),
                "credited_from": bucket["credited_from"],
                "credited_to": bucket["credited_to"],
                "count": bucket["count"],
                "tds_paise": bucket["tds_paise"],
                "commission_paise": bucket["commission_paise"],
                "open_paise": bucket["open_paise"],
                "deposited_paise": bucket["deposited_paise"],
                "tds": paise_to_rupees_str(bucket["tds_paise"]),
                "commission": paise_to_rupees_str(bucket["commission_paise"]),
                "open": paise_to_rupees_str(bucket["open_paise"]),
                "deposited": paise_to_rupees_str(bucket["deposited_paise"]),
                **challan,
            }
        )
    total_open = sum(item["open_paise"] for item in by_user.values())
    total_tds = sum(item["tds_paise"] for item in by_user.values())
    open_gaps = [line for line in missing if line]
    return {
        "month": month,
        "section": period["section"],
        "quarter": period["quarter"],
        "financial_year": period["financial_year"],
        "deductor_tan": tan,
        "ready": not open_gaps and total_open >= 0,
        "missing": open_gaps,
        "totals": {
            "tds": paise_to_rupees_str(total_tds),
            "open": paise_to_rupees_str(total_open),
            "open_paise": total_open,
            "retailers": len(retailers),
        },
        "retailers": retailers,
    }


def _rupees_to_paise(amount: Any) -> int:
    text = str(amount if amount is not None else "").strip().replace(",", "")
    if not text:
        raise ValueError("Challan amount is required.")
    try:
        paise = int((Decimal(text) * PAISE).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    except Exception as exc:
        raise ValueError("Challan amount must be a rupee amount.") from exc
    if paise < 0:
        raise ValueError("Challan amount must be a rupee amount.")
    return paise


def _refuse_deposit(reason: str, *, month: str, user_id: str) -> None:
    log_action(
        action="domain.payswap.commission.tds.deposit",
        outcome="error",
        status=400,
        duration_ms=0,
        target_id=month,
        error_code="validation",
        error_reason=reason[:200],
        request=json.dumps({"month": month, "user_id": user_id}),
        response=json.dumps({"error": reason[:200]}),
    )
    raise ValueError(reason)


def mark_tds_deposited(
    *,
    month: str,
    user_id: str = "",
    actor: str = "",
    challan_bsr: str = "",
    challan_serial: str = "",
    challan_date: str = "",
    challan_amount: Any = None,
) -> dict[str, Any]:
    """Mark open accruals deposited only when the 194H challan matches them.

    The challan amount is the total being marked, stored on each row so the
    desk can show which challan covered that retailer. PAN is not logged.
    """
    month = str(month or "").strip()
    user_id = str(user_id or "").strip().lower()
    if not MONTH_RE.fullmatch(month):
        _refuse_deposit("Month must be YYYY-MM.", month=month, user_id=user_id)
    bsr = "".join(ch for ch in str(challan_bsr or "") if ch.isdigit())
    serial = "".join(ch for ch in str(challan_serial or "") if ch.isdigit())
    on_text = str(challan_date or "").strip()
    if not BSR_RE.fullmatch(bsr):
        _refuse_deposit("Challan BSR must be 7 digits.", month=month, user_id=user_id)
    if not SERIAL_RE.fullmatch(serial):
        _refuse_deposit("Challan serial must be 1 to 10 digits.", month=month, user_id=user_id)
    try:
        on = date.fromisoformat(on_text)
    except ValueError:
        _refuse_deposit("Challan date must be YYYY-MM-DD.", month=month, user_id=user_id)
    amount_paise = _rupees_to_paise(challan_amount)
    tan = str(get_or_create_policy().deductor_tan or "").strip().upper()
    if not TAN_RE.fullmatch(tan):
        _refuse_deposit("Save the company TAN before marking TDS deposited.", month=month, user_id=user_id)
    qs = TdsAccrual.objects.filter(month=month, status="open")
    if user_id:
        qs = qs.filter(user_id=user_id)
    rows = list(qs)
    if not rows:
        _refuse_deposit("No open TDS for that month.", month=month, user_id=user_id)
    open_paise = sum(int(row.tds_paise or 0) for row in rows)
    if amount_paise != open_paise:
        expected = paise_to_rupees_str(open_paise)
        _refuse_deposit(
            f"Challan amount must equal the open TDS (₹{expected}).",
            month=month,
            user_id=user_id,
        )
    gaps = []
    for email in sorted({row.user_id for row in rows}):
        who = retailer_tax_identity(email)
        if not who["pan"]:
            gaps.append(f"{email} has no PAN on the account file")
        if not who["name"]:
            gaps.append(f"{email} has no name on the account file")
    if gaps:
        _refuse_deposit("Cannot deposit yet. " + "; ".join(gaps) + ".", month=month, user_id=user_id)
    now = timezone.now()
    updated = qs.update(
        status="deposited",
        deposited_at=now,
        deposited_by=actor or "",
        challan_bsr=bsr,
        challan_serial=serial,
        challan_on=on,
        challan_amount_paise=amount_paise,
    )
    log_action(
        action="domain.payswap.commission.tds.deposit",
        outcome="ok",
        status=200,
        duration_ms=0,
        target_id=month,
        request=json.dumps(
            {
                "month": month,
                "user_id": user_id,
                "challan_bsr": bsr,
                "challan_serial": serial,
                "challan_date": on.isoformat(),
                "challan_amount_paise": amount_paise,
            }
        ),
        response=json.dumps({"updated": updated}),
    )
    return {"month": month, "updated": updated, "challan_amount": paise_to_rupees_str(amount_paise)}


def retailer_commission_summary(*, user_id: str, month: str = "", service: str = "all") -> dict[str, Any]:
    from domain.payswap.economics.invoices import retailer_settlement_summary

    return retailer_settlement_summary(user_id=user_id, month=month, service=service or "all")


def create_monthly_invoice(
    *,
    user_id: str,
    month: str,
    gstin: str,
    actor: str = "",
    place_of_supply_same_state: bool = True,
) -> dict[str, Any]:
    from domain.payswap.economics.invoices import create_monthly_invoice as _create

    return _create(
        user_id=user_id,
        month=month,
        gstin=gstin,
        actor=actor,
        place_of_supply_same_state=place_of_supply_same_state,
    )


def serialize_invoice(row: CommissionInvoice) -> dict[str, Any]:
    from domain.payswap.economics.invoices import serialize_invoice as _ser

    return _ser(row)


def invoice_html(row: CommissionInvoice) -> str:
    from domain.payswap.economics.invoices import invoice_html as _html

    return _html(row)
