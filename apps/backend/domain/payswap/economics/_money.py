"""Shared paise helpers for economics (no imports from commission.py)."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any

ZERO = Decimal("0")
HUNDRED = Decimal("100")
PAISE = Decimal("100")


def d(value: Any) -> Decimal:
    try:
        return Decimal(str(value).strip())
    except Exception:
        return ZERO


def to_paise(rupees: Decimal | str | float | int) -> int:
    return int((d(rupees) * PAISE).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def paise_to_rupees_str(paise: int) -> str:
    return f"{(Decimal(int(paise)) / PAISE):.2f}"
