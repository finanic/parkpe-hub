"""PaySwap unified transaction queries (BBPS, PG orders, vouchers, fund requests, wallet ledger).

Callers: api/v1/routes/payswap.py and api/v1/routes/desk.py.
"""

from __future__ import annotations

from typing import Any

from domain.payswap.wallet import paise_to_rupees_str, serialize_topup_request
from models.models import (
    BbpsTransaction,
    IdempotencyRecord,
    PgOrder,
    WalletHold,
    WalletLedgerEntry,
    WalletTopupRequest,
)

# Desk reports use success|pending|failed across rails; map to stored values.
_PG_STATE = {"success": "paid", "pending": "created", "failed": "failed"}
_TOPUP_STATE = {"success": "approved", "pending": "pending", "failed": "rejected"}
_HOLD_STATE = {"success": "captured", "pending": "active", "failed": "released"}


def serialize_bbps_tx(row: BbpsTransaction, *, hold: WalletHold | None = None) -> dict[str, Any]:
    bulk_batch_id = str(getattr(row, "bulk_batch_id", "") or "")
    out: dict[str, Any] = {
        "reference": row.reference,
        "user_id": row.user_id,
        "operator_id": row.operator_id,
        "biller": row.biller_name,
        "category": row.category,
        "account": row.account_mask,
        "amount_paise": int(row.amount_paise),
        "amount": paise_to_rupees_str(row.amount_paise),
        "fee": paise_to_rupees_str(row.fee_paise),
        "commission": paise_to_rupees_str(row.commission_paise),
        "vendor_commission": paise_to_rupees_str(int(getattr(row, "vendor_commission_paise", 0) or 0)),
        "admin_revenue": paise_to_rupees_str(int(getattr(row, "admin_revenue_paise", 0) or 0)),
        "retailer_commission": paise_to_rupees_str(int(getattr(row, "retailer_commission_paise", 0) or 0)),
        "tds": paise_to_rupees_str(int(getattr(row, "tds_paise", 0) or 0)),
        "gst": paise_to_rupees_str(int(getattr(row, "gst_paise", 0) or 0)),
        "net_commission": paise_to_rupees_str(int(row.commission_paise or 0)),
        "payment_channel": row.payment_channel,
        "payment_mode": row.payment_mode,
        "bbps_pipe": str(getattr(row, "bbps_pipe", "") or ""),
        "source": "bulk" if bulk_batch_id else "single",
        "bulk_batch_id": bulk_batch_id,
        "bulk_row_id": str(getattr(row, "bulk_row_id", "") or ""),
        "state": row.state,
        "vendor_status": row.vendor_status,
        "vendor_txn_id": row.vendor_txn_id,
        "error_message": row.error_message,
        "wallet_hold_id": row.wallet_hold_id,
        "pg_order_id": row.pg_order_id,
        "idempotency_key": row.idempotency_key,
        "last_checked_at": row.last_checked_at.isoformat() if row.last_checked_at else "",
        "created_at": row.created_at.isoformat() if row.created_at else "",
        "updated_at": row.updated_at.isoformat() if row.updated_at else "",
    }
    if hold is not None:
        out["hold_status"] = hold.status
        out["hold_resolved_at"] = hold.resolved_at.isoformat() if hold.resolved_at else ""
    return out


