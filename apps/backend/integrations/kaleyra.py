"""Kaleyra OTP SMS for auth.verify.LiveVerify.send_sms.

Credentials stay in apps/backend/.env (loaded by config.envfile), or in
apps/backend/data/kaleyra.env as a fallback. That data directory is
gitignored. Django settings do not carry them. A customer signup uses the
ParkPe sender and DLT template. A retailer signup uses the PaySwap pair.
auth.server._signup_start and _signup_resend pass that role and still
audit signup_delivery_failed in auth/store.py. The OTP check in
auth.server._signup_contact hashes the code locally and does not call Kaleyra.

The action line is core/actions.py action integration.kaleyra.sms.
The code, the API key, the account SID, and the message body stay off that line.
"""

from __future__ import annotations

import json
import os
import re
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from core.actions import elapsed_ms, log_action

_DEFAULT_BASE = "https://api.kaleyra.io"
_DEFAULT_BODY = "Your ParkPe verification code is {otp}. It expires in 10 minutes."
_PLACEHOLDERS = ("{otp}", "{#numeric#}", "{#var#}")
_SID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_SENDER_RE = re.compile(r"^[A-Za-z0-9]{3,14}$")
_CODE_RE = re.compile(r"^[0-9]{4,8}$")
_PATHS = {"messages", "sms"}
_PROFILES = {
    "customer": "KALEYRA_PARKPE",
    "parkpe": "KALEYRA_PARKPE",
    "retailer": "KALEYRA_PAYSWAP",
    "payswap": "KALEYRA_PAYSWAP",
}


class SmsResult:
    """Safe outcome for LiveVerify. No provider body and no secrets."""

    __slots__ = ("ok", "status", "error_code", "error_reason")

    def __init__(self, ok: bool, status: int, error_code: str = "", error_reason: str = ""):
        self.ok = ok
        self.status = status
        self.error_code = error_code
        self.error_reason = error_reason


def load_local_env(path: Path | None = None) -> None:
    """Fill unset KALEYRA_* keys from data/kaleyra.env (fallback).

    Prefer apps/backend/.env via config.envfile.load_backend_env first.
    A value already in the environment wins. Other names in the file are ignored.
    """
    file = path or Path(__file__).resolve().parents[1] / "data" / "kaleyra.env"
    try:
        text = file.read_text()
    except OSError:
        return
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        name = name.strip()
        if not name.startswith("KALEYRA_"):
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        os.environ.setdefault(name, value)


def configured(role: str | None = None) -> bool:
    """True when credentials and DLT profile are present. Never returns secrets."""
    return _config(role) is not None


def send_otp(mobile: str, code: str, transport=None, role: str | None = None) -> SmsResult:
    """POST one OTP. transport replaces urllib for tests. role picks the DLT profile."""
    started = time.perf_counter()
    config = _config(role)
    if config is None:
        return _finish(
            started,
            ok=False,
            status=503,
            error_code="server_error",
            error_reason="Kaleyra is not configured.",
            request="POST /v1/[sid]/messages",
            response="HTTP 503\nKaleyra is not configured.",
        )
    e164 = to_e164(mobile)
    if e164 is None:
        return _finish(started, ok=False, status=400, error_code="validation", error_reason="Check the mobile number.", request="POST /v1/[sid]/messages", response="HTTP 400\nCheck the mobile number.")
    otp = code.strip() if isinstance(code, str) else ""
    if not _CODE_RE.fullmatch(otp):
        return _finish(started, ok=False, status=400, error_code="validation", error_reason="Check the code.", request="POST /v1/[sid]/messages", response="HTTP 400\nCheck the code.")
    body = _fill(config["body"], otp)
    brand = _brand(role)
    payload = {
        "to": e164,
        "sender": config["sender"],
        "type": "OTP",
        "body": body,
    }
    if config["path"] == "messages":
        payload["channel"] = "sms"
    if config["template"]:
        payload["template_id"] = config["template"]
    url = f"{config['base']}/v1/{urllib.parse.quote(config['sid'])}/{config['path']}"
    headers = {"Content-Type": "application/json", "api-key": config["key"]}
    # The logged request names the call. The OTP, API key, SID, and body stay off it.
    exchange = _exchange_request(config, e164, brand)
    post = transport or urllib_post
    try:
        status, provider_body = post(url, json.dumps(payload).encode(), headers, config["timeout"])
    except TimeoutError:
        return _finish(
            started,
            ok=False,
            status=504,
            target=_mask(e164, brand),
            error_code="server_error",
            error_reason="Kaleyra did not respond.",
            request=exchange,
            response="HTTP 504\nKaleyra did not respond.",
        )
    except urllib.error.URLError as err:
        if isinstance(err.reason, ssl.SSLError):
            reason = "Kaleyra TLS verification failed."
        else:
            reason = "Kaleyra is not reachable."
        return _finish(
            started,
            ok=False,
            status=503,
            target=_mask(e164, brand),
            error_code="server_error",
            error_reason=reason,
            request=exchange,
            response=f"HTTP 503\n{reason}",
        )
    except OSError:
        return _finish(
            started,
            ok=False,
            status=503,
            target=_mask(e164, brand),
            error_code="server_error",
            error_reason="Kaleyra is not reachable.",
            request=exchange,
            response="HTTP 503\nKaleyra is not reachable.",
        )
    answered = _exchange_response(status, provider_body)
    if status in {200, 201, 202}:
        return _finish(started, ok=True, status=status, target=_mask(e164, brand), request=exchange, response=answered)
    return _finish(
        started,
        ok=False,
        status=status,
        target=_mask(e164, brand),
        error_code="server_error",
        error_reason="Kaleyra rejected the message.",
        request=exchange,
        response=answered,
    )


