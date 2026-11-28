"""PayU hosted checkout orchestration on top of models.PgOrder.

initiate builds form params for an existing unpaid order.
Callbacks verify reverse hash (or verify_payment fallback) then settle.
"""

from __future__ import annotations

import re
import secrets
import time
from decimal import Decimal, InvalidOperation
from typing import Any

from core.actions import elapsed_ms, log_action
from domain.payswap.wallet import WalletError, apply_pg_topup_paid
from integrations.payu import (
    PayUConfigError,
    build_checkout_params,
    payu_configured,
    require_payu_config,
    reverse_hash_ok,
    verify_payment,
)
from models.models import PgOrder

_TXN_RE = re.compile(r"^[A-Za-z0-9_-]{8,25}$")
_FRONTEND_OK = "http://127.0.0.1:4500/#wallet"
_FRONTEND_FAIL = "http://127.0.0.1:4500/#wallet"


def _amount_str(paise: int) -> str:
    return f"{Decimal(paise) / Decimal(100):.2f}"


def _new_txnid() -> str:
    # Unique per attempt; alphanumeric + hyphen, max 25.
    return ("pu" + secrets.token_hex(10))[:25]


def _paid_amount_ok(order: PgOrder, paid_amount: str) -> bool:
    """Settle only when PayU reports the same rupee amount as the stored order."""
    if not str(paid_amount or "").strip():
        return False
    return _amounts_equal(int(order.amount_paise), str(paid_amount))


def _amounts_equal(order_paise: int, posted_amount: str) -> bool:
    try:
        posted = Decimal(str(posted_amount).strip())
    except (InvalidOperation, ValueError):
        return False
    expected = Decimal(order_paise) / Decimal(100)
    return posted == expected.quantize(Decimal("0.01"))


def resolve_pg_provider() -> str:
    """cashfree | payu | both — from default policy, else env PAYSWAP_PG_PROVIDER."""
    from domain.payswap.entitlements import get_default_policy

    policy = get_default_policy()
    raw = str(getattr(policy, "pg_provider", "") or "").strip().lower()
    if raw not in {"cashfree", "payu", "both"}:
        import os

        raw = (os.environ.get("PAYSWAP_PG_PROVIDER", "both") or "both").strip().lower()
    if raw not in {"cashfree", "payu", "both"}:
        raw = "both"
    return raw


def pick_provider(*, prefer: str = "") -> str:
    """Choose gateway for a new order. prefer may be cashfree|payu when mode is both."""
    mode = resolve_pg_provider()
    pref = (prefer or "").strip().lower()
    if mode == "payu":
        if not payu_configured():
            raise WalletError("PayU is not configured.", status=503, code="server_error")
        return "payu"
    if mode == "cashfree":
        return "cashfree"
    # both
    if pref == "payu" and payu_configured():
        return "payu"
    if pref == "cashfree":
        return "cashfree"
    if payu_configured():
        return "payu"
    return "cashfree"


def initiate_payu_checkout(order_id: str, *, user_id: str = "") -> dict[str, Any]:
    """POST /api/payu/initiate body { order_id }. Returns { action, params }."""
    started = time.perf_counter()
    try:
        require_payu_config()
    except PayUConfigError as err:
        log_action(
            action="payswap.payu.initiate",
            outcome="error",
            status=500,
            duration_ms=elapsed_ms(started),
            target_id=order_id or "",
            error_code="server_error",
            error_reason=str(err),
            request=f"order_id={order_id}",
            response="HTTP 500\npayment provider misconfigured",
        )
        raise WalletError("payment provider misconfigured", status=500, code="server_error") from err

    if not order_id:
        raise WalletError("order_id is required.", status=400, code="validation")

    order = PgOrder.objects.filter(pg_order_id=order_id).first()
    if order is None:
        raise WalletError("Order not found.", status=404, code="validation")
    if user_id and order.user_id != user_id:
        raise WalletError("Order not found.", status=404, code="validation")
    if order.provider != "payu":
        raise WalletError("Order is not a PayU payment.", status=400, code="validation")
    if order.status == "paid":
        raise WalletError("Order is already paid.", status=409, code="conflict")
    if order.status == "failed":
        # Retry needs a fresh txnid.
        pass

    meta = dict(order.meta or {})
    firstname = str(meta.get("firstname") or order.user_id.split("@")[0] or "Retailer")[:60]
    email = str(meta.get("email") or order.user_id).strip()
    phone = str(meta.get("phone") or "9999999999")
    productinfo = str(meta.get("productinfo") or ("Wallet top-up" if order.purpose == "wallet_topup" else "Bill payment"))[:100]
    if not email or "@" not in email:
        raise WalletError("Customer email is required for PayU.", status=400, code="validation")
    if not firstname.strip():
        raise WalletError("Customer name is required for PayU.", status=400, code="validation")

    amount = _amount_str(int(order.amount_paise))
    if Decimal(amount) <= 0:
        raise WalletError("Invalid order amount.", status=400, code="validation")

    txnid = _new_txnid()
    if not _TXN_RE.fullmatch(txnid):
        raise WalletError("Could not allocate txnid.", status=500, code="server_error")

    checkout = build_checkout_params(
        txnid=txnid,
        amount=amount,
        productinfo=productinfo,
        firstname=firstname.strip(),
        email=email,
        phone="".join(ch for ch in phone if ch.isdigit())[-10:] or "9999999999",
        udf1=order.pg_order_id,
        udf2=order.purpose,
        udf3=order.user_id[:50],
    )
    order.provider_order_id = txnid
    order.status = "created"
    meta["txnid"] = txnid
    meta["amount"] = amount
    meta["productinfo"] = productinfo
    meta["firstname"] = firstname.strip()
    meta["email"] = email
    order.meta = meta
    order.save(update_fields=["provider_order_id", "status", "meta", "updated_at"])

    log_action(
        action="payswap.payu.initiate",
        outcome="ok",
        status=200,
        duration_ms=elapsed_ms(started),
        target_id=order.pg_order_id,
        request=f"order_id={order.pg_order_id} purpose={order.purpose}",
        response=f"HTTP 200\ntxnid={txnid}",
    )
    return {
        "order_id": order.pg_order_id,
        "txnid": txnid,
        "provider": "payu",
        "action": checkout["action"],
        "params": checkout["params"],
    }