def list_retailer_transactions(
    user_id: str,
    *,
    service: str = "all",
    state: str = "all",
    query: str = "",
    source: str = "all",
    batch_id: str = "",
    limit: int = 50,
) -> dict[str, Any]:
    lim = max(1, min(int(limit), 200))
    q = (query or "").strip().lower()
    src = (source or "all").strip().lower()
    batch = (batch_id or "").strip()

    bbps_qs = BbpsTransaction.objects.filter(user_id=user_id).order_by("-created_at")
    if state in {"pending", "success", "failed"}:
        bbps_qs = bbps_qs.filter(state=state)
    if batch:
        bbps_qs = bbps_qs.filter(bulk_batch_id=batch)
    elif src == "bulk":
        bbps_qs = bbps_qs.exclude(bulk_batch_id="")
    elif src == "single":
        bbps_qs = bbps_qs.filter(bulk_batch_id="")
    bbps_rows = []
    for row in bbps_qs[:lim]:
        item = serialize_bbps_tx(row)
        item["service"] = "bbps"
        item["direction"] = "DR"
        if q and not (
            q in item["reference"].lower()
            or q in item["biller"].lower()
            or q in item["account"].lower()
            or q in item["vendor_txn_id"].lower()
        ):
            continue
        bbps_rows.append(item)

    pg_rows = [
        {
            "pg_order_id": row.pg_order_id,
            "purpose": row.purpose,
            "amount": paise_to_rupees_str(row.amount_paise),
            "status": row.status,
            "service_ref": row.service_ref,
            "provider_payment_id": row.provider_payment_id,
            "created_at": row.created_at.isoformat() if row.created_at else "",
        }
        for row in PgOrder.objects.filter(user_id=user_id).order_by("-created_at")[:30]
    ]

    voucher_rows = []
    if service in {"all", "vouchers"}:
        for rec in IdempotencyRecord.objects.filter(
            app_context="payswap",
            user_id=user_id,
            endpoint="/api/v1/payswap/vouchers/order",
            state="done",
        ).order_by("-created_at")[:30]:
            body = rec.body if isinstance(rec.body, dict) else {}
            voucher_rows.append(
                {
                    "service": "vouchers",
                    "direction": "DR",
                    "reference": body.get("reference", ""),
                    "biller": body.get("brand", "Voucher"),
                    "amount": str(body.get("amount", "0.00")),
                    "state": "success",
                    "payment_channel": "wallet",
                    "created_at": rec.created_at.isoformat() if rec.created_at else "",
                }
            )

    credit_rows = []
    # Credited commission is settled wallet money. It belongs on All and Success, not Pending or Failed.
    if service in {"all", "bbps"} and state in {"all", "success"}:
        for row in (
            WalletLedgerEntry.objects.select_related("wallet")
            .filter(wallet__user_id=user_id, direction="CR", entry_type__in=["COMMISSION_CR", "TDS_REFUND"])
            .order_by("-created_at", "-id")[:lim]
        ):
            label = "Commission credit" if row.entry_type == "COMMISSION_CR" else "TDS refund"
            if q and q not in f"{row.reference} {label} {row.narration or ''}".lower():
                continue
            credit_rows.append(
                {
                    "service": "commission",
                    "direction": "CR",
                    "entry_type": row.entry_type,
                    "reference": row.reference,
                    "entry_id": row.entry_id,
                    "biller": label,
                    "account": row.narration or label,
                    "amount": paise_to_rupees_str(row.amount_paise),
                    "amount_paise": int(row.amount_paise),
                    "state": "credited",
                    "payment_channel": "wallet",
                    "vendor_txn_id": "",
                    "created_at": row.created_at.isoformat() if row.created_at else "",
                }
            )

    if service == "bbps":
        all_items = bbps_rows + credit_rows
    elif service == "vouchers":
        all_items = voucher_rows
    else:
        all_items = bbps_rows + voucher_rows + credit_rows
    all_items.sort(key=lambda r: r.get("created_at", ""), reverse=True)

    return {
        "transactions": all_items[:lim],
        "bbps": bbps_rows,
        "pg_orders": pg_rows,
        "vouchers": voucher_rows,
    }


