"""Mobikwik BBPS client and operator catalogue for domain/payswap/bbps.py.

Credentials stay in apps/backend/.env (config.envfile), or apps/backend/data/mobikwik.env
when that file exists. Operators.xlsx and public_key.pem stay under
apps/backend/data/mobikwik/. That directory is gitignored.
"""

from __future__ import annotations

import base64
import fcntl
import json
import os
import re
import secrets
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from core.actions import elapsed_ms, log_action

# No silent prod host fallback: MOBIKWIK_BBPS_BASE_URL must be set when enabled.
_DEFAULT_PATHS = {
    "token": "/recharge/v1/verify/retailer",
    "balance": "/recharge/v3/retailerBalance",
    "validation": "/recharge/v3/retailerValidation",
    "view_bill": "/recharge/v3/retailerViewbill",
    "pay": "/recharge/v3/retailerPayment",
    "status": "/recharge/v3/retailerStatus",
    # GET — one plan catalogue for a known operator and circle. No operator-detect call.
    "plans": "/recharge/v1/rechargePlansAPI",
}
# Mobikwik numeric circle codes for prepaid rechargePlansAPI / pay `cir`.
TELECOM_CIRCLES: tuple[tuple[str, str], ...] = (
    ("1", "Andhra Pradesh"),
    ("2", "Assam"),
    ("3", "Bihar & Jharkhand"),
    ("4", "Chennai"),
    ("5", "Delhi NCR"),
    ("6", "Gujarat"),
    ("7", "Haryana"),
    ("8", "Himachal Pradesh"),
    ("9", "Jammu & Kashmir"),
    ("10", "Karnataka"),
    ("11", "Kerala"),
    ("12", "Kolkata"),
    ("13", "Madhya Pradesh"),
    ("14", "Maharashtra"),
    ("15", "Mumbai"),
    ("16", "North East"),
    ("17", "Orissa"),
    ("18", "Punjab"),
    ("19", "Rajasthan"),
    ("20", "Tamil Nadu"),
    ("21", "UP East"),
    ("22", "UP West"),
    ("23", "West Bengal"),
)
_ICON_BASE = "https://static.mobikwik.com/appdata/operator_icons"
_CIRCLE_NONE = frozenset({"", "0", "00", "000", "na", "n/a", "none", "-", "null", "nil", "as per state"})
_CATEGORY_LABELS = {
    "ELECTRICITY": "Electricity",
    "WATER": "Water",
    "GAS": "Piped gas",
    "LPG_BOOKING": "LPG cylinder",
    "DTH": "DTH",
    "PREPAID": "Mobile prepaid",
    "POSTPAID": "Mobile postpaid",
    "MOBILE_POSTPAID": "Mobile postpaid",
    "FASTAG": "FASTag",
    "BROADBAND": "Broadband",
    "BROADBAND_POSTPAID": "Broadband postpaid",
    "LANDLINE": "Landline",
    "LOAN_REPAYMENT": "Loan repayment",
    "EMI_PAYMENT": "EMI payment",
    "CREDIT_CARD": "Credit card",
    "INSURANCE": "Insurance",
    "HEALTH_INSURANCE": "Health insurance",
    "CABLE_TV": "Cable TV",
    "MUNICIPAL_TAXES": "Municipal taxes",
    "EDUCATION": "Education fees",
    "HOUSING_SOCIETY": "Housing society",
    "HOSPITAL_PATHOLOGY": "Hospital & pathology",
    "SUBSCRIPTION": "Subscription",
    "CLUBS_AND_ASSOCIATIONS": "Clubs & associations",
}
_CATEGORY_MAP = {
    "WATER": "WATER",
    "WATER_SUPPLIER": "WATER",
    "WATERSUPPLIER": "WATER",
    "MUNICIPAL_TAXES": "MUNICIPAL_TAXES",
    "MUNICIPALITY": "MUNICIPAL_TAXES",
    "MUNCIPAL": "MUNICIPAL_TAXES",
    "MUNICIPAL": "MUNICIPAL_TAXES",
    "MUNICIPAL_SERVICES": "MUNICIPAL_TAXES",
    "EMI": "EMI_PAYMENT",
    "EMI_PAYMENT": "EMI_PAYMENT",
    "CREDIT_CARD": "CREDIT_CARD",
    "CREDITCARDPAY": "CREDIT_CARD",
    "CREDIT_CARD_PAY": "CREDIT_CARD",
    "PREPAID": "PREPAID",
    "POSTPAID": "MOBILE_POSTPAID",
    "MOBILE_POSTPAID": "MOBILE_POSTPAID",
    "PNG": "GAS",
    "PIPELINE_GAS": "GAS",
    "GAS": "GAS",
    "HOSPITAL_PATHOLOGY": "HOSPITAL_PATHOLOGY",
    "HOSPITALS_AND_PATHOLOGY": "HOSPITAL_PATHOLOGY",
    "HOSPITAL_AND_PATHOLOGY": "HOSPITAL_PATHOLOGY",
    "PATHOLOGY": "HOSPITAL_PATHOLOGY",
    "CYLINDER": "LPG_BOOKING",
    "LPG": "LPG_BOOKING",
    "LPG_GAS": "LPG_BOOKING",
    "LPG_CYLINDER": "LPG_BOOKING",
    "GAS_BOOKING": "LPG_BOOKING",
    "LPG_BOOKING": "LPG_BOOKING",
    "HEALTH_INSURANCE": "HEALTH_INSURANCE",
    "HEALTH": "HEALTH_INSURANCE",
    "HOUSING_SOCIETY": "HOUSING_SOCIETY",
    "HOUSING_SOCIETY_MAINTENANCE": "HOUSING_SOCIETY",
    "CLUBS_AND_ASSOCIATIONS": "CLUBS_AND_ASSOCIATIONS",
    "CLUBS_ASSOCIATIONS": "CLUBS_AND_ASSOCIATIONS",
    "EDUCATION_FEES": "EDUCATION",
    "FEE_PAYMENT": "EDUCATION",
    "EDUCATION": "EDUCATION",
    "FASTAG": "FASTAG",
    "BROADBAND": "BROADBAND",
    "BROADBAND_POSTPAID": "BROADBAND_POSTPAID",
    "LANDLINE_POSTPAID": "LANDLINE",
    "LANDLINE": "LANDLINE",
    "LOAN_REPAYMENT": "LOAN_REPAYMENT",
    "PREPAID_METER": "ELECTRICITY",
    "ELECTRICITY": "ELECTRICITY",
    "DTH": "DTH",
    "CABLE_TV": "CABLE_TV",
    "CABLE": "CABLE_TV",
    "INSURANCE": "INSURANCE",
    "SUBSCRIPTION": "SUBSCRIPTION",
}
_SUCCESS_STATUSES = frozenset(
    {
        "SUCCESS",
        "COMPLETED",
        "DONE",
        "SUCCESSFUL",
        "RECHARGESUCCESS",
        "RECHARGE_SUCCESS",
        "BILLPAYSUCCESS",
        "BILL_PAY_SUCCESS",
        "BILLPAYMENTSUCCESS",
        "PAYMENTSUCCESS",
    }
)
_FAILED_STATUSES = frozenset(
    {
        "FAILED",
        "FAILURE",
        "REJECTED",
        "CANCELLED",
        "REVERSED",
        "ERROR",
        "RECHARGEFAILED",
        "RECHARGE_FAILED",
        "RECHARGEFAILURE",
        "BILLPAYFAILED",
        "BILL_PAY_FAILED",
        "BILLPAYMENTFAILED",
        "PAYMENTFAILED",
    }
)

_TOKEN_LOCK = threading.Lock()
_MEM_TOKEN: dict[str, Any] = {}
_MINT_HOLD_UNTIL = 0.0
_CAT_LOCK = threading.Lock()
_CAT_CACHE: tuple[float, list[dict[str, Any]]] | None = None


def _backend_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _data_dir() -> Path:
    custom = os.environ.get("AUTH_DATA_DIR", "").strip()
    return Path(custom) if custom else _backend_root() / "data"


def _truthy(value: str | None, default: bool = False) -> bool:
    if value is None or not value.strip():
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def load_local_env(path: Path | None = None) -> None:
    """Fill unset MOBIKWIK_BBPS_* keys from data/mobikwik.env (fallback).

    Prefer apps/backend/.env via config.envfile.load_backend_env first.
    """
    file = path or (_data_dir() / "mobikwik.env")
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
        if not name.startswith("MOBIKWIK_BBPS_"):
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        os.environ.setdefault(name, value)


def _public_key_pem() -> str:
    inline = os.environ.get("MOBIKWIK_BBPS_PUBLIC_KEY", "").strip()
    if inline:
        return inline
    raw_path = os.environ.get("MOBIKWIK_BBPS_PUBLIC_KEY_PATH", "").strip()
    candidates = []
    if raw_path:
        p = Path(raw_path).expanduser()
        candidates.append(p if p.is_absolute() else _backend_root() / p)
    candidates.append(_data_dir() / "mobikwik" / "public_key.pem")
    for path in candidates:
        try:
            text = path.read_text(encoding="utf-8").strip()
            if text:
                return text
        except OSError:
            continue
    return ""


