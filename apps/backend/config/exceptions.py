"""JSON errors use the codes in packages/contracts/index.js ErrorCode.

validation, unauthenticated, forbidden_app, idempotency_conflict, server_error.
DRF's default `detail` envelope is rewritten so apps/parkpe and apps/payswap
can read one shape. An uncaught /api/ failure uses server_error and no traceback.
"""

from __future__ import annotations

from django.http import JsonResponse
from rest_framework.views import exception_handler


def api_exception(exc, context):
    response = exception_handler(exc, context)
    if response is None:
        return None
    payload = response.data
    if isinstance(payload, dict) and "error" in payload and "code" in payload:
        return response
    detail = payload.get("detail") if isinstance(payload, dict) else payload
    if isinstance(detail, dict) and "error" in detail and "code" in detail:
        response.data = detail
        return response
    if response.status_code == 400 and isinstance(payload, dict) and "detail" not in payload:
        response.data = {"error": "Check the request.", "code": "validation", "fields": payload}
        return response
    if response.status_code == 401:
        code = "unauthenticated"
    elif response.status_code == 409:
        code = "idempotency_conflict"
    elif response.status_code == 403:
        code = "forbidden_app"
    else:
        code = "validation"
    message = detail if isinstance(detail, str) else "Check the request."
    response.data = {"error": message, "code": code}
    return response


class ApiErrorEnvelopeMiddleware:
    """Last resort for /api/ routes. The client gets a JSON body, not a traceback."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            return self.get_response(request)
        except Exception:
            if not request.path.startswith("/api/"):
                raise
            return JsonResponse(
                {"error": "Something went wrong.", "code": "server_error"},
                status=500,
            )