def list_admin_transactions(
    *,
    user_id: str = "",
    state: str = "all",
    channel: str = "all",
    query: str = "",
    source: str = "all",
    batch_id: str = "",
    limit: int = 200,
) -> dict[str, Any]:
    lim = max(1, min(int(limit), 500))
    uid = user_id.strip().lower() if user_id else ""
    q = (query or "").strip().lower()
    src = (source or "all").strip().lower()
    batch = (batch_id or "").strip()
    # PG reconcile stays on verify_pg_order / cron — not on every desk list paint.

    qs = BbpsTransaction.objects.all().order_by("-created_at")
    if uid:
        qs = qs.filter(user_id=uid)
    if state in {"pending", "success", "failed"}:
        qs = qs.filter(state=state)
    if channel in {"wallet", "pg"}:
        qs = qs.filter(payment_channel=channel)
    if batch:
        qs = qs.filter(bulk_batch_id=batch)
    elif src == "bulk":
        qs = qs.exclude(bulk_batch_id="")
    elif src == "single":
        qs = qs.filter(bulk_batch_id="")

    bbps_list = list(qs[:lim])
    hold_ids = [r.wallet_hold_id for r in bbps_list if r.wallet_hold_id]
    hold_map = {h.hold_id: h for h in WalletHold.objects.filter(hold_id__in=hold_ids)} if hold_ids else {}
    rows = []
    for row in bbps_list:
        item = serialize_bbps_tx(row, hold=hold_map.get(row.wallet_hold_id))
        if q and q not in " ".join([
            item["reference"],
            item["user_id"],
            item["biller"],
            item["category"],
            item["account"],
            item["vendor_txn_id"],
            item["vendor_status"],
            item["wallet_hold_id"],
            item["pg_order_id"],
        ]).lower():
            continue
        rows.append(item)

    pg_qs = PgOrder.objects.all().order_by("-created_at")
    if uid:
        pg_qs = pg_qs.filter(user_id=uid)
    if state in _PG_STATE:
        pg_qs = pg_qs.filter(status=_PG_STATE[state])
    pg_rows = []
    for row in pg_qs[:lim]:
        item = {
            "pg_order_id": row.pg_order_id,
            "user_id": row.user_id,
            "provider": row.provider,
            "purpose": row.purpose,
            "amount": paise_to_rupees_str(row.amount_paise),
            "currency": row.currency,
            "status": row.status,
            "service_ref": row.service_ref,
            "provider_order_id": row.provider_order_id,
            "provider_payment_id": row.provider_payment_id,
            "signature_verified": bool(row.signature_verified),
            "paid_at": row.paid_at.isoformat() if row.paid_at else "",
            "created_at": row.created_at.isoformat() if row.created_at else "",
            "updated_at": row.updated_at.isoformat() if row.updated_at else "",
            "meta": row.meta if isinstance(row.meta, dict) else {},
        }
        if q and q not in " ".join([
            item["pg_order_id"],
            item["user_id"],
            item["purpose"],
            item["service_ref"],
            item["provider_order_id"],
            item["provider_payment_id"],
            item["status"],
        ]).lower():
            continue
        pg_rows.append(item)

    ledger_qs = WalletLedgerEntry.objects.select_related("wallet").order_by("-created_at", "-id")
    if uid:
        ledger_qs = ledger_qs.filter(wallet__user_id=uid)
    ledger_rows = []
    for row in ledger_qs[:lim]:
        item = {
            "entry_id": row.entry_id,
            "user_id": row.wallet.user_id,
            "direction": row.direction,
            "entry_type": row.entry_type,
            "amount": paise_to_rupees_str(row.amount_paise),
            "balance_before": paise_to_rupees_str(row.balance_before_paise),
            "balance_after": paise_to_rupees_str(row.balance_after_paise),
            "held_before": paise_to_rupees_str(row.held_before_paise),
            "held_after": paise_to_rupees_str(row.held_after_paise),
            "reference": row.reference,
            "idempotency_key": row.idempotency_key,
            "actor": row.actor,
            "actor_role": row.actor_role,
            "narration": row.narration,
            "meta": row.meta if isinstance(row.meta, dict) else {},
            "created_at": row.created_at.isoformat() if row.created_at else "",
        }
        if q and q not in " ".join([
            item["entry_id"],
            item["user_id"],
            item["entry_type"],
            item["reference"],
            item["actor"],
            item["narration"],
            item["idempotency_key"],
        ]).lower():
            continue
        ledger_rows.append(item)

    topup_qs = WalletTopupRequest.objects.select_related("wallet").order_by("-created_at", "-id")
    if uid:
        topup_qs = topup_qs.filter(user_id=uid)
    if state in _TOPUP_STATE:
        topup_qs = topup_qs.filter(status=_TOPUP_STATE[state])
    topup_list = list(topup_qs[:lim])
    topup_ids = [r.request_id for r in topup_list]
    topup_ledgers = (
        {
            e.reference: e
            for e in WalletLedgerEntry.objects.filter(reference__in=topup_ids, entry_type="TOPUP_ADMIN")
        }
        if topup_ids
        else {}
    )
    topup_rows = []
    for row in topup_list:
        item = serialize_topup_request(row, wallet=row.wallet, ledger_entry=topup_ledgers.get(row.request_id))
        if q and q not in " ".join([
            item["request_id"],
            item["user_id"],
            item["utr"],
            item["mode"],
            item["remarks"],
            item["status"],
            item["reviewed_by"],
            item["review_note"],
        ]).lower():
            continue
        topup_rows.append(item)

    holds_qs = WalletHold.objects.select_related("wallet").order_by("-created_at", "-id")
    if uid:
        holds_qs = holds_qs.filter(wallet__user_id=uid)
    if state in _HOLD_STATE:
        holds_qs = holds_qs.filter(status=_HOLD_STATE[state])
    hold_rows = []
    for row in holds_qs[:lim]:
        item = {
            "hold_id": row.hold_id,
            "user_id": row.wallet.user_id,
            "reference": row.reference,
            "service": row.service,
            "amount": paise_to_rupees_str(row.amount_paise),
            "fee": paise_to_rupees_str(row.fee_paise),
            "total": paise_to_rupees_str(int(row.amount_paise) + int(row.fee_paise)),
            "status": row.status,
            "expires_at": row.expires_at.isoformat() if row.expires_at else "",
            "resolved_at": row.resolved_at.isoformat() if row.resolved_at else "",
            "created_at": row.created_at.isoformat() if row.created_at else "",
        }
        if q and q not in " ".join([
            item["hold_id"],
            item["user_id"],
            item["reference"],
            item["service"],
            item["status"],
        ]).lower():
            continue
        hold_rows.append(item)

    voucher_qs = IdempotencyRecord.objects.filter(
        app_context="payswap",
        endpoint="/api/v1/payswap/vouchers/order",
        state="done",
    ).order_by("-created_at")
    if uid:
        voucher_qs = voucher_qs.filter(user_id=uid)
    voucher_rows = []
    for rec in voucher_qs[:lim]:
        body = rec.body if isinstance(rec.body, dict) else {}
        item = {
            "reference": str(body.get("reference", "")),
            "user_id": rec.user_id,
            "brand": str(body.get("brand", "Voucher")),
            "amount": str(body.get("amount", "0.00")),
            "state": str(body.get("state") or rec.state),
            "status_code": rec.status_code,
            "idempotency_key": rec.idempotency_key,
            "created_at": rec.created_at.isoformat() if rec.created_at else "",
        }
        if q and q not in " ".join([
            item["reference"],
            item["user_id"],
            item["brand"],
            item["idempotency_key"],
        ]).lower():
            continue
        voucher_rows.append(item)

    return {
        "bbps_transactions": rows,
        "pg_orders": pg_rows,
        "ledger": ledger_rows,
        "topup_requests": topup_rows,
        "holds": hold_rows,
        "voucher_orders": voucher_rows,
    }
