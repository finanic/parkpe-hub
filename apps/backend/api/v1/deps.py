"""Dependencies for api/v1 routes.

packages/sdk-client sends X-App-Context: parkpe from apps/parkpe and
payswap from apps/payswap. A domain/parkpe handler rejects payswap.
A domain/payswap handler rejects parkpe.

This header does not replace the role check in apps/backend/auth/server.py
(customer, retailer, admin) or the AUTH_ORIGINS allowlist. apps/backend/run.py
does not mount this module.

AppContextAuthentication calls core.security.fetch_session, which GETs
/api/auth/me on that server with the auth_access cookie. AppScopePermission
then requires the header context to match the view, and the role from /me
to match domain/common/scope.py (customer for parkpe, retailer for payswap).
"""

from __future__ import annotations

from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed, ParseError, PermissionDenied
from rest_framework.permissions import BasePermission

from core.security import (
    ACCESS_COOKIE,
    SessionRejected,
    fetch_session,
    parse_context,
    role_matches,
)
from domain.common.scope import PARKPE, PAYSWAP, BadContext

APP_CONTEXT_HEADER = "X-App-Context"


class Actor:
    """Signed-in account. user_id is the email from GET /api/auth/me.

    apps/backend/auth/server.py does not return a numeric id. Idempotency
    rows and domain calls use this email so one account cannot replay
    another account's key.
    """

    def __init__(self, email: str, role: str, app_context: str):
        self.email = email
        self.user_id = email
        # DRF UserRateThrottle keys on user.pk; auth /me has no numeric id.
        self.pk = email
        self.role = role
        self.app_context = app_context
        self.is_authenticated = True


class AppContextAuthentication(BaseAuthentication):
    """Identify the caller. Route scope is AppScopePermission, not this class.

    authenticate_header keeps a missing cookie at 401. Without it, DRF turns
    AuthenticationFailed into 403.
    """

    def authenticate_header(self, request):
        return 'Cookie realm="hub"'

    def authenticate(self, request):
        try:
            app_context = parse_context(request.headers.get(APP_CONTEXT_HEADER))
        except BadContext as exc:
            raise ParseError(detail={"error": exc.message, "code": "validation"}) from exc
        token = request.COOKIES.get(ACCESS_COOKIE, "")
        if not token:
            raise AuthenticationFailed(detail={"error": "Sign in again.", "code": "unauthenticated"})
        try:
            session = fetch_session(token)
        except SessionRejected as exc:
            detail = {"error": exc.message, "code": "unauthenticated", **exc.extra}
            if exc.status == 403:
                raise PermissionDenied(detail=detail) from exc
            raise AuthenticationFailed(detail=detail) from exc
        return Actor(session["email"], session["role"], app_context), token


class AppScopePermission(BasePermission):
    """View.app_context is parkpe or payswap. The other context is forbidden_app."""

    def has_permission(self, request, view):
        required = getattr(view, "app_context", None)
        actor = request.user
        if required not in {PARKPE, PAYSWAP} or actor is None or not getattr(actor, "is_authenticated", False):
            raise PermissionDenied(detail={"error": "Sign in again.", "code": "forbidden_app"})
        if actor.app_context != required or not role_matches(actor.app_context, actor.role):
            raise PermissionDenied(
                detail={"error": "This account cannot use that app.", "code": "forbidden_app"}
            )
        if not actor.user_id:
            raise PermissionDenied(detail={"error": "Sign in again.", "code": "forbidden_app"})
        return True


def require_app(app_context):
    """Mark a view as parkpe-only or payswap-only.

    AppScopePermission then returns 403 forbidden_app when X-App-Context
    (packages/sdk-client) does not match. Authentication still comes from
    AppContextAuthentication.
    """

    if app_context not in {PARKPE, PAYSWAP}:
        raise RuntimeError("app context must be parkpe or payswap")

    def mark(view):
        view.app_context = app_context
        return view

    return mark


parkpe_only = require_app(PARKPE)
payswap_only = require_app(PAYSWAP)