def frontend_result_url(order: PgOrder | None, *, ok: bool) -> str:
    import os

    base = (os.environ.get("PAYSWAP_ORIGIN") or "http://127.0.0.1:4500").rstrip("/")
    page = "bills" if order and order.purpose == "bbps_direct" else "wallet"
    oid = order.pg_order_id if order else ""
    flag = "ok" if ok else "fail"
    if oid:
        return f"{base}/#{page}?payu={flag}&order_id={oid}"
    return f"{base}/#{page}?payu={flag}"


def _settle_success(order: PgOrder, *, provider_payment_id: str, signature_verified: bool, paid_amount: str) -> None:
    if order.status == "paid":
        return
    if order.purpose == "wallet_topup":
        apply_pg_topup_paid(
            order.pg_order_id,
            provider_payment_id=provider_payment_id,
            signature_verified=signature_verified,
            paid_amount=paid_amount,
        )
        return
    if order.purpose == "bbps_direct":
        from domain.payswap.bbps import execute_pg_paid_bbps

        execute_pg_paid_bbps(order.pg_order_id, provider_payment_id=provider_payment_id, paid_amount=paid_amount)
        return
    raise WalletError("Unsupported PayU order purpose.", status=400, code="validation")


def handle_payu_callback(posted: dict[str, Any]) -> dict[str, Any]:
    """Shared surl/furl handler. Returns { redirect, order_id, status }."""
    started = time.perf_counter()
    txnid = str(posted.get("txnid") or "").strip()
    status = str(posted.get("status") or "").strip().lower()
    order_id = str(posted.get("udf1") or "").strip()
    amount = str(posted.get("amount") or "").strip()

    order = None
    if order_id:
        order = PgOrder.objects.filter(pg_order_id=order_id, provider="payu").first()
    if order is None and txnid:
        order = PgOrder.objects.filter(provider_order_id=txnid, provider="payu").first()

    if order is None:
        log_action(
            action="payswap.payu.callback",
            outcome="error",
            status=400,
            duration_ms=elapsed_ms(started),
            target_id=txnid or order_id,
            error_code="validation",
            error_reason="unknown txnid",
            request=f"txnid={txnid} status={status}",
            response="HTTP 400\nunknown order",
        )
        return {"redirect": frontend_result_url(None, ok=False), "order_id": "", "status": "failed"}

    # Already final — idempotent redirect (still reject tampered hash below when present).
    try:
        cfg = require_payu_config()
        hash_ok = reverse_hash_ok(
            posted, key=cfg["key"], salt=cfg["salt"], salt_v2=cfg.get("salt_v2") or ""
        )
    except PayUConfigError:
        hash_ok = False

    verified_via = "hash" if hash_ok else ""
    mapped = status if hash_ok else ""
    verify: dict[str, Any] = {}

    if not hash_ok:
        log_action(
            action="payswap.payu.callback",
            outcome="error",
            status=400,
            duration_ms=elapsed_ms(started),
            target_id=order.pg_order_id,
            error_code="validation",
            error_reason="hash mismatch",
            request=f"txnid={txnid} status={status}",
            response="HTTP 400\nhash mismatch; trying verify_payment",
        )
        verify = verify_payment(order.provider_order_id or txnid)
        if not verify.get("ok"):
            return {"redirect": frontend_result_url(order, ok=False), "order_id": order.pg_order_id, "status": order.status}
        mapped = str(verify.get("status") or "")
        verified_via = "verify_payment"
        amount = str(verify.get("amount") or "")
        if mapped == "success":
            status = "success"
        elif mapped == "failure":
            status = "failure"
        else:
            return {"redirect": frontend_result_url(order, ok=False), "order_id": order.pg_order_id, "status": order.status}

    if order.provider_order_id and txnid and order.provider_order_id != txnid:
        log_action(
            action="payswap.payu.callback",
            outcome="error",
            status=400,
            duration_ms=elapsed_ms(started),
            target_id=order.pg_order_id,
            error_code="validation",
            error_reason="txnid mismatch",
            request=f"txnid={txnid}",
            response="HTTP 400\ntxnid mismatch",
        )
        return {"redirect": frontend_result_url(order, ok=False), "order_id": order.pg_order_id, "status": order.status}

    if (status == "success" or mapped == "success") and not _paid_amount_ok(order, amount):
        log_action(
            action="payswap.payu.callback",
            outcome="error",
            status=400,
            duration_ms=elapsed_ms(started),
            target_id=order.pg_order_id,
            error_code="validation",
            error_reason="amount mismatch",
            request=f"txnid={txnid} via={verified_via}",
            response="HTTP 400\namount mismatch",
        )
        return {"redirect": frontend_result_url(order, ok=False), "order_id": order.pg_order_id, "status": order.status}

    if order.status == "paid":
        # Never downgrade.
        return {"redirect": frontend_result_url(order, ok=True), "order_id": order.pg_order_id, "status": "paid"}

    if status == "success" or mapped == "success":
        mihpayid = str(posted.get("mihpayid") or verify.get("provider_payment_id") or "")
        _settle_success(
            order,
            provider_payment_id=mihpayid,
            signature_verified=bool(hash_ok or verified_via == "verify_payment"),
            paid_amount=amount,
        )
        log_action(
            action="payswap.payu.callback",
            outcome="ok",
            status=200,
            duration_ms=elapsed_ms(started),
            target_id=order.pg_order_id,
            request=f"txnid={txnid} via={verified_via}",
            response="HTTP 200\npaid",
        )
        return {"redirect": frontend_result_url(order, ok=True), "order_id": order.pg_order_id, "status": "paid"}

    if status == "failure" or mapped == "failure":
        if order.status != "paid":
            order.status = "failed"
            order.save(update_fields=["status", "updated_at"])
        log_action(
            action="payswap.payu.callback",
            outcome="ok",
            status=200,
            duration_ms=elapsed_ms(started),
            target_id=order.pg_order_id,
            request=f"txnid={txnid} via={verified_via}",
            response="HTTP 200\nfailed",
        )
        return {"redirect": frontend_result_url(order, ok=False), "order_id": order.pg_order_id, "status": "failed"}

    # pending / other — leave unchanged
    log_action(
        action="payswap.payu.callback",
        outcome="ok",
        status=200,
        duration_ms=elapsed_ms(started),
        target_id=order.pg_order_id,
        request=f"txnid={txnid} status={status}",
        response="HTTP 200\npending",
    )
    return {"redirect": frontend_result_url(order, ok=False), "order_id": order.pg_order_id, "status": order.status}


