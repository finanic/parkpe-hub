"""Email, SMS, Aadhaar, and PAN checks for signup.

auth.server is the only caller. OTPs, Aadhaar numbers, and PAN values are not
logged. SMS goes through integrations/kaleyra.py. Email uses auth/otp-mail.php
(which calls the existing ses-smtp.php). Aadhaar and PAN use Cashfree Secure ID.
A missing setting fails the check.
"""

from __future__ import annotations

import json
import os
import re
import ssl
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

from core.actions import elapsed_ms, log_action
from integrations.cashfree_signature import build_x_cf_signature
from integrations.kaleyra import send_otp

PAN_RE = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")
GSTIN_RE = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")
UDYAM_RE = re.compile(r"^UDYAM-[A-Z]{2}-[0-9]{2}-[0-9]{7}$")
_NAME_SKIP = {
    "PRIVATE",
    "LIMITED",
    "PVT",
    "LTD",
    "LLP",
    "ENTERPRISES",
    "ENTERPRISE",
    "STORE",
    "SHOP",
    "AND",
    "THE",
}
OTP_CODE_TTL = 10 * 60
# Desk signup rows stay until the account opens or an operator cancels them.
SIGNUP_INTENT_TTL = 24 * 60 * 60


def signup_expires_at(now: int | None = None) -> int:
    base = int(time.time()) if now is None else int(now)
    return base + SIGNUP_INTENT_TTL


