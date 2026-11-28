"""App-scope checks for apps/backend.

Callers: api/v1/deps.py, then domain/parkpe or domain/payswap.
Context values parkpe and payswap come from packages/sdk-client
(APP_CONTEXT_HEADER in api/v1/deps.py).

Do not reimplement scrypt, TOTP, or cookie issue here. Those stay in
apps/backend/auth/security.py and apps/backend/auth/server.py.
fetch_session asks that server's GET /api/auth/me (apps/backend/auth/contract.py
Paths.ME) and trusts its answer. A down auth process is a failed sign-in,
not an open route.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from auth.contract import ACCESS_COOKIE
from domain.common.scope import ROLE_FOR_CONTEXT, BadContext, parse_context

# Header and /api/auth/me path from apps/backend/auth/contract.py. Cookie name
# is ACCESS_COOKIE in that file, issued on port 4600.
AUTH_REQUEST_HEADER = "X-Auth-Request"
AUTH_ME_PATH = "/api/auth/me"


class SessionRejected(Exception):
    def __init__(self, status: int, message: str, extra: dict | None = None):
        self.status = status
        self.message = message
        self.extra = extra or {}
        super().__init__(message)


def role_matches(app_context: str, role: str) -> bool:
    return ROLE_FOR_CONTEXT.get(app_context) == role


def reject_foreign_owner(actor, claimed_user_id) -> None:
    """The body must not name an account other than the signed-in one.

    Called from api/v1/routes before domain/parkpe or domain/payswap runs.
    A missing claim is fine: the view uses actor.user_id.
    """
    from rest_framework.exceptions import PermissionDenied

    if claimed_user_id in (None, ""):
        return
    if str(claimed_user_id) != actor.user_id:
        raise PermissionDenied(
            detail={"error": "This account cannot use that app.", "code": "forbidden_app"}
        )


def fetch_session(access_token: str, *, base_url: str | None = None) -> dict:
    """Return {"email", "role"} from the auth server, or raise SessionRejected.

    Sends X-Auth-Request so apps/backend/auth/server.py _browser_ok accepts the call.
    Does not send the refresh cookie. A 403 with mfa_setup_required stays a 403.
    """
    base = (base_url or os.environ.get("AUTH_BASE_URL") or "http://127.0.0.1:4600").rstrip("/")
    # Only http(s) may leave this process. file: and other schemes stay blocked.
    if not (base.startswith("http://") or base.startswith("https://")):
        raise SessionRejected(401, "Sign in again.")
    request = urllib.request.Request(
        base + AUTH_ME_PATH,
        headers={
            AUTH_REQUEST_HEADER: "1",
            "Cookie": f"{ACCESS_COOKIE}={access_token}",
            "Accept": "application/json",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=2) as response:
            raw = response.read()
            status = response.status
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        status = exc.code
    except OSError:
        # URLError is an OSError subclass; keep one handler.
        raise SessionRejected(401, "Sign in again.") from None
    try:
        payload = json.loads(raw.decode() or "{}")
    except json.JSONDecodeError:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    if status == 200 and payload.get("email") and payload.get("role"):
        return {"email": str(payload["email"]), "role": str(payload["role"])}
    if status == 403 and payload.get("mfa_setup_required"):
        raise SessionRejected(403, "Turn on the authenticator first.", {"mfa_setup_required": True})
    raise SessionRejected(401, "Sign in again.")


__all__ = [
    "ACCESS_COOKIE",
    "AUTH_ME_PATH",
    "AUTH_REQUEST_HEADER",
    "BadContext",
    "SessionRejected",
    "fetch_session",
    "parse_context",
    "role_matches",
]
