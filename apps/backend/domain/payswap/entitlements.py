"""Retailer service and payment-rail entitlements for PaySwap.

Default policy is stored in DefaultServicePolicy (hub_models). Per-retailer
overrides live in RetailerEntitlement. Admin console manages both via
api/v1/routes/desk.py; PaySwap routes enforce them via api/v1/deps.py.
BBPS category and biller allow-lists filter apps/backend/domain/payswap/bbps.py catalogue.
"""

from __future__ import annotations

import time
from typing import Any

from core.actions import elapsed_ms, log_action
from django.db import transaction
from domain.payswap.bbps_pipes import normalize_pipe, serialize_pipes
from models.models import DefaultServicePolicy, RetailerEntitlement
from rest_framework.exceptions import PermissionDenied

ALL_SERVICES = (
    "bbps",
    "wallet",
    "transactions",
    "profile",
    "support",
    "recharge",
    "vouchers",
    "dmt",
    "aeps",
)
SERVICE_LABELS = {
    "bbps": "Bill Pay (BBPS)",
    "wallet": "Wallet & Float",
    "transactions": "Transactions",
    "profile": "Profile & KYC",
    "support": "Support",
    "recharge": "Mobile & DTH Recharges",
    "vouchers": "Gift Vouchers",
    "dmt": "Domestic Money Transfer (DMT)",
    "aeps": "AEPS Cash Withdrawal",
}
DEFAULT_ENABLED_SERVICES = ["bbps", "wallet", "transactions", "profile", "support"]
POLICY_KEY = "payswap_default"
_UNSET = object()


def _bbps_category_catalog() -> list[dict[str, Any]]:
    from integrations.bbps import list_categories

    return [
        {"id": str(c.get("id") or ""), "label": str(c.get("label") or c.get("id") or ""), "count": int(c.get("count") or 0)}
        for c in list_categories()
        if c.get("id")
    ]


def _normalize_biller_id(value: Any) -> str:
    return str(value or "").strip()


def _clean_biller_allowlist(raw: Any, *, known_categories: set[str] | None = None) -> dict[str, list[str]]:
    """category -> allow-listed biller_ids. Missing category = unrestricted within that category."""
    if not isinstance(raw, dict):
        return {}
    known = known_categories if known_categories is not None else {c["id"] for c in _bbps_category_catalog()}
    out: dict[str, list[str]] = {}
    for key, val in raw.items():
        cat = str(key or "").strip().upper()
        if not cat or (known and cat not in known):
            continue
        if not isinstance(val, list):
            continue
        seen: set[str] = set()
        cleaned: list[str] = []
        for item in val:
            bid = _normalize_biller_id(item)
            if not bid or bid in seen:
                continue
            seen.add(bid)
            cleaned.append(bid)
        out[cat] = cleaned
    return out


def default_biller_allowlist(policy: DefaultServicePolicy | None = None) -> dict[str, list[str]]:
    p = policy or get_default_policy()
    return _clean_biller_allowlist(getattr(p, "bbps_biller_allowlist", None) or {})


def allowed_billers_for_category(category: str, *, user_id: str = "") -> set[str] | None:
    """None = all billers in the category. Set = curated allow-list (may be empty)."""
    cat = str(category or "").strip().upper()
    if not cat:
        return None
    # Category must be enabled for the retailer before biller rules apply.
    resolved = resolve_bbps_categories(user_id)
    if cat not in set(resolved.get("enabled_bbps_categories") or []):
        return set()
    allowlist = default_biller_allowlist()
    if cat not in allowlist:
        return None
    return set(allowlist.get(cat) or [])


def list_default_bbps_billers(*, category: str, query: str = "", limit: int = 400) -> dict[str, Any]:
    """Desk helper: billers in one category with default allow flags."""
    from integrations.bbps import list_operators

    cat = str(category or "").strip().upper()
    if not cat:
        return {"category": "", "unrestricted": True, "billers": [], "allowed_count": 0, "total": 0}
    allowlist = default_biller_allowlist()
    unrestricted = cat not in allowlist
    allowed = set(allowlist.get(cat) or [])
    rows = list_operators(category=cat, query=query, limit=max(1, min(int(limit or 400), 800)))
    billers = []
    for row in rows:
        bid = _normalize_biller_id(row.get("biller_id"))
        if not bid:
            continue
        billers.append(
            {
                "biller_id": bid,
                "op": str(row.get("op") or ""),
                "name": str(row.get("name") or bid),
                "category": str(row.get("category") or cat),
                "allowed": unrestricted or bid in allowed,
            }
        )
    return {
        "category": cat,
        "unrestricted": unrestricted,
        "billers": billers,
        "allowed_count": len(billers) if unrestricted else sum(1 for b in billers if b["allowed"]),
        "total": len(billers),
    }