def normalize_mobile(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    digits = "".join(ch for ch in value if ch.isdigit())
    if digits.startswith("91") and len(digits) == 12:
        digits = digits[2:]
    if len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    if len(digits) != 10 or digits[0] not in "6789":
        return None
    return digits


def normalize_pan(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    pan = value.strip().upper()
    if not PAN_RE.fullmatch(pan):
        return None
    return pan


def mask_pan(pan: str) -> str:
    """Desk-safe PAN label. Full value stays off account_profiles."""
    normalized = normalize_pan(pan)
    if not normalized:
        return ""
    return normalized[:5] + "····" + normalized[-1]


def mask_digilocker_ref(ref: str) -> str:
    """Cashfree verification id only; not an Aadhaar number."""
    if not isinstance(ref, str):
        return ""
    return ref.strip()[:160]


def mask_pan_name(name: str) -> str:
    clean = " ".join((name or "").split())
    if not clean:
        return ""
    if len(clean) <= 24:
        return clean
    return clean[:24] + "…"


def normalize_gstin(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    gstin = value.strip().upper()
    if not GSTIN_RE.fullmatch(gstin):
        return None
    return gstin


def gstin_embeds_pan(gstin: str, pan: str) -> bool:
    return bool(gstin) and bool(pan) and gstin[2:12] == pan


def normalize_udyam(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    udyam = value.strip().upper().replace(" ", "")
    if not UDYAM_RE.fullmatch(udyam):
        return None
    return udyam


def names_overlap(left: str, right: str) -> bool:
    """True when two registry names share a meaningful word."""
    def tokens(value: str) -> set[str]:
        words = re.findall(r"[A-Z0-9]+", (value or "").upper())
        return {word for word in words if len(word) >= 4 and word not in _NAME_SKIP}

    one, two = tokens(left), tokens(right)
    return bool(one and two and one & two)


def normalize_shop_point(lat: object, lng: object) -> tuple[str, str] | None:
    try:
        lat_n = float(lat)
        lng_n = float(lng)
    except (TypeError, ValueError):
        return None
    if not (-90 <= lat_n <= 90 and -180 <= lng_n <= 180):
        return None
    if abs(lat_n) < 0.01 and abs(lng_n) < 0.01:
        return None
    return f"{lat_n:.6f}", f"{lng_n:.6f}"


def normalize_aadhaar(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    digits = "".join(ch for ch in value if ch.isdigit())
    if len(digits) != 12 or len(set(digits)) == 1:
        return None
    return digits


class LiveVerify:
    """Real providers. Tests pass a stand-in so the suite does not call them."""

    def send_email(self, to: str, code: str, role: str | None = None) -> bool:
        # core/actions.py action integration.mail.send. The code stays out of the line.
        started = time.perf_counter()
        script = Path(__file__).with_name("otp-mail.php")
        # The code stays in the PHP stdin. The log only names the recipient and subject.
        exchange = f"php otp-mail.php\nto={_mask_email(to)} subject=Your verification code"
        if not os.environ.get("AUTH_MAIL_CONFIG") or not os.environ.get("AUTH_SES_SMTP_PHP"):
            _provider_log(
                "integration.mail.send",
                ok=False,
                status=503,
                started=started,
                target=_mask_email(to),
                reason="Mail is not configured.",
                request=exchange,
                response="HTTP 503\nMail is not configured. PHP was not started.",
            )
            return False
        payload = json.dumps(
            {
                "to": to,
                "subject": f"{_email_brand(role)} verification code",
                "text": f"Your verification code is {code}. It expires in 10 minutes.",
                "role": role or "customer",
            }
        ).encode()
        try:
            done = subprocess.run(
                ["php", str(script)],
                input=payload,
                capture_output=True,
                timeout=25,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            _provider_log(
                "integration.mail.send",
                ok=False,
                status=504,
                started=started,
                target=_mask_email(to),
                reason="Mail did not send.",
                request=exchange,
                response="HTTP 504\nMail did not send.",
            )
            return False
        ok = done.returncode == 0
        detail = (done.stderr or b"")[:400].decode("utf-8", "replace").strip()
        _provider_log(
            "integration.mail.send",
            ok=ok,
            status=200 if ok else 502,
            started=started,
            target=_mask_email(to),
            reason="" if ok else "Mail did not send.",
            request=exchange,
            response=f"exit {done.returncode}" + (f"\n{detail}" if detail else ""),
        )
        return ok

    def send_sms(self, mobile: str, code: str, role: str | None = None) -> bool:
        # integrations/kaleyra.py picks ParkPe or PaySwap from role.
        # auth.server._signup_start and _signup_resend still treat False as
        # 503. The code check in _signup_contact is a local hash, not Kaleyra.
        return send_otp(mobile, code, role=role).ok

    def digilocker_link(self, verification_id: str) -> str | None:
        # Cashfree discontinued offline Aadhaar OTP. DigiLocker is the supported check.
        started = time.perf_counter()
        req_text = f"POST /verification/digilocker\n{json.dumps({'verification_id': verification_id, 'document_requested': ['AADHAAR'], 'user_flow': 'signup'})}"
        if not _cashfree_ready():
            _provider_log("integration.cashfree.digilocker", ok=False, status=503, started=started, target="digilocker", reason="Verification provider is not configured.", request=req_text)
            return None
        data, http_status, provider_reason = _cashfree_call(
            "/verification/digilocker",
            {
                "verification_id": verification_id,
                "document_requested": ["AADHAAR"],
                "user_flow": "signup",
            },
        )
        safe = _cashfree_link(data) if data else None
        if not safe:
            reason = provider_reason or "Verification provider rejected the check."
            _provider_log(
                "integration.cashfree.digilocker",
                ok=False,
                status=http_status if http_status >= 400 else 502,
                started=started,
                target="digilocker",
                reason=reason,
                request=req_text,
                response=f"HTTP {http_status}\n{reason}" if http_status else reason,
            )
            return None
        _provider_log(
            "integration.cashfree.digilocker",
            ok=True,
            status=200,
            started=started,
            target="digilocker",
            request=req_text,
            response=f"HTTP {http_status or 200}\n{json.dumps({'status': str(data.get('status') or 'CREATED'), 'link_ready': True})}",
        )
        return safe

    def digilocker_ok(self, verification_id: str) -> bool:
        started = time.perf_counter()
        req_text = f"GET /verification/digilocker?verification_id={verification_id}"
        if not _cashfree_ready():
            _provider_log("integration.cashfree.digilocker", ok=False, status=503, started=started, target="digilocker", reason="Verification provider is not configured.", request=req_text)
            return False
        data, http_status, provider_reason = _cashfree_get("/verification/digilocker", {"verification_id": verification_id})
        if not data:
            reason = provider_reason or "Verification provider rejected the check."
            _provider_log(
                "integration.cashfree.digilocker",
                ok=False,
                status=http_status if http_status >= 400 else 502,
                started=started,
                target="digilocker",
                reason=reason,
                request=req_text,
            )
            return False
        cf_status = str(data.get("status") or "").upper()
        if cf_status != "AUTHENTICATED":
            _provider_log(
                "integration.cashfree.digilocker",
                ok=False,
                status=200,
                started=started,
                target="digilocker",
                reason="Verification provider rejected the check.",
                request=req_text,
                response=f"HTTP 200\n{json.dumps({'status': cf_status})}",
            )
            return False
        consent = data.get("document_consent") or []
        ok = isinstance(consent, list) and any(str(item).upper() == "AADHAAR" for item in consent)
        _provider_log(
            "integration.cashfree.digilocker",
            ok=ok,
            status=200,
            started=started,
            target="digilocker",
            reason="" if ok else "Verification provider rejected the check.",
            request=req_text,
            response=f"HTTP 200\n{json.dumps({'status': cf_status, 'aadhaar_consent': ok})}",
        )
        return ok

    def digilocker_poll(self, verification_id: str) -> str:
        """Quiet poll for the console timer. pending until Cashfree says AUTHENTICATED."""
        if not _cashfree_ready():
            return "rejected"
        data, http_status, _provider_reason = _cashfree_get("/verification/digilocker", {"verification_id": verification_id})
        if not data:
            if http_status in {0, 404}:
                return "pending"
            return "rejected"
        if str(data.get("status") or "").upper() != "AUTHENTICATED":
            return "pending"
        consent = data.get("document_consent") or []
        if isinstance(consent, list) and any(str(item).upper() == "AADHAAR" for item in consent):
            _provider_log(
                "integration.cashfree.digilocker",
                ok=True,
                status=200,
                started=time.perf_counter(),
                target="digilocker",
                request=f"GET /verification/digilocker?verification_id={verification_id}",
                response='HTTP 200\n{"status":"AUTHENTICATED","aadhaar_consent":true}',
            )
            return "authenticated"
        return "rejected"

    def pan_verify(self, pan: str, name: str) -> tuple[bool, str]:
        started = time.perf_counter()
        req_text = 'POST /verification/pan\n{"pan":"[redacted]"}'
        if not _cashfree_ready():
            _provider_log("integration.cashfree.pan", ok=False, status=503, started=started, target="pan", reason="Verification provider is not configured.", request=req_text)
            return False, ""
        data, http_status, provider_reason = _cashfree_call("/verification/pan", {"pan": pan, "name": name})
        if not data:
            reason = provider_reason or "Verification provider rejected the check."
            _provider_log(
                "integration.cashfree.pan",
                ok=False,
                status=http_status if http_status >= 400 else 502,
                started=started,
                target="pan",
                reason=reason,
                request=req_text,
            )
            return False, ""
        status = str(data.get("status") or data.get("valid") or "").upper()
        registered = str(data.get("registered_name") or "")
        ok = status in {"VALID", "SUCCESS", "TRUE"} and _same_name(name, registered)
        _provider_log(
            "integration.cashfree.pan",
            ok=ok,
            status=200,
            started=started,
            target="pan",
            reason="" if ok else "Verification provider rejected the check.",
            request=req_text,
            response=f"HTTP 200\n{json.dumps({'status': status, 'name_match': ok})}",
        )
        return ok, registered

    def pan_check(self, pan: str, name: str) -> bool:
        ok, _registered = self.pan_verify(pan, name)
        return ok

    def gstin_verify(self, gstin: str) -> tuple[bool, dict]:
        # Cashfree Secure ID POST /verification/gstin. The number stays out of the log.
        started = time.perf_counter()
        req_text = 'POST /verification/gstin\n{"GSTIN":"[redacted]"}'
        if not _cashfree_ready():
            _provider_log("integration.cashfree.gstin", ok=False, status=503, started=started, target="gstin", reason="Verification provider is not configured.", request=req_text)
            return False, {}
        data, http_status, provider_reason = _cashfree_call("/verification/gstin", {"GSTIN": gstin})
        if not data:
            reason = provider_reason or "Verification provider rejected the check."
            _provider_log(
                "integration.cashfree.gstin",
                ok=False,
                status=http_status if http_status >= 400 else 502,
                started=started,
                target="gstin",
                reason=reason,
                request=req_text,
            )
            return False, {}
        status = str(data.get("gst_in_status") or "").strip().upper()
        valid = data.get("valid")
        ok = status == "ACTIVE" or (valid is True and status in {"", "ACTIVE"})
        record = {
            "legal_name": str(data.get("legal_name_of_business") or "").strip(),
            "trade_name": str(data.get("trade_name_of_business") or "").strip(),
            "status": status or ("ACTIVE" if valid is True else ""),
        }
        _provider_log(
            "integration.cashfree.gstin",
            ok=ok,
            status=200,
            started=started,
            target="gstin",
            reason="" if ok else "Verification provider rejected the check.",
            request=req_text,
            response=f"HTTP 200\n{json.dumps({'status': record['status'], 'valid': bool(ok)})}",
        )
        return ok, record

    def udyam_verify(self, udyam: str, verification_id: str) -> tuple[bool, str]:
        # Cashfree Secure ID POST /verification/udyam.
        started = time.perf_counter()
        safe_id = re.sub(r"[^A-Za-z0-9._-]", "", verification_id)[:50] or "signup"
        req_text = f"POST /verification/udyam\n{json.dumps({'verification_id': safe_id, 'udyam': '[redacted]'})}"
        if not _cashfree_ready():
            _provider_log("integration.cashfree.udyam", ok=False, status=503, started=started, target="udyam", reason="Verification provider is not configured.", request=req_text)
            return False, ""
        data, http_status, provider_reason = _cashfree_call(
            "/verification/udyam",
            {"verification_id": safe_id, "udyam": udyam},
        )
        if not data:
            reason = provider_reason or "Verification provider rejected the check."
            _provider_log(
                "integration.cashfree.udyam",
                ok=False,
                status=http_status if http_status >= 400 else 502,
                started=started,
                target="udyam",
                reason=reason,
                request=req_text,
            )
            return False, ""
        status = str(data.get("status") or "").upper()
        enterprise = str(data.get("enterprise_name") or "").strip()
        ok = status == "SUCCESS" and bool(enterprise)
        _provider_log(
            "integration.cashfree.udyam",
            ok=ok,
            status=200,
            started=started,
            target="udyam",
            reason="" if ok else "Verification provider rejected the check.",
            request=req_text,
            response=f"HTTP 200\n{json.dumps({'status': status, 'name_present': bool(enterprise)})}",
        )
        return ok, enterprise


def _provider_log(
    action: str,
    *,
    ok: bool,
    status: int,
    started: float,
    target: str = "",
    reason: str = "",
    request: str = "",
    response: str = "",
) -> None:
    """Logs screen API list. Callers pass a name, never the OTP, PAN, or body."""
    if not request:
        request = action
    if not response:
        response = f"HTTP {status}" + (f"\n{reason}" if reason else "")
    log_action(
        action=action,
        outcome="ok" if ok else "error",
        status=status,
        duration_ms=elapsed_ms(started),
        target_id=target,
        error_code="" if ok else "server_error",
        error_reason=reason,
        request=request,
        response=response,
    )


def _apply_cashfree_aliases() -> None:
    """Cashfree dashboard copy sometimes uses App ID / Secret Key names."""
    pairs = (
        ("CASHFREE_API_KEY", "CASHFREE_CLIENT_ID"),
        ("CASHFREE_API_SECRET", "CASHFREE_CLIENT_SECRET"),
        ("CASHFREE_APP_ID", "CASHFREE_CLIENT_ID"),
        ("CASHFREE_SECRET_KEY", "CASHFREE_CLIENT_SECRET"),
        ("CASHFREE_CLIENT_SECRET_KEY", "CASHFREE_CLIENT_SECRET"),
    )
    for source, target in pairs:
        if not os.environ.get(target, "").strip():
            value = os.environ.get(source, "").strip()
            if value:
                os.environ.setdefault(target, value)


def _load_cashfree_lines(text: str) -> None:
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        name = name.strip()
        if name != "AUTH_CASHFREE_ENV" and not name.startswith("CASHFREE_"):
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        os.environ.setdefault(name, value)


def load_cashfree_env(path: Path | None = None) -> None:
    """Fill unset Cashfree keys from data/cashfree.env (fallback).

    Prefer apps/backend/.env via config.envfile.load_backend_env first.
    auth.server.main / manage.py call that before this helper. Lines named
    CASHFREE_* under data/*.env remain a fallback. A value already in the
    environment wins.
    """
    root = Path(__file__).resolve().parents[1]
    custom = os.environ.get("AUTH_DATA_DIR", "").strip()
    data = Path(custom) if custom else root / "data"
    files = [path] if path else [data / "cashfree.env"]
    if path is None:
        files.extend(sorted(data.glob("*.env")))
    seen: set[Path] = set()
    for file in files:
        if file is None or file in seen:
            continue
        seen.add(file)
        try:
            text = file.read_text()
        except OSError:
            continue
        _load_cashfree_lines(text)
    extra = os.environ.get("AUTH_CASHFREE_ENV", "").strip()
    if extra:
        platform = Path(extra).expanduser()
        if platform.is_file():
            try:
                _load_cashfree_lines(platform.read_text())
            except OSError:
                pass
            pem = os.environ.get("CASHFREE_PUBLIC_KEY_PATH", "").strip()
            if pem:
                pem_path = Path(pem).expanduser()
                if not pem_path.is_absolute():
                    pem_path = (platform.parent / pem).resolve()
                if pem_path.is_file():
                    os.environ["CASHFREE_PUBLIC_KEY_PATH"] = str(pem_path)
    _apply_cashfree_aliases()


def load_mail_env(path: Path | None = None) -> None:
    """Fill unset mail paths from data/mail.env (fallback).

    Prefer AUTH_MAIL_CONFIG / AUTH_SES_SMTP_PHP in apps/backend/.env
    (config.envfile.load_backend_env). otp-mail.php reads those two names.
    A value already in the environment wins. Other names are ignored.
    """
    file = path or Path(__file__).resolve().parents[1] / "data" / "mail.env"
    allowed = {"AUTH_MAIL_CONFIG", "AUTH_SES_SMTP_PHP"}
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
        if name not in allowed:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        os.environ.setdefault(name, value)


def _mask_email(value: str) -> str:
    if not isinstance(value, str) or "@" not in value:
        return "email"
    local, _, domain = value.partition("@")
    return f"{local[:1]}***@{domain}"[:80]


def _email_brand(role: str | None) -> str:
    return "PaySwap" if role in {"retailer", "payswap"} else "ParkPe"


def _cashfree_ready() -> bool:
    return bool(os.environ.get("CASHFREE_CLIENT_ID", "").strip() and os.environ.get("CASHFREE_CLIENT_SECRET", "").strip())


def cashfree_configured() -> bool:
    return _cashfree_ready()


def mail_configured() -> bool:
    return bool(
        os.environ.get("AUTH_MAIL_CONFIG", "").strip()
        and os.environ.get("AUTH_SES_SMTP_PHP", "").strip()
    )


def _same_name(given: str, registered: str) -> bool:
    left = " ".join(given.upper().split())
    right = " ".join(registered.upper().split())
    return bool(left) and left == right


def _cashfree_page(url: str) -> str | None:
    """Only an https Cashfree page is safe to open from the console."""
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not host:
        return None
    if host != "cashfree.com" and not host.endswith(".cashfree.com"):
        return None
    return url


def _cashfree_link(data: dict) -> str | None:
    for key in ("url", "verification_url", "redirect_url", "link"):
        raw = data.get(key)
        if not raw:
            continue
        safe = _cashfree_page(str(raw))
        if safe:
            return safe
    return None


def _ssl_context() -> ssl.SSLContext | None:
    # integrations/kaleyra.py uses the same bundle on macOS Python.
    try:
        import certifi
    except ImportError:
        return None
    return ssl.create_default_context(cafile=certifi.where())


def _cashfree_headers() -> dict | None:
    client_id = os.environ.get("CASHFREE_CLIENT_ID", "").strip()
    secret = os.environ.get("CASHFREE_CLIENT_SECRET", "").strip()
    if not client_id or not secret:
        return None
    headers = {
        "Content-Type": "application/json",
        "x-client-id": client_id,
        "x-client-secret": secret,
        "x-api-version": "2023-12-18",
    }
    pem = os.environ.get("CASHFREE_PUBLIC_KEY_PATH", "").strip()
    if pem:
        path = Path(pem).expanduser()
        if path.is_file():
            headers["x-cf-signature"] = build_x_cf_signature(client_id, path)
    return headers


def _cashfree_reason(status: int, body: bytes) -> str:
    if status == 0 and not body:
        return "Cashfree is not reachable from this host (check TLS or network)."
    if not body:
        if status:
            return f"Cashfree returned HTTP {status}."
        return "Cashfree is not reachable from this host."
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        return f"Cashfree returned HTTP {status}." if status else "Cashfree returned an unreadable response."
    if not isinstance(parsed, dict):
        return f"Cashfree returned HTTP {status}."
    for key in ("message", "code", "error", "type"):
        text = str(parsed.get(key) or "").strip()
        if text:
            return text[:200]
    return f"Cashfree returned HTTP {status}."


def _cashfree_parse(status: int, body: bytes) -> tuple[dict | None, int, str]:
    reason = _cashfree_reason(status, body)
    if status not in {200, 201, 202}:
        return None, status or 502, reason
    if not body:
        return None, status, reason
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        return None, status, reason
    if not isinstance(parsed, dict):
        return None, status, reason
    return parsed, status, reason


def _cashfree_call(path: str, payload: dict) -> tuple[dict | None, int, str]:
    headers = _cashfree_headers()
    root = os.environ.get("CASHFREE_VERIFICATION_BASE_URL", "https://api.cashfree.com").rstrip("/")
    if not headers:
        return None, 503, "Verification provider is not configured."
    status, body = _post(
        root + path,
        json.dumps(payload).encode(),
        headers,
    )
    return _cashfree_parse(status, body)


def _cashfree_get(path: str, query: dict) -> tuple[dict | None, int, str]:
    headers = _cashfree_headers()
    root = os.environ.get("CASHFREE_VERIFICATION_BASE_URL", "https://api.cashfree.com").rstrip("/")
    if not headers:
        return None, 503, "Verification provider is not configured."
    encoded = "&".join(f"{key}={urllib.request.quote(str(value))}" for key, value in query.items())
    del headers["Content-Type"]
    status, body = _request(
        f"{root}{path}?{encoded}",
        headers,
        method="GET",
    )
    return _cashfree_parse(status, body)


def _request(url: str, headers: dict, *, data: bytes | None = None, method: str = "POST") -> tuple[int, bytes]:
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    context = _ssl_context()
    try:
        with urllib.request.urlopen(request, timeout=20, context=context) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as err:
        return err.code, err.read()
    except urllib.error.URLError as err:
        return 0, b""
    except (TimeoutError, OSError):
        return 0, b""


def _post(url: str, payload: bytes, headers: dict) -> tuple[int, bytes]:
    return _request(url, headers, data=payload, method="POST")
