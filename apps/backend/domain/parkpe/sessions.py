"""Start a ParkPe QR parking or connect session.

HTTP caller: POST /api/v1/parkpe/sessions/initiate in api/v1/routes/parkpe.py.
App caller: apps/parkpe/features/qr-connect and features/parking, via
packages/sdk-client with X-App-Context: parkpe.
The account is the signed-in customer. The body cannot name another user.
Does not import domain/payswap. Audit shape: domain/common/audit.py.
"""

from __future__ import annotations

import hashlib

from domain.common.audit import audit_entry
from domain.common.scope import PARKPE


def initiate_session(*, user_id: str, site_code: str, bay: str, vehicle: str) -> dict:
    digest = hashlib.sha256(f"{user_id}|{site_code}|{bay}|{vehicle}".encode()).hexdigest()[:12]
    reference = f"sess-{digest}"
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
