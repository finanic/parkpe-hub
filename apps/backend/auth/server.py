"""HTTP adapter for the auth contract in auth.contract.

Payswap calls these routes through apps/payswap/js/session.js. A missing or reused
refresh cookie revokes that login family. Unexpected exceptions stay as a
generic 500 so stack traces never reach either frontend.
"""

from __future__ import annotations

import json
import os
import secrets
import socket
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from auth.contract import (
    ACCESS_COOKIE,
    ACCESS_PATH,
    HEADER,
    LOGIN_ERROR,
    MFA_COOKIE,
    MFA_PATH,
    REFRESH_COOKIE,
    REFRESH_PATH,
    ROLE_CUSTOMER,
    ROLE_ADMIN,
    ROLE_RETAILER,
    ROLES,
    SCOPE_ENROLL,
    SCOPE_FULL,
    Paths,
)
from auth.security import (
    ACCESS_TTL,
    BODY_MAX,
    CHALLENGE_TTL,
    REFRESH_TTL,
    hash_password,
    new_token,
    new_totp_secret,
    normalize_email,
    password_problem,
    token_hash,
    totp_matches,
)
from auth.store import Store
from auth.verify import SIGNUP_TTL, LiveVerify, normalize_mobile, normalize_pan

def _split_csv(value: str) -> set[str]:
    return {item.strip().rstrip("/") for item in value.split(",") if item.strip()}


