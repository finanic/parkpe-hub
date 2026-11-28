"""Bulk BBPS: Excel upload → fetch queue → verify → wallet auto-pay.

Retailer APIs: /api/v1/payswap/bbps/bulk/*
Worker: manage.py process_bulk_bbps
Pipe + wallet only (no PG). Downstream: bbps_pipes, bbps.collect, entitlements.
"""

from __future__ import annotations

import csv
import io
import re
import secrets
import time
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from core.actions import elapsed_ms, log_action
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.http import HttpResponse
from django.utils import timezone
from domain.payswap.bbps import BbpsServiceError, collect, mask_consumer_account
from domain.payswap.bbps_pipes import pipe_configured, pipe_fetch_bill
from domain.payswap.entitlements import (
    require_bbps_bulk,
    require_bbps_biller,
    resolve_bbps_categories,
    resolve_bbps_pipe,
)
from domain.payswap.wallet import get_or_create_wallet, paise_to_rupees_str, rupees_to_paise
from integrations.bbps import find_operator
from models.models import BulkBbpsBatch, BulkBbpsRow, WalletAccount
from rest_framework.exceptions import PermissionDenied

# Cap inline pays on proceed; remainder stays queued for process_bulk_bbps.
INLINE_PAY_LIMIT = 20

_HEADER_ALIASES = {
    "biller_id": ("biller_id", "billerid", "biller", "op", "operator_id", "operator"),
    "consumer_number": ("consumer_number", "consumer", "account", "ca", "customer_id", "consumer_id"),
    "customer_mobile": ("customer_mobile", "mobile", "phone", "customer_phone"),
    "amount": ("amount", "due_amount", "bill_amount"),
    "circle": ("circle", "circle_code"),
}


def _norm_header(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower()).strip("_")


def _map_headers(headers: list[str]) -> dict[str, str]:
    mapped: dict[str, str] = {}
    normalized = {_norm_header(h): h for h in headers}
    for canonical, aliases in _HEADER_ALIASES.items():
        for alias in aliases:
            if alias in normalized:
                mapped[canonical] = normalized[alias]
                break
    for key, original in normalized.items():
        if key.startswith("ad_") and key not in mapped:
            mapped[key] = original
    return mapped


def _cell(row: dict[str, Any], headers: dict[str, str], key: str) -> str:
    src = headers.get(key)
    if not src:
        return ""
    return str(row.get(src) or "").strip()


def _parse_amount_paise(raw: str) -> int:
    text = str(raw or "").strip().replace(",", "")
    if not text:
        return 0
    try:
        return rupees_to_paise(Decimal(text))
    except (InvalidOperation, ValueError):
        return -1


def _account_norm(value: str) -> str:
    return re.sub(r"\s+", "", str(value or "").strip().upper())


def _new_batch_id() -> str:
    return "bbulk-" + secrets.token_hex(8)


def _new_row_id() -> str:
    return "brow-" + secrets.token_hex(8)


def _bill_fetch_mode(op: dict[str, Any] | None) -> str:
    if not op:
        return "MANDATORY"
    return str(op.get("bill_fetch") or "MANDATORY").strip().upper() or "MANDATORY"


def _extract_bill_fields(bill: dict[str, Any] | None) -> dict[str, Any]:
    data = bill if isinstance(bill, dict) else {}
    amount_raw = (
        data.get("amount")
        or data.get("billAmount")
        or data.get("dueamount")
        or data.get("dueAmount")
        or data.get("BillAmount")
        or ""
    )
    amount_paise = _parse_amount_paise(str(amount_raw))
    if amount_paise < 0:
        amount_paise = 0
    return {
        "due_amount_paise": amount_paise,
        "bill_date": str(data.get("billDate") or data.get("bill_date") or data.get("BillDate") or "")[:40],
        "due_date": str(data.get("dueDate") or data.get("due_date") or data.get("DueDate") or "")[:40],
        "bill_number": str(data.get("billNumber") or data.get("bill_number") or data.get("BillNumber") or "")[:80],
        "customer_name": str(data.get("customerName") or data.get("customer_name") or data.get("name") or "")[:160],
    }


def _resolve_locked_operator(*, user_id: str, op: str = "", biller_id: str = "") -> dict[str, Any]:
    """Resolve catalogue op for biller-locked template/upload. Raises BbpsServiceError / PermissionDenied."""
    raw = str(op or biller_id or "").strip()
    if not raw:
        raise BbpsServiceError("Choose a biller (op) first.", status=400, code="validation")
    found = find_operator(raw)
    if not found:
        raise BbpsServiceError("Unknown biller.", status=400, code="validation")
    require_bbps_biller(
        user_id,
        category=str(found.get("category") or ""),
        biller_id=str(found.get("biller_id") or found.get("op") or raw),
    )
    return found


MAX_TEMPLATE_ROWS = 500
MAX_TEMPLATE_BILLERS = 40


