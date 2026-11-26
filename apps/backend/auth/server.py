"""HTTP adapter for the auth contract in auth.contract.

Payswap calls these routes through apps/payswap/js/session.js. A missing or reused
refresh cookie revokes that login family. Unexpected exceptions stay as a
generic 500 so stack traces never reach either frontend.
"""

from __future__ import annotations

import hmac
import json
import os
import re
import secrets
import socket
import time
import urllib.error
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlencode, urlparse

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
    MAX_FAILS,
    REFRESH_TTL,
    hash_password,
    new_token,
    new_totp_secret,
    normalize_email,
    password_problem,
    token_hash,
    totp_step,
    verify_password,
)
from auth.store import Store
from core.actions import set_action_sink
from auth.verify import (
    SIGNUP_INTENT_EXPIRES,
    LiveVerify,
    cashfree_configured,
    mail_configured,
    mask_digilocker_ref,
    mask_pan,
    mask_pan_name,
    normalize_mobile,
    normalize_pan,
)
from integrations import bbps as bbps_integration
from integrations import kaleyra
from integrations import pg as pg_integration

def _split_csv(value: str) -> set[str]:
    return {item.strip().rstrip("/") for item in value.split(",") if item.strip()}


# console.js quotes this sentence from the log reader. No code, address, or provider body.
_AUDIT_WHY = {
    "login_failed": "The email or password did not match.",
    "mfa_failed": "The authenticator code did not match.",
    "mfa_challenge": "The password matched. The desk is waiting for the authenticator code.",
    "mfa_setup": "Authenticator setup started.",
    "mfa_enabled": "The authenticator was turned on.",
    "login_enroll": "The password matched. The authenticator is not on yet.",
    "login": "Signed in.",
    "logout": "Signed out.",
    "sign_in_closed": "Sign-in is closed for this account.",
    "sign_in_opened": "Sign-in was opened for this account.",
    "register": "The admin account was created.",
    "register_existing": "That email already had an account.",
    "register_operator_closed": "Admin signup is closed.",
    "operator_added": "An admin account was added.",
    "role_removed": "A role was removed from this account.",
    "password_reset": "The password was changed.",
    "authenticator_reset": "The authenticator was turned off.",
    "refresh_reuse": "A refresh token was used twice, so that login was revoked.",
    "server_error": "The auth server hit an internal error.",
    "signup_started": "The codes were accepted by email and SMS. The account is still not created.",
    "signup_resent": "New email and SMS codes were sent.",
    "signup_delivery_failed": "Email or SMS did not send, so no code was stored and the account was not created. Open the API log from the same minute to see which service failed.",
    "signup_rejected": "A verification step did not succeed. The account was not created.",
    "signup_contact_ok": "The email code and the SMS code matched.",
    "signup_cancelled": "This signup was cancelled before the account was created.",
    "signup_account": "The account was created after verification.",
}
_FAILED_AUDIT = {
    "login_failed",
    "mfa_failed",
    "sign_in_closed",
    "register_operator_closed",
    "signup_rejected",
    "signup_delivery_failed",
    "refresh_reuse",
    "server_error",
}
_API_SERVICES = (
    ("integration.kaleyra", "Kaleyra"),
    ("integration.mail", "Email"),
    ("integration.cashfree", "Cashfree"),
    ("integration.parking", "Parking"),
    ("integration.bbps", "BBPS"),
    ("domain.payswap.bbps", "BBPS"),
    ("payswap.bbps", "BBPS"),
    ("domain.parkpe", "ParkPe"),
    ("parkpe.", "ParkPe"),
    ("domain.payswap", "PaySwap"),
    ("payswap.", "PaySwap"),
    ("idempotency.", "Idempotency"),
)


def _api_service(action: str) -> str:
    for prefix, name in _API_SERVICES:
        if action.startswith(prefix):
            return name
    return "API"


def _api_why(outcome: str, reason: str) -> str:
    if reason:
        return reason
    if outcome == "error":
        return "The call failed."
    return "Completed."


