"""Payment gateway adapter (Cashfree PG v3) for retailer wallet top-up and direct pay.

Callers: domain/payswap/wallet.py and domain/payswap/bbps.py.
Credentials come from environment variables or apps/backend/data/pg.env (gitignored):
  CASHFREE_PG_APP_ID, CASHFREE_PG_SECRET, CASHFREE_PG_ENV (sandbox|production),
  CASHFREE_PG_RETURN_URL, CASHFREE_PG_NOTIFY_URL.
Never returns fake success when credentials are missing.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from core.actions import elapsed_ms, log_action

_DATA_ENV = Path(__file__).resolve().parents[1] / "data" / "pg.env"
_API_VERSION = "2023-08-01"


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
            request=f"POST /pg/orders\norder_id={order_id} amount_paise={amount_paise}",
            response="HTTP 503\nPayment gateway credentials missing.",
        )
        return {
            "ok": False,
            "status": 503,
            "error": "Payment gateway is not configured on this server. Use Wallet or contact admin.",
        }

    base = _base_url(cfg)
    amount_inr = round(amount_paise / 100.0, 2)
    safe_cust = "".join(ch for ch in customer_id if ch.isalnum() or ch in "_-")[:48] or "retailer"
    phone = "".join(ch for ch in (customer_phone or "") if ch.isdigit())[-10:] or "9999999999"
    payload = {
        "order_id": order_id,
        "order_amount": amount_inr,
        "order_currency": "INR",
        "customer_details": {
            "customer_id": safe_cust,
            "customer_email": customer_email,
            "customer_phone": phone,
        },
        "order_meta": {
            "return_url": return_url or cfg.get("CASHFREE_PG_RETURN_URL", "http://127.0.0.1:4500/#wallet"),
        },
        "order_note": note[:120] if note else "PaySwap payment",
    }
    if cfg.get("CASHFREE_PG_NOTIFY_URL"):
        payload["order_meta"]["notify_url"] = cfg["CASHFREE_PG_NOTIFY_URL"]

    req = urllib.request.Request(
        f"{base}/orders",
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "x-api-version": _API_VERSION,
            "x-client-id": app_id,
            "x-client-secret": secret,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            data = json.loads(raw)
    except urllib.error.HTTPError as exc:
        err_body = exc.read().decode("utf-8", errors="replace")[:400]
        log_action(
            action="integration.pg.create_order",
            outcome="error",
            status=exc.code,
            duration_ms=elapsed_ms(started),
            target_id=order_id,
            error_code="server_error",
            error_reason=f"PG HTTP {exc.code}",
            request=f"POST {base}/orders\norder_id={order_id} amount={amount_inr}",
            response=f"HTTP {exc.code}\n{err_body}",
        )
        return {"ok": False, "status": 502, "error": "Payment gateway could not create order."}
    except Exception as exc:
        log_action(
            action="integration.pg.create_order",
            outcome="error",
            status=502,
            duration_ms=elapsed_ms(started),
            target_id=order_id,
            error_code="server_error",
            error_reason=str(exc)[:180],
            request=f"POST {base}/orders\norder_id={order_id} amount={amount_inr}",
            response=f"HTTP 502\n{str(exc)[:180]}",
        )
        return {"ok": False, "status": 502, "error": "Could not reach payment gateway."}

    log_action(
        action="integration.pg.create_order",
        outcome="ok",
        status=200,
        duration_ms=elapsed_ms(started),
        target_id=order_id,
        request=f"POST {base}/orders\norder_id={order_id} amount={amount_inr}",
        response=f"HTTP 200\ncf_order_id={data.get('cf_order_id','')} status={data.get('order_status','')}",
    )
    return {
        "ok": True,
        "status": 200,
        "provider_order_id": str(data.get("cf_order_id") or data.get("order_id") or order_id),
        "payment_session_id": str(data.get("payment_session_id") or ""),
        "checkout_url": str(data.get("payment_link") or ""),
        "order_status": str(data.get("order_status") or "ACTIVE"),
    }


def fetch_gateway_order_status(*, order_id: str) -> dict[str, Any]:
    started = time.perf_counter()
    cfg = _load_env()
    app_id = cfg.get("CASHFREE_PG_APP_ID", "")
    secret = cfg.get("CASHFREE_PG_SECRET", "")
    if not app_id or not secret:
        return {"ok": False, "status": 503, "error": "Payment gateway is not configured on this server."}

    base = _base_url(cfg)
    req = urllib.request.Request(
        f"{base}/orders/{order_id}",
        method="GET",
        headers={
            "x-api-version": _API_VERSION,
            "x-client-id": app_id,
            "x-client-secret": secret,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as exc:
        err_body = exc.read().decode("utf-8", errors="replace")[:300]
        log_action(
            action="integration.pg.verify_order",
            outcome="error",
            status=exc.code,
            duration_ms=elapsed_ms(started),
            target_id=order_id,
            error_code="server_error",
            error_reason=f"PG HTTP {exc.code}",
            request=f"GET {base}/orders/{order_id}",
            response=f"HTTP {exc.code}\n{err_body}",
        )
        return {"ok": False, "status": 502, "error": "Could not verify payment status with gateway."}
    except Exception as exc:
        return {"ok": False, "status": 502, "error": str(exc)[:180]}

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
    }


def verify_webhook_signature(raw_body: bytes, timestamp: str, signature: str) -> bool:
    cfg = _load_env()
    secret = cfg.get("CASHFREE_PG_SECRET", "")
    if not secret or not timestamp or not signature:
        return False
    signed = (timestamp + raw_body.decode("utf-8", errors="replace")).encode("utf-8")
    digest = hmac.new(secret.encode("utf-8"), signed, hashlib.sha256).digest()
    expected = base64.b64encode(digest).decode("ascii")
    return hmac.compare_digest(expected, signature.strip())