def verify_payu_order(order_id: str, *, user_id: str = "") -> dict[str, Any]:
    order = PgOrder.objects.filter(pg_order_id=order_id, provider="payu").first()
    if order is None:
        raise WalletError("Order not found.", status=404, code="validation")
    if user_id and order.user_id != user_id:
        raise WalletError("Order not found.", status=404, code="validation")
    txnid = order.provider_order_id or str((order.meta or {}).get("txnid") or "")
    if not txnid:
        raise WalletError("No PayU txnid on this order.", status=400, code="validation")
    if order.status == "paid":
        return {"order_id": order.pg_order_id, "txnid": txnid, "status": "paid"}

    result = verify_payment(txnid)
    if not result.get("ok"):
        raise WalletError("Could not verify payment with PayU.", status=503, code="server_error")
    mapped = result.get("status")
    if mapped == "success":
        if not _paid_amount_ok(order, str(result.get("amount") or "")):
            raise WalletError("PayU amount does not match this order.", status=400, code="validation")
        _settle_success(
            order,
            provider_payment_id=str(result.get("provider_payment_id") or ""),
            signature_verified=True,
            paid_amount=str(result.get("amount") or ""),
        )
        return {"order_id": order.pg_order_id, "txnid": txnid, "status": "paid"}
    if mapped == "failure":
        if order.status != "paid":
            from domain.payswap.wallet import abandon_unpaid_pg_order

            abandon_unpaid_pg_order(order, reason="payu:failure")
        return {"order_id": order.pg_order_id, "txnid": txnid, "status": "failed"}
    if order.status == "created":
        from domain.payswap.wallet import PG_ORDER_STALE_MINUTES, abandon_unpaid_pg_order, pg_stale_cutoff

        if order.created_at and order.created_at <= pg_stale_cutoff():
            abandon_unpaid_pg_order(order, reason=f"no_success_after_{PG_ORDER_STALE_MINUTES}m")
            return {"order_id": order.pg_order_id, "txnid": txnid, "status": "failed"}
    return {"order_id": order.pg_order_id, "txnid": txnid, "status": order.status}
