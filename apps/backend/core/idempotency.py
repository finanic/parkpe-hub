"""Idempotency for POST, PUT, and PATCH under /api/v1.

Callers: api/v1/routes/parkpe.py (sessions/initiate) and
api/v1/routes/payswap.py (vouchers/order). The key is the Idempotency-Key
header. packages/sdk-client sends it. apps/payswap/js/app.js and
apps/parkpe/js/screens.js keep one key until that attempt finishes.

Scope is (app_context, user_id, endpoint, idempotency_key). The payload
hash is the canonical JSON body only. The same key and same body return
the stored response and do not call the domain function again. The same
key with a different body is 409 idempotency_conflict (packages/contracts
ErrorCode). A missing key is 400 validation.

The row is locked with select_for_update inside transaction.atomic, and
the domain call stays inside that transaction. Postgres waits on that lock.
SQLite can raise OperationalError while the first write is still open;
run_once retries and then reads the stored response. Each outcome is
logged by core/actions.py as idempotency.reserve. This is not the
refresh-cookie rule in apps/backend/auth/server.py.
"""

from __future__ import annotations

import hashlib
import json
import time
from decimal import Decimal

from core.actions import elapsed_ms, log_action
from django.db import IntegrityError, OperationalError, transaction
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
    locked = None
    for _ in range(40):
        try:
            return _locked(app_context, user_id, endpoint, cleaned, body_hash, produce)
        except IntegrityError:
            continue
        except OperationalError as exc:
            if "locked" not in str(exc).lower():
                raise
            locked = exc
            time.sleep(0.01)
    if locked is not None:
        raise locked
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
                log_action(
                    action="idempotency.reserve",
                    outcome="conflict",
                    status=409,
                    duration_ms=0,
                    error_code="idempotency_conflict",
                    error_reason="This key was already used for a different request.",
                    request=json.dumps({"endpoint": endpoint, "key": key, "payload_hash": body_hash[:12]}),
                    response='HTTP 409\n{"outcome":"conflict","error":"This key was already used for a different request."}',
                )
                raise IdempotencyProblem(
                    "This key was already used for a different request.",
                    "idempotency_conflict",
                    409,
                )
            ref = _reference(existing.body)
            log_action(
                action="idempotency.reserve",
                outcome="replay",
                status=existing.status_code,
                duration_ms=0,
                target_id=ref,
                request=json.dumps({"endpoint": endpoint, "key": key, "payload_hash": body_hash[:12]}),
                response=f"HTTP {existing.status_code}\n{json.dumps({'outcome': 'replay', 'reference': ref})}",
            )
            return existing.status_code, existing.body
        started = time.perf_counter()
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
        ref = _reference(body)
        log_action(
            action="idempotency.reserve",
            outcome="created",
            status=status,
            duration_ms=elapsed_ms(started),
            target_id=ref,
            request=json.dumps({"endpoint": endpoint, "key": key, "payload_hash": body_hash[:12]}),
            response=f"HTTP {status}\n{json.dumps({'outcome': 'created', 'reference': ref})}",
        )
        record.state = "done"
        record.status_code = status
        record.body = body
        record.save(update_fields=["state", "status_code", "body"])
        return status, body


def run_once_external(*, app_context: str, user_id: str, endpoint: str, key: str, body_hash: str, produce):
    """Idempotency guard that releases the DB lock before external HTTP calls."""
    from models.models import IdempotencyRecord

    cleaned = (key or "").strip()
    if not cleaned or len(cleaned) > 200 or any(char.isspace() for char in cleaned):
        raise IdempotencyProblem("Send an Idempotency-Key.", "validation", 400)

    started = time.perf_counter()
    record_id = None
    for _ in range(40):
        try:
            with transaction.atomic():
                existing = (
                    IdempotencyRecord.objects.select_for_update()
                    .filter(
                        app_context=app_context,
                        user_id=user_id,
                        endpoint=endpoint,
                        idempotency_key=cleaned,
                    )
                    .first()
                )
                if existing is not None:
                    if existing.payload_hash != body_hash:
                        log_action(
                            action="idempotency.reserve",
                            outcome="conflict",
                            status=409,
                            duration_ms=0,
                            error_code="idempotency_conflict",
                            error_reason="This key was already used for a different request.",
                            request=json.dumps({"endpoint": endpoint, "key": cleaned, "payload_hash": body_hash[:12]}),
                            response='HTTP 409\n{"outcome":"conflict"}',
                        )
                        raise IdempotencyProblem(
                            "This key was already used for a different request.",
                            "idempotency_conflict",
                            409,
                        )
                    if existing.state == "pending":
                        raise IdempotencyProblem(
                            "This payment request is already in progress.",
                            "idempotency_conflict",
                            409,
                        )
                    ref = _reference(existing.body)
                    log_action(
                        action="idempotency.reserve",
                        outcome="replay",
                        status=existing.status_code,
                        duration_ms=0,
                        target_id=ref,
                        request=json.dumps({"endpoint": endpoint, "key": cleaned, "payload_hash": body_hash[:12]}),
                        response=f"HTTP {existing.status_code}\n{json.dumps({'outcome': 'replay', 'reference': ref})}",
                    )
                    return existing.status_code, existing.body

                record = IdempotencyRecord.objects.create(
                    app_context=app_context,
                    user_id=user_id,
                    endpoint=endpoint,
                    idempotency_key=cleaned,
                    payload_hash=body_hash,
                    state="pending",
                    status_code=0,
                    body={},
                )
                record_id = record.pk
                break
        except IntegrityError:
            continue
        except OperationalError as exc:
            if "locked" not in str(exc).lower():
                raise
            time.sleep(0.01)

    if record_id is None:
        raise IdempotencyProblem("Could not reserve idempotency key; try again.", "server_error", 503)

    try:
        status, body = produce()
    except Exception:
        IdempotencyRecord.objects.filter(pk=record_id, state="pending").delete()
        raise

    ref = _reference(body)
    log_action(
        action="idempotency.reserve",
        outcome="created",
        status=status,
        duration_ms=elapsed_ms(started),
        target_id=ref,
        request=json.dumps({"endpoint": endpoint, "key": cleaned, "payload_hash": body_hash[:12]}),
        response=f"HTTP {status}\n{json.dumps({'outcome': 'created', 'reference': ref})}",
    )
    IdempotencyRecord.objects.filter(pk=record_id).update(state="done", status_code=status, body=body)
    return status, body


def _reference(body) -> str:
    if isinstance(body, dict) and isinstance(body.get("reference"), str):
        return body["reference"]
    return ""


def _plain(value):
    if isinstance(value, Decimal):
        return f"{value:.2f}"
    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value