def to_e164(value: object) -> str | None:
    """Same digit rules as auth.verify.normalize_mobile, then +91 and ten digits."""
    if not isinstance(value, str):
        return None
    digits = "".join(ch for ch in value if ch.isdigit())
    if digits.startswith("91") and len(digits) == 12:
        digits = digits[2:]
    if len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    if len(digits) != 10 or digits[0] not in "6789":
        return None
    return "+91" + digits


def _ssl_context() -> ssl.SSLContext | None:
    """macOS Python often lacks system roots. certifi supplies a CA bundle."""
    try:
        import certifi
    except ImportError:
        return None
    return ssl.create_default_context(cafile=certifi.where())


def urllib_post(url: str, payload: bytes, headers: dict, timeout: float) -> tuple[int, bytes]:
    """POST and return a short provider body. The log scrubs it before storage."""
    request = urllib.request.Request(url, data=payload, headers=headers, method="POST")
    context = _ssl_context()
    try:
        with urllib.request.urlopen(request, timeout=timeout, context=context) as response:
            return response.status, _read_limited(response)
    except urllib.error.HTTPError as err:
        return err.code, _read_limited(err)
    except TimeoutError:
        raise
    except urllib.error.URLError as err:
        if isinstance(err.reason, TimeoutError):
            raise TimeoutError from err
        raise


def _config(role: str | None) -> dict | None:
    key = os.environ.get("KALEYRA_API_KEY", "").strip()
    sid = os.environ.get("KALEYRA_ACCOUNT_SID", "").strip()
    sender, template, body = _profile(role)
    path = os.environ.get("KALEYRA_SMS_PATH", "messages").strip().strip("/")
    base = _base_url(os.environ.get("KALEYRA_BASE_URL", _DEFAULT_BASE))
    timeout = _timeout(os.environ.get("KALEYRA_TIMEOUT", "10"))
    if not key or not _SID_RE.fullmatch(sid) or not _SENDER_RE.fullmatch(sender):
        return None
    if path not in _PATHS or base is None or not any(slot in body for slot in _PLACEHOLDERS):
        return None
    if template and not _SID_RE.fullmatch(template):
        return None
    return {
        "key": key,
        "sid": sid,
        "sender": sender,
        "template": template,
        "path": path,
        "body": body,
        "base": base,
        "timeout": timeout,
    }


def _profile(role: str | None) -> tuple[str, str, str]:
    """ParkPe for a customer, PaySwap for a retailer. Otherwise the single profile."""
    prefix = _PROFILES.get((role or "").strip().lower())
    if prefix:
        sender = os.environ.get(prefix + "_SENDER_ID", "").strip()
        template = os.environ.get(prefix + "_TEMPLATE_ID", "").strip()
        body = os.environ.get(prefix + "_BODY", "").strip()
        if sender or template or body:
            return sender, template, body
    return (
        os.environ.get("KALEYRA_SENDER_ID", "").strip(),
        os.environ.get("KALEYRA_OTP_TEMPLATE_ID", "").strip(),
        os.environ.get("KALEYRA_OTP_BODY_TEMPLATE", _DEFAULT_BODY),
    )


def _brand(role: str | None) -> str:
    prefix = _PROFILES.get((role or "").strip().lower(), "")
    if prefix.endswith("PARKPE"):
        return "parkpe"
    if prefix.endswith("PAYSWAP"):
        return "payswap"
    return ""


def _fill(body: str, otp: str) -> str:
    filled = body
    for slot in _PLACEHOLDERS:
        filled = filled.replace(slot, otp)
    return filled


def _base_url(value: str) -> str | None:
    parsed = urllib.parse.urlparse(value.strip())
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.query:
        return None
    if parsed.path not in {"", "/"}:
        return None
    host = parsed.hostname
    if parsed.port:
        host = f"{host}:{parsed.port}"
    return f"https://{host}"


def _timeout(value: str) -> float:
    try:
        timeout = float(value)
    except (TypeError, ValueError):
        return 10.0
    if timeout < 1 or timeout > 30:
        return 10.0
    return timeout


def _mask(e164: str, brand: str = "") -> str:
    tail = "******" + e164[-4:]
    return f"{brand}:{tail}" if brand else tail


def _read_limited(stream, limit: int = 1500) -> bytes:
    try:
        return stream.read(limit)
    except OSError:
        return b""


def _exchange_request(config: dict, e164: str, brand: str) -> str:
    channel = "sms" if config["path"] == "messages" else "-"
    template = config["template"] or "-"
    return "\n".join(
        [
            f"POST {config['base']}/v1/[sid]/{config['path']}",
            f"to={_mask(e164, brand)} sender={config['sender']} template={template} type=OTP channel={channel}",
        ]
    )


def _exchange_response(status: int, raw: bytes) -> str:
    text = raw[:1500].decode("utf-8", "replace").strip()
    return f"HTTP {status}\n{text}" if text else f"HTTP {status}"


def _finish(
    started: float,
    *,
    ok: bool,
    status: int,
    target: str = "",
    error_code: str = "",
    error_reason: str = "",
    request: str = "",
    response: str = "",
) -> SmsResult:
    log_action(
        action="integration.kaleyra.sms",
        outcome="ok" if ok else "error",
        status=status,
        duration_ms=elapsed_ms(started),
        target_id=target,
        error_code=error_code,
        error_reason=error_reason,
        request=request,
        response=response,
    )
    return SmsResult(ok, status, error_code, error_reason)
