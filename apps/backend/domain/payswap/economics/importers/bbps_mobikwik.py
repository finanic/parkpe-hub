"""Import Mobikwik B2B commission Excel into ServiceRateRow (service=bbps).

Also mirrors rows into legacy VendorCommissionRate for one-release compatibility.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from core.actions import elapsed_ms, log_action
from django.db import transaction
from domain.payswap.economics._money import ZERO, d, to_paise
from domain.payswap.economics.catalogue import stamp_policy_import
from models.models import ServiceRateRow, VendorCommissionRate


def _normalize_rate_type(raw: str) -> str:
    text = str(raw or "").strip().lower()
    if "percent" in text or text in {"%", "pct", "percentage"}:
        return "percent"
    return "flat"


def import_bbps_mobikwik_sheet(path: str | Path, *, actor: str = "") -> dict[str, Any]:
    started = time.perf_counter()
    file_path = Path(path).expanduser()
    if not file_path.is_file():
        raise ValueError(f"Commission sheet not found: {file_path}")

    try:
        import openpyxl
    except ImportError as exc:
        raise ValueError("openpyxl is required to import the commission sheet.") from exc

    wb = openpyxl.load_workbook(file_path, data_only=True, read_only=True)
    ws = wb.active
    upserted = 0
    skipped = 0
    source = file_path.name

    with transaction.atomic():
        for index, row in enumerate(ws.iter_rows(values_only=True), 1):
            if index == 1:
                continue
            if not row or row[0] in (None, ""):
                continue
            op_id = str(row[0]).strip()
            if op_id.endswith(".0") and op_id[:-2].isdigit():
                op_id = op_id[:-2]
            name = str(row[1] or "").strip()[:160]
            rate = d(row[2]) if row[2] not in (None, "", "#N/A") else None
            if rate is None or rate < 0:
                skipped += 1
                continue
            min_txn = d(row[3]) if row[3] not in (None, "", "#N/A") else ZERO
            category = str(row[4] or "").strip()[:80]
            bbps_raw = row[5]
            enabled = bool(bbps_raw) if not isinstance(bbps_raw, str) else bbps_raw.strip().lower() in {
                "1",
                "true",
                "yes",
                "y",
            }
            rate_type = _normalize_rate_type(str(row[6] or ""))
            min_paise = to_paise(min_txn)
            ServiceRateRow.objects.update_or_create(
                service="bbps",
                external_id=op_id,
                category=category,
                defaults={
                    "name": name,
                    "rate_value": rate,
                    "rate_type": rate_type,
                    "min_txn_paise": min_paise,
                    # Sheet column "BBPS Enabled" marks a biller, not whether commission is paid.
                    "enabled": True,
                    "source_file": source,
                    "meta": {"bbps_enabled": enabled},
                },
            )
            VendorCommissionRate.objects.update_or_create(
                operator_id=op_id,
                category=category,
                defaults={
                    "operator_name": name,
                    "rate_value": rate,
                    "rate_type": rate_type,
                    "min_txn_paise": min_paise,
                    "bbps_enabled": enabled,
                    "source_file": source,
                },
            )
            upserted += 1

    try:
        mtime = float(file_path.stat().st_mtime)
    except OSError:
        mtime = 0.0
    stamp_policy_import("bbps", mtime=mtime, actor=actor)
    body = {"upserted": upserted, "skipped": skipped, "source": source, "rates_file_mtime": mtime, "service": "bbps"}
    log_action(
        action="domain.payswap.economics.import",
        outcome="ok",
        status=200,
        duration_ms=elapsed_ms(started),
        target_id=source,
        request=json.dumps({"path": str(file_path), "actor": actor, "service": "bbps"}),
        response=json.dumps(body),
    )
    return body
