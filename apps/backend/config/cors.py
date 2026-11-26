"""Reflect the ParkPe and PaySwap origins. Never `*`.

The allowlist is FRONTEND_ORIGINS in config/settings.py, the same hosts
apps/backend/auth/server.py allows (4310 and 4500) plus this process on 4610.
packages/sdk-client calls from those pages send credentials, so the browser
needs the reflected origin. A foreign Origin is not copied onto the response.

A POST, PUT, or PATCH under /api/v1 from a foreign Origin is refused here,
before api/v1/deps.py. A form on another port of 127.0.0.1 can still carry
the auth_access cookie (SameSite=Lax, path /) and cannot set X-App-Context.
Desk paths also refuse any Origin. The auth process on 4600 calls them
with no Origin and only the access cookie. ParkPe and PaySwap must not.
deps.py still requires that header, so an allowlisted page that omits it
never reaches domain/parkpe or domain/payswap. packages/sdk-client also
sends X-Request-Id. config/request.py keeps that value for core/actions.py
only when it is a short token.
"""

from __future__ import annotations

from django.http import HttpResponse, JsonResponse

from config.settings import FRONTEND_ORIGINS

ALLOW_HEADERS = "Content-Type, X-App-Context, X-Auth-Request, Idempotency-Key, X-Request-Id"
MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH"})


def _clean(origin: str) -> str:
    return origin.rstrip("/")


class FrontendOriginMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        origin = _clean(request.headers.get("Origin", ""))
        if request.path.startswith("/api/v1/desk/") and origin:
            return JsonResponse(
                {"error": "Request blocked.", "code": "forbidden_app"},
                status=403,
            )
        if request.method == "OPTIONS":
            if origin and origin not in FRONTEND_ORIGINS:
                return JsonResponse(
                    {"error": "Request blocked.", "code": "forbidden_app"},
                    status=403,
                )
            response = HttpResponse(status=204)
            if origin in FRONTEND_ORIGINS:
                _allow(response, origin)
            return response
        if _cross_site_mutation(request, origin):
            return JsonResponse(
                {"error": "Request blocked.", "code": "forbidden_app"},
                status=403,
            )
        response = self.get_response(request)
        if origin in FRONTEND_ORIGINS:
            _allow(response, origin)
        return response


def _cross_site_mutation(request, origin: str) -> bool:
    """True when a mutating /api/v1 call names an origin outside the allowlist.

    Missing Origin stays allowed so the Django test client and a same-process
    caller still reach api/v1/deps.py, which requires X-App-Context.
    """
    return (
        request.method in MUTATING_METHODS
        and request.path.startswith("/api/v1/")
        and bool(origin)
        and origin not in FRONTEND_ORIGINS
    )


def _allow(response, origin: str) -> None:
    response["Access-Control-Allow-Origin"] = origin
    response["Access-Control-Allow-Credentials"] = "true"
    response["Access-Control-Allow-Headers"] = ALLOW_HEADERS
    response["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response["Vary"] = "Origin"
