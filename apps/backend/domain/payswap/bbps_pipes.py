"""BBPS provider pipe registry for fetch/pay/status.

Admin assigns pipe via DefaultServicePolicy / RetailerEntitlement (bbps_pipe).
Mobikwik ships in v1; pipe_b is entitlement-ready but refuses until configured.
"""

from __future__ import annotations

import os
from typing import Any, Callable

from rest_framework.exceptions import PermissionDenied

BBPS_PIPES = ("mobikwik", "pipe_b")
PIPE_LABELS = {
    "mobikwik": "Mobikwik",
    "pipe_b": "Pipe B (reserved)",
}


def normalize_pipe(value: str = "") -> str:
    key = str(value or "").strip().lower()
    return key if key in BBPS_PIPES else "mobikwik"


def pipe_configured(pipe: str) -> bool:
    key = normalize_pipe(pipe)
    if key == "mobikwik":
        from integrations.bbps import configured

        return bool(configured())
    if key == "pipe_b":
        return bool(
            os.environ.get("BBPS_PIPE_B_BASE_URL", "").strip()
            and (
                os.environ.get("BBPS_PIPE_B_API_KEY", "").strip()
                or os.environ.get("BBPS_PIPE_B_CLIENT_ID", "").strip()
            )
        )
    return False


def _pipe_b_unavailable(**_kwargs: Any) -> dict[str, Any]:
    return {
        "ok": False,
        "status": 503,
        "error": "Pipe B is not configured yet. Assign Mobikwik or finish Pipe B credentials.",
        "phase": "failed",
        "vendor_status": "PIPE_UNAVAILABLE",
        "transaction_id": "",
        "bill": {},
    }


def _mobikwik_fetch(**kwargs: Any) -> dict[str, Any]:
    from integrations.bbps import fetch_bill

    return fetch_bill(**kwargs)


def _mobikwik_pay(**kwargs: Any) -> dict[str, Any]:
    from integrations.bbps import pay_bill

    return pay_bill(**kwargs)


def _mobikwik_status(**kwargs: Any) -> dict[str, Any]:
    from integrations.bbps import payment_status

    return payment_status(**kwargs)


_ADAPTERS: dict[str, dict[str, Callable[..., dict[str, Any]]]] = {
    "mobikwik": {
        "fetch_bill": _mobikwik_fetch,
        "pay_bill": _mobikwik_pay,
        "payment_status": _mobikwik_status,
    },
    "pipe_b": {
        "fetch_bill": _pipe_b_unavailable,
        "pay_bill": _pipe_b_unavailable,
        "payment_status": _pipe_b_unavailable,
    },
}


def get_pipe_adapter(pipe: str) -> dict[str, Callable[..., dict[str, Any]]]:
    key = normalize_pipe(pipe)
    if not pipe_configured(key):
        raise PermissionDenied(
            detail={
                "error": f"{PIPE_LABELS.get(key, key)} is not available. Contact admin.",
                "code": "bulk_pipe_unavailable",
            }
        )
    return _ADAPTERS[key]


def pipe_fetch_bill(pipe: str, **kwargs: Any) -> dict[str, Any]:
    return get_pipe_adapter(pipe)["fetch_bill"](**kwargs)


def pipe_pay_bill(pipe: str, **kwargs: Any) -> dict[str, Any]:
    return get_pipe_adapter(pipe)["pay_bill"](**kwargs)


def pipe_payment_status(pipe: str, **kwargs: Any) -> dict[str, Any]:
    return get_pipe_adapter(pipe)["payment_status"](**kwargs)


def serialize_pipes() -> list[dict[str, Any]]:
    return [
        {
            "key": key,
            "label": PIPE_LABELS[key],
            "configured": pipe_configured(key),
        }
        for key in BBPS_PIPES
    ]
