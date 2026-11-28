"""Shared path for mutating /api/v1 views.

Order: reject a foreign user_id, validate the schema, then
core.idempotency.run_once. A stored replay does not call produce.
POST, PUT, and PATCH require Idempotency-Key. GET does not use this helper.

Every caller passes action so core.actions.log_action records the result.
The line does not include the body. apps/parkpe/js/hub.js and
apps/payswap/js/hub.js are the current callers.
"""

from __future__ import annotations

import json
import time

from core.actions import bind_action, elapsed_ms, log_action
from core.idempotency import (
    IDEMPOTENCY_HEADER,
    MUTATING_METHODS,
    IdempotencyProblem,
    payload_hash,
    run_once,
    run_once_external,
)
from core.security import reject_foreign_owner
from rest_framework.exceptions import ParseError
from rest_framework.response import Response

_OMIT_KEYS = frozenset({"vehicle", "pan", "aadhaar", "mobile", "customer_mobile", "email", "otp", "password", "token", "secret", "wallet_pin", "current_pin", "new_pin"})


def _safe_fields(mapping) -> dict:
    if not isinstance(mapping, dict):
        return {}
    return {
        str(k): (f"{v:.2f}" if hasattr(v, "as_tuple") else v)
        for k, v in mapping.items()
        if str(k) not in _OMIT_KEYS and v not in (None, "")
    }


def _default_summarize(request, data, status, body):
    req = f"{request.method} {request.path}\n{json.dumps(_safe_fields(data), separators=(',', ':'), default=str)}"
    resp = (
        f"HTTP {status}\n{json.dumps(_safe_fields(body), separators=(',', ':'), default=str)}"
        if isinstance(body, dict)
        else ""
    )
    return req, resp


def post_mutation(request, serializer_cls, produce, *, action, summarize=None, external: bool = False):
    if request.method not in MUTATING_METHODS:
        raise ParseError(detail={"error": "This method is not supported.", "code": "validation"})
    claimed = request.data.get("user_id") if isinstance(request.data, dict) else None
    reject_foreign_owner(request.user, claimed)
    serializer = serializer_cls(data=request.data)
    serializer.is_valid(raise_exception=True)
    bind_action(
        app_context=request.user.app_context,
        actor=request.user.user_id,
        role=request.user.role,
        idempotency_key=request.headers.get(IDEMPOTENCY_HEADER, ""),
    )
    started = time.perf_counter()
    runner = run_once_external if external else run_once
    try:
        status, body = runner(
            app_context=request.user.app_context,
            user_id=request.user.user_id,
            endpoint=request.path,
            key=request.headers.get(IDEMPOTENCY_HEADER, ""),
            body_hash=payload_hash(serializer.validated_data),
            produce=lambda: (201, produce(serializer.validated_data, request.user.user_id)),
        )
    except IdempotencyProblem as exc:
        detail = exc.detail if isinstance(exc.detail, dict) else {}
        req_text, _ = summarize(serializer.validated_data, None) if summarize else _default_summarize(request, serializer.validated_data, exc.status_code, None)
        request._hub_logged = True
        log_action(
            action=action,
            outcome="error",
            status=exc.status_code,
            duration_ms=elapsed_ms(started),
            error_code=str(detail.get("code") or ""),
            error_reason=str(detail.get("error") or ""),
            request=req_text,
            response=f"HTTP {exc.status_code}\n{detail.get('error') or ''}",
        )
        raise
    except Exception:
        request._hub_logged = True
        raise
    target = body.get("reference") if isinstance(body, dict) else ""
    req_text, resp_text = summarize(serializer.validated_data, body) if summarize else _default_summarize(request, serializer.validated_data, status, body)
    request._hub_logged = True
    log_action(
        action=action,
        outcome="ok",
        status=status,
        duration_ms=elapsed_ms(started),
        target_id=str(target or ""),
        request=req_text,
        response=resp_text,
    )
    return Response(body, status=status)
