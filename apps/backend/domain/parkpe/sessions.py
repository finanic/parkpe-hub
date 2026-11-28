"""Start a ParkPe QR parking or connect session.

HTTP caller: POST /api/v1/parkpe/sessions/initiate in api/v1/routes/parkpe.py.
App caller: apps/parkpe/features/qr-connect and features/parking, via
packages/sdk-client with X-App-Context: parkpe.
The account is the signed-in customer. The body cannot name another user.
Does not import domain/payswap. Audit shape: domain/common/audit.py.
The service line is core/actions.py action domain.parkpe.session.initiate.
"""

from __future__ import annotations

import json
import secrets
import time

from core.actions import elapsed_ms, log_action
from domain.common.audit import audit_entry
from domain.common.scope import PARKPE


def initiate_session(*, user_id: str, site_code: str, bay: str, vehicle: str) -> dict:
    started = time.perf_counter()
    reference = f"sess-{secrets.token_hex(8)}"
    log_action(
        action="domain.parkpe.session.initiate",
        outcome="ok",
        status=201,
        duration_ms=elapsed_ms(started),
        target_id=reference,
        request=json.dumps({"site_code": site_code, "bay": bay}),
        response=json.dumps({"reference": reference, "state": "initiated"}),
    )
    return {
        "site_code": site_code,
        "bay": bay,
        "vehicle": vehicle,
        "reference": reference,
        "state": "initiated",
        "audit": audit_entry(
            app_context=PARKPE,
            user_id=user_id,
            action="session.initiate",
            reference=reference,
        ),
    }
