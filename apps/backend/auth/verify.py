"""Email, SMS, Aadhaar, and PAN checks for signup.

auth.server is the only caller. OTPs, Aadhaar numbers, and PAN values are not
logged. Delivery uses Kaleyra, Cashfree Secure ID, and auth/otp-mail.php
(which calls the existing ses-smtp.php). A missing setting fails the check.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

PAN_RE = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")
SIGNUP_TTL = 10 * 60


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


def normalize_aadhaar(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    digits = "".join(ch for ch in value if ch.isdigit())
    if len(digits) != 12 or len(set(digits)) == 1:
        return None
    return digits


class LiveVerify:
    """Real providers. Tests pass a stand-in so the suite does not call them."""

    def send_email(self, to: str, code: str) -> bool:
        script = Path(__file__).with_name("otp-mail.php")
        if not os.environ.get("AUTH_MAIL_CONFIG") or not os.environ.get("AUTH_SES_SMTP_PHP"):
            return False
        payload = json.dumps(
            {
                "to": to,
                "subject": "Your verification code",
                "text": f"Your verification code is {code}. It expires in 10 minutes.",
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
            return False
        return done.returncode == 0

    def send_sms(self, mobile: str, code: str) -> bool:
        sid = os.environ.get("KALEYRA_ACCOUNT_SID", "").strip()
        key = os.environ.get("KALEYRA_API_KEY", "").strip()
        template = os.environ.get("KALEYRA_OTP_TEMPLATE_ID", "").strip()
        sender = os.environ.get("KALEYRA_SENDER_ID", "PARKPA").strip()
        root = os.environ.get("KALEYRA_BASE_URL", "https://api.kaleyra.io").rstrip("/")
        if not sid or not key or not template:
            return False
        body = os.environ.get(
            "KALEYRA_OTP_BODY_TEMPLATE",
            "Your ParkPe verification code is {otp}. It expires in 10 minutes.",
        ).format(otp=code)
        url = f"{root}/v1/{sid}/messages"
        payload = json.dumps(
            {
                "to": "91" + mobile,
                "sender": sender,
                "type": "OTP",
                "template_id": template,
                "body": body,
                "variables": {"var1": code},
            }
        ).encode()
        return _post(url, payload, {"api-key": key, "Content-Type": "application/json"}) is not None

    def digilocker_link(self, verification_id: str) -> str | None:
        # Cashfree discontinued offline Aadhaar OTP. DigiLocker is the supported check.
        data = _cashfree(
            "/verification/digilocker",
            {
                "verification_id": verification_id,
                "document_requested": ["AADHAAR"],
                "user_flow": "signup",
            },
        )
        url = data.get("url") if data else None
        if not url:
            return None
        return str(url)

    def digilocker_ok(self, verification_id: str) -> bool:
        data = _cashfree_get("/verification/digilocker", {"verification_id": verification_id})
        if not data:
            return False
        if str(data.get("status") or "").upper() != "AUTHENTICATED":
            return False
        consent = data.get("document_consent") or []
        if isinstance(consent, list) and consent:
            return any(str(item).upper() == "AADHAAR" for item in consent)
        return True

    def pan_check(self, pan: str, name: str) -> bool:
        data = _cashfree("/verification/pan", {"pan": pan, "name": name})
        if not data:
            return False
        status = str(data.get("status") or data.get("valid") or "").upper()
        return status in {"VALID", "SUCCESS", "TRUE"}


def _cashfree(path: str, payload: dict) -> dict | None:
    client_id = os.environ.get("CASHFREE_CLIENT_ID", "").strip()
    secret = os.environ.get("CASHFREE_CLIENT_SECRET", "").strip()
    root = os.environ.get("CASHFREE_VERIFICATION_BASE_URL", "https://api.cashfree.com").rstrip("/")
    if not client_id or not secret:
        return None
    raw = _post(
        root + path,
        json.dumps(payload).encode(),
        {
            "Content-Type": "application/json",
            "x-client-id": client_id,
            "x-client-secret": secret,
            "x-api-version": "2023-12-18",
        },
    )
    if raw is None:
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _cashfree_get(path: str, query: dict) -> dict | None:
    client_id = os.environ.get("CASHFREE_CLIENT_ID", "").strip()
    secret = os.environ.get("CASHFREE_CLIENT_SECRET", "").strip()
    root = os.environ.get("CASHFREE_VERIFICATION_BASE_URL", "https://api.cashfree.com").rstrip("/")
    if not client_id or not secret:
        return None
    encoded = "&".join(f"{key}={urllib.request.quote(str(value))}" for key, value in query.items())
    request = urllib.request.Request(
        f"{root}{path}?{encoded}",
        headers={
            "x-client-id": client_id,
            "x-client-secret": secret,
            "x-api-version": "2023-12-18",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            if response.status != 200:
                return None
            parsed = json.loads(response.read())
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _post(url: str, payload: bytes, headers: dict) -> bytes | None:
    request = urllib.request.Request(url, data=payload, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            if response.status not in {200, 201, 202}:
                return None
            return response.read()
    except (urllib.error.URLError, TimeoutError, OSError):
        return None
