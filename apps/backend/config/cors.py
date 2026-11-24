"""Reflect the ParkPe and PaySwap origins. Never `*`.

The allowlist is FRONTEND_ORIGINS in config/settings.py, the same hosts
apps/backend/auth/server.py allows (4310 and 4500) plus this process on 4610.
packages/sdk-client calls from those pages send credentials, so the browser
needs the reflected origin. A foreign Origin is not copied onto the response.
"""

from __future__ import annotations

from django.http import HttpResponse, JsonResponse

from config.settings import FRONTEND_ORIGINS

ALLOW_HEADERS = "Content-Type, X-App-Context, X-Auth-Request, Idempotency-Key"


def _clean(origin: str) -> str:
    return origin.rstrip("/")


class FrontendOriginMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        origin = _clean(request.headers.get("Origin", ""))
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
        response = self.get_response(request)
        if origin in FRONTEND_ORIGINS:
            _allow(response, origin)
        return response


def _allow(response, origin: str) -> None:
    response["Access-Control-Allow-Origin"] = origin
    response["Access-Control-Allow-Credentials"] = "true"
    response["Access-Control-Allow-Headers"] = ALLOW_HEADERS
    response["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response["Vary"] = "Origin"