class AuthApp:
    def __init__(self, data_dir: Path, origins: set[str], scrypt_n: int, cookie_secure: bool, samesite: str, verifiers=None):
        self.origins = origins
        self.cookie_secure = cookie_secure
        self.samesite = samesite
        self.verifiers = verifiers or LiveVerify()
        self.store = Store(data_dir / "auth.sqlite", scrypt_n)
        set_action_sink(self.store.remember_service)

    def close(self) -> None:
        set_action_sink(None)
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
            try:
                length = int(request.headers.get("Content-Length", "0") or 0)
            except ValueError:
                length = -1
            if length < 0 or length > BODY_MAX:
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
            elif method == "POST" and path == Paths.SIGNUP_AADHAAR_STATUS:
                self._signup_aadhaar_status(request, body, ip, origin)
            elif method == "POST" and path == Paths.SIGNUP_AADHAAR_CONFIRM:
                self._signup_aadhaar_confirm(request, body, ip, origin)
            elif method == "POST" and path == Paths.SIGNUP_PAN:
                self._signup_pan(request, body, ip, origin)
            elif method == "POST" and path == Paths.SIGNUP_CANCEL:
                self._signup_cancel(request, body, ip, origin)
            elif method == "POST" and path == Paths.SIGNUP_RESEND:
                self._signup_resend(request, body, ip, origin)
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
            elif method == "GET" and path == Paths.PROFILE:
                self._self_profile_get(request, origin)
            elif method == "POST" and path == Paths.PROFILE:
                self._self_profile_post(request, body, ip, origin)
            elif method == "POST" and path == Paths.PASSWORD_CHANGE:
                self._self_password_change(request, body, ip, origin)
            elif method == "GET" and path == Paths.SELF_SESSIONS:
                self._self_sessions_get(request, origin)
            elif method == "POST" and path == Paths.SELF_SESSIONS_REVOKE:
                self._self_sessions_revoke(request, ip, origin)
            elif method == "GET" and path == Paths.DESK:
                self._desk(request, origin)
            elif method == "GET" and path == Paths.DESK_OVERVIEW:
                self._hub(request, origin, "GET", "/api/v1/desk/overview")
            elif method == "GET" and path == Paths.DESK_PEOPLE:
                self._people(request, origin)
            elif method == "GET" and path == Paths.DESK_USER_FILE:
                self._user_file(request, origin)
            elif method == "POST" and path == Paths.DESK_VERIFICATION_RECORD:
                self._verification_record(request, body, ip, origin)
            elif method == "POST" and path == Paths.DESK_SIGN_IN:
                self._sign_in_switch(request, body, ip, origin)
            elif method == "POST" and path == Paths.DESK_ROLE:
                self._role_remove(request, body, ip, origin)
            elif method == "POST" and path == Paths.DESK_PASSWORD:
                self._password_reset(request, body, ip, origin)
            elif method == "POST" and path == Paths.DESK_AUTHENTICATOR:
                self._authenticator_reset(request, body, ip, origin)
            elif method == "GET" and path == Paths.DESK_SESSIONS:
                self._open_sessions(request, origin)
            elif method == "GET" and path == Paths.DESK_SIGNUPS:
                self._signups(request, origin)
            elif method == "GET" and path == Paths.DESK_PROCESSES:
                self._processes(request, origin)
            elif method == "GET" and path == Paths.DESK_SERVICES:
                self._services(request, origin)
            elif method == "GET" and path == Paths.DESK_PARKPE:
                self._hub(request, origin, "GET", "/api/v1/desk/parkpe/sessions")
            elif method == "GET" and path == Paths.DESK_PAYSWAP:
                self._hub(request, origin, "GET", "/api/v1/desk/payswap/orders")
            elif method == "GET" and path == Paths.DESK_ENTITLEMENTS_DEFAULT:
                self._hub(request, origin, "GET", "/api/v1/desk/entitlements/default")
            elif method == "POST" and path == Paths.DESK_ENTITLEMENTS_DEFAULT:
                self._hub(request, origin, "POST", "/api/v1/desk/entitlements/default", body)
            elif method == "GET" and path == Paths.DESK_ENTITLEMENTS_RETAILER:
                self._hub(request, origin, "GET", "/api/v1/desk/entitlements/retailer")
            elif method == "POST" and path == Paths.DESK_ENTITLEMENTS_RETAILER:
                self._hub(request, origin, "POST", "/api/v1/desk/entitlements/retailer", body)
            elif method == "GET" and path == Paths.DESK_WALLETS:
                self._hub(request, origin, "GET", "/api/v1/desk/wallets")
            elif method == "POST" and path == Paths.DESK_WALLETS_TOPUP_REVIEW:
                self._hub(request, origin, "POST", "/api/v1/desk/wallets/topup-review", body)
            elif method == "POST" and path == Paths.DESK_WALLETS_ADJUST:
                self._hub(request, origin, "POST", "/api/v1/desk/wallets/adjust", body)
            elif method == "POST" and path == Paths.DESK_WALLETS_CONTROLS:
                self._hub(request, origin, "POST", "/api/v1/desk/wallets/controls", body)
            elif method == "GET" and path == Paths.DESK_TRANSACTIONS:
                self._hub(request, origin, "GET", "/api/v1/desk/transactions")
            elif method == "POST" and path == Paths.DESK_TRANSACTIONS_BBPS_SYNC:
                self._hub(request, origin, "POST", "/api/v1/desk/transactions/bbps-sync", body)
            elif method == "GET" and path == Paths.DESK_COMMISSION_POLICY:
                self._hub(request, origin, "GET", "/api/v1/desk/commission/policy")
            elif method == "POST" and path == Paths.DESK_COMMISSION_POLICY:
                self._hub(request, origin, "POST", "/api/v1/desk/commission/policy", body)
            elif method == "GET" and path == Paths.DESK_COMMISSION_RATES:
                self._hub(request, origin, "GET", "/api/v1/desk/commission/rates")
            elif method == "POST" and path == Paths.DESK_COMMISSION_RATES:
                self._hub(request, origin, "POST", "/api/v1/desk/commission/rates", body)
            elif method == "POST" and path == Paths.DESK_COMMISSION_RATES_IMPORT:
                self._hub(request, origin, "POST", "/api/v1/desk/commission/rates/import", body)
            elif method == "GET" and path == Paths.DESK_COMMISSION_RETAILER:
                self._hub(request, origin, "GET", "/api/v1/desk/commission/retailer")
            elif method == "POST" and path == Paths.DESK_COMMISSION_RETAILER:
                self._hub(request, origin, "POST", "/api/v1/desk/commission/retailer", body)
            elif method == "GET" and path == Paths.DESK_COMMISSION_REVENUE:
                self._hub(request, origin, "GET", "/api/v1/desk/commission/revenue")
            elif method == "GET" and path == Paths.DESK_COMMISSION_TDS:
                self._hub(request, origin, "GET", "/api/v1/desk/commission/tds")
            elif method == "POST" and path == Paths.DESK_COMMISSION_TDS:
                self._hub(request, origin, "POST", "/api/v1/desk/commission/tds", body)
            elif method == "GET" and path == Paths.DESK_COMMISSION_TDS_CERTIFICATE:
                self._hub(request, origin, "GET", "/api/v1/desk/commission/tds/certificate")
            elif method == "POST" and path == Paths.DESK_COMMISSION_TDS_CERTIFICATE:
                self._hub(request, origin, "POST", "/api/v1/desk/commission/tds/certificate", body)
            elif method == "GET" and path == Paths.DESK_COMMISSION_INVOICES:
                self._hub(request, origin, "GET", "/api/v1/desk/commission/invoices")
            elif method == "POST" and path == Paths.DESK_COMMISSION_INVOICES:
                self._hub(request, origin, "POST", "/api/v1/desk/commission/invoices", body)
            elif method == "GET" and path == Paths.DESK_LOGS:
                self._logs(request, origin)
            elif method == "POST" and path == Paths.DESK_PARKPE_CLOSE:
                self._hub(request, origin, "POST", "/api/v1/desk/parkpe/sessions/close", body)
            elif method == "POST" and path == Paths.DESK_ACCOUNTS:
                self._add_operator(request, body, ip, origin)
            elif method == "GET" and path == Paths.SETUP:
                self._setup(request, origin)
            else:
                self._json(request, 404, {"error": "Not found."}, origin)
        except Exception:
            self.store.audit(
                "server_error",
                request.client_address[0],
                request=f"{request.command} {urlparse(request.path).path}",
                response='HTTP 500\n{"error":"Something went wrong."}',
            )
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
            self.store.audit(
                "register_operator_closed",
                ip,
                request=f"POST {Paths.REGISTER}\n{json.dumps({'email': email, 'role': role})}",
                response='HTTP 403\n{"error":"Admin signup is closed."}',
            )
            self._json(request, 403, {"error": "Admin signup is closed."}, origin)
            return
        problem = password_problem(password, email)
        if problem:
            self._json(request, 400, {"error": problem}, origin)
            return
        if self.store.ip_blocked(ip):
            self._json(request, 200, {"ok": True}, origin)
            return
        created = self.store.create_user(email, password, role, close_admin_signup=True)
        if role == ROLE_ADMIN and not created and self.store.operator_exists():
            self.store.audit(
                "register_operator_closed",
                ip,
                request=f"POST {Paths.REGISTER}\n{json.dumps({'email': email, 'role': role})}",
                response='HTTP 403\n{"error":"Admin signup is closed."}',
            )
            self._json(request, 403, {"error": "Admin signup is closed."}, origin)
            return
        self.store.audit(
            "register" if created else "register_existing",
            ip,
            request=f"POST {Paths.REGISTER}\n{json.dumps({'email': email, 'role': role})}",
            response='HTTP 200\n{"ok":true}',
        )
        self._json(request, 200, {"ok": True}, origin)

    def _login(self, request, body, ip, origin) -> None:
        email = normalize_email(body.get("email")) or ""
        password = body.get("password") if isinstance(body.get("password"), str) else ""
        role = body.get("role")
        login_req = f"POST {Paths.LOGIN}\n{json.dumps({'email': email, 'role': role})}"
        if self.store.ip_blocked(ip) or role not in ROLES or not email:
            self.store.note_attempt(ip, email, False)
            self._json(request, 401, {"error": LOGIN_ERROR}, origin)
            return
        user = self.store.user_by_email_role(email, role)
        member = user is not None and self.store.has_membership(user["id"], role)
        blocked = self.store.locked(user) or user is None or not member
        password_ok = self.store.check_password(None if blocked else user, password)
        if not password_ok or blocked or user is None:
            if user is not None and not blocked and member:
                self.store.register_failure(user)
            self.store.note_attempt(ip, email, False)
            self.store.audit(
                "login_failed",
                ip,
                user["id"] if user else None,
                request=login_req,
                response=f"HTTP 401\n{json.dumps({'error': LOGIN_ERROR})}",
            )
            self._json(request, 401, {"error": LOGIN_ERROR}, origin)
            return
        self.store.clear_failures(user["id"])
        self.store.note_attempt(ip, email, True)
        if not user["sign_in"]:
            self.store.audit(
                "sign_in_closed",
                ip,
                user["id"],
                request=login_req,
                response=f"HTTP 401\n{json.dumps({'error': LOGIN_ERROR})}",
            )
            self._json(request, 401, {"error": LOGIN_ERROR}, origin)
            return
        if user["mfa_enabled"]:
            challenge = new_token()
            device_key = self._device_key(body)
            self.store.save_challenge(
                challenge, user["id"], int(time.time()) + CHALLENGE_TTL, role, device_key=device_key
            )
            self.store.audit(
                "mfa_challenge",
                ip,
                user["id"],
                request=login_req,
                response='HTTP 200\n{"mfa_required":true}',
            )
            self._json(
                request,
                200,
                {"mfa_required": True},
                origin,
                cookies=[self._cookie(MFA_COOKIE, challenge, CHALLENGE_TTL, MFA_PATH)],
            )
            return
        self.store.audit(
            "login_enroll",
            ip,
            user["id"],
            request=login_req,
            response=f"HTTP 200\n{json.dumps({'mfa_setup_required': True, 'role': role})}",
        )
        self._issue(request, user, SCOPE_ENROLL, ip, origin, role, setup=True, device_key=self._device_key(body))

    def _mfa(self, request, body, ip, origin) -> None:
        challenge = self._read_cookie(request, MFA_COOKIE)
        row = self.store.peek_challenge(challenge) if challenge else None
        code = body.get("code") if isinstance(body.get("code"), str) else ""
        user = self.store.user_by_id(row["user_id"]) if row else None
        mfa_req = f"POST {Paths.MFA}\n{json.dumps({'email': user['email'] if user else ''})}"
        if user and not user["sign_in"]:
            self.store.audit(
                "sign_in_closed",
                ip,
                user["id"],
                request=mfa_req,
                response='HTTP 401\n{"error":"Code is incorrect."}',
            )
            self._json(request, 401, {"error": "Code is incorrect."}, origin, cookies=[self._clear(MFA_COOKIE, MFA_PATH)])
            return
        if not user or not user["mfa_enabled"]:
            self._json(request, 401, {"error": "Code is incorrect."}, origin, cookies=[self._clear(MFA_COOKIE, MFA_PATH)])
            return
        ok = self._accept_totp(user, code) or self.store.use_backup(user["id"], code)
        if not ok:
            count = self.store.register_failure(user)
            self.store.audit(
                "mfa_failed",
                ip,
                user["id"],
                request=mfa_req,
                response='HTTP 401\n{"error":"Code is incorrect."}',
            )
            cookies = None
            if count >= MAX_FAILS:
                self.store.use_challenge(challenge)
                cookies = [self._clear(MFA_COOKIE, MFA_PATH)]
            self._json(request, 401, {"error": "Code is incorrect."}, origin, cookies=cookies)
            return
        self.store.use_challenge(challenge)
        active = row["role"] or user["role"]
        device_key = self._device_key(body) or (
            row["device_key"] if "device_key" in row.keys() and row["device_key"] else ""
        )
        self.store.audit(
            "login",
            ip,
            user["id"],
            request=mfa_req,
            response=f"HTTP 200\n{json.dumps({'ok': True, 'email': user['email'], 'role': active})}",
        )
        # Full MFA login continues this device's family; other devices stay until revoke/timeout.
        self._issue(
            request,
            user,
            SCOPE_FULL,
            ip,
            origin,
            active,
            clear_mfa=True,
            device_key=device_key,
        )

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
        self.store.audit(
            "mfa_setup",
            ip,
            user["id"],
            request=f"POST {Paths.MFA_SETUP}\n{json.dumps({'email': user['email']})}",
            response='HTTP 200\n{"secret":"[redacted]","backup_codes":"[redacted]"}',
        )
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
        if not user or not user["mfa_secret"] or not self._accept_totp(user, code):
            self._json(request, 401, {"error": "Code is incorrect."}, origin)
            return
        self.store.enable_mfa(user["id"])
        self.store.revoke_user(user["id"])
        active = session["role"] or user["role"]
        self.store.audit(
            "mfa_enabled",
            ip,
            user["id"],
            request=f"POST {Paths.MFA_CONFIRM}\n{json.dumps({'email': user['email']})}",
            response=f"HTTP 200\n{json.dumps({'ok': True, 'email': user['email'], 'role': active})}",
        )
        user = self.store.user_by_id(user["id"])
        self._issue(
            request,
            user,
            SCOPE_FULL,
            ip,
            origin,
            active,
            device_key=self._device_key(body),
        )

    def _refresh(self, request, ip, origin) -> None:
        refresh = self._read_cookie(request, REFRESH_COOKIE)
        if not refresh:
            self._json(request, 401, {"error": "Sign in again."}, origin)
            return
        new_refresh = new_token()
        row = self.store.rotate_refresh(refresh, new_refresh, int(time.time()) + REFRESH_TTL)
        if not row:
            self.store.audit(
                "refresh_reuse",
                ip,
                request=f"POST {Paths.REFRESH}",
                response='HTTP 401\n{"error":"Sign in again."}',
            )
            self._json(request, 401, {"error": "Sign in again."}, origin, cookies=self._clear_all())
            return
        access = new_token()
        active = row["role"] if "role" in row.keys() and row["role"] else ""
        holder = self.store.user_by_id(row["user_id"])
        if (
            not holder
            or not holder["sign_in"]
            or not active
            or not self.store.has_membership(row["user_id"], active)
        ):
            self.store.revoke_session_family(row["id"])
            self._json(request, 401, {"error": "Sign in again."}, origin, cookies=self._clear_all())
            return
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
            self.store.audit(
                "logout",
                ip,
                session["user_id"],
                request=f"POST {Paths.LOGOUT}",
                response='HTTP 200\n{"ok":true}',
            )
        self._json(request, 200, {"ok": True}, origin, cookies=self._clear_all())

    def _desk_session(self, request, origin) -> dict | None:
        """Full admin session on this console. ParkPe and PaySwap cannot read the desk.

        A same-origin GET from console.js does not send Origin. A cross-origin
        call from 4310 or 4500 does, and that Origin is refused.
        """
        host = request.headers.get("Host", "")
        console_origin = f"http://{host}".rstrip("/")
        if origin:
            console = origin.rstrip("/") == console_origin
        else:
            console = request.command == "GET"
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
                "super": bool(user["is_super"]),
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

    def _desk_person(self, body: dict | None, query: dict | None):
        data = body or {}
        q = query or {}
        user_id = data.get("user_id") or (q.get("user_id") or [""])[0]
        if isinstance(user_id, str) and user_id:
            return self.store.user_by_id(user_id)
        email = normalize_email(data.get("email") or (q.get("email") or [""])[0])
        role = data.get("role") or (q.get("role") or [""])[0]
        if email and role in ROLES:
            return self.store.user_by_email_role(email, role)
        if email:
            return self.store.user_by_email(email)
        return None

    def _signup_field(self, row, key: str) -> str:
        if row is None:
            return ""
        try:
            value = row[key]
        except (KeyError, IndexError):
            return ""
        return value if isinstance(value, str) else ""

    def _verification_record(self, request, body, ip, origin) -> None:
        if not self._require_operator(request, origin):
            return
        user = self._desk_person(body, None)
        role = body.get("role") if isinstance(body.get("role"), str) else ""
        if not user or role not in {ROLE_CUSTOMER, ROLE_RETAILER}:
            self._json(request, 400, {"error": "Check the account and role."}, origin)
            return
        pan_mask = ""
        pan = normalize_pan(body.get("pan"))
        if pan:
            pan_mask = mask_pan(pan)
        elif isinstance(body.get("pan_mask"), str):
            pan_mask = body["pan_mask"].strip()[:20]
        pan_name = body.get("pan_name") if isinstance(body.get("pan_name"), str) else ""
        pan_name_hint = mask_pan_name(pan_name) if pan_name.strip() else ""
        pan_registered = body.get("pan_registered_name") if isinstance(body.get("pan_registered_name"), str) else ""
        mobile = normalize_mobile(body.get("mobile")) or ""
        digi = body.get("digilocker_ref") if isinstance(body.get("digilocker_ref"), str) else ""
        digi = digi or (body.get("digilocker_verification_id") if isinstance(body.get("digilocker_verification_id"), str) else "")
        digilocker_ref = mask_digilocker_ref(digi) if digi.strip() else ""
        if not pan_mask and not digilocker_ref and not pan_name_hint and not mobile and not pan and not pan_name:
            self._json(request, 400, {"error": "Send KYC fields to store for this account."}, origin)
            return
        if not self.store.patch_profile_verification(
            user["id"],
            role,
            pan_mask=pan_mask,
            digilocker_ref=digilocker_ref,
            pan_name_hint=pan_name_hint,
            mobile=mobile,
            pan=pan or "",
            pan_name=pan_name,
            pan_registered_name=pan_registered,
            digilocker_verification_id=digi.strip(),
        ):
            self._json(request, 400, {"error": "No profile row for this account."}, origin)
            return
        self.store.audit(
            "verification_record_saved",
            ip,
            user["id"],
            request=f"POST /api/auth/desk/user/verify\n{json.dumps({'email': user['email'], 'role': role})}",
            response='HTTP 200\n{"ok":true}',
        )
        self._json(request, 200, {"ok": True}, origin)

    def _user_file(self, request, origin) -> None:
        """One person on the Users screen. Mobile is the last four digits."""
        if not self._desk_session(request, origin):
            return
        query = parse_qs(urlparse(request.path).query)
        user = self._desk_person(None, query)
        if not user:
            self._json(request, 400, {"error": "Check the email."}, origin)
            return
        self._json(
            request,
            200,
            {
                "email": user["email"],
                "roles": self.store.roles_for(user["id"]),
                "authenticator": bool(user["mfa_enabled"]),
                "sign_in": bool(user["sign_in"]),
                "created_at": int(user["created_at"]),
                "super": bool(user["is_super"]),
                "profiles": self.store.profiles_for(user["id"]),
                "sessions": self.store.open_sessions(user["id"]),
            },
            origin,
        )

    def _sign_in_switch(self, request, body, ip, origin) -> None:
        actor = self._desk_session(request, origin)
        if not actor:
            return
        enabled = body.get("enabled")
        user = self._desk_person(body, None)
        if not user or not isinstance(enabled, bool):
            self._json(request, 400, {"error": "Check the email and the sign-in switch."}, origin)
            return
        if not enabled and user["id"] == actor["id"]:
            self._json(request, 400, {"error": "You cannot close your own sign-in."}, origin)
            return
        operator = self.store.has_membership(user["id"], ROLE_ADMIN) or user["role"] == ROLE_ADMIN
        if operator and user["id"] != actor["id"] and not actor["is_super"]:
            self._json(request, 403, {"error": "Only the super admin can change an admin."}, origin)
            return
        if not enabled and operator and user["sign_in"] and self.store.open_operator_count() <= 1:
            self._json(request, 409, {"error": "The last admin stays able to sign in."}, origin)
            return
        self.store.set_sign_in(user["id"], enabled)
        self.store.audit(
            "sign_in_opened" if enabled else "sign_in_closed",
            ip,
            user["id"],
            request=f"POST /api/auth/desk/sign-in\n{json.dumps({'email': user['email'], 'sign_in': enabled})}",
            response=f"HTTP 200\n{json.dumps({'ok': True, 'email': user['email'], 'sign_in': enabled})}",
        )
        self._json(request, 200, {"ok": True, "email": user["email"], "sign_in": enabled}, origin)

    def _role_remove(self, request, body, ip, origin) -> None:
        actor = self._desk_session(request, origin)
        if not actor:
            return
        role = body.get("role")
        email = normalize_email(body.get("email"))
        user = None
        if email and role in ROLES:
            user = self.store.user_by_email_role(email, role)
        if user is None:
            user = self._desk_person(body, None)
        if not user or role not in ROLES or not self.store.has_membership(user["id"], role):
            self._json(request, 400, {"error": "That person does not have this account."}, origin)
            return
        if role == ROLE_ADMIN and user["id"] == actor["id"]:
            self._json(request, 400, {"error": "You cannot remove your own admin role."}, origin)
            return
        if role == ROLE_ADMIN and not actor["is_super"]:
            self._json(request, 403, {"error": "Only the super admin can change an admin."}, origin)
            return
        if role == ROLE_ADMIN and user["sign_in"] and self.store.open_operator_count() <= 1:
            self._json(request, 409, {"error": "The last admin stays able to sign in."}, origin)
            return
        self.store.remove_membership(user["id"], role)
        self.store.audit(
            "role_removed",
            ip,
            user["id"],
            request=f"POST /api/auth/desk/role/remove\n{json.dumps({'email': user['email'], 'role': role})}",
            response=f"HTTP 200\n{json.dumps({'ok': True, 'email': user['email'], 'role': role})}",
        )
        self._json(request, 200, {"ok": True, "email": user["email"], "role": role}, origin)

    def _password_reset(self, request, body, ip, origin) -> None:
        actor = self._desk_session(request, origin)
        if not actor:
            return
        user = self._desk_person(body, None)
        password = body.get("password")
        if not user:
            self._json(request, 400, {"error": "Check the email."}, origin)
            return
        if self._admin_target_forbidden(request, actor, user, origin):
            return
        problem = password_problem(password, user["email"])
        if problem:
            self._json(request, 400, {"error": problem}, origin)
            return
        self.store.set_password_hash(user["id"], hash_password(password, n=self.store.scrypt_n))
        if user["id"] != actor["id"]:
            self.store.revoke_user(user["id"])
        self.store.audit(
            "password_reset",
            ip,
            user["id"],
            request=f"POST /api/auth/desk/password/reset\n{json.dumps({'email': user['email']})}",
            response=f"HTTP 200\n{json.dumps({'ok': True, 'email': user['email']})}",
        )
        self._json(request, 200, {"ok": True, "email": user["email"]}, origin)

    def _authenticator_reset(self, request, body, ip, origin) -> None:
        actor = self._desk_session(request, origin)
        if not actor:
            return
        user = self._desk_person(body, None)
        if not user:
            self._json(request, 400, {"error": "Check the email."}, origin)
            return
        if self._admin_target_forbidden(request, actor, user, origin):
            return
        self.store.clear_mfa(user["id"])
        self.store.revoke_user(user["id"])
        self.store.audit(
            "authenticator_reset",
            ip,
            user["id"],
            request=f"POST /api/auth/desk/mfa/reset\n{json.dumps({'email': user['email']})}",
            response=f"HTTP 200\n{json.dumps({'ok': True, 'email': user['email']})}",
        )
        self._json(
            request,
            200,
            {"ok": True, "email": user["email"], "self": user["id"] == actor["id"]},
            origin,
        )

    def _open_sessions(self, request, origin) -> None:
        if not self._desk_session(request, origin):
            return
        query = parse_qs(urlparse(request.path).query)
        user = self._desk_person(None, query)
        if not user:
            self._json(request, 400, {"error": "Check the email."}, origin)
            return
        self._json(request, 200, {"email": user["email"], "sessions": self.store.open_sessions(user["id"])}, origin)

    def _signups(self, request, origin) -> None:
        if not self._desk_session(request, origin):
            return
        pending = self.store.recent_signups()
        verified = self.store.recent_verified_accounts()
        if not verified:
            verified = self._verified_from_people()
        self._json(
            request,
            200,
            {
                "pending": pending,
                "verified": verified,
                "signups": pending,
            },
            origin,
        )

    def _verified_from_people(self) -> list[dict]:
        """Same accounts as the Users directory when the desk list helper is empty."""
        rows = []
        for person in self.store.list_people():
            profiles = {row["role"]: row for row in self.store.profiles_for(person["id"])}
            for role in person.get("roles") or []:
                if role not in {"customer", "retailer"}:
                    continue
                profile = profiles.get(role)
                if profile:
                    email_ok = bool(profile["email_ok"])
                    mobile_ok = bool(profile["mobile_ok"])
                    aadhaar_ok = bool(profile["aadhaar_ok"])
                    pan_ok = bool(profile["pan_ok"])
                    mobile_last4 = profile["mobile_last4"] or ""
                    pan_mask = profile.get("pan_mask") or ""
                    digilocker_ref = profile.get("digilocker_ref") or ""
                    pan_name_hint = profile.get("pan_name_hint") or ""
                else:
                    email_ok = mobile_ok = True
                    aadhaar_ok = pan_ok = role == "customer"
                    mobile_last4 = ""
                    pan_mask = digilocker_ref = pan_name_hint = ""
                rows.append(
                    {
                        "user_id": person["id"],
                        "email": person["email"],
                        "role": role,
                        "mobile_last4": mobile_last4,
                        "email_ok": email_ok,
                        "mobile_ok": mobile_ok,
                        "aadhaar_ok": aadhaar_ok,
                        "pan_ok": pan_ok,
                        "pan_mask": pan_mask,
                        "digilocker_ref": digilocker_ref,
                        "pan_name_hint": pan_name_hint,
                        "verified_at": int(person.get("created_at") or 0),
                    }
                )
        rows.sort(key=lambda row: row["verified_at"], reverse=True)
        return rows

    def _processes(self, request, origin) -> None:
        if not self._desk_session(request, origin):
            return
        checks = (
            ("Auth", 4600, "http://127.0.0.1:4600/", True),
            ("ParkPe", 4310, "http://127.0.0.1:4310/", None),
            ("PaySwap", 4500, "http://127.0.0.1:4500/", None),
            ("API", 4610, "http://127.0.0.1:4610/api/v1/health/", None),
        )
        processes = []
        for name, port, url, known in checks:
            if known is not None:
                up = known
            elif name == "API":
                up = self._health_ok(url)
            else:
                up = self._port_open(port)
            processes.append({"name": name, "port": port, "up": up, "url": url})
        self._json(request, 200, {"processes": processes}, origin)

    def _services(self, request, origin) -> None:
        """Live integration & API visibility for the console. Secrets stay out."""
        if not self._desk_session(request, origin):
            return
        latest: dict[str, dict] = {}
        for row in self.store.service_logs(100):
            service = _api_service(row["action"])
            if service not in latest:
                latest[service] = {
                    "action": row["action"],
                    "outcome": row["outcome"],
                    "status": row["status"],
                    "duration_ms": row["duration_ms"],
                    "at": row["at"],
                }
        hub_base = os.environ.get("HUB_API_ORIGIN", "http://127.0.0.1:4610").rstrip("/")
        hub_up = self._health_ok(hub_base + "/api/v1/health/")
        kaleyra_parkpe = kaleyra.configured("customer")
        kaleyra_payswap = kaleyra.configured("retailer")
        kaleyra_ready = kaleyra_parkpe or kaleyra_payswap or kaleyra.configured()
        mail_ready = mail_configured()
        cashfree_ready = cashfree_configured()
        bbps_ready = bbps_integration.configured()
        pg_ready = pg_integration.pg_configured()
        hub_last = latest.get("ParkPe") or latest.get("PaySwap") or latest.get("Idempotency")
        services = [
            {
                "id": "kaleyra",
                "name": "Kaleyra SMS OTP",
                "kind": "External provider",
                "state": "ready" if kaleyra_ready else "warn",
                "status_label": (
                    "Configured (ParkPe + PaySwap)"
                    if kaleyra_parkpe and kaleyra_payswap
                    else "Configured"
                    if kaleyra_ready
                    else "Not configured"
                ),
                "summary": "Sends 6-digit SMS OTPs for ParkPe and PaySwap onboarding via DLT profiles.",
                "routes": [Paths.SIGNUP_START, Paths.SIGNUP_RESEND],
                "log_filter": "Kaleyra",
                "last_call": latest.get("Kaleyra"),
            },
            {
                "id": "email",
                "name": "Email OTP (SES / PHP Mailer)",
                "kind": "External provider",
                "state": "ready" if mail_ready else "warn",
                "status_label": "Configured" if mail_ready else "Not configured",
                "summary": "Delivers email verification codes through otp-mail.php and SES SMTP.",
                "routes": [Paths.SIGNUP_START, Paths.SIGNUP_RESEND],
                "log_filter": "Email",
                "last_call": latest.get("Email"),
            },
            {
                "id": "cashfree",
                "name": "Cashfree Secure ID",
                "kind": "External provider",
                "state": "ready" if cashfree_ready else "warn",
                "status_label": "Configured" if cashfree_ready else "Not configured",
                "summary": "Runs DigiLocker Aadhaar consent and PAN verification for PaySwap retailers.",
                "routes": [Paths.SIGNUP_AADHAAR, Paths.SIGNUP_AADHAAR_CONFIRM, Paths.SIGNUP_PAN],
                "log_filter": "Cashfree",
                "last_call": latest.get("Cashfree"),
            },
            {
                "id": "hub_api",
                "name": "Shared Django API (/api/v1/)",
                "kind": "Internal API",
                "state": "ready" if hub_up else "down",
                "status_label": "Up" if hub_up else "Down",
                "summary": "Handles ParkPe session starts, PaySwap voucher orders, idempotency, and desk reads.",
                "routes": [
                    "/api/v1/health/",
                    "/api/v1/parkpe/sessions/initiate",
                    "/api/v1/payswap/vouchers/order",
                ],
                "log_filter": "all",
                "last_call": hub_last,
            },
            {
                "id": "bbps",
                "name": "Mobikwik BBPS",
                "kind": "External provider",
                "state": "ready" if bbps_ready else "warn",
                "status_label": "Configured" if bbps_ready else "Not configured",
                "summary": "Runs operator catalogue, bill fetch, bill payment, and status checks for PaySwap retailers.",
                "routes": [
                    "/api/v1/payswap/bbps/operators",
                    "/api/v1/payswap/bbps/fetch-bill",
                    "/api/v1/payswap/bbps/pay",
                ],
                "log_filter": "BBPS",
                "last_call": latest.get("BBPS"),
            },
            {
                "id": "pg",
                "name": "Cashfree Payment Gateway",
                "kind": "External provider",
                "state": "ready" if pg_ready else "warn",
                "status_label": "Configured" if pg_ready else "Not configured",
                "summary": "Handles retailer PG wallet top-ups and direct PG bill payments when enabled.",
                "routes": [
                    "/api/v1/payswap/pg/order",
                    "/api/v1/payswap/pg/verify",
                    "/api/v1/payswap/pg/webhook",
                ],
                "log_filter": "PaySwap",
                "last_call": latest.get("PaySwap"),
            },
            {
                "id": "parking",
                "name": "Parking Reservation",
                "kind": "Local stub",
                "state": "stub",
                "status_label": "Local stub",
                "summary": "Generates local park-* references only. Not mounted on /api/v1/ yet.",
                "routes": ["integrations/parking.py"],
                "log_filter": "Parking",
                "last_call": latest.get("Parking"),
            },
        ]
        self._json(request, 200, {"services": services}, origin)

    def _health_ok(self, url: str) -> bool:
        request = urllib.request.Request(url, method="GET")
        try:
            with urllib.request.urlopen(request, timeout=0.4) as response:
                return response.status == 200
        except (urllib.error.URLError, TimeoutError, OSError):
            return False

    def _hub(self, request, origin, method: str, upstream: str, body: dict | None = None) -> None:
        """Forward a desk read or mutation to Django on 4610. The console stays on this origin.

        The browser calls this process. Django desk routes reject a browser Origin.
        Only auth_access is copied. The refresh cookie stays on port 4600.
        """
        if not self._desk_session(request, origin):
            return
        params = parse_qs(urlparse(request.path).query, keep_blank_values=False)
        clean_params = {}
        for k, vals in params.items():
            if not vals:
                continue
            if k == "email":
                norm = normalize_email(vals[0])
                if norm:
                    clean_params["email"] = norm
            elif k in {"state", "channel", "service", "q", "limit", "category", "month", "sheet"}:
                clean_params[k] = vals[0][:80]
        upstream_path = f"{upstream}?{urlencode(clean_params)}" if clean_params else upstream
        base = os.environ.get("HUB_API_ORIGIN", "http://127.0.0.1:4610").rstrip("/")
        data = None if body is None else json.dumps(body).encode()
        headers = {
            "Accept": "application/json",
            "Cookie": self._access_cookie_header(request),
        }
        if data is not None:
            headers["Content-Type"] = "application/json"
        outgoing = urllib.request.Request(base + upstream_path, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(outgoing, timeout=20) as response:
                raw = response.read()
                status = response.status
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            status = exc.code
        except (urllib.error.URLError, TimeoutError, OSError):
            self._json(request, 503, {"error": "The hub API is not running."}, origin)
            return
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            self._json(request, 502, {"error": "The hub API did not answer."}, origin)
            return
        if not isinstance(payload, dict):
            self._json(request, 502, {"error": "The hub API did not answer."}, origin)
            return
        self._json(request, status, payload, origin)

    def _logs(self, request, origin) -> None:
        """Logs screen. User actions are audit rows. API lines are provider calls plus /api/v1."""
        if not self._desk_session(request, origin):
            return
        actions = [
            {
                "id": f"A-{row['id']}",
                "at": row["at"],
                "service": "Signup" if str(row["event"]).startswith("signup_") else "Auth",
                "event": row["event"],
                "email": row["email"],
                "outcome": "error" if row["event"] in _FAILED_AUDIT else "ok",
                "why": _AUDIT_WHY.get(row["event"], "Recorded."),
                "request": row.get("request") or "",
                "response": row.get("response") or "",
            }
            for row in self.store.recent_audit(80)
        ]
        api = []
        for row in self.store.service_logs(80):
            api.append(
                {
                    "id": f"S-{row['id']}",
                    "at": row["at"],
                    "service": _api_service(row["action"]),
                    "action": row["action"],
                    "actor": row["actor"],
                    "role": row["role"],
                    "target_id": row["target_id"],
                    "outcome": row["outcome"],
                    "status": row["status"],
                    "duration_ms": row["duration_ms"],
                    "error_code": row["error_code"],
                    "error_reason": row["error_reason"],
                    "request": row["request"],
                    "response": row["response"],
                    "why": _api_why(row["outcome"], row["error_reason"]),
                }
            )
        self._json(request, 200, {"actions": actions, "api": api}, origin)

    def _hub_entries(self, request, upstream: str) -> list:
        """Read a Django desk list. A down hub leaves the local provider lines in place."""
        base = os.environ.get("HUB_API_ORIGIN", "http://127.0.0.1:4610").rstrip("/")
        outgoing = urllib.request.Request(
            base + upstream,
            headers={"Accept": "application/json", "Cookie": self._access_cookie_header(request)},
            method="GET",
        )
        try:
            with urllib.request.urlopen(outgoing, timeout=2) as response:
                if response.status != 200:
                    return []
                payload = json.loads(response.read())
        except urllib.error.HTTPError as exc:
            exc.read()
            return []
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
            return []
        entries = payload.get("entries") if isinstance(payload, dict) else None
        return entries if isinstance(entries, list) else []

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
        if not user["sign_in"] or not active or not self.store.has_membership(user["id"], active):
            self._json(request, 401, {"error": "Sign in again."}, origin)
            return
        prof = self.store.self_profile(user["id"], active)
        self._json(
            request,
            200,
            {
                "email": user["email"],
                "role": active,
                "account_id": prof["account_id"],
                "display_name": prof["display_name"],
                "outlet_name": prof["outlet_name"],
                "kyc_verified": prof["kyc_verified"],
            },
            origin,
        )

    def _full_user_session(self, request, origin):
        session = self._session(request)
        if not session:
            self._json(request, 401, {"error": "Sign in again."}, origin)
            return None, None, ""
        user = self.store.user_by_id(session["user_id"])
        if not user:
            self._json(request, 401, {"error": "Sign in again."}, origin)
            return None, None, ""
        active = session["role"] or user["role"]
        if session["scope"] != SCOPE_FULL:
            self._json(request, 403, {"error": "Turn on the authenticator first."}, origin)
            return None, None, ""
        if not user["sign_in"] or not active or not self.store.has_membership(user["id"], active):
            self._json(request, 401, {"error": "Sign in again."}, origin)
            return None, None, ""
        return session, user, active

    def _self_profile_get(self, request, origin) -> None:
        _, user, active = self._full_user_session(request, origin)
        if not user:
            return
        self._json(request, 200, {"profile": self.store.self_profile(user["id"], active)}, origin)

    def _self_profile_post(self, request, body: dict, ip: str, origin: str) -> None:
        _, user, active = self._full_user_session(request, origin)
        if not user:
            return
        display_name = str(body.get("display_name") or "").strip()[:80]
        outlet_name = str(body.get("outlet_name") or "").strip()[:80]
        city = str(body.get("city") or "").strip()[:64]
        address = str(body.get("address") or "").strip()[:200]
        gstin = str(body.get("gstin") or "").strip().upper()[:20]
        if gstin and not re.fullmatch(r"[0-9A-Z]{15}", gstin):
            self._json(request, 400, {"error": "Enter a valid 15-character GSTIN or leave it blank."}, origin)
            return
        prof = self.store.update_self_profile(
            user["id"],
            active,
            display_name=display_name,
            outlet_name=outlet_name,
            city=city,
            address=address,
            gstin=gstin,
        )
        self.store.audit(
            "profile_updated",
            ip,
            user["id"],
            request=f"POST {Paths.PROFILE}\nrole={active}",
            response='HTTP 200\n{"ok":true}',
        )
        self._json(request, 200, {"ok": True, "profile": prof}, origin)

    def _self_password_change(self, request, body: dict, ip: str, origin: str) -> None:
        session, user, active = self._full_user_session(request, origin)
        if not user:
            return
        current = body.get("current_password")
        new_pw = body.get("new_password")
        if not isinstance(current, str) or not verify_password(current, user["password_hash"]):
            self._json(request, 403, {"error": "Current password is incorrect."}, origin)
            return
        problem = password_problem(new_pw, user["email"])
        if problem:
            self._json(request, 400, {"error": problem}, origin)
            return
        self.store.set_password_hash(user["id"], hash_password(new_pw, n=self.store.scrypt_n))
        self.store.revoke_other_sessions(user["id"], session["session_id"])
        self.store.audit(
            "self_password_changed",
            ip,
            user["id"],
            request=f"POST {Paths.PASSWORD_CHANGE}",
            response='HTTP 200\n{"ok":true}',
        )
        self._json(request, 200, {"ok": True}, origin)

    def _self_sessions_get(self, request, origin) -> None:
        session, user, _ = self._full_user_session(request, origin)
        if not user:
            return
        rows = self.store.open_sessions(user["id"])
        for row in rows:
            row["current"] = row["id"] == session["session_id"]
        self._json(request, 200, {"sessions": rows}, origin)

    def _self_sessions_revoke(self, request, ip: str, origin: str) -> None:
        session, user, _ = self._full_user_session(request, origin)
        if not user:
            return
        count = self.store.revoke_other_sessions(user["id"], session["session_id"])
        self.store.audit(
            "self_sessions_revoked",
            ip,
            user["id"],
            request=f"POST {Paths.SELF_SESSIONS_REVOKE}",
            response=f'HTTP 200\n{{"revoked":{count}}}',
        )
        self._json(request, 200, {"ok": True, "revoked": count}, origin)

    def _device_key(self, body: dict | None) -> str:
        """Stable browser/device id from the client (localStorage). Soft binding, not attestation."""
        if not isinstance(body, dict):
            return ""
        raw = body.get("device_id") or body.get("device_key") or ""
        if not isinstance(raw, str):
            return ""
        raw = raw.strip()
        if not raw or len(raw) < 8 or len(raw) > 128:
            return ""
        # Store a digest so the raw client id is not sitting in SQLite.
        return token_hash(raw)

    def _request_user_agent(self, request) -> str:
        return str(request.headers.get("User-Agent") or "")[:300]

    def _issue(
        self,
        request,
        user,
        scope: str,
        ip: str,
        origin: str,
        role: str,
        setup: bool = False,
        clear_mfa: bool = False,
        device_key: str = "",
    ) -> None:
        refresh = new_token()
        access = new_token()
        now = int(time.time())
        session_id = self.store.save_session(
            user["id"],
            refresh,
            scope,
            now + REFRESH_TTL,
            role=role,
            device_key=device_key or "",
            user_agent=self._request_user_agent(request),
            ip=ip or "",
            continue_device=bool(device_key) and scope == SCOPE_FULL,
        )
        self.store.save_access(access, session_id, user["id"], scope, now + ACCESS_TTL, role)
        cookies = [
            self._cookie(ACCESS_COOKIE, access, ACCESS_TTL, ACCESS_PATH),
            self._cookie(REFRESH_COOKIE, refresh, REFRESH_TTL, REFRESH_PATH),
        ]
        if clear_mfa:
            cookies.append(self._clear(MFA_COOKIE, MFA_PATH))
        payload = {"mfa_setup_required": True, "role": role} if setup else {"ok": True, "email": user["email"], "role": role}
        self._json(request, 200, payload, origin, cookies=cookies)

    def _admin_target_forbidden(self, request, actor, user, origin) -> bool:
        """A non-super admin cannot change another admin. Self stays allowed."""
        operator = self.store.has_membership(user["id"], ROLE_ADMIN) or user["role"] == ROLE_ADMIN
        if operator and user["id"] != actor["id"] and not actor["is_super"]:
            self._json(request, 403, {"error": "Only the super admin can change an admin."}, origin)
            return True
        return False

    def _accept_totp(self, user, code: str) -> bool:
        step = totp_step(user["mfa_secret"], code.strip() if isinstance(code, str) else "")
        if step is None:
            return False
        return self.store.claim_totp_step(user["id"], step)

    def _access_cookie_header(self, request) -> str:
        token = self._read_cookie(request, ACCESS_COOKIE)
        if not token:
            return ""
        return f"{ACCESS_COOKIE}={token}"

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
        actor = self.store.user_by_id(self._session(request)["user_id"])
        if not actor or not actor["is_super"]:
            self._json(request, 403, {"error": "Only the super admin can add an admin."}, origin)
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
        if self.store.admin_with_email(email):
            self._json(request, 409, {"error": "That email already has an account."}, origin)
            return
        if not self.store.create_user(email, password, ROLE_ADMIN):
            self._json(request, 409, {"error": "That email already has an account."}, origin)
            return
        self.store.audit(
            "operator_added",
            ip,
            request=f"POST /api/auth/desk/operator/add\n{json.dumps({'email': email, 'role': ROLE_ADMIN})}",
            response='HTTP 200\n{"ok":true,"account_ready":true}',
        )
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
        if self.store.admin_with_email(email):
            self._json(request, 409, {"error": "An admin email stays an admin account."}, origin)
            return
        blocked = self.store.desk_signup_blocked(email, role)
        if blocked:
            duplicate = "That person already has this account."
            if role == ROLE_CUSTOMER and not self.store.desk_signup_blocked(email, ROLE_RETAILER):
                duplicate = "This email already has a ParkPe customer. Choose PaySwap retailer."
            elif role == ROLE_RETAILER and not self.store.desk_signup_blocked(email, ROLE_CUSTOMER):
                duplicate = "This email already has a PaySwap retailer. Choose ParkPe customer."
            self._json(request, 409, {"error": duplicate}, origin)
            return
        email_code = f"{secrets.randbelow(1_000_000):06d}"
        sms_code = f"{secrets.randbelow(1_000_000):06d}"
        digest = hash_password(password, n=self.store.scrypt_n)
        if not self.verifiers.send_email(email, email_code, role) or not self.verifiers.send_sms(mobile, sms_code, role):
            self.store.audit(
                "signup_delivery_failed",
                ip,
                None,
                request=f"POST /api/auth/desk/signup/start\n{json.dumps({'email': email, 'role': role})}",
                response='HTTP 503\n{"error":"Verification delivery is not available."}',
            )
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
                "user_id": None,
                "email_code_hash": token_hash(email_code),
                "sms_code_hash": token_hash(sms_code),
                "live": True,
                "expires_at": SIGNUP_INTENT_EXPIRES,
                "created_at": now,
            }
        )
        self.store.audit(
            "signup_started",
            ip,
            None,
            request=f"POST /api/auth/desk/signup/start\n{json.dumps({'email': email, 'role': role})}",
            response=f"HTTP 200\n{json.dumps({'ok': True, 'signup_id': signup_id})}",
        )
        self._json(request, 200, {"ok": True, "signup_id": signup_id}, origin)

    def _signup_contact(self, request, body, ip, origin) -> None:
        if not self._require_operator(request, origin):
            return
        intent = self._live_signup(body.get("signup_id"))
        email_code = body.get("email_code") if isinstance(body.get("email_code"), str) else ""
        sms_code = body.get("sms_code") if isinstance(body.get("sms_code"), str) else ""
        email_ok = bool(intent) and hmac.compare_digest(token_hash(email_code.strip()), intent["email_code_hash"])
        sms_ok = bool(intent) and hmac.compare_digest(token_hash(sms_code.strip()), intent["sms_code_hash"])
        if intent is None or not email_ok or not sms_ok:
            if intent is not None and self.store.note_signup_failure(intent["id"]) >= MAX_FAILS:
                self.store.delete_signup(intent["id"])
            self.store.audit(
                "signup_rejected",
                ip,
                request=f"POST /api/auth/desk/signup/contact\n{json.dumps({'signup_id': str(body.get('signup_id') or '')})}",
                response='HTTP 400\n{"error":"Verification did not succeed."}',
            )
            self._json(request, 400, {"error": "Verification did not succeed."}, origin)
            return
        self.store.mark_signup(intent["id"], email_ok=1, mobile_ok=1)
        ready = False
        if intent["role"] == ROLE_CUSTOMER:
            ready = self._open_verified_account(intent)
        self.store.audit(
            "signup_contact_ok",
            ip,
            intent["user_id"],
            request=f"POST /api/auth/desk/signup/contact\n{json.dumps({'signup_id': intent['id']})}",
            response=f"HTTP 200\n{json.dumps({'ok': True, 'account_ready': ready})}",
        )
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
            self.store.audit(
                "signup_rejected",
                ip,
                intent["user_id"],
                request=f"POST /api/auth/desk/signup/aadhaar\n{json.dumps({'signup_id': intent['id']})}",
                response='HTTP 400\n{"error":"Verification did not succeed."}',
            )
            self._json(request, 400, {"error": "Verification did not succeed."}, origin)
            return
        self.store.mark_signup(intent["id"], aadhaar_ref=verification_id, aadhaar_ok=0)
        self._json(request, 200, {"ok": True, "url": url}, origin)

    def _complete_aadhaar_when_ready(self, intent, ip: str) -> str:
        """pending, authenticated, or rejected. Marks aadhaar_ok only on authenticated."""
        if intent["aadhaar_ok"]:
            return "authenticated"
        if not intent["aadhaar_ref"]:
            return "rejected"
        poll = getattr(self.verifiers, "digilocker_poll", None)
        if poll is not None:
            state = poll(intent["aadhaar_ref"])
        else:
            state = "authenticated" if self.verifiers.digilocker_ok(intent["aadhaar_ref"]) else "pending"
        if state == "authenticated":
            self.store.mark_signup(intent["id"], aadhaar_ok=1)
            self.store.audit(
                "signup_aadhaar_ok",
                ip,
                intent["user_id"],
                request=f"POST /api/auth/desk/signup/aadhaar/status\n{json.dumps({'signup_id': intent['id']})}",
                response='HTTP 200\n{"state":"authenticated"}',
            )
        return state

    def _signup_aadhaar_status(self, request, body, ip, origin) -> None:
        if not self._require_operator(request, origin):
            return
        intent = self._live_signup(body.get("signup_id"))
        if intent is None or intent["role"] != ROLE_RETAILER or not intent["email_ok"] or not intent["mobile_ok"]:
            self._json(request, 400, {"error": "That signup is not ready for DigiLocker.", "state": "rejected"}, origin)
            return
        if not intent["aadhaar_ref"]:
            self._json(request, 400, {"error": "Open DigiLocker before checking status.", "state": "pending"}, origin)
            return
        state = self._complete_aadhaar_when_ready(intent, ip)
        if state == "rejected":
            self._json(request, 200, {"ok": True, "state": "rejected"}, origin)
            return
        self._json(
            request,
            200,
            {"ok": True, "state": state, "authenticated": state == "authenticated"},
            origin,
        )

    def _signup_aadhaar_confirm(self, request, body, ip, origin) -> None:
        if not self._require_operator(request, origin):
            return
        intent = self._live_signup(body.get("signup_id"))
        if intent is None or not intent["aadhaar_ref"]:
            self.store.audit(
                "signup_rejected",
                ip,
                request=f"POST /api/auth/desk/signup/aadhaar/confirm\n{json.dumps({'signup_id': str(body.get('signup_id') or '')})}",
                response='HTTP 400\n{"error":"Verification did not succeed."}',
            )
            self._json(request, 400, {"error": "Verification did not succeed."}, origin)
            return
        state = self._complete_aadhaar_when_ready(intent, ip)
        if state != "authenticated":
            self.store.audit(
                "signup_rejected",
                ip,
                request=f"POST /api/auth/desk/signup/aadhaar/confirm\n{json.dumps({'signup_id': intent['id']})}",
                response='HTTP 400\n{"error":"Verification did not succeed."}',
            )
            self._json(request, 400, {"error": "Verification did not succeed."}, origin)
            return
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
        pan_ok, pan_registered = self.verifiers.pan_verify(pan, name)
        if not pan_ok:
            self.store.audit(
                "signup_rejected",
                ip,
                intent["user_id"],
                request=f"POST /api/auth/desk/signup/pan\n{json.dumps({'signup_id': intent['id']})}",
                response='HTTP 400\n{"error":"Verification did not succeed."}',
            )
            self._json(request, 400, {"error": "Verification did not succeed."}, origin)
            return
        self.store.mark_signup(
            intent["id"],
            pan_ok=1,
            pan_mask=mask_pan(pan),
            pan_name_hint=mask_pan_name(name),
        )
        ready = self._open_verified_account(
            intent, pan=pan, pan_name=name, pan_registered_name=pan_registered
        )
        self._json(request, 200, {"ok": True, "account_ready": ready}, origin)

    def _signup_cancel(self, request, body, ip, origin) -> None:
        if not self._require_operator(request, origin):
            return
        signup_id = body.get("signup_id")
        intent = self.store.signup_any(signup_id) if isinstance(signup_id, str) else None
        if intent is None:
            self._json(request, 400, {"error": "That signup is not open."}, origin)
            return
        self.store.delete_signup(intent["id"])
        self.store.audit(
            "signup_cancelled",
            ip,
            intent["user_id"],
            request=f"POST /api/auth/desk/signup/cancel\n{json.dumps({'signup_id': intent['id']})}",
            response='HTTP 200\n{"ok":true}',
        )
        self._json(request, 200, {"ok": True}, origin)

    def _signup_resend(self, request, body, ip, origin) -> None:
        if not self._require_operator(request, origin):
            return
        signup_id = body.get("signup_id")
        intent = self.store.signup_any(signup_id) if isinstance(signup_id, str) else None
        if intent is None or intent["email_ok"] or intent["mobile_ok"]:
            self._json(request, 400, {"error": "Those checks already passed."}, origin)
            return
        email_code = f"{secrets.randbelow(1_000_000):06d}"
        sms_code = f"{secrets.randbelow(1_000_000):06d}"
        if not self.verifiers.send_email(intent["email"], email_code, intent["role"]) or not self.verifiers.send_sms(intent["mobile"], sms_code, intent["role"]):
            self.store.audit(
                "signup_delivery_failed",
                ip,
                intent["user_id"],
                request=f"POST /api/auth/desk/signup/resend\n{json.dumps({'signup_id': intent['id']})}",
                response='HTTP 503\n{"error":"Verification delivery is not available."}',
            )
            self._json(request, 503, {"error": "Verification delivery is not available."}, origin)
            return
        self.store.mark_signup(
            intent["id"],
            email_code_hash=token_hash(email_code),
            sms_code_hash=token_hash(sms_code),
            expires_at=SIGNUP_INTENT_EXPIRES,
        )
        self.store.audit(
            "signup_resent",
            ip,
            intent["user_id"],
            request=f"POST /api/auth/desk/signup/resend\n{json.dumps({'signup_id': intent['id']})}",
            response=f"HTTP 200\n{json.dumps({'ok': True, 'signup_id': intent['id']})}",
        )
        self._json(request, 200, {"ok": True, "signup_id": intent["id"]}, origin)

    def _live_signup(self, signup_id: object):
        if not isinstance(signup_id, str) or not signup_id:
            return None
        intent = self.store.signup(signup_id)
        if intent is None or not intent["live"]:
            return None
        return intent

    def _open_verified_account(
        self,
        intent,
        pan: str | None = None,
        pan_name: str = "",
        *,
        pan_registered_name: str = "",
    ) -> bool:
        stored = self.store.signup_any(intent["id"]) or intent
        if not self.store.create_user_with_hash(stored["email"], stored["password_hash"], stored["role"]):
            return False
        created = self.store.user_by_email_role(stored["email"], stored["role"])
        user_id = created["id"] if created else ""
        if user_id:
            pan_mask = mask_pan(pan) if pan else self._signup_field(stored, "pan_mask")
            digi_full = self._signup_field(stored, "aadhaar_ref") if stored["aadhaar_ok"] else ""
            digilocker_ref = mask_digilocker_ref(digi_full) if digi_full else ""
            pan_name_hint = mask_pan_name(pan_name) if pan_name else self._signup_field(stored, "pan_name_hint")
            name_on_pan = pan_name or self._signup_field(stored, "pan_name_hint")
            self.store.save_profile(
                user_id,
                stored["role"],
                stored["mobile"] or "",
                bool(stored["email_ok"]),
                bool(stored["mobile_ok"]),
                bool(stored["aadhaar_ok"]),
                bool(stored["pan_ok"]),
                pan_mask=pan_mask,
                digilocker_ref=digilocker_ref,
                pan_name_hint=pan_name_hint,
                pan=pan or "",
                pan_name=name_on_pan,
                pan_registered_name=pan_registered_name,
                digilocker_verification_id=digi_full,
            )
        self.store.delete_signup(stored["id"])
        self.store.audit(
            "signup_account",
            "",
            user_id or None,
            request=json.dumps({"email": stored["email"], "role": stored["role"]}),
            response=json.dumps({"account_ready": True, "role": stored["role"]}),
        )
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
    from auth.verify import load_cashfree_env, load_mail_env, _cashfree_ready
    from integrations.bbps import configured as bbps_ready, load_local_env as load_bbps_env
    from integrations.kaleyra import load_local_env

    load_local_env()
    load_mail_env()
    load_cashfree_env()
    load_bbps_env()
    mail_config = os.environ.get("AUTH_MAIL_CONFIG", "")
    mail_smtp = os.environ.get("AUTH_SES_SMTP_PHP", "")
    mail_ready = bool(mail_config and mail_smtp and Path(mail_config).is_file() and Path(mail_smtp).is_file())
    print("Mail config ready" if mail_ready else "Mail config missing", flush=True)
    print("Cashfree verification ready" if _cashfree_ready() else "Cashfree verification missing", flush=True)
    print("Mobikwik BBPS ready" if bbps_ready() else "Mobikwik BBPS missing", flush=True)
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
    cookie_secure = os.environ.get("AUTH_COOKIE_SECURE", "0") == "1"
    if host not in {"127.0.0.1", "localhost", "::1"} and not cookie_secure:
        raise SystemExit("Set AUTH_COOKIE_SECURE=1 for a non-loopback AUTH_HOST.")
    origins.add(f"http://{host}:{port}")
    if host in {"127.0.0.1", "localhost"}:
        origins.add(f"http://127.0.0.1:{port}")
        origins.add(f"http://localhost:{port}")
    app = AuthApp(
        data_dir=data_dir,
        origins=origins,
        scrypt_n=int(os.environ.get("AUTH_SCRYPT_N", "32768")),
        cookie_secure=cookie_secure,
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