def get_default_policy() -> DefaultServicePolicy:
    policy, created = DefaultServicePolicy.objects.get_or_create(
        key=POLICY_KEY,
        defaults={
            "enabled_services": list(DEFAULT_ENABLED_SERVICES),
            "enabled_bbps_categories": [],
            "allow_wallet_pay": True,
            "allow_pg_pay": True,
            "allow_pg_topup": True,
            "default_per_txn_limit_paise": 5_000_000,
            "default_daily_debit_limit_paise": 20_000_000,
            "default_min_balance_paise": 0,
        },
    )
    if created or not isinstance(policy.enabled_services, list):
        if not isinstance(policy.enabled_services, list):
            policy.enabled_services = list(DEFAULT_ENABLED_SERVICES)
            policy.save(update_fields=["enabled_services"])
    return policy


def serialize_default_policy(policy: DefaultServicePolicy | None = None) -> dict[str, Any]:
    p = policy or get_default_policy()
    enabled = [s for s in (p.enabled_services or []) if s in ALL_SERVICES]
    bbps_catalog = _bbps_category_catalog()
    known = {c["id"] for c in bbps_catalog}
    raw_cats = [str(c).strip().upper() for c in (p.enabled_bbps_categories or []) if str(c).strip()]
    enabled_cats = [c for c in raw_cats if c in known]
    biller_allowlist = _clean_biller_allowlist(getattr(p, "bbps_biller_allowlist", None) or {}, known_categories=known)
    bbps_catalog = [
        {
            **cat,
            "biller_restricted": cat["id"] in biller_allowlist,
            "allowed_billers": len(biller_allowlist.get(cat["id"]) or []) if cat["id"] in biller_allowlist else int(cat.get("count") or 0),
        }
        for cat in bbps_catalog
    ]
    return {
        "catalog": [{"key": k, "label": SERVICE_LABELS[k]} for k in ALL_SERVICES],
        "enabled_services": enabled,
        "bbps_catalog": bbps_catalog,
        # Empty enabled_bbps_categories means unrestricted (all categories).
        "enabled_bbps_categories": enabled_cats,
        "bbps_categories_unrestricted": not bool(raw_cats),
        "bbps_biller_allowlist": biller_allowlist,
        "allow_wallet_pay": bool(p.allow_wallet_pay),
        "allow_pg_pay": bool(p.allow_pg_pay),
        "allow_pg_topup": bool(p.allow_pg_topup),
        "pg_provider": (
            str(getattr(p, "pg_provider", "") or "both").strip().lower()
            if str(getattr(p, "pg_provider", "") or "both").strip().lower() in {"cashfree", "payu", "both"}
            else "both"
        ),
        "bbps_pipe": normalize_pipe(getattr(p, "bbps_pipe", "") or "mobikwik"),
        "bbps_bulk_enabled": bool(getattr(p, "bbps_bulk_enabled", False)),
        "bbps_pipes": serialize_pipes(),
        "default_per_txn_limit_paise": int(p.default_per_txn_limit_paise),
        "default_daily_debit_limit_paise": int(p.default_daily_debit_limit_paise),
        "default_min_balance_paise": int(p.default_min_balance_paise),
        "updated_by": p.updated_by,
        "updated_at": p.updated_at.isoformat() if p.updated_at else "",
    }


def resolve_bbps_pipe(user_id: str = "") -> str:
    policy = get_default_policy()
    default_pipe = normalize_pipe(getattr(policy, "bbps_pipe", "") or "mobikwik")
    if not user_id:
        return default_pipe
    row = RetailerEntitlement.objects.filter(user_id=user_id).first()
    if row and str(getattr(row, "bbps_pipe", "") or "").strip():
        return normalize_pipe(row.bbps_pipe)
    return default_pipe