def build_template_csv(
    *,
    operator: dict[str, Any] | None = None,
    plan: list[tuple[dict[str, Any], int]] | None = None,
) -> tuple[bytes, str]:
    """CSV template. plan = [(operator, row_count), ...]. Legacy single operator still supported."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["biller_id", "consumer_number", "customer_mobile", "amount", "circle"])
    entries = plan
    if entries is None and operator is not None:
        entries = [(operator, 2)]
    if entries:
        total = 0
        names: list[str] = []
        for op_row, count in entries:
            bid = str(op_row.get("biller_id") or op_row.get("op") or "").strip()
            n = max(1, min(int(count), MAX_TEMPLATE_ROWS))
            for _ in range(n):
                writer.writerow([bid, "", "", "", ""])
                total += 1
                if total >= MAX_TEMPLATE_ROWS:
                    break
            names.append(str(op_row.get("name") or bid or "biller"))
            if total >= MAX_TEMPLATE_ROWS:
                break
        if len(names) == 1:
            safe = re.sub(r"[^A-Za-z0-9._-]+", "-", names[0])[:40].strip("-") or "biller"
            filename = f"bulk-{safe}.csv"
        else:
            filename = f"bulk-{len(names)}-billers.csv"
    else:
        writer.writerow(["TOLL00000NAT72", "24BH8017B", "9876543210", "", ""])
        filename = "payswap-bulk-bbps-template.csv"
    return buf.getvalue().encode("utf-8"), filename


def template_response(
    *,
    user_id: str = "",
    op: str = "",
    biller_id: str = "",
    plan_raw: str = "",
) -> HttpResponse:
    """CSV template. plan_raw is 'op:count,op:count' for multi-biller sheets (browser GET download)."""
    if plan_raw.strip():
        return template_plan_response(
            user_id=user_id,
            billers=[{"op": part.partition(":")[0], "count": part.partition(":")[2] or "1"} for part in plan_raw.split(",") if part.strip()],
        )
    operator = None
    if op or biller_id:
        require_bbps_bulk(user_id)
        operator = _resolve_locked_operator(user_id=user_id, op=op, biller_id=biller_id)
    body, filename = build_template_csv(operator=operator)
    resp = HttpResponse(body, content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="{filename}"'
    return resp


def template_plan_response(*, user_id: str, billers: list[dict[str, Any]]) -> HttpResponse:
    """Build a sheet from several billers, each with a requested blank-row count."""
    require_bbps_bulk(user_id)
    if not isinstance(billers, list) or not billers:
        raise BbpsServiceError("Select at least one biller and bill count.", status=400, code="validation")
    if len(billers) > MAX_TEMPLATE_BILLERS:
        raise BbpsServiceError(f"At most {MAX_TEMPLATE_BILLERS} billers per sheet.", status=400, code="validation")
    plan: list[tuple[dict[str, Any], int]] = []
    total = 0
    for item in billers:
        if not isinstance(item, dict):
            raise BbpsServiceError("Each biller entry must be an object.", status=400, code="validation")
        raw_op = str(item.get("op") or item.get("operator_id") or item.get("biller_id") or "").strip()
        try:
            count = int(item.get("count") or 0)
        except (TypeError, ValueError):
            count = 0
        if count < 1:
            raise BbpsServiceError("Bill count must be at least 1 for each selected biller.", status=400, code="validation")
        if count > MAX_TEMPLATE_ROWS:
            raise BbpsServiceError(f"Bill count cannot exceed {MAX_TEMPLATE_ROWS} per biller.", status=400, code="validation")
        total += count
        if total > MAX_TEMPLATE_ROWS:
            raise BbpsServiceError(f"Total rows cannot exceed {MAX_TEMPLATE_ROWS}.", status=400, code="validation")
        op_row = _resolve_locked_operator(user_id=user_id, op=raw_op)
        plan.append((op_row, count))
    body, filename = build_template_csv(plan=plan)
    resp = HttpResponse(body, content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="{filename}"'
    return resp


MAX_BULK_BYTES = 1_000_000


def _read_tabular(upload) -> tuple[list[str], list[dict[str, Any]]]:
    name = str(getattr(upload, "name", "") or "").lower()
    if not (name.endswith(".csv") or name.endswith(".xlsx")):
        raise BbpsServiceError("Upload a CSV or XLSX file.", status=400, code="validation")
    size = getattr(upload, "size", None)
    if size is not None and int(size) > MAX_BULK_BYTES:
        raise BbpsServiceError("Bulk file is too large.", status=400, code="validation")
    raw = upload.read(MAX_BULK_BYTES + 1)
    if len(raw) > MAX_BULK_BYTES:
        raise BbpsServiceError("Bulk file is too large.", status=400, code="validation")
    if name.endswith(".xlsx"):
        try:
            from openpyxl import load_workbook
        except ImportError as exc:
            raise BbpsServiceError(
                "Excel support requires openpyxl. Upload CSV or install openpyxl.",
                status=400,
                code="validation",
            ) from exc
        wb = load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
        ws = wb.active
        rows_iter = ws.iter_rows(values_only=True)
        try:
            header_row = next(rows_iter)
        except StopIteration:
            return [], []
        headers = [str(h or "").strip() for h in header_row]
        out_rows: list[dict[str, Any]] = []
        for values in rows_iter:
            if values is None or all(v is None or str(v).strip() == "" for v in values):
                continue
            item = {}
            for idx, key in enumerate(headers):
                if not key:
                    continue
                item[key] = "" if idx >= len(values) or values[idx] is None else values[idx]
            out_rows.append(item)
        return headers, out_rows

    text = raw.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    headers = list(reader.fieldnames or [])
    return headers, list(reader)


def create_batch_from_upload(*, user_id: str, upload, locked_op: str = "", locked_biller_id: str = "") -> dict[str, Any]:
    started = time.perf_counter()
    resolved = require_bbps_bulk(user_id)
    pipe = resolve_bbps_pipe(user_id)
    if not pipe_configured(pipe):
        raise PermissionDenied(
            detail={"error": "Your BBPS pipe is not available.", "code": "bulk_pipe_unavailable"}
        )

    locked = None
    if locked_op or locked_biller_id:
        locked = _resolve_locked_operator(user_id=user_id, op=locked_op, biller_id=locked_biller_id)

    headers, table = _read_tabular(upload)
    if not headers:
        raise BbpsServiceError("File has no header row.", status=400, code="validation")
    colmap = _map_headers(headers)
    if "consumer_number" not in colmap:
        raise BbpsServiceError("Template needs a consumer_number column.", status=400, code="validation")
    if not locked and "biller_id" not in colmap:
        raise BbpsServiceError(
            "Template needs biller_id (or op) and consumer_number columns, or choose a biller first.",
            status=400,
            code="validation",
        )
    if len(table) > 500:
        raise BbpsServiceError("Maximum 500 rows per bulk file.", status=400, code="validation")
    if not table:
        raise BbpsServiceError("File has no data rows.", status=400, code="validation")

    cats = resolve_bbps_categories(user_id)
    allowed_cats = set(cats.get("enabled_bbps_categories") or [])
    cats_unrestricted = bool(cats.get("bbps_categories_unrestricted"))
    filename = str(getattr(upload, "name", "") or "bulk.csv")[:200]
    batch_id = _new_batch_id()
    seen: set[tuple[str, str]] = set()
    row_models: list[BulkBbpsRow] = []
    locked_op_id = str((locked or {}).get("op") or "").strip()
    locked_bid = str((locked or {}).get("biller_id") or locked_op_id).strip()
    locked_name = str((locked or {}).get("name") or "").strip()
    locked_cat = str((locked or {}).get("category") or "").strip().upper()

    with transaction.atomic():
        batch = BulkBbpsBatch.objects.create(
            batch_id=batch_id,
            user_id=user_id,
            pipe=pipe,
            operator_id=locked_op_id[:32],
            biller_id=locked_bid[:64],
            biller_name=locked_name[:120],
            category=locked_cat[:80],
            source_filename=filename,
            status="fetching",
            row_count=0,
        )
        for idx, raw_row in enumerate(table, start=1):
            biller_raw = _cell(raw_row, colmap, "biller_id") if "biller_id" in colmap else ""
            account = _cell(raw_row, colmap, "consumer_number")
            mobile = _cell(raw_row, colmap, "customer_mobile")
            circle = _cell(raw_row, colmap, "circle")
            amount_paise = _parse_amount_paise(_cell(raw_row, colmap, "amount"))
            # Skip blank template placeholder rows (user only fills needed accounts).
            if not account:
                continue
            ad_params: dict[str, Any] = {}
            for key, original in colmap.items():
                if key.startswith("ad_"):
                    val = str(raw_row.get(original) or "").strip()
                    if val:
                        ad_params[key[3:] or key] = val

            parse_error = ""
            if locked is not None:
                # Stamp every row with the chosen biller; reject mismatched sheet values.
                if biller_raw:
                    sheet_op = find_operator(biller_raw)
                    sheet_id = str((sheet_op or {}).get("op") or biller_raw).strip()
                    sheet_bid = str((sheet_op or {}).get("biller_id") or biller_raw).strip()
                    if sheet_id not in {locked_op_id, locked_bid} and sheet_bid not in {locked_op_id, locked_bid}:
                        parse_error = "Row biller does not match the selected biller."
                op = locked
                operator_id = locked_op_id
                biller_id = locked_bid
                biller_name = locked_name
                category = locked_cat
            else:
                op = find_operator(biller_raw) if biller_raw else None
                operator_id = str((op or {}).get("op") or biller_raw or "").strip()
                biller_id = str((op or {}).get("biller_id") or biller_raw or "").strip()
                biller_name = str((op or {}).get("name") or biller_raw or "").strip()
                category = str((op or {}).get("category") or "").strip().upper()
                if not biller_raw:
                    parse_error = "Missing biller_id / op."
                elif not op:
                    parse_error = "Unknown biller."

            account_norm = _account_norm(account) or f"__row_{idx}__"
            fetch_mode = _bill_fetch_mode(op)

            if parse_error:
                pass
            elif not account:
                parse_error = "Missing consumer_number."
            elif category and not cats_unrestricted and category not in allowed_cats:
                parse_error = "BBPS category not enabled for this account."
            elif amount_paise < 0:
                parse_error = "Invalid amount."
            elif fetch_mode == "NOT_REQUIRED" and amount_paise <= 0:
                parse_error = "Amount required when bill fetch is not needed."

            dedupe = (operator_id or f"x{idx}", account_norm)
            if parse_error == "" and dedupe in seen:
                parse_error = "Duplicate biller + consumer in this file."
            if parse_error == "":
                seen.add(dedupe)

            if parse_error:
                fetch_state = "failed"
                pay_state = "blocked"
                fetch_error = parse_error
            elif fetch_mode == "NOT_REQUIRED":
                fetch_state = "not_required"
                pay_state = "ready"
                fetch_error = ""
            else:
                fetch_state = "pending"
                pay_state = "blocked"
                fetch_error = ""

            due_amount = amount_paise if fetch_state in {"not_required", "ok"} and amount_paise > 0 else 0
            row_models.append(
                BulkBbpsRow(
                    row_id=_new_row_id(),
                    batch=batch,
                    row_no=idx,
                    operator_id=operator_id[:32],
                    biller_id=biller_id[:64],
                    biller_name=biller_name[:120],
                    category=category[:80],
                    account=account[:120],
                    account_norm=account_norm[:120],
                    customer_mobile=mobile[:20],
                    circle=circle[:40],
                    ad_params=ad_params,
                    declared_amount_paise=max(amount_paise, 0),
                    fetch_state=fetch_state,
                    due_amount_paise=due_amount if fetch_state == "not_required" else 0,
                    pay_state=pay_state,
                    pay_amount_paise=due_amount if pay_state == "ready" else 0,
                    fetch_error=fetch_error[:240],
                    parse_error=parse_error[:240],
                    fetched_at=timezone.now() if fetch_state == "not_required" else None,
                )
            )

        if not row_models:
            raise BbpsServiceError(
                "File has no consumer rows. Add account numbers and upload again.",
                status=400,
                code="validation",
            )
        BulkBbpsRow.objects.bulk_create(row_models)
        _refresh_batch_counters(batch)

    log_action(
        action="domain.payswap.bbps.bulk.create",
        outcome="ok",
        status=201,
        duration_ms=elapsed_ms(started),
        target_id=batch_id,
        request=f"upload rows={len(row_models)} pipe={pipe} locked_op={locked_op_id or '-'}",
        response=f"HTTP 201\nbatch={batch_id} status={batch.status}",
    )
    # Process a few fetches inline so small files feel instant; worker continues the rest.
    process_fetch_queue(limit=5, batch_id=batch_id)
    return serialize_batch(batch_id, user_id=user_id)


def _refresh_batch_counters(batch: BulkBbpsBatch) -> None:
    agg = BulkBbpsRow.objects.filter(batch=batch).aggregate(
        row_count=Count("id"),
        fetch_ok=Count("id", filter=Q(fetch_state__in=["ok", "not_required"])),
        fetch_fail=Count("id", filter=Q(fetch_state="failed")),
        pay_ok=Count("id", filter=Q(pay_state="success")),
        pay_fail=Count("id", filter=Q(pay_state="failed")),
        pay_skipped=Count("id", filter=Q(pay_state="skipped")),
        fetch_due_total_paise=Sum("due_amount_paise", filter=Q(fetch_state__in=["ok", "not_required"])),
        pay_total_paise=Sum("pay_amount_paise", filter=Q(pay_state__in=["ready", "queued", "pending", "success"])),
        paid_paise=Sum("pay_amount_paise", filter=Q(pay_state="success")),
        pending_fetch=Count("id", filter=Q(fetch_state="pending")),
        pending_pay=Count("id", filter=Q(pay_state__in=["queued", "pending"])),
    )
    batch.row_count = int(agg["row_count"] or 0)
    batch.fetch_ok = int(agg["fetch_ok"] or 0)
    batch.fetch_fail = int(agg["fetch_fail"] or 0)
    batch.pay_ok = int(agg["pay_ok"] or 0)
    batch.pay_fail = int(agg["pay_fail"] or 0)
    batch.pay_skipped = int(agg["pay_skipped"] or 0)
    batch.fetch_due_total_paise = int(agg["fetch_due_total_paise"] or 0)
    batch.pay_total_paise = int(agg["pay_total_paise"] or 0)
    batch.paid_paise = int(agg["paid_paise"] or 0)
    pending_fetch = int(agg["pending_fetch"] or 0) > 0
    pending_pay = int(agg["pending_pay"] or 0) > 0
    if batch.status == "cancelled":
        pass
    elif pending_pay or batch.status == "paying":
        batch.status = "paying" if pending_pay or batch.pay_ok or batch.pay_fail else batch.status
        if not pending_pay and batch.status == "paying":
            batch.status = "completed"
    elif pending_fetch:
        batch.status = "fetching"
    elif batch.status in {"uploaded", "fetching"}:
        batch.status = "fetched"
    batch.save()


def _batch_payload(
    batch: BulkBbpsBatch,
    *,
    ready_total_paise: int = 0,
    wallet_available_paise: int | None = None,
) -> dict[str, Any]:
    wallet_paise = wallet_available_paise
    if wallet_paise is None:
        wallet_paise = int(get_or_create_wallet(batch.user_id).available_paise)
    return {
        "batch_id": batch.batch_id,
        "user_id": batch.user_id,
        "pipe": batch.pipe,
        "operator_id": getattr(batch, "operator_id", "") or "",
        "biller_id": getattr(batch, "biller_id", "") or "",
        "biller_name": getattr(batch, "biller_name", "") or "",
        "category": getattr(batch, "category", "") or "",
        "source_filename": batch.source_filename,
        "status": batch.status,
        "row_count": batch.row_count,
        "fetch_ok": batch.fetch_ok,
        "fetch_fail": batch.fetch_fail,
        "pay_ok": batch.pay_ok,
        "pay_fail": batch.pay_fail,
        "pay_skipped": batch.pay_skipped,
        "fetch_due_total": paise_to_rupees_str(batch.fetch_due_total_paise),
        "pay_total": paise_to_rupees_str(batch.pay_total_paise),
        "paid_total": paise_to_rupees_str(batch.paid_paise),
        "ready_total": paise_to_rupees_str(ready_total_paise),
        "wallet_available": paise_to_rupees_str(wallet_paise),
        "error_message": batch.error_message,
        "verified_at": batch.verified_at.isoformat() if batch.verified_at else "",
        "proceed_at": batch.proceed_at.isoformat() if batch.proceed_at else "",
        "created_at": batch.created_at.isoformat() if batch.created_at else "",
        "updated_at": batch.updated_at.isoformat() if batch.updated_at else "",
    }


def serialize_batch(batch_id: str, *, user_id: str = "", admin: bool = False) -> dict[str, Any]:
    batch = BulkBbpsBatch.objects.filter(batch_id=batch_id).first()
    if batch is None:
        raise BbpsServiceError("Batch not found.", status=404, code="validation")
    if not admin and user_id and batch.user_id != user_id:
        raise BbpsServiceError("Batch not found.", status=404, code="validation")
    ready_total = int(
        BulkBbpsRow.objects.filter(batch=batch, pay_state="ready").aggregate(total=Sum("pay_amount_paise"))["total"]
        or 0
    )
    return _batch_payload(batch, ready_total_paise=ready_total)


def list_batches(*, user_id: str = "", admin: bool = False, limit: int = 40) -> dict[str, Any]:
    qs = BulkBbpsBatch.objects.all().order_by("-id")
    if not admin:
        require_bbps_bulk(user_id)
        qs = qs.filter(user_id=user_id)
    rows = list(qs[: max(1, min(limit, 100))])
    if not rows:
        return {"batches": []}
    batch_ids = [b.id for b in rows]
    ready_map = {
        item["batch_id"]: int(item["total"] or 0)
        for item in BulkBbpsRow.objects.filter(batch_id__in=batch_ids, pay_state="ready")
        .values("batch_id")
        .annotate(total=Sum("pay_amount_paise"))
    }
    user_ids = sorted({b.user_id for b in rows})
    wallet_map = {
        w.user_id: int(w.available_paise)
        for w in WalletAccount.objects.filter(user_id__in=user_ids).only("user_id", "available_paise")
    }
    for uid in user_ids:
        if uid not in wallet_map:
            wallet_map[uid] = int(get_or_create_wallet(uid).available_paise)
    return {
        "batches": [
            _batch_payload(
                b,
                ready_total_paise=ready_map.get(b.id, 0),
                wallet_available_paise=wallet_map.get(b.user_id, 0),
            )
            for b in rows
        ]
    }


def serialize_row(row: BulkBbpsRow) -> dict[str, Any]:
    due_bucket = "none"
    due_raw = str(row.due_date or "").strip()
    if due_raw:
        parsed = None
        for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d"):
            try:
                parsed = date.fromisoformat(due_raw) if fmt == "%Y-%m-%d" and len(due_raw) == 10 and due_raw[4] == "-" else None
            except ValueError:
                parsed = None
            if parsed is None:
                try:
                    from datetime import datetime

                    parsed = datetime.strptime(due_raw[:10], fmt).date()
                except ValueError:
                    continue
            break
        if parsed is not None:
            today = timezone.localdate()
            if parsed < today:
                due_bucket = "overdue"
            elif parsed == today:
                due_bucket = "today"
            else:
                due_bucket = "upcoming"
    return {
        "row_id": row.row_id,
        "row_no": row.row_no,
        "operator_id": row.operator_id,
        "biller_id": row.biller_id,
        "biller_name": row.biller_name,
        "category": row.category,
        "account_mask": mask_consumer_account(row.account),
        "customer_mobile": row.customer_mobile,
        "circle": row.circle,
        "fetch_state": row.fetch_state,
        "due_amount": paise_to_rupees_str(row.due_amount_paise),
        "bill_date": row.bill_date,
        "due_date": row.due_date,
        "due_bucket": due_bucket,
        "bill_number": row.bill_number,
        "customer_name": row.customer_name,
        "fetch_error": row.fetch_error or row.parse_error,
        "pay_state": row.pay_state,
        "pay_amount": paise_to_rupees_str(row.pay_amount_paise),
        "bbps_reference": row.bbps_reference,
        "pay_error": row.pay_error,
        "paid_at": row.paid_at.isoformat() if row.paid_at else "",
        "fetched_at": row.fetched_at.isoformat() if row.fetched_at else "",
    }


def list_rows(
    batch_id: str,
    *,
    user_id: str = "",
    admin: bool = False,
    fetch_state: str = "",
    pay_state: str = "",
    due_bucket: str = "",
    q: str = "",
    limit: int = 200,
    offset: int = 0,
) -> dict[str, Any]:
    batch = serialize_batch(batch_id, user_id=user_id, admin=admin)
    qs = BulkBbpsRow.objects.filter(batch__batch_id=batch_id).order_by("row_no")
    if fetch_state:
        qs = qs.filter(fetch_state=fetch_state)
    if pay_state:
        qs = qs.filter(pay_state=pay_state)
    if q:
        qs = qs.filter(
            Q(biller_name__icontains=q)
            | Q(operator_id__icontains=q)
            | Q(account__icontains=q)
            | Q(bill_number__icontains=q)
            | Q(bbps_reference__icontains=q)
        )
    rows = [serialize_row(r) for r in qs[offset : offset + max(1, min(limit, 500))]]
    if due_bucket:
        rows = [r for r in rows if r.get("due_bucket") == due_bucket]
    return {"batch": batch, "rows": rows, "count": len(rows)}


def refetch_rows(batch_id: str, *, user_id: str, row_ids: list[str] | None = None) -> dict[str, Any]:
    require_bbps_bulk(user_id)
    batch = BulkBbpsBatch.objects.filter(batch_id=batch_id, user_id=user_id).first()
    if batch is None:
        raise BbpsServiceError("Batch not found.", status=404, code="validation")
    if batch.status in {"paying", "completed"}:
        raise BbpsServiceError("Cannot re-fetch after payment has started.", status=409, code="validation")
    qs = BulkBbpsRow.objects.filter(batch=batch)
    if row_ids:
        qs = qs.filter(row_id__in=row_ids)
    else:
        qs = qs.filter(fetch_state="failed")
    # Only requeue rows that failed fetch (not parse-only with missing biller) when operator exists.
    count = 0
    for row in qs:
        if row.parse_error and not row.operator_id:
            continue
        if _bill_fetch_mode(find_operator(row.operator_id or row.biller_id)) == "NOT_REQUIRED":
            continue
        row.fetch_state = "pending"
        row.fetch_error = ""
        row.pay_state = "blocked"
        row.save(update_fields=["fetch_state", "fetch_error", "pay_state", "updated_at"])
        count += 1
    batch.status = "fetching"
    batch.save(update_fields=["status", "updated_at"])
    process_fetch_queue(limit=10, batch_id=batch_id)
    log_action(
        action="domain.payswap.bbps.bulk.refetch",
        outcome="ok",
        status=200,
        duration_ms=0,
        target_id=batch_id,
        request=f"rows={count}",
        response=f"HTTP 200\nqueued={count}",
    )
    return serialize_batch(batch_id, user_id=user_id)


def proceed_batch(
    batch_id: str,
    *,
    user_id: str,
    wallet_pin: str,
    row_ids: list[str] | None = None,
    exclude_row_ids: list[str] | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    require_bbps_bulk(user_id)
    with transaction.atomic():
        batch = BulkBbpsBatch.objects.select_for_update().filter(batch_id=batch_id, user_id=user_id).first()
        if batch is None:
            raise BbpsServiceError("Batch not found.", status=404, code="validation")
        if batch.status in {"paying", "completed"}:
            return serialize_batch(batch_id, user_id=user_id)
        if BulkBbpsRow.objects.filter(batch=batch, fetch_state="pending").exists():
            raise BbpsServiceError("Wait until all fetches finish.", status=409, code="validation")

        qs = BulkBbpsRow.objects.select_for_update().filter(batch=batch, pay_state="ready")
        if row_ids:
            qs = qs.filter(row_id__in=row_ids)
        if exclude_row_ids:
            qs = qs.exclude(row_id__in=exclude_row_ids)
        rows = list(qs)
        if not rows:
            raise BbpsServiceError("No ready rows to pay.", status=400, code="validation")

        total = sum(int(r.pay_amount_paise or 0) for r in rows)
        wallet = get_or_create_wallet(user_id)
        if int(wallet.available_paise) < total:
            raise BbpsServiceError(
                f"Insufficient wallet float. Need {paise_to_rupees_str(total)}, available {paise_to_rupees_str(wallet.available_paise)}.",
                status=400,
                code="bulk_insufficient_float",
            )
        from domain.payswap.wallet import WalletError, _check_pin_locked

        pin_err = _check_pin_locked(wallet, wallet_pin)
        if pin_err is not None:
            detail = pin_err.detail if isinstance(pin_err.detail, dict) else {"error": str(pin_err)}
            raise BbpsServiceError(
                str(detail.get("error") or "Wallet PIN required."),
                status=getattr(pin_err, "status_code", 400),
                code=str(detail.get("code") or "pin_required"),
            )

        for row in rows:
            row.pay_state = "queued"
            row.save(update_fields=["pay_state", "updated_at"])
        batch.status = "paying"
        batch.verified_at = timezone.now()
        batch.proceed_at = timezone.now()
        batch.pay_total_paise = total
        batch.save(update_fields=["status", "verified_at", "proceed_at", "pay_total_paise", "updated_at"])

    # Cap inline pays; leftover queued rows need manage.py process_bulk_bbps + PIN or a later proceed.
    paid = process_pay_queue(
        limit=INLINE_PAY_LIMIT,
        batch_id=batch_id,
        wallet_pin=wallet_pin,
        user_id=user_id,
    )
    remaining_n = BulkBbpsRow.objects.filter(batch__batch_id=batch_id, pay_state="queued").count()
    log_action(
        action="domain.payswap.bbps.bulk.proceed",
        outcome="ok",
        status=200,
        duration_ms=elapsed_ms(started),
        target_id=batch_id,
        request=f"rows={len(rows)} pin=redacted",
        response=f"HTTP 200\nprocessed={paid} queued_left={remaining_n}",
    )
    return serialize_batch(batch_id, user_id=user_id)


def cancel_batch(batch_id: str, *, user_id: str) -> dict[str, Any]:
    require_bbps_bulk(user_id)
    with transaction.atomic():
        batch = BulkBbpsBatch.objects.select_for_update().filter(batch_id=batch_id, user_id=user_id).first()
        if batch is None:
            raise BbpsServiceError("Batch not found.", status=404, code="validation")
        BulkBbpsRow.objects.filter(batch=batch, fetch_state="pending").update(fetch_state="skipped", fetch_error="Cancelled")
        BulkBbpsRow.objects.filter(batch=batch, pay_state__in=["ready", "queued"]).update(
            pay_state="skipped",
            pay_error="Cancelled",
        )
        batch.status = "cancelled"
        batch.save(update_fields=["status", "updated_at"])
        _refresh_batch_counters(batch)
    return serialize_batch(batch_id, user_id=user_id)


def process_fetch_queue(*, limit: int = 20, batch_id: str = "") -> int:
    qs = BulkBbpsRow.objects.filter(fetch_state="pending").select_related("batch").order_by("id")
    if batch_id:
        qs = qs.filter(batch__batch_id=batch_id)
    claimed = list(qs[: max(1, min(limit, 100))])
    done = 0
    for row in claimed:
        batch = row.batch
        pipe = batch.pipe or resolve_bbps_pipe(batch.user_id)
        op = find_operator(row.operator_id or row.biller_id)
        try:
            if row.category or row.biller_id:
                require_bbps_biller(
                    batch.user_id,
                    category=row.category or (op or {}).get("category") or "",
                    biller_id=row.biller_id or (op or {}).get("biller_id") or "",
                )
            result = pipe_fetch_bill(
                pipe,
                operator_id=row.operator_id,
                customer_id=row.account,
                circle=row.circle,
                ad_params=row.ad_params or {},
                payment_mode="",
                op_row=op,
            )
        except Exception as exc:
            detail = getattr(exc, "detail", None)
            reason = str(detail.get("error") if isinstance(detail, dict) else exc)[:240]
            row.fetch_state = "failed"
            row.fetch_error = reason
            row.fetched_at = timezone.now()
            row.save(update_fields=["fetch_state", "fetch_error", "fetched_at", "updated_at"])
            _refresh_batch_counters(batch)
            done += 1
            continue

        if not result.get("ok"):
            row.fetch_state = "failed"
            row.fetch_error = str(result.get("error") or "Fetch failed")[:240]
            row.fetched_at = timezone.now()
            row.save(update_fields=["fetch_state", "fetch_error", "fetched_at", "updated_at"])
        else:
            fields = _extract_bill_fields(result.get("bill") or {})
            amount = int(fields["due_amount_paise"] or 0)
            if amount <= 0 and row.declared_amount_paise > 0:
                amount = int(row.declared_amount_paise)
            row.fetch_state = "ok"
            row.due_amount_paise = amount
            row.bill_date = fields["bill_date"]
            row.due_date = fields["due_date"]
            row.bill_number = fields["bill_number"]
            row.customer_name = fields["customer_name"]
            row.fetch_raw = {"bill": {k: fields[k] for k in ("bill_date", "due_date", "bill_number", "customer_name")}}
            row.fetch_error = ""
            row.fetched_at = timezone.now()
            if amount > 0:
                row.pay_state = "ready"
                row.pay_amount_paise = amount
            else:
                row.pay_state = "blocked"
                row.fetch_error = "Fetched amount is zero."
                row.fetch_state = "failed"
            row.save()
        _refresh_batch_counters(batch)
        done += 1
        log_action(
            action="domain.payswap.bbps.bulk.fetch_row",
            outcome="ok" if row.fetch_state in {"ok", "not_required"} else "error",
            status=200 if row.fetch_state in {"ok", "not_required"} else 502,
            duration_ms=0,
            target_id=row.row_id,
            request=f"batch={batch.batch_id} op={row.operator_id} account={mask_consumer_account(row.account)}",
            response=f"state={row.fetch_state}",
        )
    return done


def process_pay_queue(
    *,
    limit: int = 20,
    batch_id: str = "",
    wallet_pin: str = "",
    user_id: str = "",
) -> int:
    qs = BulkBbpsRow.objects.filter(pay_state="queued").select_related("batch").order_by("id")
    if batch_id:
        qs = qs.filter(batch__batch_id=batch_id)
    if user_id:
        qs = qs.filter(batch__user_id=user_id)
    claimed = list(qs[: max(1, min(limit, 200))])
    done = 0
    for row in claimed:
        batch = row.batch
        if not wallet_pin:
            row.pay_error = "Wallet PIN required to continue payment."
            row.save(update_fields=["pay_error", "updated_at"])
            continue
        amount = Decimal(paise_to_rupees_str(row.pay_amount_paise))
        try:
            body = collect(
                biller=row.operator_id or row.biller_id,
                account=row.account,
                amount=amount,
                user_id=batch.user_id,
                circle=row.circle,
                customer_mobile=row.customer_mobile,
                remitter_name=batch.user_id,
                payment_mode="Cash",
                payment_rail="wallet",
                wallet_pin=wallet_pin,
                idempotency_key=f"bulk:{batch.batch_id}:{row.row_id}",
                ad_params=row.ad_params or {},
                bulk_batch_id=batch.batch_id,
                bulk_row_id=row.row_id,
                pipe=batch.pipe,
            )
            state = str(body.get("state") or "")
            row.bbps_reference = str(body.get("reference") or "")[:80]
            if state == "success":
                row.pay_state = "success"
                row.pay_error = ""
                row.paid_at = timezone.now()
            elif state == "pending":
                row.pay_state = "pending"
                row.pay_error = ""
            else:
                row.pay_state = "failed"
                row.pay_error = "Payment did not succeed."
        except Exception as exc:
            detail = getattr(exc, "detail", None)
            if isinstance(detail, dict):
                reason = str(detail.get("error") or exc)
                code = str(detail.get("code") or "")
            else:
                reason = str(exc)
                code = ""
            if code == "bulk_insufficient_float" or "Insufficient" in reason:
                # Mark this and remaining queued as skipped.
                row.pay_state = "skipped"
                row.pay_error = reason[:240]
                BulkBbpsRow.objects.filter(batch=batch, pay_state="queued").exclude(pk=row.pk).update(
                    pay_state="skipped",
                    pay_error="insufficient_float",
                )
            else:
                row.pay_state = "failed"
                row.pay_error = reason[:240]
        row.save()
        _refresh_batch_counters(batch)
        done += 1
        log_action(
            action="domain.payswap.bbps.bulk.pay_row",
            outcome="ok" if row.pay_state in {"success", "pending"} else "error",
            status=200 if row.pay_state in {"success", "pending"} else 502,
            duration_ms=0,
            target_id=row.row_id,
            request=f"batch={batch.batch_id} ref={row.bbps_reference}",
            response=f"state={row.pay_state}",
        )
    return done


def export_batch_csv(batch_id: str, *, user_id: str = "", admin: bool = False) -> HttpResponse:
    data = list_rows(batch_id, user_id=user_id, admin=admin, limit=500)
    buf = io.StringIO()
    writer = csv.DictWriter(
        buf,
        fieldnames=[
            "row_no",
            "operator_id",
            "biller_name",
            "category",
            "account_mask",
            "fetch_state",
            "due_amount",
            "due_date",
            "due_bucket",
            "pay_state",
            "pay_amount",
            "bbps_reference",
            "fetch_error",
            "pay_error",
        ],
    )
    writer.writeheader()
    for row in data["rows"]:
        writer.writerow({k: row.get(k, "") for k in writer.fieldnames})
    resp = HttpResponse(buf.getvalue(), content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="bulk-bbps-{batch_id}.csv"'
    return resp


def admin_list_batches(*, limit: int = 50, q: str = "") -> dict[str, Any]:
    qs = BulkBbpsBatch.objects.all().order_by("-id")
    if q:
        qs = qs.filter(Q(user_id__icontains=q) | Q(batch_id__icontains=q) | Q(source_filename__icontains=q))
    rows = list(qs[: max(1, min(limit, 100))])
    if not rows:
        return {"batches": []}
    batch_ids = [b.id for b in rows]
    ready_map = {
        item["batch_id"]: int(item["total"] or 0)
        for item in BulkBbpsRow.objects.filter(batch_id__in=batch_ids, pay_state="ready")
        .values("batch_id")
        .annotate(total=Sum("pay_amount_paise"))
    }
    user_ids = sorted({b.user_id for b in rows})
    wallet_map = {
        w.user_id: int(w.available_paise)
        for w in WalletAccount.objects.filter(user_id__in=user_ids).only("user_id", "available_paise")
    }
    for uid in user_ids:
        if uid not in wallet_map:
            wallet_map[uid] = int(get_or_create_wallet(uid).available_paise)
    return {
        "batches": [
            _batch_payload(
                b,
                ready_total_paise=ready_map.get(b.id, 0),
                wallet_available_paise=wallet_map.get(b.user_id, 0),
            )
            for b in rows
        ]
    }
