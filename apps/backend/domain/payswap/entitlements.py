"""Retailer service and payment-rail entitlements for PaySwap.

Default policy is stored in DefaultServicePolicy (hub_models). Per-retailer
overrides live in RetailerEntitlement. Admin console manages both via
api/v1/routes/desk.py; PaySwap routes enforce them via api/v1/deps.py.
BBPS category allow-lists filter apps/backend/domain/payswap/bbps.py catalogue.
"""

from __future__ import annotations

import time
from typing import Any

from core.actions import elapsed_ms, log_action
from django.db import transaction
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
    return {
        "catalog": [{"key": k, "label": SERVICE_LABELS[k]} for k in ALL_SERVICES],
        "enabled_services": enabled,
        "bbps_catalog": bbps_catalog,
        # Empty enabled_bbps_categories means unrestricted (all categories).
        "enabled_bbps_categories": enabled_cats,
        "bbps_categories_unrestricted": not bool(raw_cats),
        "allow_wallet_pay": bool(p.allow_wallet_pay),
        "allow_pg_pay": bool(p.allow_pg_pay),
        "allow_pg_topup": bool(p.allow_pg_topup),
        "default_per_txn_limit_paise": int(p.default_per_txn_limit_paise),
        "default_daily_debit_limit_paise": int(p.default_daily_debit_limit_paise),
        "default_min_balance_paise": int(p.default_min_balance_paise),
        "updated_by": p.updated_by,
        "updated_at": p.updated_at.isoformat() if p.updated_at else "",
    }


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
        "payment_modes": {
            "wallet_pay": allow_wallet_pay,
            "pg_pay": allow_pg_pay,
            "pg_topup": allow_pg_topup,
        },
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
    allow_wallet_pay: bool | None = None,
    allow_pg_pay: bool | None = None,
    allow_pg_topup: bool | None = None,
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
        if allow_wallet_pay is not None:
            policy.allow_wallet_pay = bool(allow_wallet_pay)
        if allow_pg_pay is not None:
            policy.allow_pg_pay = bool(allow_pg_pay)
        if allow_pg_topup is not None:
            policy.allow_pg_topup = bool(allow_pg_topup)
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
            f"pg_topup={out['allow_pg_topup']} bbps_cats={len(out['enabled_bbps_categories'])}"
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
        response=f"HTTP 200\nenabled={out['enabled_services']} bbps_cats={len(out['enabled_bbps_categories'])}",
    )
    return out


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