def resolve_bbps_bulk_enabled(user_id: str = "") -> bool:
    policy = get_default_policy()
    default_on = bool(getattr(policy, "bbps_bulk_enabled", False))
    if not user_id:
        return default_on
    row = RetailerEntitlement.objects.filter(user_id=user_id).first()
    if row and row.bbps_bulk_enabled is not None:
        return bool(row.bbps_bulk_enabled)
    return default_on


def resolve_bbps_categories(user_id: str = "") -> dict[str, Any]:
    """Effective BBPS category allow-list for a retailer (or default when user_id empty)."""
    policy = get_default_policy()
    catalog = _bbps_category_catalog()
    known = [c["id"] for c in catalog]
    known_set = set(known)
    raw_default = [str(c).strip().upper() for c in (policy.enabled_bbps_categories or []) if str(c).strip()]
    default_set = {c for c in raw_default if c in known_set} if raw_default else set(known)

    overrides: dict[str, bool] = {}
    if user_id:
        row = RetailerEntitlement.objects.filter(user_id=user_id).first()
        raw_ov = dict(row.bbps_category_overrides or {}) if row and isinstance(row.bbps_category_overrides, dict) else {}
        for key, val in raw_ov.items():
            cat = str(key).strip().upper()
            if cat in known_set and isinstance(val, bool):
                overrides[cat] = val

    allowed: set[str] = set(default_set)
    for cat, val in overrides.items():
        if val:
            allowed.add(cat)
        else:
            allowed.discard(cat)

    categories_map = {cat: cat in allowed for cat in known}
    return {
        "catalog": catalog,
        "enabled_bbps_categories": [c for c in known if categories_map.get(c)],
        "bbps_categories": categories_map,
        "bbps_category_overrides": overrides,
        "bbps_categories_unrestricted": not bool(raw_default) and not overrides,
    }


def resolve_retailer_entitlements(user_id: str) -> dict[str, Any]:
    policy = get_default_policy()
    default_set = {s for s in (policy.enabled_services or []) if s in ALL_SERVICES}
    row = RetailerEntitlement.objects.filter(user_id=user_id).first()
    overrides = dict(row.service_overrides or {}) if row and isinstance(row.service_overrides, dict) else {}

    services_map: dict[str, bool] = {}
    for svc in ALL_SERVICES:
        if svc in overrides and isinstance(overrides[svc], bool):
            services_map[svc] = overrides[svc]
        else:
            services_map[svc] = svc in default_set

    enabled_list = [svc for svc in ALL_SERVICES if services_map.get(svc, False)]
    allow_wallet_pay = (
        bool(row.allow_wallet_pay)
        if row and row.allow_wallet_pay is not None
        else bool(policy.allow_wallet_pay)
    )
    allow_pg_pay = (
        bool(row.allow_pg_pay)
        if row and row.allow_pg_pay is not None
        else bool(policy.allow_pg_pay)
    )
    allow_pg_topup = (
        bool(row.allow_pg_topup)
        if row and row.allow_pg_topup is not None
        else bool(policy.allow_pg_topup)
    )
    bbps = resolve_bbps_categories(user_id)
    bbps_pipe = resolve_bbps_pipe(user_id)
    bbps_bulk = resolve_bbps_bulk_enabled(user_id)

    return {
        "user_id": user_id,
        "catalog": [{"key": k, "label": SERVICE_LABELS[k]} for k in ALL_SERVICES],
        "services": services_map,
        "enabled_services": enabled_list,
        "service_overrides": overrides,
        "bbps_catalog": bbps["catalog"],
        "enabled_bbps_categories": bbps["enabled_bbps_categories"],
        "bbps_categories": bbps["bbps_categories"],
        "bbps_category_overrides": bbps["bbps_category_overrides"],
        "bbps_pipe": bbps_pipe,
        "bbps_bulk_enabled": bbps_bulk,
        "bbps_pipes": serialize_pipes(),
        "bbps_pipe_override": (row.bbps_pipe if row and str(row.bbps_pipe or "").strip() else None),
        "bbps_bulk_override": (row.bbps_bulk_enabled if row else None),
        "payment_modes": {
            "wallet_pay": allow_wallet_pay,
            "pg_pay": allow_pg_pay,
            "pg_topup": allow_pg_topup,
        },
        "pg_provider": serialize_default_policy(policy).get("pg_provider", "both"),
        "payment_overrides": {
            "allow_wallet_pay": row.allow_wallet_pay if row else None,
            "allow_pg_pay": row.allow_pg_pay if row else None,
            "allow_pg_topup": row.allow_pg_topup if row else None,
        },
        "updated_by": row.updated_by if row else "",
        "updated_at": row.updated_at.isoformat() if row and row.updated_at else "",
    }