class AuthApp:
    def __init__(self, data_dir: Path, origins: set[str], scrypt_n: int, cookie_secure: bool, samesite: str, verifiers=None):
        self.origins = origins
        self.cookie_secure = cookie_secure
        self.samesite = samesite
        self.verifiers = verifiers or LiveVerify()
        self.store = Store(data_dir / "auth.sqlite", scrypt_n)

    def close(self) -> None:
        self.store.close()

    def handle(self, request: BaseHTTPRequestHandler) -> None:
        parsed = urlparse(request.path)
        path = parsed.path
        method = request.command
        origin = request.headers.get("Origin", "")
        try:
            if method == "OPTIONS":
                self._send(request, 204, b"", origin)
                return
            if method == "GET" and path in CONSOLE_FILES:
                self._console(request, path)
                return
            if method == "GET" and path == Paths.HEALTH:
                self._json(request, 200, {"ok": True}, origin)
                return
            if not self._browser_ok(request, method):
                self._json(request, 403, {"error": "Request blocked."}, origin)
                return
            length = int(request.headers.get("Content-Length", "0") or 0)
            if length > BODY_MAX:
                self._json(request, 413, {"error": "Request is too large."}, origin)
                return
            body = {}
            if method == "POST":
                raw = request.rfile.read(length) if length else b""
                if raw:
                    if request.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
                        self._json(request, 415, {"error": "Send JSON."}, origin)
                        return
                    try:
                        body = json.loads(raw)
                    except json.JSONDecodeError:
                        self._json(request, 400, {"error": "Send JSON."}, origin)
                        return
                if not isinstance(body, dict):
                    self._json(request, 400, {"error": "Send JSON."}, origin)
                    return
            ip = request.client_address[0]
            if method == "POST" and path == Paths.REGISTER:
                self._register(request, body, ip, origin)
            elif method == "POST" and path == Paths.SIGNUP_START:
                self._signup_start(request, body, ip, origin)
            elif method == "POST" and path == Paths.SIGNUP_CONTACT:
                self._signup_contact(request, body, ip, origin)
            elif method == "POST" and path == Paths.SIGNUP_AADHAAR:
                self._signup_aadhaar(request, body, ip, origin)
            elif method == "POST" and path == Paths.SIGNUP_AADHAAR_CONFIRM:
                self._signup_aadhaar_confirm(request, body, ip, origin)
            elif method == "POST" and path == Paths.SIGNUP_PAN:
                self._signup_pan(request, body, ip, origin)
            elif method == "POST" and path == Paths.LOGIN:
                self._login(request, body, ip, origin)
            elif method == "POST" and path == Paths.MFA:
                self._mfa(request, body, ip, origin)
            elif method == "POST" and path == Paths.REFRESH:
                self._refresh(request, ip, origin)
            elif method == "POST" and path == Paths.LOGOUT:
                self._logout(request, ip, origin)
            elif method == "POST" and path == Paths.MFA_SETUP:
                self._mfa_setup(request, ip, origin)
            elif method == "POST" and path == Paths.MFA_CONFIRM:
                self._mfa_confirm(request, body, ip, origin)
            elif method == "GET" and path == Paths.ME:
                self._me(request, origin)
            elif method == "GET" and path == Paths.DESK:
                self._desk(request, origin)
            elif method == "GET" and path == Paths.DESK_PEOPLE:
                self._people(request, origin)
            elif method == "POST" and path == Paths.DESK_SIGN_IN:
                self._sign_in_switch(request, body, ip, origin)
            elif method == "GET" and path == Paths.DESK_SIGNUPS:
                self._signups(request, origin)
            elif method == "GET" and path == Paths.DESK_PROCESSES:
                self._processes(request, origin)
            elif method == "POST" and path == Paths.DESK_ACCOUNTS:
                self._add_operator(request, body, ip, origin)
            elif method == "GET" and path == Paths.SETUP:
                self._setup(request, origin)
            else:
                self._json(request, 404, {"error": "Not found."}, origin)
        except Exception:
            self.store.audit("server_error", request.client_address[0])
            self._json(request, 500, {"error": "Something went wrong."}, origin)

    def _browser_ok(self, request: BaseHTTPRequestHandler, method: str) -> bool:
        origin = request.headers.get("Origin")
        if origin and origin.rstrip("/") not in self.origins:
            return False
        if method in {"GET", "POST"} and request.headers.get(HEADER) != "1":
            return False
        return True

    def _register(self, request, body, ip, origin) -> None:
        email = normalize_email(body.get("email"))
        role = body.get("role")
        password = body.get("password")
        if not email or role not in ROLES:
            self._json(request, 400, {"error": "Check the email and account type."}, origin)
            return
        if role in {ROLE_CUSTOMER, ROLE_RETAILER}:
            self._json(request, 400, {"error": "Verify email and mobile before the account is created."}, origin)
            return
        if role == ROLE_ADMIN and self.store.operator_exists():
            self.store.audit("register_operator_closed", ip)
            self._json(request, 403, {"error": "Admin signup is closed."}, origin)
            return
        problem = password_problem(password, email)
        if problem:
            self._json(request, 400, {"error": problem}, origin)
            return
        if self.store.ip_blocked(ip):
            self._json(request, 200, {"ok": True}, origin)
            return
        created = self.store.create_user(email, password, role)
        self.store.audit("register" if created else "register_existing", ip)
        self._json(request, 200, {"ok": True}, origin)

    def _login(self, request, body, ip, origin) -> None:
        email = normalize_email(body.get("email")) or ""
        password = body.get("password") if isinstance(body.get("password"), str) else ""
        role = body.get("role")
        if self.store.ip_blocked(ip) or role not in ROLES or not email:
            self.store.note_attempt(ip, email, False)
            self._json(request, 401, {"error": LOGIN_ERROR}, origin)
            return
        user = self.store.user_by_email(email)
        member = user is not None and self.store.has_membership(user["id"], role)
        blocked = self.store.locked(user) or (user is not None and not member)
        password_ok = self.store.check_password(None if blocked else user, password)
        if not password_ok or blocked or user is None:
            if user is not None and not blocked and member:
                self.store.register_failure(user)
            self.store.note_attempt(ip, email, False)
            self.store.audit("login_failed", ip, user["id"] if user else None)
            self._json(request, 401, {"error": LOGIN_ERROR}, origin)
            return
        self.store.clear_failures(user["id"])
        self.store.note_attempt(ip, email, True)
        if not user["sign_in"]:
            self.store.audit("sign_in_closed", ip, user["id"])
            self._json(request, 401, {"error": LOGIN_ERROR}, origin)
            return
        if user["mfa_enabled"]:
            challenge = new_token()
            self.store.save_challenge(challenge, user["id"], int(time.time()) + CHALLENGE_TTL, role)
            self.store.audit("mfa_challenge", ip, user["id"])
            self._json(
                request,
                200,
                {"mfa_required": True},
                origin,
                cookies=[self._cookie(MFA_COOKIE, challenge, CHALLENGE_TTL, MFA_PATH)],
            )
            return
        self.store.audit("login_enroll", ip, user["id"])
        self._issue(request, user, SCOPE_ENROLL, ip, origin, role, setup=True)

    def _mfa(self, request, body, ip, origin) -> None:
        challenge = self._read_cookie(request, MFA_COOKIE)
        row = self.store.peek_challenge(challenge) if challenge else None
        code = body.get("code") if isinstance(body.get("code"), str) else ""
        user = self.store.user_by_id(row["user_id"]) if row else None
        if user and not user["sign_in"]:
            self.store.audit("sign_in_closed", ip, user["id"])
            self._json(request, 401, {"error": "Code is incorrect."}, origin, cookies=[self._clear(MFA_COOKIE, MFA_PATH)])
            return
        if not user or not user["mfa_enabled"]:
            self._json(request, 401, {"error": "Code is incorrect."}, origin, cookies=[self._clear(MFA_COOKIE, MFA_PATH)])
            return
        ok = totp_matches(user["mfa_secret"], code.strip()) or self.store.use_backup(user["id"], code)
        if not ok:
            self.store.audit("mfa_failed", ip, user["id"])
            self._json(request, 401, {"error": "Code is incorrect."}, origin)
            return
        self.store.use_challenge(challenge)
        self.store.audit("login", ip, user["id"])
        active = row["role"] or user["role"]
        self._issue(request, user, SCOPE_FULL, ip, origin, active, clear_mfa=True)

    def _mfa_setup(self, request, ip, origin) -> None:
        session = self._session(request)
        if not session or session["scope"] != SCOPE_ENROLL:
            self._json(request, 401, {"error": "Sign in again."}, origin)
            return
        user = self.store.user_by_id(session["user_id"])
        if not user or user["mfa_enabled"]:
            self._json(request, 409, {"error": "Authenticator is already on."}, origin)
            return
        secret = new_totp_secret()
        codes = self.store.stage_mfa(user["id"], secret)
        self.store.audit("mfa_setup", ip, user["id"])
        issuer = "PaySwap" if (session["role"] or user["role"]) == ROLE_RETAILER else "ParkPe"
        label = f"{issuer}:{user['email']}"
        self._json(
            request,
            200,
            {
                "secret": secret,
                "otpauth": f"otpauth://totp/{label}?secret={secret}&issuer={issuer}&algorithm=SHA1&digits=6&period=30",
                "backup_codes": codes,
            },
            origin,
        )

    def _mfa_confirm(self, request, body, ip, origin) -> None:
        session = self._session(request)
        code = body.get("code") if isinstance(body.get("code"), str) else ""
        if not session or session["scope"] != SCOPE_ENROLL:
            self._json(request, 401, {"error": "Sign in again."}, origin)
            return
        user = self.store.user_by_id(session["user_id"])
        if not user or not user["mfa_secret"] or not totp_matches(user["mfa_secret"], code.strip()):
            self._json(request, 401, {"error": "Code is incorrect."}, origin)
            return
        self.store.enable_mfa(user["id"])
        self.store.revoke_user(user["id"])
        self.store.audit("mfa_enabled", ip, user["id"])
        user = self.store.user_by_id(user["id"])
        self._issue(request, user, SCOPE_FULL, ip, origin, session["role"] or user["role"])

    def _refresh(self, request, ip, origin) -> None:
        refresh = self._read_cookie(request, REFRESH_COOKIE)
        if not refresh:
            self._json(request, 401, {"error": "Sign in again."}, origin)
            return
        new_refresh = new_token()
        row = self.store.rotate_refresh(refresh, new_refresh, int(time.time()) + REFRESH_TTL)
        if not row:
            self.store.audit("refresh_reuse", ip)
            self._json(request, 401, {"error": "Sign in again."}, origin, cookies=self._clear_all())
            return
        access = new_token()
        active = row["role"] if "role" in row.keys() and row["role"] else ""
        self.store.save_access(access, row["id"], row["user_id"], row["scope"], int(time.time()) + ACCESS_TTL, active)
        self._json(
            request,
            200,
            {"ok": True},
            origin,
            cookies=[
                self._cookie(ACCESS_COOKIE, access, ACCESS_TTL, ACCESS_PATH),
                self._cookie(REFRESH_COOKIE, new_refresh, REFRESH_TTL, REFRESH_PATH),
            ],
        )

    def _logout(self, request, ip, origin) -> None:
        session = self._session(request)
        if session:
            self.store.revoke_session_family(session["session_id"])
            self.store.audit("logout", ip, session["user_id"])
        self._json(request, 200, {"ok": True}, origin, cookies=self._clear_all())

    def _desk_session(self, request, origin) -> dict | None:
        """Full operator session opened from this console. ParkPe and PaySwap cannot read the desk."""
        host = request.headers.get("Host", "")
        console = bool(origin) and origin.rstrip("/") == f"http://{host}".rstrip("/")
        session = self._session(request)
        user = self.store.user_by_id(session["user_id"]) if session else None
        role = (session["role"] or user["role"]) if session and user else ""
        if not session or not user or session["scope"] != SCOPE_FULL:
            self._json(request, 401, {"error": "Sign in again."}, origin)
            return None
        if not console or role != ROLE_ADMIN:
            self._json(request, 403, {"error": "Admin session required."}, origin)
            return None
        return user

    def _desk(self, request, origin) -> None:
        """Operator home. Counts and event names only. No tokens, codes, or addresses."""
        user = self._desk_session(request, origin)
        if not user:
            return
        role = ROLE_ADMIN
        self._json(
            request,
            200,
            {
                "email": user["email"],
                "role": role,
                "signup_open": not self.store.operator_exists(),
                "counts": self.store.membership_counts(),
                "events": self.store.recent_audit(8),
            },
            origin,
        )

    def _people(self, request, origin) -> None:
        if not self._desk_session(request, origin):
            return
        self._json(request, 200, {"people": self.store.list_people()}, origin)

    def _sign_in_switch(self, request, body, ip, origin) -> None:
        actor = self._desk_session(request, origin)
        if not actor:
            return
        email = normalize_email(body.get("email"))
        enabled = body.get("enabled")
        user = self.store.user_by_email(email) if email else None
        if not user or not isinstance(enabled, bool):
            self._json(request, 400, {"error": "Check the email and the sign-in switch."}, origin)
            return
        if not enabled and user["id"] == actor["id"]:
            self._json(request, 400, {"error": "You cannot close your own sign-in."}, origin)
            return
        operator = self.store.has_membership(user["id"], ROLE_ADMIN) or user["role"] == ROLE_ADMIN
        if not enabled and operator and user["sign_in"] and self.store.open_operator_count() <= 1:
            self._json(request, 409, {"error": "The last admin stays able to sign in."}, origin)
            return
        self.store.set_sign_in(user["id"], enabled)
        self.store.audit("sign_in_opened" if enabled else "sign_in_closed", ip, user["id"])
        self._json(request, 200, {"ok": True, "email": user["email"], "sign_in": enabled}, origin)

    def _signups(self, request, origin) -> None:
        if not self._desk_session(request, origin):
            return
        self._json(request, 200, {"signups": self.store.recent_signups()}, origin)

    def _processes(self, request, origin) -> None:
        if not self._desk_session(request, origin):
            return
        checks = (
            ("Auth", 4600, True),
            ("ParkPe", 4310, None),
            ("PaySwap", 4500, None),
            ("API", 4610, None),
        )
        processes = []
        for name, port, known in checks:
            up = known if known is not None else self._port_open(port)
            processes.append({"name": name, "port": port, "up": up})
        self._json(request, 200, {"processes": processes}, origin)

    def _port_open(self, port: int) -> bool:
        try:
            with socket.create_connection(("127.0.0.1", port), 0.4):
                return True
        except OSError:
            return False

    def _setup(self, request, origin) -> None:
        """Tells the backend console whether the first operator can still be created."""
        self._json(request, 200, {"signup_open": not self.store.operator_exists()}, origin)

    def _console(self, request, path: str) -> None:
        """Login page for this process. Browser navigation does not send X-Auth-Request."""
        name, content_type = CONSOLE_FILES[path]
        root = CONSOLE_DIR.resolve()
        file_path = (root / name).resolve()
        if not file_path.is_relative_to(root):
            self._send(request, 404, b"Not found.", "")
            return
        try:
            body = file_path.read_bytes()
        except OSError:
            self._send(request, 404, b"Not found.", "")
            return
        self._send(
            request,
            200,
            body,
            "",
            content_type,
            csp="default-src 'self'; style-src 'self' https://fonts.googleapis.com; font-src https://fonts.gstatic.com; script-src 'self'; connect-src 'self' https://fonts.googleapis.com https://fonts.gstatic.com; base-uri 'none'; frame-ancestors 'none'",
        )

    def _me(self, request, origin) -> None:
        session = self._session(request)
        if not session:
            self._json(request, 401, {"error": "Sign in again."}, origin)
            return
        user = self.store.user_by_id(session["user_id"])
        if not user:
            self._json(request, 401, {"error": "Sign in again."}, origin)
            return
        active = session["role"] or user["role"]
        if session["scope"] != SCOPE_FULL:
            self._json(
                request,
                403,
                {"error": "Turn on the authenticator first.", "mfa_setup_required": True, "role": active},
                origin,
            )
            return
        self._json(request, 200, {"email": user["email"], "role": active}, origin)

    def _issue(self, request, user, scope: str, ip: str, origin: str, role: str, setup: bool = False, clear_mfa: bool = False) -> None:
        refresh = new_token()
        access = new_token()
        now = int(time.time())
        session_id = self.store.save_session(user["id"], refresh, scope, now + REFRESH_TTL, role=role)
        self.store.save_access(access, session_id, user["id"], scope, now + ACCESS_TTL, role)
        cookies = [
            self._cookie(ACCESS_COOKIE, access, ACCESS_TTL, ACCESS_PATH),
            self._cookie(REFRESH_COOKIE, refresh, REFRESH_TTL, REFRESH_PATH),
        ]
        if clear_mfa:
            cookies.append(self._clear(MFA_COOKIE, MFA_PATH))
        payload = {"mfa_setup_required": True, "role": role} if setup else {"ok": True, "email": user["email"], "role": role}
        self._json(request, 200, payload, origin, cookies=cookies)

    def _session(self, request):
        token = self._read_cookie(request, ACCESS_COOKIE)
        if not token:
            return None
        return self.store.access_session(token)

    def _require_operator(self, request, origin) -> bool:
        host = request.headers.get("Host", "")
        if not origin or origin.rstrip("/") != f"http://{host}".rstrip("/"):
            self._json(request, 403, {"error": "An admin creates this account."}, origin)
            return False
        session = self._session(request)
        user = self.store.user_by_id(session["user_id"]) if session else None
        role = (session["role"] or user["role"]) if session and user else ""
        if not session or not user or session["scope"] != SCOPE_FULL or role != ROLE_ADMIN:
            self._json(request, 403, {"error": "An admin creates this account."}, origin)
            return False
        return True

    def _add_operator(self, request, body, ip, origin) -> None:
        if not self._require_operator(request, origin):
            return
        email = normalize_email(body.get("email"))
        password = body.get("password")
        if body.get("role") != ROLE_ADMIN or not email:
            self._json(request, 400, {"error": "Check the email and account type."}, origin)
            return
        problem = password_problem(password, email)
        if problem:
            self._json(request, 400, {"error": problem}, origin)
            return
        if self.store.user_by_email(email):
            self._json(request, 409, {"error": "That email already has an account."}, origin)
            return
        if not self.store.create_user(email, password, ROLE_ADMIN):
            self._json(request, 409, {"error": "That email already has an account."}, origin)
            return
        self.store.audit("operator_added", ip)
        self._json(request, 200, {"ok": True, "account_ready": True}, origin)

    def _signup_start(self, request, body, ip, origin) -> None:
        if not self._require_operator(request, origin):
            return
        email = normalize_email(body.get("email"))
        mobile = normalize_mobile(body.get("mobile"))
        role = body.get("role")
        password = body.get("password")
        if not email or not mobile or role not in {ROLE_CUSTOMER, ROLE_RETAILER}:
            self._json(request, 400, {"error": "Check the email, mobile, and account type."}, origin)
            return
        problem = password_problem(password, email)
        if problem:
            self._json(request, 400, {"error": problem}, origin)
            return
        user = self.store.user_by_email(email)
        operator_email = user is not None and (
            self.store.has_membership(user["id"], ROLE_ADMIN) or user["role"] == ROLE_ADMIN
        )
        if operator_email:
            self._json(request, 409, {"error": "An admin email stays an admin account."}, origin)
            return
        if user is not None and self.store.has_membership(user["id"], role):
            self._json(request, 409, {"error": "That person already has this account."}, origin)
            return
        if user is not None and not self.store.check_password(user, password):
            self._json(request, 400, {"error": "Password does not match the existing account."}, origin)
            return
        email_code = f"{secrets.randbelow(1_000_000):06d}"
        sms_code = f"{secrets.randbelow(1_000_000):06d}"
        digest = user["password_hash"] if user is not None else hash_password(password, n=self.store.scrypt_n)
        if not self.verifiers.send_email(email, email_code) or not self.verifiers.send_sms(mobile, sms_code):
            self.store.audit("signup_delivery_failed", ip, user["id"] if user else None)
            self._json(request, 503, {"error": "Verification delivery is not available."}, origin)
            return
        signup_id = str(uuid.uuid4())
        now = int(time.time())
        self.store.save_signup(
            {
                "id": signup_id,
                "email": email,
                "mobile": mobile,
                "role": role,
                "password_hash": digest,
                "user_id": user["id"] if user else None,
                "email_code_hash": token_hash(email_code),
                "sms_code_hash": token_hash(sms_code),
                "live": True,
                "expires_at": now + SIGNUP_TTL,
                "created_at": now,
            }
        )
        self.store.audit("signup_started", ip, user["id"] if user else None)
        self._json(request, 200, {"ok": True, "signup_id": signup_id}, origin)

    def _signup_contact(self, request, body, ip, origin) -> None:
        if not self._require_operator(request, origin):
            return
        intent = self._live_signup(body.get("signup_id"))
        email_code = body.get("email_code") if isinstance(body.get("email_code"), str) else ""
        sms_code = body.get("sms_code") if isinstance(body.get("sms_code"), str) else ""
        if intent is None or token_hash(email_code.strip()) != intent["email_code_hash"] or token_hash(sms_code.strip()) != intent["sms_code_hash"]:
            self.store.audit("signup_rejected", ip)
            self._json(request, 400, {"error": "Verification did not succeed."}, origin)
            return
        self.store.mark_signup(intent["id"], email_ok=1, mobile_ok=1)
        ready = False
        if intent["role"] == ROLE_CUSTOMER:
            ready = self._open_verified_account(intent)
        self.store.audit("signup_contact_ok", ip, intent["user_id"])
        self._json(request, 200, {"ok": True, "account_ready": ready}, origin)

    def _signup_aadhaar(self, request, body, ip, origin) -> None:
        if not self._require_operator(request, origin):
            return
        intent = self._live_signup(body.get("signup_id"))
        if intent is None or intent["role"] != ROLE_RETAILER or not intent["email_ok"] or not intent["mobile_ok"]:
            self._json(request, 400, {"error": "Verification did not succeed."}, origin)
            return
        verification_id = "pp" + intent["id"].replace("-", "")
        url = self.verifiers.digilocker_link(verification_id)
        if not url:
            self.store.audit("signup_rejected", ip, intent["user_id"])
            self._json(request, 400, {"error": "Verification did not succeed."}, origin)
            return
        self.store.mark_signup(intent["id"], aadhaar_ref=verification_id, aadhaar_ok=0)
        self._json(request, 200, {"ok": True, "url": url}, origin)

    def _signup_aadhaar_confirm(self, request, body, ip, origin) -> None:
        if not self._require_operator(request, origin):
            return
        intent = self._live_signup(body.get("signup_id"))
        if intent is None or not intent["aadhaar_ref"] or not self.verifiers.digilocker_ok(intent["aadhaar_ref"]):
            self.store.audit("signup_rejected", ip)
            self._json(request, 400, {"error": "Verification did not succeed."}, origin)
            return
        self.store.mark_signup(intent["id"], aadhaar_ok=1)
        self._json(request, 200, {"ok": True}, origin)

    def _signup_pan(self, request, body, ip, origin) -> None:
        if not self._require_operator(request, origin):
            return
        intent = self._live_signup(body.get("signup_id"))
        pan = normalize_pan(body.get("pan"))
        name = body.get("name") if isinstance(body.get("name"), str) else ""
        name = " ".join(name.split())
        if intent is None or intent["role"] != ROLE_RETAILER or not intent["aadhaar_ok"] or not pan or len(name) < 2:
            self._json(request, 400, {"error": "Verification did not succeed."}, origin)
            return
        if not self.verifiers.pan_check(pan, name):
            self.store.audit("signup_rejected", ip, intent["user_id"])
            self._json(request, 400, {"error": "Verification did not succeed."}, origin)
            return
        self.store.mark_signup(intent["id"], pan_ok=1)
        ready = self._open_verified_account(intent)
        self._json(request, 200, {"ok": True, "account_ready": ready}, origin)

    def _live_signup(self, signup_id: object):
        if not isinstance(signup_id, str) or not signup_id:
            return None
        intent = self.store.signup(signup_id)
        if intent is None or not intent["live"]:
            return None
        return intent

    def _open_verified_account(self, intent) -> bool:
        if intent["user_id"]:
            self.store.add_membership(intent["user_id"], intent["role"])
        elif not self.store.create_user_with_hash(intent["email"], intent["password_hash"], intent["role"]):
            return False
        self.store.delete_signup(intent["id"])
        self.store.audit("signup_account", "", intent["user_id"])
        return True

    def _cookie(self, name: str, value: str, max_age: int, path: str) -> str:
        parts = [
            f"{name}={value}",
            f"Path={path}",
            "HttpOnly",
            f"SameSite={self.samesite}",
            f"Max-Age={max_age}",
        ]
        if self.cookie_secure:
            parts.append("Secure")
        return "; ".join(parts)

    def _clear(self, name: str, path: str) -> str:
        parts = [f"{name}=", f"Path={path}", "HttpOnly", f"SameSite={self.samesite}", "Max-Age=0"]
        if self.cookie_secure:
            parts.append("Secure")
        return "; ".join(parts)

    def _clear_all(self) -> list[str]:
        return [
            self._clear(ACCESS_COOKIE, ACCESS_PATH),
            self._clear(REFRESH_COOKIE, REFRESH_PATH),
            self._clear(MFA_COOKIE, MFA_PATH),
        ]

    def _read_cookie(self, request, name: str) -> str:
        header = request.headers.get("Cookie", "")
        for part in header.split(";"):
            if "=" not in part:
                continue
            key, value = part.strip().split("=", 1)
            if key == name:
                return value
        return ""

    def _json(self, request, status: int, payload: dict, origin: str, cookies: list[str] | None = None) -> None:
        raw = json.dumps(payload).encode("utf-8")
        self._send(request, status, raw, origin, "application/json; charset=utf-8", cookies or [])

    def _send(
        self,
        request,
        status: int,
        body: bytes,
        origin: str,
        content_type: str = "text/plain",
        cookies: list[str] | None = None,
        csp: str = "default-src 'none'",
    ) -> None:
        request.send_response(status)
        request.send_header("Content-Type", content_type)
        request.send_header("Content-Length", str(len(body)))
        request.send_header("Cache-Control", "no-store")
        request.send_header("X-Content-Type-Options", "nosniff")
        request.send_header("Referrer-Policy", "no-referrer")
        request.send_header("X-Frame-Options", "DENY")
        request.send_header("Content-Security-Policy", csp)
        clean_origin = origin.rstrip("/")
        if clean_origin in self.origins:
            request.send_header("Access-Control-Allow-Origin", clean_origin)
            request.send_header("Access-Control-Allow-Credentials", "true")
            request.send_header("Access-Control-Allow-Headers", f"Content-Type, {HEADER}")
            request.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            request.send_header("Vary", "Origin")
        for cookie in cookies or []:
            request.send_header("Set-Cookie", cookie)
        request.end_headers()
        if body:
            request.wfile.write(body)


