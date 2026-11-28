"""One structured line for a state change under /api/v1.

Callers: api/v1/routes/support.py (the HTTP result), domain/parkpe and
domain/payswap, integrations/parking.py, integrations/bbps.py,
integrations/kaleyra.py (the SMS provider call), and core/idempotency.py.
The auth process registers set_action_sink so those lines also land in
auth/store.py service_log. The Logs screen merges that table with Django
HubAction via GET /api/v1/desk/actions (auth proxies desk/logs).
apps/parkpe/js/hub.js and apps/payswap/js/hub.js are the browser callers
of the two mounted routes. Error codes are the strings in
packages/contracts ErrorCode. Auth events on port 4600 stay in
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
_SINK = None

_FIELDS = ("request_id", "idempotency_key", "app_context", "actor", "role")
_SECRET_KEY = re.compile(
    r"(?i)(password|token|secret|cookie|otp|totp|authorization|aadhaar|cvv|pin|payload|raw|body|api[_-]?key|(^|_)sid$|^pan($|_)|_pan$)"
)
_SECRET_TEXT = re.compile(
    r"(?i)(bearer\s+\S+|auth_(?:access|refresh|mfa)=[^;\s]+|otpauth://\S+|password=\S+|otp[\s=:]+\d{4,8}|token=\S+|secret=\S+|api[_-]key[=:]\s*\S+)"
)
_CODE_TEXT = re.compile(r"\b\d{4,8}\b")
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


def set_action_sink(sink) -> None:
    """AuthApp points this at Store.remember_service. Django does not."""
    global _SINK
    _SINK = sink


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
    request: str = "",
    response: str = "",
) -> None:
    """Write one JSON object. request and response are redacted summaries.

    The OTP, API key, account SID, PAN, and message body are removed before
    the line is stored. Callers still must not pass those values on purpose.
    """
    ctx = _ACTION.get()
    mask_codes = not str(action).startswith(("payswap.", "domain.payswap.", "integration.bbps.", "parkpe.", "domain.parkpe."))
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
        "request": scrub_exchange(request, mask_codes=mask_codes),
        "response": scrub_exchange(response, mask_codes=mask_codes),
    }
    LOG.info("%s", _dump(record))
    _remember(record)


def scrub_exchange(value: str, *, mask_codes: bool = True) -> str:
    """A request or response line safe for the Logs screen. No OTP and no key."""
    import json

    if not isinstance(value, str) or not value.strip():
        return ""
    lines = []
    for line in value.splitlines():
        piece = line.strip()
        if piece[:1] in "{[":
            try:
                parsed = json.loads(piece)
            except json.JSONDecodeError:
                parsed = piece
            cleaned = redact(parsed)
            piece = cleaned if isinstance(cleaned, str) else json.dumps(cleaned, ensure_ascii=False)
        else:
            cleaned = redact(piece)
            piece = cleaned if isinstance(cleaned, str) else ""
        if mask_codes:
            piece = _CODE_TEXT.sub("[redacted]", piece)
        if piece:
            lines.append(piece)
    return "\n".join(lines)[:1000]


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


def _remember(record: dict) -> None:
    """Keep the redacted line for the operator desk.

    Django /api/v1 writes HubAction. The auth process is not Django, so
    set_action_sink stores the same line in auth/store.py service_log.
    A sink that is set is always called, including when Django is also up.
    A line written inside transaction.atomic waits for that transaction to
    commit. Auth audit events stay in store.audit and never reach this helper.
    """
    # The auth process registers a sink. Django also stores HubAction.
    # Both run when manage.py loads the auth tests in the same process.
    if _SINK is not None:
        try:
            _SINK(record)
        except Exception as exc:
            LOG.exception("action sink failed: %s", exc)
            try:
                import sys

                sys.stderr.write(f"hub.actions sink failed: {exc}\n{_dump(record)}\n")
            except Exception:
                pass
    if _django_ready():
        _remember_hub(record)


def _django_ready() -> bool:
    try:
        from django.apps import apps
    except Exception:
        return False
    return bool(apps.ready)


def _remember_hub(record: dict) -> None:
    try:
        from django.db import transaction
        from models.models import HubAction
    except Exception:
        return

    def write() -> None:
        try:
            HubAction.objects.create(
                request_id=str(record["request_id"])[:80],
                idempotency_key=str(record["idempotency_key"])[:200],
                app_context=str(record["app_context"])[:16],
                actor=str(record["actor"])[:320],
                role=str(record["role"])[:16],
                action=str(record["action"])[:80],
                target_id=str(record["target_id"])[:80],
                outcome=str(record["outcome"])[:16],
                status=int(record["status"]),
                duration_ms=max(0, int(record["duration_ms"])),
                error_code=str(record["error_code"])[:40],
                error_reason=str(record["error_reason"])[:200],
                request=str(record["request"])[:1000],
                response=str(record["response"])[:1000],
            )
        except Exception as exc:
            LOG.exception("HubAction write failed: %s", exc)
            try:
                import sys

                sys.stderr.write(f"hub.actions HubAction failed: {exc}\n{_dump(record)}\n")
            except Exception:
                pass

    try:
        if transaction.get_connection().in_atomic_block:
            transaction.on_commit(write)
        else:
            write()
    except Exception as exc:
        LOG.exception("HubAction schedule failed: %s", exc)
        try:
            import sys

            sys.stderr.write(f"hub.actions schedule failed: {exc}\n{_dump(record)}\n")
        except Exception:
            pass


def _dump(record: dict) -> str:
    import json

    return json.dumps(record, separators=(",", ":"), sort_keys=True)