def update_default_policy(
    *,
    enabled_services: list[str] | None = None,
    enabled_bbps_categories: list[str] | None = None,
    bbps_biller_allowlist: dict[str, list[str] | None] | None = None,
    allow_wallet_pay: bool | None = None,
    allow_pg_pay: bool | None = None,
    allow_pg_topup: bool | None = None,
    pg_provider: str | None = None,
    bbps_pipe: str | None = None,
    bbps_bulk_enabled: bool | None = None,
    default_per_txn_limit_paise: int | None = None,
    default_daily_debit_limit_paise: int | None = None,
    default_min_balance_paise: int | None = None,
    admin_email: str = "",
) -> dict[str, Any]:
    started = time.perf_counter()
    with transaction.atomic():
        policy = get_default_policy()
        if enabled_services is not None:
            policy.enabled_services = [s for s in enabled_services if s in ALL_SERVICES]
        if enabled_bbps_categories is not None:
            known = {c["id"] for c in _bbps_category_catalog()}
            cleaned = [str(c).strip().upper() for c in enabled_bbps_categories if str(c).strip()]
            policy.enabled_bbps_categories = [c for c in cleaned if c in known]
        if bbps_biller_allowlist is not None:
            known = {c["id"] for c in _bbps_category_catalog()}
            merged = _clean_biller_allowlist(getattr(policy, "bbps_biller_allowlist", None) or {}, known_categories=known)
            for key, val in (bbps_biller_allowlist or {}).items():
                cat = str(key or "").strip().upper()
                if not cat or cat not in known:
                    continue
                # null / omit-as-unrestricted clears the curated list for that category.
                if val is None:
                    merged.pop(cat, None)
                    continue
                if not isinstance(val, list):
                    continue
                seen: set[str] = set()
                cleaned_ids: list[str] = []
                for item in val:
                    bid = _normalize_biller_id(item)
                    if not bid or bid in seen:
                        continue
                    seen.add(bid)
                    cleaned_ids.append(bid)
                merged[cat] = cleaned_ids
            policy.bbps_biller_allowlist = merged
        if allow_wallet_pay is not None:
            policy.allow_wallet_pay = bool(allow_wallet_pay)
        if allow_pg_pay is not None:
            policy.allow_pg_pay = bool(allow_pg_pay)
        if allow_pg_topup is not None:
            policy.allow_pg_topup = bool(allow_pg_topup)
        if pg_provider is not None:
            mode = str(pg_provider).strip().lower()
            if mode in {"cashfree", "payu", "both"}:
                policy.pg_provider = mode
        if bbps_pipe is not None:
            policy.bbps_pipe = normalize_pipe(bbps_pipe)
        if bbps_bulk_enabled is not None:
            policy.bbps_bulk_enabled = bool(bbps_bulk_enabled)
        if default_per_txn_limit_paise is not None and default_per_txn_limit_paise >= 0:
            policy.default_per_txn_limit_paise = int(default_per_txn_limit_paise)
        if default_daily_debit_limit_paise is not None and default_daily_debit_limit_paise >= 0:
            policy.default_daily_debit_limit_paise = int(default_daily_debit_limit_paise)
        if default_min_balance_paise is not None and default_min_balance_paise >= 0:
            policy.default_min_balance_paise = int(default_min_balance_paise)
        policy.updated_by = admin_email
        policy.save()
    out = serialize_default_policy(policy)
    log_action(
        action="desk.entitlements.default.update",
        outcome="ok",
        status=200,
        duration_ms=elapsed_ms(started),
        target_id=POLICY_KEY,
        request=f"POST /api/v1/desk/entitlements/default\nenabled={out['enabled_services']}",
        response=(
            f"HTTP 200\nwallet={out['allow_wallet_pay']} pg_pay={out['allow_pg_pay']} "
            f"pg_topup={out['allow_pg_topup']} pg_provider={out['pg_provider']} "
            f"bbps_pipe={out['bbps_pipe']} bulk={out['bbps_bulk_enabled']} "
            f"bbps_cats={len(out['enabled_bbps_categories'])} "
            f"biller_cats={len(out.get('bbps_biller_allowlist') or {})}"
        ),
    )
    return out


