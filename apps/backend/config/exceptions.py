"""JSON errors use the codes in packages/contracts/index.js ErrorCode.

validation, unauthenticated, forbidden_app, idempotency_conflict, server_error.
DRF's default `detail` envelope is rewritten so apps/parkpe and apps/payswap
can read one shape. An uncaught /api/ failure uses server_error and no traceback.
"""

from __future__ import annotations

import json

from core.actions import bind_action, log_action
from core.errors import retailer_message
from django.core.exceptions import RequestDataTooBig, TooManyFieldsSent, TooManyFilesSent
from django.http import JsonResponse
from rest_framework.views import exception_handler

_TOO_LARGE = (RequestDataTooBig, TooManyFieldsSent, TooManyFilesSent)

_ACTION_MAP = {
    "/api/v1/payswap/bbps/operators": "payswap.bbps.operators",
    "/api/v1/payswap/bbps/fetch-bill": "payswap.bbps.fetch_bill",
    "/api/v1/payswap/bbps/pay": "payswap.bbps.pay",
    "/api/v1/payswap/bbps/status": "payswap.bbps.status",
    "/api/v1/payswap/vouchers/order": "payswap.voucher.order",
    "/api/v1/parkpe/sessions/initiate": "parkpe.session.initiate",
    "/api/v1/desk/parkpe/sessions/close": "parkpe.session.close",
}


def _action_for(path: str) -> str:
    clean = path.rstrip("/") or "/"
    if clean in _ACTION_MAP:
        return _ACTION_MAP[clean]
    trimmed = clean.removeprefix("/api/v1/").strip("/")
    return trimmed.replace("/", ".").replace("-", "_") or "api.v1"


def _public_payload(data: dict) -> dict:
    """The browser sees our sentence. error_reason in the log keeps the original."""
    if not isinstance(data, dict) or "error" not in data:
        return data
    original = str(data.get("error") or "")
    public = retailer_message(original)
    if public == original:
        return data
    return {**data, "error": public}


def _log_v1_error(request, status: int, data: dict) -> None:
    if request is None or not str(getattr(request, "path", "")).startswith("/api/v1/"):
        return
    if getattr(request, "_hub_logged", False):
        return
    request._hub_logged = True
    actor = getattr(request, "user", None)
    ctx_header = request.headers.get("X-App-Context", "")
    bind_action(
        app_context=getattr(actor, "app_context", "") or ctx_header,
        actor=getattr(actor, "user_id", "") or "",
        role=getattr(actor, "role", "") or "",
        idempotency_key=request.headers.get("Idempotency-Key", ""),
    )
    req_meta = {"app_context": ctx_header} if ctx_header else {}
    req_line = f"{request.method} {request.path}"
    if req_meta:
        req_line += "\n" + json.dumps(req_meta, separators=(",", ":"))
    shown = {key: value for key, value in data.items() if key != "_raw_error"}
    log_action(
        action=_action_for(request.path),
        outcome="error",
        status=status,
        duration_ms=0,
        error_code=str(data.get("code") or ""),
        error_reason=str(data.get("_raw_error") or data.get("error") or "")[:200],
        request=req_line,
        response=f"HTTP {status}\n{json.dumps(shown, separators=(',', ':'), ensure_ascii=False)}",
    )


def api_exception(exc, context):
    response = exception_handler(exc, context)
    if response is None:
        return None
    request = context.get("request") if isinstance(context, dict) else None
    payload = response.data
    if isinstance(payload, dict) and "error" in payload and "code" in payload:
        raw = str(payload.get("error") or "")
        response.data = _public_payload(payload)
        _log_v1_error(request, response.status_code, {**payload, "_raw_error": raw})
        return response
    detail = payload.get("detail") if isinstance(payload, dict) else payload
    if isinstance(detail, dict) and "error" in detail and "code" in detail:
        raw = str(detail.get("error") or "")
        response.data = _public_payload(detail)
        _log_v1_error(request, response.status_code, {**detail, "_raw_error": raw})
        return response
    if response.status_code == 400 and isinstance(payload, dict) and "detail" not in payload:
        response.data = {"error": "Check the request.", "code": "validation", "fields": payload}
        _log_v1_error(request, response.status_code, response.data)
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
    _log_v1_error(request, response.status_code, response.data)
    return response


class ApiErrorEnvelopeMiddleware:
    """Last resort for /api/ routes. The client gets a JSON body, not a traceback."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            return self.get_response(request)
        except Exception:
            response = self._api_failure(request)
            if response is None:
                raise
            return response

    def process_exception(self, request, exception):
        # DRF re-raises inside the view. Django handles that before __call__
        # sees it, so the JSON body has to be returned from here.
        if isinstance(exception, _TOO_LARGE):
            return self._too_large(request)
        return self._api_failure(request)

    def _too_large(self, request):
        if not str(getattr(request, "path", "")).startswith("/api/"):
            return None
        data = {"error": "The request is too large.", "code": "validation"}
        _log_v1_error(request, 400, data)
        return JsonResponse(data, status=400)

    def _api_failure(self, request):
        if not str(getattr(request, "path", "")).startswith("/api/"):
            return None
        data = {"error": "Something went wrong.", "code": "server_error"}
        _log_v1_error(request, 500, data)
        return JsonResponse(data, status=500)
