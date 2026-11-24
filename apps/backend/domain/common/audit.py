"""Shared audit line for both products.

domain/parkpe and domain/payswap both call this. Neither imports the other.
The line is returned on the API body so apps/parkpe and apps/payswap can
show what was started. It is not the auth audit log in apps/backend/auth/store.py.
"""

from __future__ import annotations


def audit_entry(*, app_context: str, user_id: str, action: str, reference: str) -> dict:
    return {
        "app_context": app_context,
        "user_id": user_id,
        "action": action,
        "reference": reference,
    }