def update_retailer_entitlements(
    user_id: str,
    *,
    service_overrides: dict[str, bool | None] | None = None,
    bbps_category_overrides: dict[str, bool | None] | None = None,
    allow_wallet_pay: Any = _UNSET,
    allow_pg_pay: Any = _UNSET,
    allow_pg_topup: Any = _UNSET,
    bbps_pipe: Any = _UNSET,
    bbps_bulk_enabled: Any = _UNSET,
    clear_payment_overrides: bool = False,
    admin_email: str = "",
) -> dict[str, Any]:
    started = time.perf_counter()
    with transaction.atomic():
        row, _ = RetailerEntitlement.objects.select_for_update().get_or_create(
            user_id=user_id,
            defaults={"service_overrides": {}, "bbps_category_overrides": {}},
        )
        if service_overrides is not None:
            merged = dict(row.service_overrides or {})
            for key, val in service_overrides.items():
                if key not in ALL_SERVICES:
                    continue
                if val is None:
                    merged.pop(key, None)
                else:
                    merged[key] = bool(val)
            row.service_overrides = merged
        if bbps_category_overrides is not None:
            known = {c["id"] for c in _bbps_category_catalog()}
            merged_cats = dict(row.bbps_category_overrides or {})
            for key, val in bbps_category_overrides.items():
                cat = str(key).strip().upper()
                if cat not in known:
                    continue
                if val is None:
                    merged_cats.pop(cat, None)
                else:
                    merged_cats[cat] = bool(val)
            row.bbps_category_overrides = merged_cats
        if clear_payment_overrides:
            row.allow_wallet_pay = None
            row.allow_pg_pay = None
            row.allow_pg_topup = None
        else:
            if allow_wallet_pay is not _UNSET:
                row.allow_wallet_pay = None if allow_wallet_pay is None else bool(allow_wallet_pay)
            if allow_pg_pay is not _UNSET:
                row.allow_pg_pay = None if allow_pg_pay is None else bool(allow_pg_pay)
            if allow_pg_topup is not _UNSET:
                row.allow_pg_topup = None if allow_pg_topup is None else bool(allow_pg_topup)
        if bbps_pipe is not _UNSET:
            if bbps_pipe is None or str(bbps_pipe).strip() == "" or str(bbps_pipe).strip().lower() == "default":
                row.bbps_pipe = ""
            else:
                row.bbps_pipe = normalize_pipe(str(bbps_pipe))
        if bbps_bulk_enabled is not _UNSET:
            row.bbps_bulk_enabled = None if bbps_bulk_enabled is None else bool(bbps_bulk_enabled)
        row.updated_by = admin_email
        row.save()
    out = resolve_retailer_entitlements(user_id)
    log_action(
        action="desk.entitlements.retailer.update",
        outcome="ok",
        status=200,
        duration_ms=elapsed_ms(started),
        target_id=user_id,
        request=f"POST /api/v1/desk/entitlements/retailer\nuser={user_id}",
        response=(
            f"HTTP 200\nenabled={out['enabled_services']} pipe={out['bbps_pipe']} "
            f"bulk={out['bbps_bulk_enabled']} bbps_cats={len(out['enabled_bbps_categories'])}"
        ),
    )
    return out


def require_bbps_bulk(user_id: str) -> dict[str, Any]:
    resolved = require_retailer_service(user_id, "bbps")
    if not resolve_bbps_bulk_enabled(user_id):
        log_action(
            action="payswap.entitlement.block",
            outcome="error",
            status=403,
            duration_ms=0,
            target_id="bbps_bulk",
            error_code="service_disabled",
            error_reason="Bulk BBPS is not enabled for this retailer.",
            request="service=bbps_bulk",
            response="HTTP 403\nservice_disabled",
        )
        raise PermissionDenied(
            detail={
                "error": "Bulk bill payment is not enabled for your account. Contact admin.",
                "code": "service_disabled",
            }
        )
    pipe = resolve_bbps_pipe(user_id)
    from domain.payswap.bbps_pipes import pipe_configured

    if not pipe_configured(pipe):
        raise PermissionDenied(
            detail={
                "error": "Your BBPS pipe is not available. Contact admin.",
                "code": "bulk_pipe_unavailable",
            }
        )
    resolved["bbps_pipe"] = pipe
    resolved["bbps_bulk_enabled"] = True
    return resolved


