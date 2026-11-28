"""Payment gateway adapter (Cashfree PG v3) for retailer wallet top-up and direct pay.

Uses Cashfree Payment Links so the browser gets a real hosted checkout URL
(payments-test.cashfree.com / payments.cashfree.com). That avoids the JS-SDK
domain whitelist problem on localhost.

Callers: domain/payswap/wallet.py and domain/payswap/bbps.py.
Credentials: CASHFREE_PG_APP_ID, CASHFREE_PG_SECRET, CASHFREE_PG_ENV,
CASHFREE_PG_RETURN_URL, CASHFREE_PG_NOTIFY_URL (or apps/backend/data/pg.env).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from core.actions import elapsed_ms, log_action

_DATA_ENV = Path(__file__).resolve().parents[1] / "data" / "pg.env"
_API_VERSION = "2023-08-01"


def _ssl_context() -> ssl.SSLContext | None:
    # Same as integrations/bbps.py / kaleyra.py — macOS Python often lacks system roots.
    try:
        import certifi
    except ImportError:
        return None
    return ssl.create_default_context(cafile=certifi.where())


def _load_env() -> dict[str, str]:
    vals: dict[str, str] = {}
    if _DATA_ENV.exists():
        for line in _DATA_ENV.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            vals[k.strip()] = v.strip().strip('"').strip("'")
    for key in (
        "CASHFREE_PG_APP_ID",
        "CASHFREE_PG_SECRET",
        "CASHFREE_PG_ENV",
        "CASHFREE_PG_BASE_URL",
        "CASHFREE_PG_RETURN_URL",
        "CASHFREE_PG_NOTIFY_URL",
    ):
        if os.environ.get(key):
            vals[key] = os.environ[key]
    return vals


def pg_configured() -> bool:
    cfg = _load_env()
    return bool(cfg.get("CASHFREE_PG_APP_ID") and cfg.get("CASHFREE_PG_SECRET"))


def _base_url(cfg: dict[str, str]) -> str:
    explicit = cfg.get("CASHFREE_PG_BASE_URL", "").strip().rstrip("/")
    if explicit:
        return explicit
    env = cfg.get("CASHFREE_PG_ENV", "sandbox").strip().lower()
    if env == "production":
        return "https://api.cashfree.com/pg"
    return "https://sandbox.cashfree.com/pg"


def _cashfree_mode(cfg: dict[str, str]) -> str:
    env = (cfg.get("CASHFREE_PG_ENV") or "sandbox").strip().lower() or "sandbox"
    return env if env in {"sandbox", "production"} else "sandbox"


def _pg_request(
    *,
    method: str,
    url: str,
    app_id: str,
    secret: str,
    payload: dict[str, Any] | None = None,
) -> tuple[int, dict[str, Any], str]:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {
        "x-api-version": _API_VERSION,
        "x-client-id": app_id,
        "x-client-secret": secret,
        "Accept": "application/json",
    }
    if body is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=20, context=_ssl_context()) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            data = json.loads(raw) if raw.strip() else {}
            return int(resp.getcode() or 200), data if isinstance(data, dict) else {}, raw[:400]
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            data = json.loads(raw) if raw.strip() else {}
        except json.JSONDecodeError:
            data = {}
        return int(exc.code), data if isinstance(data, dict) else {}, raw[:400]
    except Exception as exc:
        return 0, {}, str(exc)[:400]


def create_gateway_order(
    *,
    order_id: str,
    amount_paise: int,
    customer_id: str,
    customer_email: str,
    customer_phone: str,
    note: str = "",
    return_url: str = "",
) -> dict[str, Any]:
    """Create a Cashfree Payment Link. Returns checkout_url for a full-page redirect."""
    started = time.perf_counter()
    cfg = _load_env()
    app_id = cfg.get("CASHFREE_PG_APP_ID", "")
    secret = cfg.get("CASHFREE_PG_SECRET", "")
    if not app_id or not secret:
        log_action(
            action="integration.pg.create_order",
            outcome="error",
            status=503,
            duration_ms=elapsed_ms(started),
            target_id=order_id,
            error_code="server_error",
            error_reason="Payment gateway is not configured.",
            request=f"POST /pg/links\nlink_id={order_id} amount_paise={amount_paise}",
            response="HTTP 503\nPayment gateway credentials missing.",
        )
        return {
            "ok": False,
            "status": 503,
            "error": "Payment gateway is not configured on this server. Use Wallet or contact admin.",
        }

    base = _base_url(cfg)
    amount_inr = round(amount_paise / 100.0, 2)
    phone = "".join(ch for ch in (customer_phone or "") if ch.isdigit())[-10:] or "9999999999"
    name = (customer_id.split("@")[0] if "@" in customer_id else customer_id)[:50] or "Retailer"
    ret = (
        return_url
        or cfg.get("CASHFREE_PG_RETURN_URL")
        or "http://127.0.0.1:4500/?cf_order_id={link_id}#wallet"
    )
    # Payment Links replace {link_id}; keep {order_id} alias for older env values.
    ret = ret.replace("{order_id}", "{link_id}")
    payload: dict[str, Any] = {
        "link_id": order_id,
        "link_amount": amount_inr,
        "link_currency": "INR",
        "link_purpose": (note or "PaySwap payment")[:500],
        "customer_details": {
            "customer_phone": phone,
            "customer_email": customer_email or "",
            "customer_name": name,
        },
        "link_meta": {"return_url": ret},
        "link_notify": {"send_sms": False, "send_email": False},
    }
    if cfg.get("CASHFREE_PG_NOTIFY_URL"):
        payload["link_meta"]["notify_url"] = cfg["CASHFREE_PG_NOTIFY_URL"]

    status, data, err_snip = _pg_request(
        method="POST",
        url=f"{base}/links",
        app_id=app_id,
        secret=secret,
        payload=payload,
    )
    if status >= 400 or not data.get("link_url"):
        log_action(
            action="integration.pg.create_order",
            outcome="error",
            status=status if status else 502,
            duration_ms=elapsed_ms(started),
            target_id=order_id,
            error_code="server_error",
            error_reason=f"PG HTTP {status}" if status else "empty link_url",
            request=f"POST {base}/links\nlink_id={order_id} amount={amount_inr}",
            response=f"HTTP {status}\n{err_snip}",
        )
        if status == 0:
            return {"ok": False, "status": 502, "error": "Could not reach payment gateway."}
        return {"ok": False, "status": 502, "error": "Payment gateway could not create order."}

    checkout_url = str(data.get("link_url") or "")
    log_action(
        action="integration.pg.create_order",
        outcome="ok",
        status=200,
        duration_ms=elapsed_ms(started),
        target_id=order_id,
        request=f"POST {base}/links\nlink_id={order_id} amount={amount_inr}",
        response=f"HTTP 200\ncf_link_id={data.get('cf_link_id','')} status={data.get('link_status','')}",
    )
    return {
        "ok": True,
        "status": 200,
        "provider_order_id": str(data.get("cf_link_id") or order_id),
        "payment_session_id": "",
        "checkout_url": checkout_url,
        "order_status": str(data.get("link_status") or "ACTIVE"),
        "cashfree_mode": _cashfree_mode(cfg),
        "rail": "payment_link",
    }


def fetch_gateway_order_status(*, order_id: str) -> dict[str, Any]:
    """Prefer Payment Link status (link_id=pg order id); fall back to Orders API."""
    started = time.perf_counter()
    cfg = _load_env()
    app_id = cfg.get("CASHFREE_PG_APP_ID", "")
    secret = cfg.get("CASHFREE_PG_SECRET", "")
    if not app_id or not secret:
        return {"ok": False, "status": 503, "error": "Payment gateway is not configured on this server."}

    base = _base_url(cfg)
    status, data, err_snip = _pg_request(
        method="GET",
        url=f"{base}/links/{urllib.parse.quote(order_id, safe='')}",
        app_id=app_id,
        secret=secret,
    )
    if status == 404 or (status >= 400 and not data.get("link_status")):
        # Legacy session/order flow.
        status, data, err_snip = _pg_request(
            method="GET",
            url=f"{base}/orders/{urllib.parse.quote(order_id, safe='')}",
            app_id=app_id,
            secret=secret,
        )
        if status >= 400:
            log_action(
                action="integration.pg.verify_order",
                outcome="error",
                status=status,
                duration_ms=elapsed_ms(started),
                target_id=order_id,
                error_code="server_error",
                error_reason=f"PG HTTP {status}",
                request=f"GET {base}/orders/{order_id}",
                response=f"HTTP {status}\n{err_snip}",
            )
            return {"ok": False, "status": 502, "error": "Could not verify payment status with gateway."}
        order_status = str(data.get("order_status") or "").upper()
        paid = order_status == "PAID"
        failed = order_status in {"EXPIRED", "TERMINATED", "CANCELLED"}
        log_action(
            action="integration.pg.verify_order",
            outcome="ok",
            status=200,
            duration_ms=elapsed_ms(started),
            target_id=order_id,
            request=f"GET {base}/orders/{order_id}",
            response=f"HTTP 200\norder_status={order_status}",
        )
        return {
            "ok": True,
            "status": 200,
            "order_status": order_status,
            "paid": paid,
            "failed": failed,
            "provider_order_id": str(data.get("cf_order_id") or order_id),
            "provider_payment_id": str(data.get("cf_payment_id") or ""),
            "amount": "" if data.get("order_amount") is None else str(data.get("order_amount")),
        }

    if status >= 400:
        log_action(
            action="integration.pg.verify_order",
            outcome="error",
            status=status,
            duration_ms=elapsed_ms(started),
            target_id=order_id,
            error_code="server_error",
            error_reason=f"PG HTTP {status}",
            request=f"GET {base}/links/{order_id}",
            response=f"HTTP {status}\n{err_snip}",
        )
        return {"ok": False, "status": 502, "error": "Could not verify payment status with gateway."}

    link_status = str(data.get("link_status") or "").upper()
    paid = link_status == "PAID"
    failed = link_status in {"EXPIRED", "CANCELLED"}
    log_action(
        action="integration.pg.verify_order",
        outcome="ok",
        status=200,
        duration_ms=elapsed_ms(started),
        target_id=order_id,
        request=f"GET {base}/links/{order_id}",
        response=f"HTTP 200\nlink_status={link_status}",
    )
    return {
        "ok": True,
        "status": 200,
        "order_status": link_status,
        "paid": paid,
        "failed": failed,
        "provider_order_id": str(data.get("cf_link_id") or order_id),
        "provider_payment_id": str(data.get("order_id") or ""),
        "amount": "" if data.get("link_amount") is None else str(data.get("link_amount")),
    }


def verify_webhook_signature(raw_body: bytes, timestamp: str, signature: str) -> bool:
    """HMAC must match, and the timestamp must be fresh.

    Signature alone is not enough: a captured valid body+sig could be replayed.
    Reject timestamps outside CASHFREE_WEBHOOK_MAX_SKEW_S (default 300, clamp 60–900).
    """
    cfg = _load_env()
    secret = cfg.get("CASHFREE_PG_SECRET", "")
    if not secret or not timestamp or not signature:
        return False
    try:
        posted_at = int(str(timestamp).strip())
    except (TypeError, ValueError):
        return False
    skew = max(60, min(900, int(os.environ.get("CASHFREE_WEBHOOK_MAX_SKEW_S", "300") or "300")))
    if abs(int(time.time()) - posted_at) > skew:
        return False
    signed = (timestamp + raw_body.decode("utf-8", errors="replace")).encode("utf-8")
    digest = hmac.new(secret.encode("utf-8"), signed, hashlib.sha256).digest()
    expected = base64.b64encode(digest).decode("ascii")
    return hmac.compare_digest(expected, signature.strip())
