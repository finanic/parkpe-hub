"""One structured line for a state change under /api/v1.

Callers: api/v1/routes/support.py (the HTTP result), domain/parkpe and
domain/payswap, integrations/parking.py, integrations/bbps.py, and
core/idempotency.py. apps/parkpe/js/hub.js and apps/payswap/js/hub.js are
the browser callers of the two mounted routes. Error codes are the strings
in packages/contracts ErrorCode. Auth events on port 4600 stay in
apps/backend/auth/store.py audit and do not come through here.

The line has request_id, idempotency_key when the request sent one,
app_context, actor, role, action, target_id, outcome, status, and
duration_ms. redact drops tokens, cookies, OTPs, secrets, and raw bodies
before the line is written.
"""

from __future__ import annotations

import contextvars
import logging
import re
import time

LOG = logging.getLogger("hub.actions")
if not LOG.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(message)s"))
    LOG.addHandler(_handler)
    LOG.setLevel(logging.INFO)
    LOG.propagate = False

_ACTION: contextvars.ContextVar[dict] = contextvars.ContextVar("hub_action", default={})

_FIELDS = ("request_id", "idempotency_key", "app_context", "actor", "role")
_SECRET_KEY = re.compile(r"(?i)(password|token|secret|cookie|otp|totp|authorization|aadhaar|cvv|pin|payload|raw|body)")
_SECRET_TEXT = re.compile(
    r"(?i)(bearer\s+\S+|auth_(?:access|refresh|mfa)=[^;\s]+|otpauth://\S+|password=\S+|otp=\d{4,8}|token=\S+|secret=\S+)"
)
_REQUEST_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{7,79}$")


def bind_action(**updates) -> None:
    """Merge safe fields for the rest of this request. Secrets are dropped."""
    current = dict(_ACTION.get())
    for key, value in updates.items():
        if key not in _FIELDS:
            continue
        if value in (None, ""):
            continue
        cleaned = redact(value)
        if cleaned in (None, "", "[redacted]"):
            continue
        current[key] = cleaned
    _ACTION.set(current)


def reset_action() -> None:
    _ACTION.set({})


def request_id_from(header: str | None) -> str:
    """Use a caller X-Request-Id only when it cannot break the log line."""
    import uuid

    if header and _REQUEST_ID.fullmatch(header.strip()):
        return header.strip()
    return uuid.uuid4().hex


def log_action(
    *,
    action: str,
    outcome: str,
    status: int,
    duration_ms: int,
    target_id: str = "",
    error_code: str = "",
    error_reason: str = "",
) -> None:
    """Write one JSON object. Callers pass names, not the request body."""
    ctx = _ACTION.get()
    record = {
        "request_id": ctx.get("request_id") or "",
        "idempotency_key": ctx.get("idempotency_key") or "",
        "app_context": ctx.get("app_context") or "",
        "actor": ctx.get("actor") or "",
        "role": ctx.get("role") or "",
        "action": redact(action) or "",
        "target_id": redact(target_id) or "",
        "outcome": outcome,
        "status": int(status),
        "duration_ms": int(duration_ms),
        "error_code": redact(error_code) or "",
        "error_reason": redact(error_reason) or "",
    }
    LOG.info("%s", _dump(record))


def redact(value):
    """Remove secret-shaped keys and substrings. Other values pass through."""
    if isinstance(value, dict):
        cleaned = {}
        for key, item in value.items():
            if _SECRET_KEY.search(str(key)):
                continue
            cleaned[str(key)] = redact(item)
        return cleaned
    if isinstance(value, (list, tuple)):
        return [redact(item) for item in value]
    if isinstance(value, str):
        return _SECRET_TEXT.sub("[redacted]", value)
    return value


def elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


def _dump(record: dict) -> str:
    import json

    return json.dumps(record, separators=(",", ":"), sort_keys=True)