def build_handler(app: AuthApp):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self):
            app.handle(self)

        def do_POST(self):
            app.handle(self)

        def do_OPTIONS(self):
            app.handle(self)

        def log_message(self, fmt: str, *args) -> None:
            return

    return Handler


CONSOLE_DIR = Path(__file__).resolve().parent / "console"
CONSOLE_FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/login": ("index.html", "text/html; charset=utf-8"),
    "/console.css": ("console.css", "text/css; charset=utf-8"),
    "/qr.js": ("qr.js", "text/javascript; charset=utf-8"),
    "/console.js": ("console.js", "text/javascript; charset=utf-8"),
}


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    data_dir = Path(os.environ.get("AUTH_DATA_DIR", root / "data"))
    origins = _split_csv(
        os.environ.get(
            "AUTH_ORIGINS",
            "http://127.0.0.1:4500,http://127.0.0.1:4310,http://localhost:4500,http://localhost:4310",
        )
    )
    host = os.environ.get("AUTH_HOST", "127.0.0.1")
    port = int(os.environ.get("AUTH_PORT", "4600"))
    origins.add(f"http://{host}:{port}")
    if host in {"127.0.0.1", "localhost"}:
        origins.add(f"http://127.0.0.1:{port}")
        origins.add(f"http://localhost:{port}")
    app = AuthApp(
        data_dir=data_dir,
        origins=origins,
        scrypt_n=int(os.environ.get("AUTH_SCRYPT_N", "32768")),
        cookie_secure=os.environ.get("AUTH_COOKIE_SECURE", "0") == "1",
        samesite=os.environ.get("AUTH_COOKIE_SAMESITE", "Lax"),
    )
    server = ThreadingHTTPServer((host, port), build_handler(app))
    print(f"Auth http://{host}:{port}/", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()
        app.close()


if __name__ == "__main__":
    main()
