"""PayU Hosted Checkout (web redirect) for PaySwap PG top-up and direct pay.

Formulas and endpoints from payu-docs MCP (Generate Hash / verify_payment).
Credentials: PAYU_MERCHANT_KEY, PAYU_MERCHANT_SALT (Salt-32), PAYU_MERCHANT_SALT_V2
(Salt-256, dual only), PAYU_HASH_MODE, PAYU_ENV, APP_BASE_URL.
Salt never leaves this module. Callers: domain/payswap/payu_checkout.py.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from core.actions import elapsed_ms, log_action


def _ssl_context() -> ssl.SSLContext | None:
    # Same pattern as integrations/pg.py — macOS Python needs certifi.
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()

_PAYMENT_TEST = "https://test.payu.in/_payment"
_PAYMENT_LIVE = "https://secure.payu.in/_payment"
# MCP sample curl sometimes omits .php; skill + other MCP pages use .php for test.
_VERIFY_TEST = "https://test.payu.in/merchant/postservice.php?form=2"
_VERIFY_LIVE = "https://info.payu.in/merchant/postservice.php?form=2"


class PayUConfigError(RuntimeError):
    """Missing or invalid PayU environment configuration."""


def _cfg() -> dict[str, str]:
    key = os.environ.get("PAYU_MERCHANT_KEY", "").strip()
    salt = os.environ.get("PAYU_MERCHANT_SALT", "").strip()
    salt_v2 = os.environ.get("PAYU_MERCHANT_SALT_V2", "").strip()
    mode = (os.environ.get("PAYU_HASH_MODE", "") or "").strip().lower()
    # Salt-256 present → dual JSON {"v1","v2"}; else plain Salt-32 hex.
    if not mode:
        mode = "dual" if salt_v2 else "v1"
    env = (os.environ.get("PAYU_ENV", "test") or "test").strip().lower() or "test"
    base = os.environ.get("APP_BASE_URL", "").strip().rstrip("/")
    return {
        "key": key,
        "salt": salt,
        "salt_v2": salt_v2,
        "hash_mode": mode,
        "env": env,
        "base": base,
    }


def payu_configured() -> bool:
    c = _cfg()
    if not (c["key"] and c["salt"] and c["base"] and c["env"] in {"test", "production"}):
        return False
    if c["hash_mode"] == "dual" and not c["salt_v2"]:
        return False
    return c["hash_mode"] in {"v1", "dual"}


def require_payu_config() -> dict[str, str]:
    c = _cfg()
    missing = []
    if not c["key"]:
        missing.append("PAYU_MERCHANT_KEY")
    if not c["salt"]:
        missing.append("PAYU_MERCHANT_SALT")
    if not c["base"]:
        missing.append("APP_BASE_URL")
    if c["env"] not in {"test", "production"}:
        missing.append("PAYU_ENV")
    if c["hash_mode"] not in {"v1", "dual"}:
        raise PayUConfigError("payment provider misconfigured: PAYU_HASH_MODE")
    if c["hash_mode"] == "dual" and not c["salt_v2"]:
        missing.append("PAYU_MERCHANT_SALT_V2")
    if missing:
        raise PayUConfigError("payment provider misconfigured: " + ", ".join(missing))
    return c


def payment_action_url(env: str | None = None) -> str:
    use = (env or _cfg()["env"]).strip().lower()
    return _PAYMENT_LIVE if use == "production" else _PAYMENT_TEST


def verify_action_url(env: str | None = None) -> str:
    use = (env or _cfg()["env"]).strip().lower()
    return _VERIFY_LIVE if use == "production" else _VERIFY_TEST


def _sha512_hex(value: str) -> str:
    return hashlib.sha512(value.encode("utf-8")).hexdigest().lower()


def _request_pipe(
    *,
    key: str,
    txnid: str,
    amount: str,
    productinfo: str,
    firstname: str,
    email: str,
    salt: str,
    udf1: str = "",
    udf2: str = "",
    udf3: str = "",
    udf4: str = "",
    udf5: str = "",
) -> str:
    # MCP: key|txnid|amount|productinfo|firstname|email|udf1|udf2|udf3|udf4|udf5||||||salt
    return (
        f"{key}|{txnid}|{amount}|{productinfo}|{firstname}|{email}|"
        f"{udf1}|{udf2}|{udf3}|{udf4}|{udf5}||||||{salt}"
    )


def request_hash(
    *,
    key: str,
    txnid: str,
    amount: str,
    productinfo: str,
    firstname: str,
    email: str,
    salt: str,
    udf1: str = "",
    udf2: str = "",
    udf3: str = "",
    udf4: str = "",
    udf5: str = "",
    hash_mode: str = "v1",
    salt_v2: str = "",
) -> str:
    """SHA-512 request hash. Dual accounts need Salt-32 (v1) + Salt-256 (v2) JSON."""
    digest = _sha512_hex(
        _request_pipe(
            key=key,
            txnid=txnid,
            amount=amount,
            productinfo=productinfo,
            firstname=firstname,
            email=email,
            salt=salt,
            udf1=udf1,
            udf2=udf2,
            udf3=udf3,
            udf4=udf4,
            udf5=udf5,
        )
    )
    if hash_mode == "dual":
        if not salt_v2:
            raise PayUConfigError("payment provider misconfigured: PAYU_MERCHANT_SALT_V2")
        digest_v2 = _sha512_hex(
            _request_pipe(
                key=key,
                txnid=txnid,
                amount=amount,
                productinfo=productinfo,
                firstname=firstname,
                email=email,
                salt=salt_v2,
                udf1=udf1,
                udf2=udf2,
                udf3=udf3,
                udf4=udf4,
                udf5=udf5,
            )
        )
        return json.dumps({"v1": digest, "v2": digest_v2}, separators=(",", ":"))
    return digest


def _hash_candidates_match(posted: str, candidates: list[str]) -> bool:
    raw = (posted or "").strip()
    if not raw:
        return False
    digests = list(candidates)
    if raw.startswith("{"):
        try:
            obj = json.loads(raw)
            if isinstance(obj, dict):
                for k in ("v1", "v2"):
                    val = obj.get(k)
                    if isinstance(val, str) and val.strip():
                        digests.append(val.strip().lower())
        except json.JSONDecodeError:
            pass
    posted_l = raw.lower()
    for dig in digests:
        if dig and hmac.compare_digest(posted_l, dig.lower()):
            return True
    return False


def reverse_hash_ok(posted: dict[str, Any], *, key: str, salt: str, salt_v2: str = "") -> bool:
    """Recompute reverse hashes per MCP + Web Checkout Pro variants. Never logs pipes/salt."""
    status = str(posted.get("status") or "").strip()
    txnid = str(posted.get("txnid") or "").strip()
    amount = str(posted.get("amount") or "").strip()
    productinfo = str(posted.get("productinfo") or "").strip()
    firstname = str(posted.get("firstname") or "").strip()
    lastname = str(posted.get("lastname") or "").strip()
    email = str(posted.get("email") or "").strip()
    udf1 = str(posted.get("udf1") or "")
    udf2 = str(posted.get("udf2") or "")
    udf3 = str(posted.get("udf3") or "")
    udf4 = str(posted.get("udf4") or "")
    udf5 = str(posted.get("udf5") or "")
    posted_hash = str(posted.get("hash") or "").strip()
    additional = str(posted.get("additionalCharges") or posted.get("additional_charges") or "").strip()
    split_info = str(posted.get("splitInfo") or posted.get("split_info") or "").strip()
    unmapped = str(posted.get("unmappedstatus") or "").strip()
    net_amount = str(posted.get("net_amount_debit") or "").strip()
    posted_key = str(posted.get("key") or "").strip() or key

    if not posted_hash or not status or not txnid:
        return False

    name_variants = [firstname]
    if lastname:
        name_variants.append(f"{firstname}{lastname}")
        name_variants.append(f"{firstname} {lastname}".strip())
    amount_variants = [amount]
    if net_amount and net_amount not in amount_variants:
        amount_variants.append(net_amount)
    status_variants = [status]
    if unmapped and unmapped not in status_variants:
        status_variants.append(unmapped)
    key_variants = [key]
    if posted_key and posted_key not in key_variants:
        key_variants.append(posted_key)
    salt_variants = [salt]
    if salt_v2 and salt_v2 not in salt_variants:
        salt_variants.append(salt_v2)

    candidates: list[str] = []

    def add(pipe: str) -> None:
        candidates.append(_sha512_hex(pipe))

    for sal in salt_variants:
        for st in status_variants:
            for nm in name_variants:
                for amt in amount_variants:
                    for ky in key_variants:
                        # With UDFs (documented)
                        add(f"{sal}|{st}||||||{udf5}|{udf4}|{udf3}|{udf2}|{udf1}|{email}|{nm}|{productinfo}|{amt}|{txnid}|{ky}")
                        # Without UDFs
                        add(f"{sal}|{st}|||||||||||{email}|{nm}|{productinfo}|{amt}|{txnid}|{ky}")
                        # Seven empty pipes after status (Web Checkout Pro variant)
                        add(f"{sal}|{st}|||||||{udf5}|{udf4}|{udf3}|{udf2}|{udf1}|{email}|{nm}|{productinfo}|{amt}|{txnid}|{ky}")
                        if additional:
                            add(
                                f"{additional}|{sal}|{st}||||||{udf5}|{udf4}|{udf3}|{udf2}|{udf1}|{email}|{nm}|{productinfo}|{amt}|{txnid}|{ky}"
                            )
                        if split_info:
                            add(
                                f"{sal}|{st}|{split_info}||||||{udf5}|{udf4}|{udf3}|{udf2}|{udf1}|{email}|{nm}|{productinfo}|{amt}|{txnid}|{ky}"
                            )

    return _hash_candidates_match(posted_hash, candidates)


def build_checkout_params(
    *,
    txnid: str,
    amount: str,
    productinfo: str,
    firstname: str,
    email: str,
    phone: str,
    udf1: str = "",
    udf2: str = "",
    udf3: str = "",
    udf4: str = "",
    udf5: str = "",
) -> dict[str, Any]:
    """Return { action, params } for browser auto-submit. Salt never included."""
    c = require_payu_config()
    params = {
        "key": c["key"],
        "txnid": txnid,
        "amount": amount,
        "productinfo": productinfo,
        "firstname": firstname,
        "email": email,
        "phone": phone,
        "surl": f"{c['base']}/api/payu/success",
        "furl": f"{c['base']}/api/payu/failure",
        "udf1": udf1,
        "udf2": udf2,
        "udf3": udf3,
        "udf4": udf4,
        "udf5": udf5,
    }
    params["hash"] = request_hash(
        key=c["key"],
        txnid=txnid,
        amount=amount,
        productinfo=productinfo,
        firstname=firstname,
        email=email,
        salt=c["salt"],
        salt_v2=c.get("salt_v2") or "",
        udf1=udf1,
        udf2=udf2,
        udf3=udf3,
        udf4=udf4,
        udf5=udf5,
        hash_mode=c["hash_mode"],
    )
    return {"action": payment_action_url(c["env"]), "params": params}


def verify_payment(txnid: str, *, retries: int = 2) -> dict[str, Any]:
    """POST verify_payment. Hash: sha512(key|command|var1|salt). Never returns raw body to callers."""
    started = time.perf_counter()
    c = require_payu_config()
    command = "verify_payment"
    var1 = txnid
    digest = _sha512_hex(f"{c['key']}|{command}|{var1}|{c['salt']}")
    body = urllib.parse.urlencode(
        {"key": c["key"], "command": command, "var1": var1, "hash": digest}
    ).encode("utf-8")
    url = verify_action_url(c["env"])
    last_err = "verify unavailable"
    attempt = 0
    while attempt <= max(0, retries):
        attempt += 1
        try:
            req = urllib.request.Request(
                url,
                data=body,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=20, context=_ssl_context()) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
                status_code = resp.getcode()
            data = json.loads(raw) if raw.strip().startswith("{") else {}
            details = data.get("transaction_details") if isinstance(data, dict) else None
            entry = None
            if isinstance(details, dict):
                entry = details.get(txnid) or next(iter(details.values()), None)
            pay_status = ""
            if isinstance(entry, dict):
                pay_status = str(entry.get("status") or entry.get("unmappedstatus") or "").strip().lower()
            mapped = "pending"
            if pay_status in {"success", "captured"}:
                mapped = "success"
            elif pay_status in {"failure", "failed", "userCancelled", "usercancelled", "bounced"}:
                mapped = "failure"
            elif pay_status in {"pending", "in progress", "initiated", "auth"}:
                mapped = "pending"
            elif pay_status in {"not found", ""}:
                mapped = "not_found"
            log_action(
                action="integration.payu.verify",
                outcome="ok" if mapped in {"success", "failure", "pending", "not_found"} else "error",
                status=status_code,
                duration_ms=elapsed_ms(started),
                target_id=txnid,
                request=f"POST verify_payment txnid={txnid} attempt={attempt}",
                response=f"HTTP {status_code}\nmapped={mapped}",
            )
            paid_amount = ""
            if isinstance(entry, dict):
                paid_amount = str(
                    entry.get("amt") or entry.get("amount") or entry.get("transaction_amount") or ""
                ).strip()
            return {
                "ok": True,
                "txnid": txnid,
                "status": mapped,
                "amount": paid_amount,
                "provider_payment_id": str(entry.get("mihpayid") or "") if isinstance(entry, dict) else "",
            }
        except PayUConfigError:
            raise
        except urllib.error.HTTPError as err:
            last_err = f"HTTP {err.code}"
            if err.code < 500:
                break
        except (TimeoutError, urllib.error.URLError, OSError, json.JSONDecodeError, ValueError):
            last_err = "network or parse error"
        if attempt <= retries:
            time.sleep(min(2 ** (attempt - 1), 4))

    log_action(
        action="integration.payu.verify",
        outcome="error",
        status=503,
        duration_ms=elapsed_ms(started),
        target_id=txnid,
        error_code="server_error",
        error_reason=last_err,
        request=f"POST verify_payment txnid={txnid}",
        response=f"HTTP 503\n{last_err}",
    )
    return {"ok": False, "txnid": txnid, "status": "error", "error": last_err}
