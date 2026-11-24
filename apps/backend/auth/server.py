"""HTTP adapter for the auth contract in auth.contract.

Payswap calls these routes through apps/payswap/js/session.js. A missing or reused
refresh cookie revokes that login family. Unexpected exceptions stay as a
generic 500 so stack traces never reach either frontend.
"""

from __future__ import annotations

import json
import os
import time
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
    ROLE_OPERATOR,
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
    new_token,
    new_totp_secret,
    normalize_email,
    password_problem,
    totp_matches,
)
from auth.store import Store

def _split_csv(value: str) -> set[str]:
    return {item.strip().rstrip("/") for item in value.split(",") if item.strip()}


class AuthApp:
    def __init__(self, data_dir: Path, origins: set[str], scrypt_n: int, cookie_secure: bool, samesite: str):
        self.origins = origins
        self.cookie_secure = cookie_secure
        self.samesite = samesite
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
        if role == ROLE_OPERATOR and self.store.operator_exists():
            self.store.audit("register_operator_closed", ip)
            self._json(request, 403, {"error": "Operator signup is closed."}, origin)
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
        blocked = self.store.locked(user) or (user is not None and user["role"] != role)
        password_ok = self.store.check_password(None if blocked else user, password)
        if not password_ok or blocked or user is None:
            if user is not None and not blocked and user["role"] == role:
                self.store.register_failure(user)
            self.store.note_attempt(ip, email, False)
            self.store.audit("login_failed", ip, user["id"] if user else None)
            self._json(request, 401, {"error": LOGIN_ERROR}, origin)
            return
        self.store.clear_failures(user["id"])
        self.store.note_attempt(ip, email, True)
        if user["mfa_enabled"]:
            challenge = new_token()
            self.store.save_challenge(challenge, user["id"], int(time.time()) + CHALLENGE_TTL)
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
        self._issue(request, user, SCOPE_ENROLL, ip, origin, setup=True)

    def _mfa(self, request, body, ip, origin) -> None:
        challenge = self._read_cookie(request, MFA_COOKIE)
        row = self.store.peek_challenge(challenge) if challenge else None
        code = body.get("code") if isinstance(body.get("code"), str) else ""
        user = self.store.user_by_id(row["user_id"]) if row else None
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
        self._issue(request, user, SCOPE_FULL, ip, origin, clear_mfa=True)

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
        issuer = "PaySwap" if user["role"] == ROLE_RETAILER else "ParkPe"
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
        self._issue(request, user, SCOPE_FULL, ip, origin)

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
        self.store.save_access(access, row["id"], row["user_id"], row["scope"], int(time.time()) + ACCESS_TTL)
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
            csp="default-src 'self'; style-src 'self'; script-src 'self'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'",
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
        if session["scope"] != SCOPE_FULL:
            self._json(
                request,
                403,
                {"error": "Turn on the authenticator first.", "mfa_setup_required": True, "role": user["role"]},
                origin,
            )
            return
        self._json(request, 200, {"email": user["email"], "role": user["role"]}, origin)

    def _issue(self, request, user, scope: str, ip: str, origin: str, setup: bool = False, clear_mfa: bool = False) -> None:
        refresh = new_token()
        access = new_token()
        now = int(time.time())
        session_id = self.store.save_session(user["id"], refresh, scope, now + REFRESH_TTL)
        self.store.save_access(access, session_id, user["id"], scope, now + ACCESS_TTL)
        cookies = [
            self._cookie(ACCESS_COOKIE, access, ACCESS_TTL, ACCESS_PATH),
            self._cookie(REFRESH_COOKIE, refresh, REFRESH_TTL, REFRESH_PATH),
        ]
        if clear_mfa:
            cookies.append(self._clear(MFA_COOKIE, MFA_PATH))
        payload = {"mfa_setup_required": True} if setup else {"ok": True, "email": user["email"], "role": user["role"]}
        self._json(request, 200, payload, origin, cookies=cookies)

    def _session(self, request):
        token = self._read_cookie(request, ACCESS_COOKIE)
        if not token:
            return None
        return self.store.access_session(token)

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