def _config() -> dict[str, Any] | None:
    if not _truthy(os.environ.get("MOBIKWIK_BBPS_ENABLED")):
        return None
    base = os.environ.get("MOBIKWIK_BBPS_BASE_URL", "").strip().rstrip("/")
    parsed = urllib.parse.urlparse(base)
    if not base or parsed.scheme != "https" or not parsed.netloc:
        return None
    client_id = os.environ.get("MOBIKWIK_BBPS_CLIENT_ID", "").strip()
    client_secret = os.environ.get("MOBIKWIK_BBPS_CLIENT_SECRET", "").strip()
    merchant_id = os.environ.get("MOBIKWIK_BBPS_MERCHANT_ID", "").strip()
    api_key = os.environ.get("MOBIKWIK_BBPS_API_KEY", "").strip()
    secret_key = os.environ.get("MOBIKWIK_BBPS_SECRET_KEY", "").strip()
    if not ((client_id and client_secret) or (merchant_id and api_key and secret_key)):
        return None

    env_name = os.environ.get("MOBIKWIK_BBPS_ENVIRONMENT", "UAT").strip().upper()
    raw_enc = _truthy(os.environ.get("MOBIKWIK_BBPS_USE_ENCRYPTION"), False)
    plain_uat = _truthy(os.environ.get("MOBIKWIK_BBPS_PLAIN_JSON_UAT"), False)
    use_encryption = False if (env_name == "UAT" and plain_uat) else raw_enc

    token_use_enc = _truthy(os.environ.get("MOBIKWIK_BBPS_TOKEN_USE_ENCRYPTION"), False)
    token_plain = _truthy(os.environ.get("MOBIKWIK_BBPS_TOKEN_PLAIN_JSON"), False)
    token_encrypted = token_use_enc and not token_plain

    pem = _public_key_pem()
    if (use_encryption or token_encrypted) and not pem:
        return None

    try:
        timeout = max(5.0, min(float(os.environ.get("MOBIKWIK_BBPS_REQUEST_TIMEOUT", "60")), 90.0))
    except ValueError:
        timeout = 60.0

    kv = os.environ.get("MOBIKWIK_BBPS_KEY_VERSION", "1.0").strip()
    return {
        "base": base,
        "client_id": client_id,
        "client_secret": client_secret,
        "merchant_id": merchant_id,
        "member_id": os.environ.get("MOBIKWIK_BBPS_MEMBER_ID", "").strip(),
        "agent_id": os.environ.get("MOBIKWIK_BBPS_AGENT_ID", "").strip(),
        "api_key": api_key,
        "secret_key": secret_key,
        "use_encryption": use_encryption,
        "token_encrypted": token_encrypted,
        "pem": pem,
        "key_version": kv if kv in {"1.0", "1"} else "1.0",
        "timeout": timeout,
        "environment": env_name,
    }


def configured() -> bool:
    """True when Mobikwik BBPS settings and keys are present. Never exposes secrets."""
    return _config() is not None


def _ssl_context() -> ssl.SSLContext | None:
    try:
        import certifi
    except ImportError:
        return None
    return ssl.create_default_context(cafile=certifi.where())


def _http_post(url: str, body: dict[str, Any], headers: dict[str, str], timeout: float) -> tuple[int, bytes]:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise OSError("BBPS URL must be https")
    req = urllib.request.Request(
        url,
        data=json.dumps(body, separators=(",", ":")).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    context = _ssl_context()
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=context) as resp:
            return resp.status, resp.read(32768)
    except urllib.error.HTTPError as err:
        return err.code, err.read(32768)
    except urllib.error.URLError as err:
        if isinstance(err.reason, TimeoutError):
            raise TimeoutError from err
        raise


def _http_get(url: str, headers: dict[str, str], timeout: float) -> tuple[int, bytes]:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise OSError("BBPS URL must be https")
    req = urllib.request.Request(url, headers=headers, method="GET")
    context = _ssl_context()
    # Plan catalogues can be large; keep a hard cap so a bad payload cannot fill memory.
    max_bytes = 524288
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=context) as resp:
            return resp.status, resp.read(max_bytes)
    except urllib.error.HTTPError as err:
        return err.code, err.read(max_bytes)
    except urllib.error.URLError as err:
        if isinstance(err.reason, TimeoutError):
            raise TimeoutError from err
        raise


