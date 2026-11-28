"""ParkPe customer vehicles and session history.

Callers: api/v1/routes/parkpe.py. Replaces hardcoded sample vehicles in
apps/parkpe/js/screens.js and apps/parkpe/dashboard/index.html.
"""

from __future__ import annotations

import json
import re
import secrets
import time
from typing import Any

from core.actions import elapsed_ms, log_action
from django.db import IntegrityError
from models.models import CustomerVehicle, IdempotencyRecord
from rest_framework.exceptions import ValidationError

_REG_RE = re.compile(r"^[A-Z0-9]{4,16}$")


def serialize_vehicle(v: CustomerVehicle) -> dict[str, Any]:
    return {
        "vehicle_id": v.vehicle_id,
        "registration": v.registration,
        "make_model": v.make_model,
        "color": v.color,
        "fastag_linked": bool(v.fastag_linked),
        "is_primary": bool(v.is_primary),
        "created_at": v.created_at.isoformat() if v.created_at else "",
    }


def list_vehicles(user_id: str) -> list[dict[str, Any]]:
    rows = CustomerVehicle.objects.filter(user_id=user_id).order_by("-is_primary", "-created_at")
    return [serialize_vehicle(row) for row in rows]


def add_vehicle(
    user_id: str,
    *,
    registration: str,
    make_model: str = "",
    color: str = "",
    fastag_linked: bool = False,
) -> dict[str, Any]:
    started = time.perf_counter()
    reg = "".join(ch for ch in (registration or "").upper() if ch.isalnum())
    if not _REG_RE.fullmatch(reg):
        raise ValidationError(detail={"error": "Enter a valid vehicle registration number.", "code": "validation"})
    is_first = not CustomerVehicle.objects.filter(user_id=user_id).exists()
    try:
        v = CustomerVehicle.objects.create(
            vehicle_id="veh-" + secrets.token_hex(8),
            user_id=user_id,
            registration=reg,
            make_model=(make_model or "").strip()[:80],
            color=(color or "").strip()[:40],
            fastag_linked=bool(fastag_linked),
            is_primary=is_first,
        )
    except IntegrityError as exc:
        raise ValidationError(detail={"error": "This vehicle is already saved.", "code": "validation"}) from exc
    out = serialize_vehicle(v)
    log_action(
        action="parkpe.vehicle.add",
        outcome="ok",
        status=201,
        duration_ms=elapsed_ms(started),
        target_id=v.vehicle_id,
        request=json.dumps({"registration": reg}),
        response=json.dumps({"vehicle_id": v.vehicle_id}),
    )
    return out


def remove_vehicle(user_id: str, vehicle_id: str) -> dict[str, Any]:
    started = time.perf_counter()
    deleted, _ = CustomerVehicle.objects.filter(user_id=user_id, vehicle_id=vehicle_id).delete()
    if not deleted:
        raise ValidationError(detail={"error": "Vehicle not found.", "code": "validation"})
    log_action(
        action="parkpe.vehicle.remove",
        outcome="ok",
        status=200,
        duration_ms=elapsed_ms(started),
        target_id=vehicle_id,
        request=json.dumps({"vehicle_id": vehicle_id}),
        response='HTTP 200\n{"ok":true}',
    )
    return {"ok": True}


def list_customer_sessions(user_id: str) -> list[dict[str, Any]]:
    rows = IdempotencyRecord.objects.filter(
        app_context="parkpe",
        user_id=user_id,
        endpoint="/api/v1/parkpe/sessions/initiate",
        state="done",
    ).order_by("-created_at")[:30]
    out = []
    for row in rows:
        body = row.body if isinstance(row.body, dict) else {}
        out.append(
            {
                "reference": body.get("reference", ""),
                "site_code": body.get("site_code", ""),
                "bay": body.get("bay", ""),
                "vehicle": body.get("vehicle", ""),
                "state": row.desk_state or body.get("state", "initiated"),
                "created_at": row.created_at.isoformat() if row.created_at else "",
            }
        )
    return out