def require_retailer_service(user_id: str, service_key: str) -> dict[str, Any]:
    resolved = resolve_retailer_entitlements(user_id)
    if not resolved["services"].get(service_key, False):
        log_action(
            action="payswap.entitlement.block",
            outcome="error",
            status=403,
            duration_ms=0,
            target_id=service_key,
            error_code="service_disabled",
            error_reason=f"Service '{service_key}' is not enabled for this retailer.",
            request=f"service={service_key}",
            response="HTTP 403\nservice_disabled",
        )
        raise PermissionDenied(
            detail={
                "error": f"{SERVICE_LABELS.get(service_key, service_key)} is not enabled for your account. Contact admin.",
                "code": "service_disabled",
            }
        )
    return resolved


def require_bbps_category(user_id: str, category: str = "") -> dict[str, Any]:
    """Block fetch/pay when the biller category is outside the retailer allow-list."""
    resolved = resolve_bbps_categories(user_id)
    allowed = set(resolved.get("enabled_bbps_categories") or [])
    cat = str(category or "").strip().upper()
    if cat and cat in allowed:
        return resolved
    log_action(
        action="payswap.bbps.category.block",
        outcome="error",
        status=403,
        duration_ms=0,
        target_id=cat or "unknown",
        error_code="bbps_category_disabled",
        error_reason=f"BBPS category '{cat or 'unknown'}' is not enabled for this retailer.",
        request=f"category={cat or 'unknown'}",
        response="HTTP 403\nbbps_category_disabled",
    )
    raise PermissionDenied(
        detail={
            "error": "This bill category is not enabled for your account. Contact admin.",
            "code": "bbps_category_disabled",
        }
    )


def require_bbps_biller(user_id: str, *, category: str = "", biller_id: str = "") -> dict[str, Any]:
    """Block fetch/pay when a curated default allow-list excludes this biller."""
    resolved = require_bbps_category(user_id, category)
    bid = _normalize_biller_id(biller_id)
    cat = str(category or "").strip().upper()
    allowed = allowed_billers_for_category(cat, user_id=user_id)
    if allowed is None or (bid and bid in allowed):
        return resolved
    log_action(
        action="payswap.bbps.biller.block",
        outcome="error",
        status=403,
        duration_ms=0,
        target_id=bid or "unknown",
        error_code="bbps_biller_disabled",
        error_reason=f"BBPS biller '{bid or 'unknown'}' is not enabled in {cat or 'category'}.",
        request=f"category={cat or 'unknown'} biller={bid or 'unknown'}",
        response="HTTP 403\nbbps_biller_disabled",
    )
    raise PermissionDenied(
        detail={
            "error": "This biller is not enabled for your account. Contact admin.",
            "code": "bbps_biller_disabled",
        }
    )


def require_payment_rail(user_id: str, rail: str, *, for_topup: bool = False) -> dict[str, Any]:
    resolved = resolve_retailer_entitlements(user_id)
    modes = resolved["payment_modes"]
    if for_topup:
        allowed = bool(modes.get("pg_topup")) if rail == "pg" else True
    elif rail == "wallet":
        allowed = bool(modes.get("wallet_pay"))
    elif rail == "pg":
        allowed = bool(modes.get("pg_pay"))
    else:
        allowed = False
    if not allowed:
        log_action(
            action="payswap.payment_rail.block",
            outcome="error",
            status=403,
            duration_ms=0,
            target_id=rail,
            error_code="payment_mode_disabled",
            error_reason=f"Payment rail '{rail}' is disabled for this retailer.",
            request=f"rail={rail} for_topup={for_topup}",
            response="HTTP 403\npayment_mode_disabled",
        )
        raise PermissionDenied(
            detail={
                "error": f"Payment via {rail.upper()} is disabled for your account. Contact admin.",
                "code": "payment_mode_disabled",
            }
        )
    return resolved