def _encrypt_payload(payload: dict[str, Any], cfg: dict[str, Any]) -> dict[str, Any]:
    """AES-256-GCM + RSA-2048 PKCS1v15 envelope expected by Mobikwik RT-Recharge."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import padding as asym_padding
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    session_key = os.urandom(32)
    nonce = os.urandom(16)
    plaintext = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    encrypted = AESGCM(session_key).encrypt(nonce, plaintext, None)
    public_key = serialization.load_pem_public_key(cfg["pem"].encode("utf-8"))
    enc_key = public_key.encrypt(session_key, asym_padding.PKCS1v15())
    return {
        "encryptedSessionKey": base64.b64encode(enc_key).decode("ascii"),
        "encryptedPayload": base64.b64encode(encrypted).decode("ascii"),
        "keyVersion": cfg["key_version"],
        "iv": base64.b64encode(nonce).decode("ascii"),
    }


def _token_cache_path() -> Path:
    return _data_dir() / "mobikwik" / "token_cache.json"


def _token_lock_path() -> Path:
    return _data_dir() / "mobikwik" / "token_cache.lock"


def _today_ist() -> str:
    return datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%Y-%m-%d")


def _max_mints_per_day() -> int:
    raw = os.environ.get("MOBIKWIK_BBPS_TOKEN_MAX_MINTS_PER_DAY", "95").strip()
    try:
        val = int(raw)
    except ValueError:
        val = 95
    return max(1, min(val, 99))


def _renew_buffer_seconds() -> float:
    raw = os.environ.get("MOBIKWIK_BBPS_TOKEN_REFRESH_BUFFER_SECONDS", "3600").strip()
    try:
        val = float(raw)
    except ValueError:
        val = 3600.0
    return max(3600.0, val)


def _compute_renew_at(now: float, expires_at: float) -> float:
    ttl = expires_at - now
    if ttl <= 7200.0:
        return max(now + 60.0, expires_at - 300.0)
    buffer_sec = _renew_buffer_seconds()
    return min(now + 82800.0, expires_at - buffer_sec)


def _load_token_state() -> dict[str, Any]:
    path = _token_cache_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except (OSError, json.JSONDecodeError):
        pass
    return {}


def _save_token_state(entry: dict[str, Any]) -> None:
    path = _token_cache_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(entry), encoding="utf-8")
        tmp.chmod(0o600)
        os.replace(tmp, path)
    except OSError:
        pass


def _read_cached_token() -> str | None:
    now = time.time()
    tok = _MEM_TOKEN.get("token")
    renew_at = float(_MEM_TOKEN.get("renew_at") or 0)
    exp = float(_MEM_TOKEN.get("expires_at") or 0)
    effective_limit = renew_at or (exp - 3600.0 if exp else 0)
    if tok and now < effective_limit:
        return str(tok)
    data = _load_token_state()
    exp = float(data.get("expires_at") or 0)
    renew_at = float(data.get("renew_at") or (exp - 3600.0 if exp else 0))
    if data.get("token") and now < renew_at:
        _MEM_TOKEN.clear()
        _MEM_TOKEN.update(data)
        return str(data["token"])
    return None


def _write_cached_token(token: str, expires_at: float) -> None:
    now = time.time()
    today = _today_ist()
    prev = _load_token_state()
    prev_count = int(prev.get("mint_count") or 0) if prev.get("mint_date") == today else 0
    entry = {
        "token": token,
        "minted_at": now,
        "expires_at": expires_at,
        "renew_at": _compute_renew_at(now, expires_at),
        "mint_date": today,
        "mint_count": prev_count + 1,
        "mint_hold_until": float(prev.get("mint_hold_until") or 0),
    }
    _MEM_TOKEN.clear()
    _MEM_TOKEN.update(entry)
    _save_token_state(entry)


def _clear_cached_token() -> None:
    prev = _load_token_state()
    _MEM_TOKEN.clear()
    if prev.get("mint_date") == _today_ist() and prev.get("mint_count"):
        _save_token_state({
            "mint_date": prev["mint_date"],
            "mint_count": int(prev["mint_count"]),
            "mint_hold_until": float(prev.get("mint_hold_until") or 0),
        })
        return
    try:
        _token_cache_path().unlink()
    except OSError:
        pass


def _daily_mint_count() -> int:
    state = _load_token_state()
    if state.get("mint_date") == _today_ist():
        return int(state.get("mint_count") or 0)
    return 0


def _parse_expiry(data: dict[str, Any]) -> float:
    now = time.time()
    inner = data.get("data") if isinstance(data.get("data"), dict) else {}
    for container in (inner, data):
        for key in ("expiryTime", "expiresAt", "expireTime", "tokenExpiry", "expiry_time"):
            val = container.get(key)
            if isinstance(val, (int, float)):
                ts = float(val)
                if ts > 1e12:
                    ts /= 1000.0
                if ts > now:
                    return ts
            if isinstance(val, str) and len(val.strip()) >= 19:
                core = val.strip()[:19].replace("T", " ")
                try:
                    dt = datetime.strptime(core, "%Y-%m-%d %H:%M:%S").replace(tzinfo=ZoneInfo("Asia/Kolkata"))
                    if dt.timestamp() > now:
                        return dt.timestamp()
                except ValueError:
                    pass
    return now + 82800.0


def _extract_token(data: dict[str, Any]) -> str:
    inner = data.get("data") if isinstance(data.get("data"), dict) else {}
    for src in (inner, data):
        for key in ("token", "accessToken", "access_token"):
            val = src.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
    return ""


def _vendor_msg(data: Any, fallback: str) -> str:
    if not isinstance(data, dict):
        return fallback
    for key in ("message", "error", "msg", "errorMessage"):
        val = data.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()[:200]
        if isinstance(val, dict):
            text = val.get("text") or val.get("message") or val.get("description") or ""
            if str(text).strip():
                return str(text).strip()[:200]
    return fallback


def _is_token_expired(status: int, data: Any) -> bool:
    if status == 401:
        return True
    if not isinstance(data, dict):
        return False
    msg = data.get("message")
    if isinstance(msg, dict):
        code = str(msg.get("code") or "").strip().lower()
        text = str(msg.get("text") or msg.get("message") or "").lower()
        if code in {"401", "token_expired", "unauthorized"}:
            return True
        if "token" in text and ("expir" in text or "invalid" in text):
            return True
    if isinstance(msg, str) and ("expir" in msg.lower() or "invalid token" in msg.lower()):
        return True
    return False


def _mint_hold_remaining() -> float:
    disk_until = float(_load_token_state().get("mint_hold_until") or 0)
    return max(0.0, _MINT_HOLD_UNTIL - time.time(), disk_until - time.time())


def _hold_mint(seconds: float) -> None:
    """One rejected mint pauses the next one, including in another process."""
    global _MINT_HOLD_UNTIL
    until = time.time() + max(30.0, seconds)
    _MINT_HOLD_UNTIL = max(_MINT_HOLD_UNTIL, until)
    state = _load_token_state()
    state["mint_hold_until"] = max(float(state.get("mint_hold_until") or 0), until)
    _save_token_state(state)


def _ensure_token(cfg: dict[str, Any], *, force: bool = False, transport=None) -> tuple[str | None, str]:
    with _TOKEN_LOCK:
        lock_path = _token_lock_path()
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(lock_path.parent, 0o700)
        except OSError:
            pass
        with lock_path.open("a+") as lock_file:
            try:
                os.chmod(lock_path, 0o600)
            except OSError:
                pass
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                if not force:
                    cached = _read_cached_token()
                    if cached:
                        return cached, ""
                wait = _mint_hold_remaining()
                if wait > 0:
                    return None, "Mobikwik token mint is paused after a rejected request. Wait before trying again."
                if force:
                    _clear_cached_token()

                if _daily_mint_count() >= _max_mints_per_day():
                    return None, "Daily Mobikwik token limit reached; refusing to mint another token today."

                return _mint_new_token(cfg, transport=transport)
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _exchange_request(url: str, payload: dict[str, Any], *, method: str = "POST") -> str:
    return f"{method} {url}\n{json.dumps(payload, separators=(',', ':'), ensure_ascii=False)}"


def _exchange_response(status: int, raw: bytes) -> str:
    text = raw[:1200].decode("utf-8", "replace").strip() if raw else ""
    return f"HTTP {status}\n{text}" if text else f"HTTP {status}"


def _mint_new_token(cfg: dict[str, Any], *, transport=None) -> tuple[str | None, str]:
        started = time.perf_counter()
        url = cfg["base"] + _DEFAULT_PATHS["token"]
        req_log = _exchange_request(url, {"clientId": cfg["client_id"]})
        payload = {"clientId": cfg["client_id"], "clientSecret": cfg["client_secret"]}
        body = _encrypt_payload(payload, cfg) if cfg["token_encrypted"] else payload
        post = transport or _http_post
        try:
            status, raw = post(
                url,
                body,
                {"Content-Type": "application/json", "Accept": "application/json"},
                min(cfg["timeout"], 30.0),
            )
        except TimeoutError:
            log_action(
                action="integration.bbps.token",
                outcome="error",
                status=504,
                duration_ms=elapsed_ms(started),
                error_code="server_error",
                error_reason="Mobikwik token request timed out.",
                request=req_log,
                response="HTTP 504\nMobikwik token request timed out.",
            )
            return None, "Mobikwik token request timed out."
        except (urllib.error.URLError, OSError):
            log_action(
                action="integration.bbps.token",
                outcome="error",
                status=503,
                duration_ms=elapsed_ms(started),
                error_code="server_error",
                error_reason="Mobikwik is not reachable.",
                request=req_log,
                response="HTTP 503\nMobikwik is not reachable.",
            )
            return None, "Mobikwik is not reachable."

        try:
            data = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            data = {}
        token = _extract_token(data) if status < 400 and isinstance(data, dict) else ""
        resp_log = _exchange_response(status, raw)
        if not token:
            reason = _vendor_msg(data, "Mobikwik rejected the token request.")
            if status == 429:
                reason = "Mobikwik rate limit. Wait before asking for another token."
                _hold_mint(60.0)
            else:
                _hold_mint(120.0)
            log_action(
                action="integration.bbps.token",
                outcome="error",
                status=status if status >= 400 else 502,
                duration_ms=elapsed_ms(started),
                error_code="server_error",
                error_reason=reason,
                request=req_log,
                response=resp_log,
            )
            return None, reason

        _write_cached_token(token, _parse_expiry(data))
        log_action(
            action="integration.bbps.token",
            outcome="ok",
            status=status,
            duration_ms=elapsed_ms(started),
            request=req_log,
            response=resp_log,
        )
        return token, ""


def _op_value(operator_id: str | int) -> str:
    raw = str(operator_id).strip()
    if raw.endswith(".0") and raw[:-2].isdigit():
        return raw[:-2]
    return raw


def _request(
    action: str,
    path_key: str,
    payload: dict[str, Any],
    *,
    target_id: str = "",
    transport=None,
    _retry: int = 0,
) -> dict[str, Any]:
    started = time.perf_counter()
    cfg = _config()
    if cfg is None:
        log_action(
            action=action,
            outcome="error",
            status=503,
            duration_ms=elapsed_ms(started),
            target_id=target_id,
            error_code="server_error",
            error_reason="Mobikwik BBPS is not configured.",
        )
        return {"ok": False, "status": 503, "error": "Mobikwik BBPS is not configured.", "data": {}}

    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if cfg["client_id"] and cfg["client_secret"]:
        token, err = _ensure_token(cfg, force=False, transport=transport)
        if not token:
            return {"ok": False, "status": 503, "error": err or "Could not get Mobikwik token.", "data": {}}
        headers["Authorization"] = token
    else:
        headers["X-API-Key"] = cfg["api_key"]
        headers["X-Merchant-Id"] = cfg["merchant_id"]

    body = _encrypt_payload(payload, cfg) if cfg["use_encryption"] else payload
    url = cfg["base"] + _DEFAULT_PATHS[path_key]
    req_log = _exchange_request(url, payload)
    post = transport or _http_post
    try:
        status, raw = post(url, body, headers, cfg["timeout"])
    except TimeoutError:
        log_action(
            action=action,
            outcome="error",
            status=504,
            duration_ms=elapsed_ms(started),
            target_id=target_id,
            error_code="server_error",
            error_reason="Mobikwik BBPS timed out.",
            request=req_log,
            response="HTTP 504\nMobikwik BBPS timed out.",
        )
        return {"ok": False, "status": 504, "error": "Mobikwik BBPS timed out.", "data": {}}
    except (urllib.error.URLError, OSError):
        log_action(
            action=action,
            outcome="error",
            status=503,
            duration_ms=elapsed_ms(started),
            target_id=target_id,
            error_code="server_error",
            error_reason="Mobikwik BBPS is not reachable.",
            request=req_log,
            response="HTTP 503\nMobikwik BBPS is not reachable.",
        )
        return {"ok": False, "status": 503, "error": "Mobikwik BBPS is not reachable.", "data": {}}

    try:
        data = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        data = {}

    if _retry < 1 and cfg["client_id"] and cfg["client_secret"] and _is_token_expired(status, data):
        _ensure_token(cfg, force=True, transport=transport)
        return _request(action, path_key, payload, target_id=target_id, transport=transport, _retry=_retry + 1)

    body_ok = True if not isinstance(data, dict) else (data.get("success") is not False)
    ok = status < 400 and body_ok
    reason = "" if ok else _vendor_msg(data, f"Mobikwik BBPS returned HTTP {status}.")
    log_action(
        action=action,
        outcome="ok" if ok else "error",
        status=status if ok else (status if status >= 400 else 502),
        duration_ms=elapsed_ms(started),
        target_id=target_id,
        error_code="" if ok else "server_error",
        error_reason=reason,
        request=req_log,
        response=_exchange_response(status, raw),
    )
    return {"ok": ok, "status": status, "error": reason, "data": data if isinstance(data, dict) else {}}


def _request_get(
    action: str,
    path_key: str,
    params: dict[str, Any],
    *,
    target_id: str = "",
    transport=None,
    path_override: str = "",
    _retry: int = 0,
) -> dict[str, Any]:
    """GET helper for rechargePlansAPI and operator lookup (query params, no encrypted body)."""
    started = time.perf_counter()
    cfg = _config()
    if cfg is None:
        log_action(
            action=action,
            outcome="error",
            status=503,
            duration_ms=elapsed_ms(started),
            target_id=target_id,
            error_code="server_error",
            error_reason="Mobikwik BBPS is not configured.",
        )
        return {"ok": False, "status": 503, "error": "Mobikwik BBPS is not configured.", "data": {}}

    headers = {"Accept": "application/json"}
    if cfg["client_id"] and cfg["client_secret"]:
        # Token mint is always POST; do not reuse the GET transport for it.
        token, err = _ensure_token(cfg, force=False)
        if not token:
            return {"ok": False, "status": 503, "error": err or "Could not get Mobikwik token.", "data": {}}
        headers["Authorization"] = token
    else:
        headers["X-API-Key"] = cfg["api_key"]
        headers["X-Merchant-Id"] = cfg["merchant_id"]

    clean = {str(k): str(v) for k, v in params.items() if v not in (None, "")}
    url = path_override or (cfg["base"] + _DEFAULT_PATHS[path_key])
    if clean:
        url = f"{url}?{urllib.parse.urlencode(clean)}"
    req_log = _exchange_request(url.split("?", 1)[0], clean, method="GET")
    get = transport or _http_get
    try:
        status, raw = get(url, headers, cfg["timeout"])
    except TimeoutError:
        log_action(
            action=action,
            outcome="error",
            status=504,
            duration_ms=elapsed_ms(started),
            target_id=target_id,
            error_code="server_error",
            error_reason="Mobikwik BBPS timed out.",
            request=req_log,
            response="HTTP 504\nMobikwik BBPS timed out.",
        )
        return {"ok": False, "status": 504, "error": "Mobikwik BBPS timed out.", "data": {}}
    except (urllib.error.URLError, OSError):
        log_action(
            action=action,
            outcome="error",
            status=503,
            duration_ms=elapsed_ms(started),
            target_id=target_id,
            error_code="server_error",
            error_reason="Mobikwik BBPS is not reachable.",
            request=req_log,
            response="HTTP 503\nMobikwik BBPS is not reachable.",
        )
        return {"ok": False, "status": 503, "error": "Mobikwik BBPS is not reachable.", "data": {}}

    try:
        data = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        data = {}

    if _retry < 1 and cfg["client_id"] and cfg["client_secret"] and _is_token_expired(status, data):
        _ensure_token(cfg, force=True)
        return _request_get(
            action,
            path_key,
            params,
            target_id=target_id,
            transport=transport,
            path_override=path_override,
            _retry=_retry + 1,
        )

    body_ok = True if not isinstance(data, dict) else (data.get("success") is not False)
    ok = status < 400 and body_ok
    reason = "" if ok else _vendor_msg(data, f"Mobikwik BBPS returned HTTP {status}.")
    log_action(
        action=action,
        outcome="ok" if ok else "error",
        status=status if ok else (status if status >= 400 else 502),
        duration_ms=elapsed_ms(started),
        target_id=target_id,
        error_code="" if ok else "server_error",
        error_reason=reason,
        request=req_log,
        response=_exchange_response(status, raw),
    )
    return {"ok": ok, "status": status, "error": reason, "data": data if isinstance(data, dict) else {}}


def balance_check(*, transport=None) -> dict[str, Any]:
    cfg = _config() or {}
    member = cfg.get("member_id", "")
    payload = {"memberId": member} if member else {"memberId": ""}
    res = _request("integration.bbps.balance", "balance", payload, transport=transport)
    if not res["ok"] and member:
        msg = res["data"].get("message") if isinstance(res.get("data"), dict) else {}
        if isinstance(msg, dict) and str(msg.get("code") or "") == "1308":
            res = _request("integration.bbps.balance", "balance", {"memberId": ""}, transport=transport)
    return res


def validate_customer(
    *,
    customer_id: str,
    operator_id: str | int = "",
    circle: str = "",
    transport=None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"cn": str(customer_id or "").strip()}
    if operator_id not in ("", None):
        payload["op"] = _op_value(operator_id)
    if circle and str(circle).strip():
        payload["cir"] = str(circle).strip()
    return _request("integration.bbps.validation", "validation", payload, target_id=payload.get("op", ""), transport=transport)


def list_telecom_circles() -> list[dict[str, str]]:
    return [{"code": code, "label": label} for code, label in TELECOM_CIRCLES]


def _normalize_indian_mobile(raw: str) -> str:
    digits = "".join(ch for ch in str(raw or "") if ch.isdigit())
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    if len(digits) > 10:
        digits = digits[-10:]
    return digits


def _first_non_empty(*values: Any) -> str:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _unwrap_plans_payload(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        return {}
    inner = data.get("data")
    if isinstance(inner, dict) and any(
        key in inner for key in ("plans", "rechargePlans", "planList", "operatorPlans", "op", "cir")
    ):
        return inner
    return data


def _plan_amount(plan: dict[str, Any]) -> str:
    for key in ("amount", "rechargeAmount", "price", "mrp", "retailPrice", "planAmount", "rs", "RS"):
        val = plan.get(key)
        if val in (None, ""):
            continue
        try:
            amount = Decimal(str(val).strip())
        except Exception:
            continue
        if amount > 0:
            return f"{amount:.2f}"
    return ""


def _flatten_category_map(mapping: dict[str, Any]) -> list[Any]:
    """Mobikwik often returns plans as {TOPUP: [...], "3G/4G": [...]}."""
    out: list[Any] = []
    for cat_key, sub in mapping.items():
        if not isinstance(sub, list):
            continue
        for item in sub:
            if isinstance(item, dict):
                row = dict(item)
                row.setdefault("category", str(cat_key))
                out.append(row)
            else:
                out.append(item)
    return out


def _collect_plan_lists(data: Any) -> list[Any]:
    if isinstance(data, list):
        return data
    if not isinstance(data, dict):
        return []
    root = _unwrap_plans_payload(data)
    for key in ("rechargePlans", "plans", "planList", "data", "operatorPlans", "popularPlans"):
        val = root.get(key)
        if isinstance(val, list):
            return val
        if isinstance(val, dict):
            flat = _flatten_category_map(val)
            if flat:
                return flat
    # Some payloads are the category map at the root.
    flat_root = _flatten_category_map(root)
    return flat_root if flat_root else []


def parse_recharge_plans(data: Any, *, limit: int = 80) -> list[dict[str, Any]]:
    """Flatten Mobikwik rechargePlansAPI payload into UI-friendly plan rows."""
    seen: set[tuple[str, str]] = set()
    out: list[dict[str, Any]] = []
    for index, item in enumerate(_collect_plan_lists(data)):
        if not isinstance(item, dict):
            continue
        amount = _plan_amount(item)
        if not amount:
            continue
        plan_id = _first_non_empty(item.get("planId"), item.get("plan_id"), item.get("id"), item.get("sku")) or f"plan_{index}_{amount}"
        validity = _first_non_empty(item.get("validity"), item.get("validityDays"), item.get("days"))
        description = _first_non_empty(
            item.get("description"),
            item.get("desc"),
            item.get("planDescription"),
            item.get("planName"),
            item.get("name"),
        )
        category = _first_non_empty(item.get("category"), item.get("planType"), item.get("type"))
        key = (plan_id, amount)
        if key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "id": plan_id,
                "amount": amount,
                "validity": validity,
                "description": description,
                "category": category,
                "label": " · ".join(part for part in (f"₹{amount}", validity or category, description[:72] if description else "") if part),
            }
        )
        if len(out) >= limit:
            break
    out.sort(key=lambda row: (Decimal(row["amount"]), row.get("category") or "", row.get("label") or ""))
    return out


def parse_operator_lookup(data: Any) -> dict[str, str]:
    """Pull operator and circle ids out of Mobikwik getconnectiondetails."""
    if not isinstance(data, dict):
        return {"operator_id": "", "circle": ""}
    root = data.get("data") if isinstance(data.get("data"), dict) else data
    if isinstance(root, dict) and isinstance(root.get("data"), dict):
        root = root["data"]
    if not isinstance(root, dict):
        return {"operator_id": "", "circle": ""}
    operator_id = _op_value(
        _first_non_empty(root.get("operatorId"), root.get("op"), root.get("operator"))
    )
    circle = _op_value(_first_non_empty(root.get("circleId"), root.get("cir"), root.get("circle")))
    if circle in _CIRCLE_NONE:
        circle = ""
    return {"operator_id": operator_id, "circle": circle}


def list_recharge_plans(
    *,
    operator_id: str | int,
    circle: str,
    customer_id: str = "",
    category: str = "prepaid",
    transport=None,
) -> dict[str, Any]:
    """GET /recharge/v1/rechargePlansAPI for prepaid (and similar) plan packs."""
    cn = _normalize_indian_mobile(customer_id)
    cir = str(circle or "").strip()
    op = _op_value(operator_id)
    if not op:
        return {"ok": False, "status": 400, "error": "Operator is required.", "plans": []}
    if not cir:
        return {"ok": False, "status": 400, "error": "Telecom circle is required.", "plans": []}
    if cn and len(cn) != 10:
        return {"ok": False, "status": 400, "error": "Enter a valid 10-digit mobile number.", "plans": []}

    cfg = _config() or {}
    params: dict[str, Any] = {"op": op, "cir": cir}
    if cn:
        params["cn"] = cn
    if category:
        params["category"] = str(category).strip()
    if cfg.get("agent_id"):
        params["agentId"] = cfg["agent_id"]
    if cfg.get("client_id"):
        params["clientId"] = cfg["client_id"]

    res = _request_get(
        "integration.bbps.plans",
        "plans",
        params,
        target_id=op,
        transport=transport,
    )
    if not res["ok"]:
        return {"ok": False, "status": res["status"], "error": res["error"], "plans": []}
    plans = parse_recharge_plans(res.get("data") or {})
    return {"ok": True, "status": 200, "error": "", "plans": plans}


def _is_fastag_row(op_row: dict[str, Any] | None) -> bool:
    if not op_row:
        return False
    return "FASTAG" in str(op_row.get("category") or "").upper() or "FASTAG" in str(op_row.get("name") or "").upper()


def _fastag_upi_account(customer_id: str) -> str:
    cleaned = "".join(ch for ch in str(customer_id or "").strip().upper() if ch.isalnum())
    if not cleaned:
        return "generic_upi"
    return f"{cleaned[:78]}@UPI"


def _map_ad_params(op_row: dict[str, Any] | None, given: dict[str, Any] | None, *, for_payment: bool) -> dict[str, str]:
    raw = {str(k).strip(): str(v).strip() for k, v in (given or {}).items() if v not in (None, "")}
    if not op_row:
        return raw
    out: dict[str, str] = {}
    matched_raw_keys: set[str] = set()
    for p in op_row.get("ad_params") or []:
        fetch_key = str(p.get("fetch_key") or p.get("key") or "").strip()
        pay_key = str(p.get("pay_key") or p.get("key") or "").strip()
        target_key = pay_key if for_payment else fetch_key
        if not target_key:
            continue
        val = ""
        for cand in (target_key, fetch_key, pay_key, p.get("key")):
            if cand and cand in raw:
                val = raw[cand]
                matched_raw_keys.add(cand)
                break
        if not val and p.get("default_value"):
            val = str(p["default_value"]).strip()
        if val:
            out[target_key] = val
    for k, v in raw.items():
        if k not in matched_raw_keys and k not in out and v:
            out[k] = v
    return out


def _lpg_channel_message(raw: str, *, category: str = "", agent_id: str = "") -> str:
    """AGT retailers get this vendor text for Indane/Bharat LPG ops; HP Gas usually progresses further."""
    text = str(raw or "").strip()
    if category != "LPG_BOOKING":
        return text
    if "unsupported payment channel" not in text.lower():
        return text
    agent_note = f" (agent {agent_id})" if agent_id else ""
    return (
        "Mobikwik rejected this LPG operator on your retailer agent channel"
        f"{agent_note}. Indane/Bharat Gas cylinder booking is not enabled for AGT on this account — "
        "ask Mobikwik to enable LPG booking for your agent, or try HP Gas with a Mobikwik-registered mobile."
    )


def fetch_bill(
    *,
    operator_id: str | int,
    customer_id: str,
    circle: str = "",
    ad_params: dict[str, Any] | None = None,
    payment_mode: str = "",
    op_row: dict[str, Any] | None = None,
    transport=None,
) -> dict[str, Any]:
    row = op_row or find_operator(str(operator_id))
    numeric_op = _op_value(row["op"] if row else operator_id)
    cir_val = str(circle or "").strip() or (str(row.get("circle_default") or "").strip() if row else "")
    mapped_ad = _map_ad_params(row, ad_params, for_payment=False)
    payload: dict[str, Any] = {
        "cn": str(customer_id).strip(),
        "op": numeric_op,
        "adParams": mapped_ad,
    }
    # Empty cir is not a numeric MDM tag — omit it (same as validate_customer).
    if cir_val:
        payload["cir"] = cir_val
    mode = (payment_mode or "").strip()
    if mode:
        payload["paymentMode"] = mode
    cfg = _config() or {}
    res = _request(
        "integration.bbps.view_bill",
        "view_bill",
        payload,
        target_id=numeric_op,
        transport=transport,
    )
    if not res["ok"]:
        err = _lpg_channel_message(
            res["error"],
            category=str((row or {}).get("category") or ""),
            agent_id=str(cfg.get("agent_id") or ""),
        )
        return {"ok": False, "status": res["status"], "error": err, "bill": None}

    data = res["data"]
    raw_list = data.get("data")
    bill: dict[str, Any] | None = None
    if isinstance(data.get("billDetails"), dict):
        bill = dict(data["billDetails"])
    elif isinstance(raw_list, list) and raw_list and isinstance(raw_list[0], dict):
        bill = dict(raw_list[0])
        nested = bill.get("Data") or bill.get("data")
        if isinstance(nested, dict):
            bill["dueDate"] = bill.get("dueDate") or nested.get("dueDate") or nested.get("due_date")
            bill.pop("Data", None)
            bill.pop("data", None)
    elif isinstance(raw_list, list) and len(raw_list) == 0:
        return {"ok": False, "status": 404, "error": "No pending bill found for this consumer.", "bill": None}
    else:
        bill = dict(data)

    amount = _extract_bill_amount(bill)
    return {
        "ok": True,
        "status": 200,
        "error": "",
        "bill": {
            "amount": amount,
            "customer_name": str(bill.get("userName") or bill.get("customerName") or bill.get("consumerName") or "").strip(),
            "bill_number": str(bill.get("billNumber") or bill.get("billNo") or "").strip(),
            "bill_date": str(bill.get("billdate") or bill.get("billDate") or "").strip(),
            "due_date": str(bill.get("dueDate") or bill.get("due_date") or "").strip(),
        },
    }


def _extract_bill_amount(bill: dict[str, Any]) -> str:
    for key in ("billAmount", "billamount", "dueAmount", "amount", "netAmount", "payableAmount"):
        val = bill.get(key)
        if val not in (None, ""):
            try:
                return f"{Decimal(str(val).strip()):.2f}"
            except Exception:
                continue
    return ""


def generate_transaction_id() -> str:
    ts_hex = hex(int(time.time() * 1000))[2:].upper()
    return f"T{ts_hex}{secrets.token_hex(6).upper()}"


def discount_to_commission_paise(amount: Decimal | str, payload: dict[str, Any] | None) -> int | None:
    """Mobikwik discountprice is what they debited. The gap is vendor commission.

    None means the response did not say. 0 means they charged the full amount.
    """
    if not isinstance(payload, dict):
        return None
    raw = payload.get("discountprice")
    if raw in (None, "", "null"):
        raw = payload.get("discountPrice")
    if raw in (None, "", "null"):
        return None
    try:
        charged = Decimal(str(raw).strip())
        billed = Decimal(str(amount).strip())
    except Exception:
        return None
    if charged < 0 or billed < 0:
        return None
    gap = billed - charged
    if gap <= 0:
        return 0
    return int((gap * Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def pay_bill(
    *,
    operator_id: str | int,
    customer_id: str,
    amount: Decimal | str,
    reqid: str = "",
    circle: str = "",
    customer_mobile: str = "",
    remitter_name: str = "",
    payment_mode: str = "",
    payment_account_info: str = "",
    ad_params: dict[str, Any] | None = None,
    op_row: dict[str, Any] | None = None,
    transport=None,
) -> dict[str, Any]:
    cfg = _config() or {}
    row = op_row or find_operator(str(operator_id))
    numeric_op = _op_value(row["op"] if row else operator_id)
    is_fastag = _is_fastag_row(row)
    mode = (payment_mode or "").strip() or (str(row.get("default_payment_mode") or "").strip() if row else "") or "Cash"
    cir_val = str(circle or "").strip() or (str(row.get("circle_default") or "").strip() if row else "")

    ref = (reqid or "").strip() or generate_transaction_id()
    amt_str = f"{Decimal(str(amount)):.2f}" if not isinstance(amount, Decimal) else f"{amount:.2f}"
    acct = (payment_account_info or "").strip()
    if not acct:
        if is_fastag and mode.upper() == "UPI":
            acct = _fastag_upi_account(customer_id)
        else:
            acct = (customer_mobile or "").strip()
    digits = "".join(ch for ch in acct if ch.isdigit())
    if len(digits) == 12 and digits.startswith("91"):
        acct = digits[2:]
    payload: dict[str, Any] = {
        "cn": str(customer_id).strip(),
        "op": numeric_op,
        "cir": cir_val,
        "amt": amt_str,
        "reqid": ref,
        "remitterName": (remitter_name or "PaySwap Retailer").strip()[:80],
        "customerMobile": (customer_mobile or "9999999999").strip(),
        "paymentRefID": ref,
        "paymentMode": mode,
        "agentId": cfg.get("agent_id", ""),
        "paymentAccountInfo": acct or "9999999999",
    }
    mapped_ad = _map_ad_params(row, ad_params, for_payment=True)
    for key, val in mapped_ad.items():
        if key not in payload and val not in (None, ""):
            payload[key] = str(val).strip()

    res = _request("integration.bbps.pay", "pay", payload, target_id=ref, transport=transport)
    if not res["ok"]:
        # On gateway timeout, Mobikwik requires treating the transaction as pending
        # and polling retailerStatus rather than marking it failed immediately.
        if res["status"] == 504:
            return {
                "ok": True,
                "status": 202,
                "error": "",
                "reference": ref,
                "transaction_id": ref,
                "vendor_status": "PENDING",
                "phase": "pending",
            }
        return {
            "ok": False,
            "status": res["status"],
            "error": res["error"],
            "reference": ref,
            "transaction_id": "",
            "vendor_status": "FAILED",
            "phase": "failed",
        }

    data = res["data"]
    inner = data.get("data") if isinstance(data.get("data"), dict) else {}
    vendor_commission_paise = discount_to_commission_paise(amt_str, inner)
    if vendor_commission_paise is None and isinstance(data, dict):
        vendor_commission_paise = discount_to_commission_paise(amt_str, data)
    vendor_status = str(
        inner.get("txStatus")
        or inner.get("txstatus")
        or inner.get("status")
        or inner.get("transactionStatus")
        or data.get("txStatus")
        or data.get("txstatus")
        or data.get("status")
        or data.get("transactionStatus")
        or "SUBMITTED"
    ).strip()
    txn_id = str(
        inner.get("txId")
        or inner.get("transactionId")
        or inner.get("refId")
        or inner.get("mobikwikrefno")
        or inner.get("mobikwikRefNo")
        or data.get("txId")
        or data.get("transactionId")
        or data.get("refId")
        or data.get("mobikwikrefno")
        or ref
    ).strip()
    return {
        "ok": True,
        "status": 200,
        "error": "",
        "reference": ref,
        "transaction_id": txn_id,
        "vendor_status": vendor_status,
        "vendor_commission_paise": vendor_commission_paise,
        "phase": _phase(vendor_status),
    }


def payment_status(*, reference: str, transport=None) -> dict[str, Any]:
    ref = str(reference or "").strip()
    res = _request("integration.bbps.status", "status", {"txId": ref}, target_id=ref, transport=transport)
    if not res["ok"]:
        return {"ok": False, "status": res["status"], "error": res["error"], "reference": ref, "vendor_status": "UNKNOWN", "phase": "pending"}
    data = res["data"]
    inner = data.get("data") if isinstance(data.get("data"), dict) else {}
    vendor_status = str(
        inner.get("txStatus")
        or inner.get("txstatus")
        or inner.get("status")
        or inner.get("transactionStatus")
        or data.get("txStatus")
        or data.get("txstatus")
        or data.get("status")
        or data.get("transactionStatus")
        or "UNKNOWN"
    ).strip()
    vendor_txn_id = str(
        inner.get("mobikwikrefno")
        or inner.get("txId")
        or inner.get("transactionId")
        or data.get("mobikwikrefno")
        or data.get("txId")
        or ""
    ).strip()
    return {
        "ok": True,
        "status": 200,
        "error": "",
        "reference": ref,
        "vendor_status": vendor_status,
        "vendor_txn_id": vendor_txn_id,
        "phase": _phase(vendor_status),
    }


def _phase(vendor_status: str) -> str:
    upper = (vendor_status or "").upper().strip()
    if upper in _SUCCESS_STATUSES:
        return "success"
    if upper in _FAILED_STATUSES:
        return "failed"
    return "pending"


def submit_bill(*, biller: str, account: str, amount: Decimal) -> str:
    """Backward-compatible wrapper for domain/payswap/bbps.py callers."""
    op = find_operator(biller)
    op_id = op["op"] if op else biller
    result = pay_bill(operator_id=op_id, customer_id=account, amount=amount)
    if not result["ok"]:
        raise RuntimeError(result["error"] or "Bill payment failed.")
    return result["reference"]


# ---------------------------------------------------------------------------
# Operator catalogue from Mobikwik Operators.xlsx
# ---------------------------------------------------------------------------

def _operators_xlsx_path() -> Path | None:
    for rel in ("mobikwik/Operators.xlsx", "Mobikwik/Operators.xlsx"):
        candidate = _data_dir() / rel
        if candidate.is_file():
            return candidate
        alt = _backend_root() / rel
        if alt.is_file():
            return alt
    return None


def _canon_category(raw: Any) -> str:
    token = str(raw or "").strip().upper().replace(" ", "_")
    return _CATEGORY_MAP.get(token, token)


def _cell_str(row: tuple[Any, ...], idx: dict[str, int], *names: str) -> str:
    for name in names:
        pos = idx.get(name)
        if pos is not None and pos < len(row):
            val = row[pos]
            if val is not None:
                s = str(val).strip()
                if s and s.lower() != "none":
                    return s
    return ""


def _op_str(raw: str) -> str:
    if raw.endswith(".0") and raw[:-2].isdigit():
        return raw[:-2]
    return raw


# FASTag rows share Mobikwik op 294. Prefer another category's Mobikwik brand icon
# (PaySwap CSP only allows static.mobikwik.com by default). Cir_Id → donor op id.
_FASTAG_BRAND_ICON_OP: dict[str, str] = {
    "11": "294",  # IHMC / highways
    "12": "328",  # IndusInd (insurance)
    "13": "1123",  # Bank of Baroda (Baroda Broadband mark)
    "14": "37",  # ICICI
    "15": "285",  # HDFC
    "16": "261",  # IDFC FIRST
    "17": "239",  # Axis
    "18": "492",  # Kotak
    "19": "575",  # Equitas
    "21": "294",  # Paul Merchants
    "22": "294",  # J&K Bank
    "23": "1609",  # Federal Bank
    "24": "294",  # IDBI
    "25": "1494",  # UCO
    "26": "294",  # Transaction Analyst
    "27": "294",  # IOB
    "28": "294",  # Transcorp
    "29": "1815",  # Karnataka Bank
    "30": "1",  # Airtel
    "31": "134",  # SBI
    "32": "294",  # South Indian Bank
    "33": "827",  # Saraswat
    "34": "294",  # Bank of Maharashtra
    "35": "1298",  # Indian Bank
    "36": "294",  # LivQuik
    "37": "819",  # Union Bank
    "38": "186",  # Canara
    "39": "385",  # AU Bank
    "40": "272",  # Bandhan
    "41": "159",  # Bajaj
    "42": "890",  # Yes Bank
    "43": "294",  # KVB
    "44": "740",  # PNB
    "45": "294",  # CUB
    "46": "1418",  # BlackBuck
}
# Credit-card Cir_Id rows share Mobikwik op 208 — reuse bank marks from FASTag/insurance/loans.
_CREDIT_CARD_BRAND_ICON_OP: dict[str, str] = {
    "1": "37",  # ICICI
    "3": "134",  # SBI
    "4": "740",  # PNB
    "7": "",  # IOB → domain
    "8": "328",  # IndusInd
    "9": "1298",  # Indian Bank
    "10": "",  # IDBI → domain
    "12": "1609",  # Federal
    "13": "",  # South Indian Bank → domain
    "15": "819",  # Union Bank
    "19": "186",  # Canara
    "21": "1123",  # BoB
    "22": "",  # Bank of India → domain
    "23": "239",  # Axis
    "26": "1841",  # RBL loan mark
    "29": "492",  # Kotak
    "30": "261",  # IDFC FIRST
    "31": "385",  # AU
    "32": "",  # HSBC → domain
    "33": "",  # SBM → domain
    "34": "",  # DBS → domain
    "35": "",  # J&K → domain
    "36": "827",  # Saraswat
    "37": "1298",  # One - Indian Bank
    "38": "",  # Dhanlaxmi → domain
    "39": "1123",  # One - BOBCARD
    "40": "",  # ESAF → domain
    "42": "",  # Suryoday → domain
    "43": "",  # CUB → domain
    "44": "",  # DCB → domain
    "45": "",  # CSB → domain
    "46": "272",  # Bandhan
    "47": "",  # TMB → domain
}
# When no Mobikwik donor exists, fall back to a public favicon (CSP allows gstatic).
_FASTAG_BRAND_DOMAINS: dict[str, str] = {
    "11": "nhai.gov.in",
    "21": "paulmerchants.net",
    "22": "jkbank.com",
    "24": "idbibank.in",
    "26": "transactionanalysts.com",
    "27": "iob.in",
    "28": "transcorpint.com",
    "32": "southindianbank.com",
    "34": "bankofmaharashtra.in",
    "36": "livquik.com",
    "43": "karurvysyabank.com",
    "45": "cityunionbank.com",
}
_CREDIT_CARD_BRAND_DOMAINS: dict[str, str] = {
    "7": "iob.in",
    "10": "idbibank.in",
    "13": "southindianbank.com",
    "22": "bankofindia.co.in",
    "32": "hsbc.co.in",
    "33": "sbm.bank.in",
    "34": "dbs.com",
    "35": "jkbank.com",
    "38": "dhanbank.com",
    "40": "esafbank.com",
    "42": "suryodaybank.com",
    "43": "cityunionbank.com",
    "44": "dcbbank.com",
    "45": "csb.co.in",
    "47": "tmb.in",
}


def _mobikwik_op_icon(op_id: str) -> str:
    clean = _op_str(op_id)
    if clean.isdigit():
        return f"{_ICON_BASE}/op{clean}.png"
    return ""


def _gstatic_favicon(domain: str) -> str:
    clean = str(domain or "").strip().lower()
    if not clean or "/" in clean or " " in clean:
        return ""
    # https:// without www — some bank hosts only resolve this way on gstatic.
    return (
        "https://t2.gstatic.com/faviconV2?client=SOCIAL&type=FAVICON"
        f"&fallback_opts=TYPE,SIZE,URL&url=https://{clean}&size=128"
    )


def _icon_url(op: str, *, category: str = "", circle_default: str = "") -> str:
    cat = str(category or "").strip().upper()
    cir = str(circle_default or "").strip()
    if cat == "FASTAG":
        donor = _FASTAG_BRAND_ICON_OP.get(cir, "")
        domain = _FASTAG_BRAND_DOMAINS.get(cir, "")
        # Prefer a real brand mark from another Mobikwik category (same CSP host).
        if donor and donor not in {"", "294", "208"}:
            return _mobikwik_op_icon(donor)
        if domain:
            return _gstatic_favicon(domain)
        if donor:
            return _mobikwik_op_icon(donor)
    if cat == "CREDIT_CARD":
        donor = _CREDIT_CARD_BRAND_ICON_OP.get(cir, "")
        domain = _CREDIT_CARD_BRAND_DOMAINS.get(cir, "")
        if donor and donor not in {"", "294", "208"}:
            return _mobikwik_op_icon(donor)
        if domain:
            return _gstatic_favicon(domain)
        if donor:
            return _mobikwik_op_icon(donor)
    return _mobikwik_op_icon(op)


_DATE_FORMAT_HINT = re.compile(
    r"^(dd[/\-.]?mm[/\-.]?yyyy|yyyy[/\-.]?mm[/\-.]?dd|dd-mmm-yyyy|dd/mm/yyyy|yyyy-mm-dd|ddmmyyyy|yyyymmdd)$",
    re.I,
)
_ENUM_SPLIT = re.compile(r"\s*,\s*")
_LABEL_CODE = re.compile(r"^(.+?)\s*[:=]\s*([A-Za-z0-9._-]{1,32})\s*$")


def _normalize_sheet_code(raw: str) -> str:
    """Excel often stores Cir_Id / bank codes as 11.0 — strip trailing .0."""
    text = _op_str(str(raw or "").strip())
    if re.fullmatch(r"\d+\.0+", text):
        return text.split(".", 1)[0]
    return text


def _parse_enum_options(raw: str) -> list[dict[str, str]]:
    """Turn 'Agra : 201, Surat : 204' or 'Monthly,Bimonthly' into select options."""
    text = str(raw or "").strip()
    if not text or any(ch in text for ch in "^$[]()*+?{}|\\"):
        return []
    parts = [p for p in _ENUM_SPLIT.split(text) if p.strip()]
    if len(parts) < 2:
        return []
    options: list[dict[str, str]] = []
    labeled = 0
    for part in parts:
        match = _LABEL_CODE.match(part.strip())
        if match:
            labeled += 1
            options.append({"label": match.group(1).strip(), "value": _normalize_sheet_code(match.group(2))})
        else:
            token = part.strip()
            if not token:
                continue
            options.append({"label": token, "value": _normalize_sheet_code(token)})
    if len(options) < 2:
        return []
    # Require at least one Label:code pair when commas look like a prose sentence.
    if labeled == 0 and any(len(o["value"]) > 40 for o in options):
        return []
    return options


def _constant_default(regex_or_code: str) -> str:
    """Fixed Mobikwik tag (bank code / Cir_Id) — not a regex and not an enum list."""
    raw = _normalize_sheet_code(str(regex_or_code or "").strip())
    if not raw:
        return ""
    if any(ch in raw for ch in "^$[]()*+?{}|\\"):
        return ""
    if _DATE_FORMAT_HINT.match(raw.replace(" ", "")):
        return ""
    if _parse_enum_options(raw):
        return ""
    if "," in raw or ":" in raw:
        return ""
    if len(raw) > 32:
        return ""
    return raw


def _enrich_ad_param(*, key: str, fetch_key: str, pay_key: str, label: str, regex_val: str, optional: bool) -> dict[str, Any]:
    """Mark constants as ui_hidden and enum lists as select options for the counter form."""
    options = _parse_enum_options(regex_val)
    default_val = "" if options else _constant_default(regex_val)
    ui_hidden = bool(default_val) and not optional and not options
    return {
        "key": key,
        "fetch_key": fetch_key,
        "pay_key": pay_key,
        "label": label,
        "regex": "" if (options or ui_hidden) else regex_val,
        "default_value": default_val,
        "optional": optional,
        "ui_hidden": ui_hidden,
        "options": options,
    }


def _parse_params(row: tuple[Any, ...], idx: dict[str, int]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    primary_label = _cell_str(row, idx, "Parameter_1_Name (cn)", "Parameter_1_Name") or "Consumer number"
    primary_regex = _cell_str(row, idx, "Param_1_Regex")
    primary = {
        "key": _cell_str(row, idx, "Param_1_id") or "cn",
        "label": primary_label,
        "regex": primary_regex,
        "optional": _cell_str(row, idx, "Param_1_Optional").lower() == "true",
    }
    extra: list[dict[str, Any]] = []
    for n in range(2, 11):
        label = _cell_str(row, idx, f"Param_{n}_Name")
        param_id = _cell_str(row, idx, f"Param_{n}_id")
        pay_id = _cell_str(row, idx, f"Param_{n}_id for payments", f"Param_{n}_id for paymnents")
        key = pay_id or param_id
        if not label and not key:
            continue
        regex_val = _cell_str(row, idx, f"Param_{n}_Regex")
        extra.append(
            _enrich_ad_param(
                key=key or f"ad{n}",
                fetch_key=param_id or key or f"ad{n}",
                pay_key=pay_id or param_id or f"ad{n}",
                label=label or param_id or key,
                regex_val=regex_val,
                optional=_cell_str(row, idx, f"Param_{n}_Optional").lower() == "true",
            )
        )
    return primary, extra


def _circle_from_sheet(cir_raw: str) -> tuple[bool, str]:
    """Return (cir_required_for_ui, circle_default).

    Mobikwik Cir_Id on FASTag / credit-card / some education rows is a fixed bank
    or board code — auto-send it, never ask the retailer for a telecom circle.
    Prepaid still uses the separate TELECOM_CIRCLES picker (isPrepaidLike).
    """
    raw = _normalize_sheet_code(cir_raw)
    if not raw or raw.lower() in _CIRCLE_NONE:
        return False, ""
    # Fixed numeric / short alphanumeric codes are defaults, not user prompts.
    if re.fullmatch(r"[A-Za-z0-9_-]{1,12}", raw):
        return False, raw
    return True, ""


# Mobikwik LPG cylinder booking ops used by ParkPe (apps/parkpe/js/screens.js).
# Operators.xlsx only lists piped Gas; cylinder Indane / Bharat Gas / HP Gas are absent.
# Live probe: empty adParams → "Tag Value Should be Numeric as per MDM";
# ad1 alone long → "Product Qty"; ad1+ad2 required as numeric tags for Bharat Gas.
_LPG_SUPPLEMENT_VERSION = "lpg-cylinder-v3"
# PARAM_UI_VERSION bumps catalogue cache when ad_param / circle UI rules change.
_PARAM_UI_VERSION = "param-ui-v4-brand-icons"
_LPG_QTY_PARAM = {
    "key": "ad1",
    "fetch_key": "ad1",
    "pay_key": "ad1",
    "label": "Cylinder quantity",
    "regex": "^[0-9]{1,3}$",
    "default_value": "1",
    "optional": False,
    "ui_hidden": False,
    "options": [],
}
_LPG_DISTRIBUTOR_PARAM = {
    "key": "ad2",
    "fetch_key": "ad2",
    "pay_key": "ad2",
    "label": "Distributor code (numeric)",
    "regex": "^[0-9]{4,12}$",
    "default_value": "",
    "optional": False,
    "ui_hidden": False,
    "options": [],
}
_LPG_SUPPLEMENT: tuple[dict[str, Any], ...] = (
    {
        "op": "293",
        "biller_id": "INDI00000NATT5",
        "name": "Indane Gas (Indian Oil / IOCL)",
        "search_aliases": ("indane", "inden", "iocl", "indian oil", "cylinder"),
        "primary_label": "LPG ID / Consumer number",
        "ad_params": (_LPG_QTY_PARAM, _LPG_DISTRIBUTOR_PARAM),
    },
    {
        "op": "897",
        "biller_id": "BHAR00000NATR4",
        "name": "Bharat Gas (BPCL)",
        "search_aliases": ("bharat gas", "bpcl", "bharat", "cylinder"),
        "primary_label": "LPG ID / Consumer number",
        "ad_params": (_LPG_QTY_PARAM, _LPG_DISTRIBUTOR_PARAM),
    },
    {
        "op": "978",
        "biller_id": "HPCL00000NATG1",
        "name": "HP Gas (HPCL / Hindustan Petroleum)",
        "search_aliases": ("hp gas", "hpcl", "hindustan", "hindustan petroleum", "cylinder"),
        "primary_label": "Registered mobile number",
        "ad_params": (_LPG_QTY_PARAM,),
    },
)


def _lpg_supplement_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for raw in _LPG_SUPPLEMENT:
        op = str(raw["op"])
        rows.append(
            {
                "op": op,
                "biller_id": str(raw["biller_id"]),
                "name": str(raw["name"]),
                "category": "LPG_BOOKING",
                "category_label": _CATEGORY_LABELS["LPG_BOOKING"],
                "bbps_enabled": True,
                "bill_fetch": "OPTIONAL",
                "cir_required": False,
                "circle_default": "",
                "is_fastag": False,
                "modes": ["Cash", "UPI", "Wallet"],
                "default_payment_mode": "Cash",
                "icon": _icon_url(op),
                "primary_param": {
                    "key": "cn",
                    "label": str(raw["primary_label"]),
                    "regex": "",
                    "optional": False,
                },
                "ad_params": [dict(p) for p in (raw.get("ad_params") or ())],
                "search_aliases": list(raw.get("search_aliases") or ()),
            }
        )
    return rows


def _load_catalogue() -> list[dict[str, Any]]:
    global _CAT_CACHE
    path = _operators_xlsx_path()
    if path is None:
        return list(_lpg_supplement_rows())
    mtime = path.stat().st_mtime
    cache_key = (mtime, _LPG_SUPPLEMENT_VERSION, _PARAM_UI_VERSION)
    with _CAT_LOCK:
        if _CAT_CACHE is not None and _CAT_CACHE[0] == cache_key:
            return _CAT_CACHE[1]

        import openpyxl

        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        items: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for sheet_name in ("Operator", "CCBP Bank List", "EdBillers(OpId274)"):
            if sheet_name not in wb.sheetnames:
                continue
            ws = wb[sheet_name]
            rows_iter = ws.iter_rows(values_only=True)
            header = next(rows_iter, None)
            if not header:
                continue
            idx = {str(col).strip(): i for i, col in enumerate(header) if col is not None}
            for row in rows_iter:
                op = _op_str(_cell_str(row, idx, "op"))
                name = _cell_str(row, idx, "Biller Name")
                if not op or not name:
                    continue
                category = _canon_category(_cell_str(row, idx, "Category"))
                if not category:
                    continue
                biller_id = _cell_str(row, idx, "Biller Id")
                if biller_id.upper() == "NA":
                    biller_id = op
                key = (category, op + ":" + biller_id)
                if key in seen:
                    continue
                seen.add(key)

                bbps_raw = _cell_str(row, idx, "BBPS Enabled").lower()
                bbps_enabled = bbps_raw in {"true", "yes", "1"}
                fetch_raw = _cell_str(row, idx, "Bill Fetch Required").upper()
                if "MANDATORY" in fetch_raw or fetch_raw == "REQUIRED":
                    bill_fetch = "MANDATORY"
                elif "OPTIONAL" in fetch_raw:
                    bill_fetch = "OPTIONAL"
                else:
                    bill_fetch = "NOT_REQUIRED"

                cir_required, circle_default = _circle_from_sheet(_cell_str(row, idx, "Cir_Id"))
                modes_raw = _cell_str(row, idx, "Payment Modes")
                modes = [m.strip() for m in modes_raw.split(",") if m.strip()] or ["Cash"]
                is_fastag = "FASTAG" in category or "FASTAG" in name.upper()
                if "Cash" in modes and not is_fastag:
                    default_mode = "Cash"
                elif is_fastag and "UPI" in modes:
                    default_mode = "UPI"
                else:
                    default_mode = modes[0]
                primary, extra = _parse_params(row, idx)
                items.append(
                    {
                        "op": op,
                        "biller_id": biller_id,
                        "name": name,
                        "category": category,
                        "category_label": _CATEGORY_LABELS.get(category, category.replace("_", " ").title()),
                        "bbps_enabled": bbps_enabled,
                        "bill_fetch": bill_fetch,
                        "cir_required": cir_required,
                        "circle_default": circle_default,
                        "is_fastag": is_fastag,
                        "modes": modes,
                        "default_payment_mode": default_mode,
                        "icon": _icon_url(op, category=category, circle_default=circle_default),
                        "primary_param": primary,
                        "ad_params": extra,
                        "search_aliases": [],
                    }
                )
        wb.close()
        for extra_row in _lpg_supplement_rows():
            key = (extra_row["category"], extra_row["op"] + ":" + extra_row["biller_id"])
            if key in seen:
                continue
            seen.add(key)
            items.append(extra_row)
        _CAT_CACHE = (cache_key, items)
        return items


_POPULAR_CATEGORIES = (
    "ELECTRICITY",
    "FASTAG",
    "PREPAID",
    "MOBILE_POSTPAID",
    "DTH",
    "GAS",
    "LPG_BOOKING",
    "WATER",
    "BROADBAND_POSTPAID",
    "BROADBAND",
    "CREDIT_CARD",
    "LOAN_REPAYMENT",
    "EMI_PAYMENT",
    "INSURANCE",
)
_CATEGORY_ORDER = {cat: idx for idx, cat in enumerate(_POPULAR_CATEGORIES)}


def list_categories() -> list[dict[str, Any]]:
    counts: dict[str, dict[str, Any]] = {}
    for row in _load_catalogue():
        cat = row["category"]
        if cat not in counts:
            counts[cat] = {
                "id": cat,
                "label": row["category_label"],
                "count": 0,
                "popular": cat in _CATEGORY_ORDER,
            }
        counts[cat]["count"] += 1
    return sorted(
        counts.values(),
        key=lambda item: (0 if item["popular"] else 1, _CATEGORY_ORDER.get(item["id"], 999), item["label"]),
    )


def list_operators(category: str | None = None, query: str = "", limit: int = 200) -> list[dict[str, Any]]:
    target = _canon_category(category) if category else ""
    needle = (query or "").strip().lower()
    preferred: list[dict[str, Any]] = []
    rest: list[dict[str, Any]] = []
    for row in _load_catalogue():
        if target and row["category"] != target:
            continue
        if needle:
            aliases = [str(a).lower() for a in (row.get("search_aliases") or ())]
            blob = f"{row['name']} {row['biller_id']} {row['op']} {row.get('category_label', '')} {' '.join(aliases)}".lower()
            if needle not in blob:
                continue
            alias_hit = any(needle == a or needle in a or a in needle for a in aliases)
            (preferred if alias_hit else rest).append(row)
        else:
            rest.append(row)
    return (preferred + rest)[:limit]


def find_operator(identifier: str) -> dict[str, Any] | None:
    needle = _op_str(str(identifier or "").strip())
    if not needle:
        return None
    items = _load_catalogue()
    upper = needle.upper()
    for row in items:
        if row["biller_id"].upper() == upper:
            return row
    for row in items:
        if row["op"] == needle:
            return row
    lower = needle.lower()
    for row in items:
        if row["name"].lower() == lower:
            return row
    return None
