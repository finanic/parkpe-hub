"""Service rate catalogue (ServiceRateRow) + ensure/import stamps."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from django.db.models import Q
from django.utils import timezone
from domain.payswap.economics._money import paise_to_rupees_str
from domain.payswap.economics.policy import get_or_create_service_policy
from models.models import ServiceRateRow

DEFAULT_BBPS_SHEET = Path(__file__).resolve().parents[3] / "data" / "mobikwik" / "commission-b2b.xlsx"


def default_sheet_path(service: str = "bbps") -> Path:
    if (service or "bbps").strip().lower() == "bbps":
        return DEFAULT_BBPS_SHEET
    return Path(__file__).resolve().parents[3] / "data" / "rates" / f"{service}.xlsx"


def _bbps_link_for_op(external_id: str) -> dict[str, Any]:
    """Match ServiceRateRow.external_id to Mobikwik BBPS catalogue op / biller_id."""
    try:
        from integrations.bbps import find_operator
    except Exception:
        return {"bbps_linked": False, "biller_id": "", "bbps_name": "", "bbps_category": ""}
    op = find_operator(str(external_id or "").strip())
    if not op:
        return {"bbps_linked": False, "biller_id": "", "bbps_name": "", "bbps_category": ""}
    return {
        "bbps_linked": True,
        "biller_id": str(op.get("biller_id") or op.get("op") or ""),
        "bbps_name": str(op.get("name") or ""),
        "bbps_category": str(op.get("category") or ""),
        "bbps_op": str(op.get("op") or ""),
    }


def serialize_rate_row(row: ServiceRateRow, *, admin_share_bps: int = 3000) -> dict[str, Any]:
    """Include receive vs pass-through preview for Economics commission tables."""
    from decimal import Decimal, ROUND_HALF_UP

    admin_bps = max(0, min(10000, int(admin_share_bps)))
    retailer_bps = 10000 - admin_bps
    rate_type = row.rate_type or "flat"
    rate_value = Decimal(str(row.rate_value))
    # Sample vendor commission: flat = rate ₹; percent = on ₹1,000 txn.
    if rate_type == "percent":
        vendor_sample = (Decimal("1000") * rate_value / Decimal("100")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        receive_label = f"{rate_value}%"
        sample_note = "on ₹1000"
    else:
        vendor_sample = rate_value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        receive_label = f"₹{vendor_sample}"
        sample_note = "per txn"
    admin_sample = (vendor_sample * Decimal(admin_bps) / Decimal(10000)).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    retailer_sample = (vendor_sample - admin_sample).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    link = _bbps_link_for_op(row.external_id) if row.service == "bbps" else {
        "bbps_linked": False,
        "biller_id": "",
        "bbps_name": "",
        "bbps_category": "",
    }
    return {
        "service": row.service,
        "external_id": row.external_id,
        "operator_id": row.external_id,  # BBPS op / biller id — must match integrations.bbps
        "operator_name": row.name,
        "name": row.name,
        "category": row.category,
        "rate_value": str(row.rate_value),
        "rate_type": rate_type,
        "min_txn_paise": int(row.min_txn_paise),
        "min_txn": paise_to_rupees_str(int(row.min_txn_paise)),
        "enabled": bool(row.enabled),
        "bbps_enabled": bool(row.enabled),
        "source_file": row.source_file,
        "updated_at": row.updated_at.isoformat() if row.updated_at else "",
        # Economics commission table columns
        "we_receive": receive_label,
        "we_receive_sample": str(vendor_sample),
        "sample_note": sample_note,
        "admin_share_bps": admin_bps,
        "admin_share_percent": round(admin_bps / 100, 2),
        "admin_keeps_sample": str(admin_sample),
        "retailer_share_bps": retailer_bps,
        "retailer_share_percent": round(retailer_bps / 100, 2),
        "retailer_gets_sample": str(retailer_sample),
        **link,
    }


def _serialize_bbps_matrix_row(
    *,
    op: dict[str, Any],
    rate: ServiceRateRow | None,
    admin_share_bps: int,
) -> dict[str, Any]:
    """One Mobikwik BBPS table row: BBPS biller + optional rate (same op id)."""
    external_id = str(op.get("op") or op.get("biller_id") or "")
    if rate:
        out = serialize_rate_row(rate, admin_share_bps=admin_share_bps)
        # Prefer live BBPS catalogue labels when linked.
        out["bbps_linked"] = True
        out["biller_id"] = str(op.get("biller_id") or external_id)
        out["bbps_name"] = str(op.get("name") or "")
        out["bbps_category"] = str(op.get("category") or "")
        out["bbps_op"] = external_id
        out["has_rate"] = True
        return out
    admin_bps = max(0, min(10000, int(admin_share_bps)))
    return {
        "service": "bbps",
        "external_id": external_id,
        "operator_id": external_id,
        "operator_name": str(op.get("name") or ""),
        "name": str(op.get("name") or ""),
        "category": str(op.get("category") or ""),
        "rate_value": "0",
        "rate_type": "flat",
        "min_txn_paise": 0,
        "min_txn": "0.00",
        "enabled": False,
        "bbps_enabled": False,
        "source_file": "",
        "updated_at": "",
        "we_receive": "₹0.00",
        "we_receive_sample": "0.00",
        "sample_note": "per txn",
        "admin_share_bps": admin_bps,
        "admin_share_percent": round(admin_bps / 100, 2),
        "admin_keeps_sample": "0.00",
        "retailer_share_bps": 10000 - admin_bps,
        "retailer_share_percent": round((10000 - admin_bps) / 100, 2),
        "retailer_gets_sample": "0.00",
        "bbps_linked": True,
        "biller_id": str(op.get("biller_id") or external_id),
        "bbps_name": str(op.get("name") or ""),
        "bbps_category": str(op.get("category") or ""),
        "bbps_op": external_id,
        "has_rate": False,
    }


def list_rate_rows(*, service: str = "bbps", category: str = "", q: str = "", limit: int = 200) -> dict[str, Any]:
    ensure_catalogue(service=service)
    svc = (service or "bbps").strip().lower()
    policy_row = get_or_create_service_policy(svc)
    admin_bps = int(policy_row.admin_share_bps)
    from domain.payswap.economics.policy import serialize_service_policy

    # BBPS Mobikwik table: billers from BBPS catalogue, rates joined on op == external_id.
    if svc == "bbps":
        from integrations.bbps import list_operators

        cat = (category or "").strip()
        needle = (q or "").strip()
        # Cap matrix size; EDUCATION alone is huge — require category or search for full matrix.
        fetch_limit = max(1, min(int(limit), 2000))
        if cat or needle:
            ops = list_operators(category=cat or None, query=needle, limit=fetch_limit)
            rate_map = {
                (r.external_id, (r.category or "").upper()): r
                for r in ServiceRateRow.objects.filter(service="bbps")
            }
            rate_by_op = {r.external_id: r for r in ServiceRateRow.objects.filter(service="bbps")}
            rows = []
            for op in ops:
                op_id = str(op.get("op") or "")
                op_cat = str(op.get("category") or "").upper()
                rate = rate_map.get((op_id, op_cat)) or rate_by_op.get(op_id)
                rows.append(_serialize_bbps_matrix_row(op=op, rate=rate, admin_share_bps=admin_bps))
            linked = sum(1 for r in rows if r.get("has_rate"))
            return {
                "service": "bbps",
                "table": "mobikwik_bbps",
                "total": len(rows),
                "bbps_billers": len(rows),
                "with_rate": linked,
                "without_rate": len(rows) - linked,
                "rates": rows,
                "policy": serialize_service_policy(policy_row),
                "commission_table": {
                    "title": "Mobikwik BBPS",
                    "admin_share_percent": round(admin_bps / 100, 2),
                    "retailer_share_percent": round((10000 - admin_bps) / 100, 2),
                    "rows": rows,
                },
            }

        qs = ServiceRateRow.objects.filter(service="bbps").order_by("category", "name", "external_id")
        total = qs.count()
        rows = [serialize_rate_row(r, admin_share_bps=admin_bps) for r in qs[:fetch_limit]]
        linked = sum(1 for r in rows if r.get("bbps_linked"))
        return {
            "service": "bbps",
            "table": "mobikwik_bbps",
            "total": total,
            "bbps_billers": total,
            "with_rate": total,
            "without_rate": 0,
            "linked": linked,
            "unlinked": len(rows) - linked,
            "rates": rows,
            "policy": serialize_service_policy(policy_row),
            "commission_table": {
                "title": "Mobikwik BBPS",
                "admin_share_percent": round(admin_bps / 100, 2),
                "retailer_share_percent": round((10000 - admin_bps) / 100, 2),
                "rows": rows,
            },
        }

    qs = ServiceRateRow.objects.filter(service=svc).order_by("category", "name", "external_id")
    if category:
        qs = qs.filter(category__iexact=category.strip())
    needle = (q or "").strip().lower()
    if needle:
        qs = qs.filter(
            Q(name__icontains=needle) | Q(external_id__icontains=needle) | Q(category__icontains=needle)
        )
    total = qs.count()
    rows = [serialize_rate_row(r, admin_share_bps=admin_bps) for r in qs[: max(1, min(int(limit), 1000))]]
    return {
        "service": svc,
        "total": total,
        "rates": rows,
        "policy": serialize_service_policy(policy_row),
        "commission_table": {
            "title": f"{svc} rates",
            "admin_share_percent": round(admin_bps / 100, 2),
            "retailer_share_percent": round((10000 - admin_bps) / 100, 2),
            "rows": rows,
        },
    }


def resolve_rate_row(*, service: str, external_id: str, category: str = "", retailer_id: str = "") -> dict[str, Any] | None:
    from models.models import RetailerServiceOverride

    svc = (service or "bbps").strip().lower()
    op = str(external_id or "").strip()
    cat = str(category or "").strip()
    if retailer_id:
        override = RetailerServiceOverride.objects.filter(user_id=retailer_id, service=svc, active=True).first()
        if override:
            for item in override.rate_overrides or []:
                if not isinstance(item, dict):
                    continue
                if str(item.get("external_id") or item.get("operator_id") or "").strip() != op:
                    continue
                item_cat = str(item.get("category") or "").strip()
                if item_cat and cat and item_cat.lower() != cat.lower():
                    continue
                return {
                    "operator_id": op,
                    "external_id": op,
                    "category": item_cat or cat,
                    "rate_value": item.get("rate_value"),
                    "rate_type": str(item.get("rate_type") or "flat"),
                    "min_txn_paise": int(item.get("min_txn_paise") or 0),
                    "source": "retailer_override",
                }
    row = None
    if cat:
        row = ServiceRateRow.objects.filter(service=svc, external_id=op, category__iexact=cat, enabled=True).first()
    if not row:
        row = ServiceRateRow.objects.filter(service=svc, external_id=op, enabled=True).order_by("id").first()
    if not row:
        return None
    return {
        "operator_id": row.external_id,
        "external_id": row.external_id,
        "category": row.category,
        "rate_value": row.rate_value,
        "rate_type": row.rate_type,
        "min_txn_paise": int(row.min_txn_paise),
        "source": "vendor_catalogue",
    }


def _running_under_tests() -> bool:
    return any(arg == "test" or arg.startswith("test") for arg in sys.argv) or "pytest" in sys.modules


def ensure_catalogue(*, service: str = "bbps", path: str | Path | None = None, force: bool = False, actor: str = "boot") -> dict[str, Any]:
    svc = (service or "bbps").strip().lower()
    if _running_under_tests() and not force:
        return {"imported": False, "reason": "test_skip", "service": svc, "count": ServiceRateRow.objects.filter(service=svc).count()}

    file_path = Path(path).expanduser() if path else default_sheet_path(svc)
    policy = get_or_create_service_policy(svc)
    if not file_path.is_file():
        return {"imported": False, "reason": "no_sheet", "service": svc, "path": str(file_path), "count": ServiceRateRow.objects.filter(service=svc).count()}

    try:
        mtime = float(file_path.stat().st_mtime)
    except OSError:
        return {"imported": False, "reason": "stat_failed", "path": str(file_path)}

    empty = not ServiceRateRow.objects.filter(service=svc).exists()
    stale = empty or force or float(policy.rates_file_mtime or 0) < mtime
    if not stale:
        return {"imported": False, "reason": "fresh", "service": svc, "count": ServiceRateRow.objects.filter(service=svc).count()}

    if svc != "bbps":
        return {"imported": False, "reason": "no_importer", "service": svc}

    from domain.payswap.economics.importers.bbps_mobikwik import import_bbps_mobikwik_sheet

    result = import_bbps_mobikwik_sheet(file_path, actor=actor or "ensure")
    return {"imported": True, "reason": "empty" if empty else ("forced" if force else "stale"), "service": svc, **result}


def stamp_policy_import(service: str, *, mtime: float, actor: str = "") -> None:
    policy = get_or_create_service_policy(service)
    policy.rates_file_mtime = float(mtime)
    policy.rates_imported_at = timezone.now()
    if actor:
        policy.updated_by = actor
    policy.save(update_fields=["rates_file_mtime", "rates_imported_at", "updated_by", "updated_at"])


def update_rate_row(
    *,
    service: str,
    external_id: str,
    category: str = "",
    actor: str = "",
    name: str | None = None,
    rate_value: Any = None,
    rate_type: str | None = None,
    min_txn_paise: int | None = None,
    min_txn: Any = None,
    enabled: bool | None = None,
) -> dict[str, Any]:
    """Desk edits one catalogue row; BBPS also mirrors VendorCommissionRate."""
    from decimal import Decimal, InvalidOperation

    from core.actions import log_action
    from models.models import VendorCommissionRate

    svc = (service or "bbps").strip().lower() or "bbps"
    op = str(external_id or "").strip()
    cat = str(category or "").strip()
    if not op:
        raise ValueError("external_id is required.")

    # BBPS: prefer catalogue op / biller_id so settle_success can resolve the same id.
    link = _bbps_link_for_op(op) if svc == "bbps" else {}
    if svc == "bbps" and link.get("bbps_linked"):
        if not cat:
            cat = str(link.get("bbps_category") or "")
        if name is None or str(name).strip() == "":
            name = str(link.get("bbps_name") or "")

    qs = ServiceRateRow.objects.filter(service=svc, external_id=op)
    if cat:
        qs = qs.filter(category__iexact=cat)
    row = qs.first()
    created = False
    if not row:
        if svc == "bbps" and not link.get("bbps_linked"):
            raise ValueError(
                f"Biller id {op} is not in the Mobikwik BBPS catalogue — commission will not settle. Use the BBPS op / biller_id."
            )
        row = ServiceRateRow(
            service=svc,
            external_id=op,
            category=cat,
            name=str(name or "").strip()[:160],
            rate_value=Decimal("0"),
            rate_type="flat",
            min_txn_paise=0,
            enabled=False,
            source_file="desk-edit",
        )
        created = True

    if name is not None:
        row.name = str(name).strip()[:160]
    if rate_type is not None:
        rt = str(rate_type).strip().lower()
        if rt not in {"flat", "percent"}:
            raise ValueError("rate_type must be flat or percent.")
        row.rate_type = rt
    if rate_value is not None and str(rate_value).strip() != "":
        try:
            row.rate_value = Decimal(str(rate_value))
        except (InvalidOperation, TypeError) as exc:
            raise ValueError("rate_value must be a number.") from exc
        if row.rate_value < 0:
            raise ValueError("rate_value cannot be negative.")
    if min_txn_paise is not None:
        row.min_txn_paise = max(0, int(min_txn_paise))
    elif min_txn is not None and str(min_txn).strip() != "":
        try:
            rupees = Decimal(str(min_txn))
        except (InvalidOperation, TypeError) as exc:
            raise ValueError("min_txn must be a rupee amount.") from exc
        row.min_txn_paise = max(0, int((rupees * 100).to_integral_value()))
    if enabled is not None:
        row.enabled = bool(enabled)
    elif created:
        row.enabled = True
    row.source_file = row.source_file or "desk-edit"
    row.save()

    if svc == "bbps":
        VendorCommissionRate.objects.update_or_create(
            operator_id=row.external_id,
            category=row.category,
            defaults={
                "operator_name": row.name,
                "rate_value": row.rate_value,
                "rate_type": row.rate_type,
                "min_txn_paise": int(row.min_txn_paise),
                "bbps_enabled": bool(row.enabled),
                "source_file": row.source_file or "desk-edit",
            },
        )

    policy = get_or_create_service_policy(svc)
    out = serialize_rate_row(row, admin_share_bps=int(policy.admin_share_bps))
    log_action(
        action="domain.payswap.economics.catalogue.update",
        outcome="ok",
        status=200,
        duration_ms=0,
        target_id=f"{svc}:{op}",
        request=json.dumps(
            {"service": svc, "external_id": op, "category": cat, "actor": actor or ""}
        ),
        response=json.dumps(
            {
                "rate_value": out["rate_value"],
                "rate_type": out["rate_type"],
                "enabled": out["enabled"],
                "min_txn_paise": out["min_txn_paise"],
            }
        ),
    )
    return out
