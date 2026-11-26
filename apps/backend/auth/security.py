"""Password, session, and one-time-code primitives. Standard library only.

auth.server and auth.store are the only callers. Nothing here knows about HTTP.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time

SCRYPT_N = 2**15
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_DKLEN = 32
ACCESS_TTL = 15 * 60
REFRESH_TTL = 14 * 24 * 60 * 60
CHALLENGE_TTL = 5 * 60
MAX_FAILS = 5
LOCK_SECONDS = 15 * 60
IP_WINDOW = 15 * 60
IP_MAX_FAILS = 30
BODY_MAX = 4096

COMMON_PASSWORDS = {
    "password",
    "password123",
    "password1234",
    "123456789012",
    "qwertyuiop12",
    "payswap12345",
    "parkpe123456",
    "admin1234567",
    "letmein12345",
    "welcome12345",
    "iloveyou1234",
    "changeme1234",
}


def b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def b64decode(value: str) -> bytes:
    pad = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + pad)


def new_token() -> str:
    return secrets.token_urlsafe(32)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def hash_password(password: str, *, n: int = SCRYPT_N) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=n,
        r=SCRYPT_R,
        p=SCRYPT_P,
        dklen=SCRYPT_DKLEN,
        maxmem=64 * 1024 * 1024,
    )
    return f"scrypt${n}${SCRYPT_R}${SCRYPT_P}${b64(salt)}${b64(digest)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt_b64, digest_b64 = stored.split("$")
        if scheme != "scrypt":
            return False
        digest = hashlib.scrypt(
            password.encode("utf-8"),
            salt=b64decode(salt_b64),
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(b64decode(digest_b64)),
            maxmem=64 * 1024 * 1024,
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(digest, b64decode(digest_b64))


def password_problem(password: str, email: str) -> str | None:
    if not isinstance(password, str) or not 12 <= len(password) <= 128:
        return "Use 12 to 128 characters."
    lowered = password.lower()
    local = email.split("@", 1)[0].lower()
    if lowered in COMMON_PASSWORDS or lowered == local or local in lowered:
        return "Choose a password that is not common and does not contain the email."
    return None


def normalize_email(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    email = value.strip().lower()
    if len(email) > 254 or email.count("@") != 1:
        return None
    local, domain = email.split("@")
    if not local or not domain or "." not in domain or " " in email:
        return None
    return email


def new_totp_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def _totp_secret(secret_b32: str) -> bytes:
    pad = "=" * (-len(secret_b32) % 8)
    return base64.b32decode(secret_b32.upper() + pad, casefold=True)


def _hotp(secret: bytes, counter: int) -> str:
    digest = hmac.new(secret, counter.to_bytes(8, "big"), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code = int.from_bytes(digest[offset : offset + 4], "big") & 0x7FFFFFFF
    return f"{code % 1_000_000:06d}"


def totp_code(secret_b32: str, when: float | None = None) -> str:
    moment = time.time() if when is None else when
    return _hotp(_totp_secret(secret_b32), int(moment) // 30)


def totp_step(secret_b32: str, code: str, when: float | None = None) -> int | None:
    """Return the 30-second counter that matched, including one step of skew."""
    if not isinstance(code, str) or not code.isdigit() or len(code) != 6:
        return None
    moment = time.time() if when is None else when
    secret = _totp_secret(secret_b32)
    for skew in (-30, 0, 30):
        step = int(moment + skew) // 30
        if hmac.compare_digest(_hotp(secret, step), code):
            return step
    return None


def totp_matches(secret_b32: str, code: str, when: float | None = None) -> bool:
    return totp_step(secret_b32, code, when) is not None


def new_backup_codes() -> list[str]:
    return [f"{secrets.token_hex(2)}-{secrets.token_hex(2)}" for _ in range(8)]


def hash_backup(code: str) -> str:
    return token_hash(code.strip().lower())
