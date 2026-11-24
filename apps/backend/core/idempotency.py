"""Idempotency for POST, PUT, and PATCH under /api/v1.

Callers: api/v1/routes/parkpe.py (sessions/initiate) and
api/v1/routes/payswap.py (vouchers/order). The key is the Idempotency-Key
header. packages/sdk-client is the place that header is meant to be set;
the running payswap page does not send it yet.

Scope is (app_context, user_id, endpoint, idempotency_key). The payload
hash is the canonical JSON body only. The same key and same body return
the stored response and do not call the domain function again. The same
key with a different body is 409 idempotency_conflict (packages/contracts
ErrorCode). A missing key is 400 validation.

The row is locked with select_for_update inside transaction.atomic, and
the domain call stays inside that transaction. A concurrent retry blocks
until the first commit, then reads the stored response. This is not the
refresh-cookie rule in apps/backend/auth/server.py.
"""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal

from django.db import IntegrityError, transaction
from rest_framework.exceptions import APIException

IDEMPOTENCY_HEADER = "Idempotency-Key"
MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH"})


class IdempotencyProblem(APIException):
    def __init__(self, message: str, code: str, status: int):
        super().__init__(detail={"error": message, "code": code})
        self.status_code = status


def payload_hash(payload: dict) -> str:
    encoded = json.dumps(_plain(payload), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()


def run_once(*, app_context: str, user_id: str, endpoint: str, key: str, body_hash: str, produce):
    cleaned = (key or "").strip()
    if not cleaned or len(cleaned) > 200 or any(char.isspace() for char in cleaned):
        raise IdempotencyProblem("Send an Idempotency-Key.", "validation", 400)
    try:
        return _locked(app_context, user_id, endpoint, cleaned, body_hash, produce)
    except IntegrityError:
        return _locked(app_context, user_id, endpoint, cleaned, body_hash, produce)


def _locked(app_context, user_id, endpoint, key, body_hash, produce):
    from models.models import IdempotencyRecord

    with transaction.atomic():
        existing = (
            IdempotencyRecord.objects.select_for_update()
            .filter(
                app_context=app_context,
                user_id=user_id,
                endpoint=endpoint,
                idempotency_key=key,
            )
            .first()
        )
        if existing is not None:
            if existing.payload_hash != body_hash:
                raise IdempotencyProblem(
                    "This key was already used for a different request.",
                    "idempotency_conflict",
                    409,
                )
            return existing.status_code, existing.body
        record = IdempotencyRecord.objects.create(
            app_context=app_context,
            user_id=user_id,
            endpoint=endpoint,
            idempotency_key=key,
            payload_hash=body_hash,
            state="pending",
            status_code=0,
            body={},
        )
        status, body = produce()
        record.state = "done"
        record.status_code = status
        record.body = body
        record.save(update_fields=["state", "status_code", "body"])
        return status, body


def _plain(value):
    if isinstance(value, Decimal):
        return f"{value:.2f}"
    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value
