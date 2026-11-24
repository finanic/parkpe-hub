"""Shared path for mutating /api/v1 views.

Order: reject a foreign user_id, validate the schema, then
core.idempotency.run_once. A stored replay does not call produce.
POST, PUT, and PATCH require Idempotency-Key. GET does not use this helper.
"""

from __future__ import annotations

from core.idempotency import IDEMPOTENCY_HEADER, MUTATING_METHODS, payload_hash, run_once
from core.security import reject_foreign_owner
from rest_framework.exceptions import ParseError
from rest_framework.response import Response


def post_mutation(request, serializer_cls, produce):
    if request.method not in MUTATING_METHODS:
        raise ParseError(detail={"error": "This method is not supported.", "code": "validation"})
    claimed = request.data.get("user_id") if isinstance(request.data, dict) else None
    reject_foreign_owner(request.user, claimed)
    serializer = serializer_cls(data=request.data)
    serializer.is_valid(raise_exception=True)
    status, body = run_once(
        app_context=request.user.app_context,
        user_id=request.user.user_id,
        endpoint=request.path,
        key=request.headers.get(IDEMPOTENCY_HEADER, ""),
        body_hash=payload_hash(serializer.validated_data),
        produce=lambda: (201, produce(serializer.validated_data, request.user.user_id)),
    )
    return Response(body, status=status)
