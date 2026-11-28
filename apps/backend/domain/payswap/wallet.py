"""Retailer wallet, double-entry ledger, holds, PIN security, and PG top-ups.

Callers: api/v1/routes/payswap.py, api/v1/routes/desk.py, domain/payswap/bbps.py.
Uses integer paise everywhere. Every mutation runs inside transaction.atomic()
with select_for_update() and logs via core/actions.py.
"""

from __future__ import annotations

import datetime
import json
import os
import secrets
import sqlite3
import threading
import time
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

from auth.security import hash_password, verify_password
from core.actions import elapsed_ms, log_action
from django.db import IntegrityError, OperationalError, transaction
from django.db.models import Sum
from django.utils import timezone
from domain.payswap.entitlements import get_default_policy, require_payment_rail, require_retailer_service
from integrations.payu import payu_configured
from integrations.pg import create_gateway_order, fetch_gateway_order_status, pg_configured
from models.models import (
    PgOrder,
    WalletAccount,
    WalletAdjustment,
    WalletHold,
    WalletLedgerEntry,
    WalletTopupRequest,
)
from rest_framework.exceptions import APIException

PIN_MAX_FAILS = 5
PIN_LOCK_MINUTES = 15
# Unpaid PG orders older than this are re-checked, then marked failed if still not paid.
PG_ORDER_STALE_MINUTES = max(5, int(os.environ.get("PG_ORDER_STALE_MINUTES", "30") or "30"))
_PG_RECONCILE_LOCK = threading.Lock()
_PG_RECONCILE_LAST = 0.0
_PG_RECONCILE_COOLDOWN_S = max(15, int(os.environ.get("PG_ORDER_RECONCILE_COOLDOWN_S", "60") or "60"))


def pg_stale_cutoff() -> datetime.datetime:
    return timezone.now() - datetime.timedelta(minutes=PG_ORDER_STALE_MINUTES)


def abandon_unpaid_pg_order(order: PgOrder, *, reason: str, actor: str = "system") -> PgOrder:
    """Mark a non-paid PG order failed after timeout / gateway expiry. wallet.py ↔ desk reports."""
    if order.status == "paid":
        return order
    started = time.perf_counter()
    meta = dict(order.meta) if isinstance(order.meta, dict) else {}
    meta["abandon_reason"] = reason
    meta["abandoned_at"] = timezone.now().isoformat()
    order.status = "failed"
    order.meta = meta
    order.save(update_fields=["status", "meta", "updated_at"])
    log_action(
        action="payswap.pg.order.abandon",
        outcome="ok",
        status=200,
        duration_ms=elapsed_ms(started),
        target_id=order.pg_order_id,
        request=f"actor={actor} reason={reason}",
        response=f"HTTP 200\nstatus=failed",
    )
    return order


def reconcile_stale_pg_orders(*, limit: int = 8, actor: str = "system") -> dict[str, int]:
    """Re-check aged created PG orders; settle paid ones, fail the rest.

    Called from desk transaction reports (list_admin_transactions) so the console
    stays current without a separate cron. verify_pg_order also abandons on read.
    Cooldown avoids stacking gateway calls when several desk tabs refresh at once.
    """
    global _PG_RECONCILE_LAST
    empty = {"checked": 0, "paid": 0, "failed": 0, "left_open": 0, "skipped": 0}
    if not _PG_RECONCILE_LOCK.acquire(blocking=False):
        empty["skipped"] = 1
        return empty
    try:
        now = time.monotonic()
        if now - _PG_RECONCILE_LAST < _PG_RECONCILE_COOLDOWN_S:
            empty["skipped"] = 1
            return empty
        _PG_RECONCILE_LAST = now
    finally:
        _PG_RECONCILE_LOCK.release()

    cutoff = pg_stale_cutoff()
    hard_cutoff = timezone.now() - datetime.timedelta(minutes=PG_ORDER_STALE_MINUTES * 2)
    rows = list(
        PgOrder.objects.filter(status="created", created_at__lte=cutoff).order_by("created_at")[: max(1, min(int(limit), 20))]
    )
    stats = {"checked": 0, "paid": 0, "failed": 0, "left_open": 0, "skipped": 0}
    started = time.perf_counter()
    for order in rows:
        stats["checked"] += 1
        try:
            out = verify_pg_order(order.pg_order_id)
            status = str(out.get("status") or "")
            if status == "paid":
                stats["paid"] += 1
            elif status == "failed":
                stats["failed"] += 1
            else:
                stats["left_open"] += 1
        except Exception:
            fresh = PgOrder.objects.filter(pg_order_id=order.pg_order_id).first()
            if fresh is None or fresh.status != "created":
                continue
            if fresh.created_at and fresh.created_at <= hard_cutoff:
                abandon_unpaid_pg_order(
                    fresh,
                    reason=f"unverified_after_{PG_ORDER_STALE_MINUTES * 2}m",
                    actor=actor,
                )
                stats["failed"] += 1
            else:
                stats["left_open"] += 1
    if stats["checked"]:
        log_action(
            action="payswap.pg.order.reconcile",
            outcome="ok",
            status=200,
            duration_ms=elapsed_ms(started),
            target_id=f"batch:{stats['checked']}",
            request=f"actor={actor} stale_minutes={PG_ORDER_STALE_MINUTES}",
            response=(
                f"HTTP 200\nchecked={stats['checked']} paid={stats['paid']} "
                f"failed={stats['failed']} left_open={stats['left_open']}"
            ),
        )
    return stats


class WalletError(APIException):
    def __init__(self, message: str, *, status: int = 400, code: str = "validation"):
        super().__init__(detail={"error": message, "code": code})
        self.status_code = status


def rupees_to_paise(amount: Decimal | str | int | float) -> int:
    try:
        dec = Decimal(str(amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise WalletError("Enter a valid rupee amount.", status=400, code="validation") from exc
    paise = int(dec * 100)
    if paise <= 0:
        raise WalletError("Amount must be greater than ₹0.00.", status=400, code="validation")
    return paise


def paise_to_rupees_str(paise: int) -> str:
    return f"{Decimal(int(paise)) / Decimal(100):.2f}"


def paid_rupees_match(order_paise: int, *reported: object) -> bool:
    """True only when every reported rupee amount equals the stored order."""
    present = [value for value in reported if value is not None and str(value).strip() != ""]
    if not present:
        return False
    expected = (Decimal(int(order_paise)) / Decimal(100)).quantize(Decimal("0.01"))
    for value in present:
        try:
            posted = Decimal(str(value).strip()).quantize(Decimal("0.01"))
        except (InvalidOperation, ValueError):
            return False
        if posted != expected:
            return False
    return True


def _with_lock_retry(fn):
    last_err = None
    for _ in range(30):
        try:
            return fn()
        except OperationalError as exc:
            if "locked" not in str(exc).lower():
                raise
            last_err = exc
            time.sleep(0.015)
    if last_err is not None:
        raise last_err
    return fn()


def get_or_create_wallet(user_id: str, *, app_context: str = "payswap", role: str = "retailer") -> WalletAccount:
    wallet = WalletAccount.objects.filter(app_context=app_context, user_id=user_id).first()
    if wallet is not None:
        return wallet
    policy = get_default_policy()
    try:
        wallet, _ = WalletAccount.objects.get_or_create(
            app_context=app_context,
            user_id=user_id,
            defaults={
                "role": role,
                "status": "active",
                "per_txn_limit_paise": int(policy.default_per_txn_limit_paise),
                "daily_debit_limit_paise": int(policy.default_daily_debit_limit_paise),
                "min_balance_paise": int(policy.default_min_balance_paise),
            },
        )
        return wallet
    except IntegrityError:
        return WalletAccount.objects.get(app_context=app_context, user_id=user_id)


def _today_start():
    now = timezone.localtime(timezone.now())
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def _today_debit_paise(wallet: WalletAccount) -> int:
    start = _today_start()
    captured = (
        WalletLedgerEntry.objects.filter(
            wallet=wallet,
            direction="DR",
            entry_type__in=["HOLD_CAPTURE", "DEBIT", "FEE_DR"],
            created_at__gte=start,
        ).aggregate(total=Sum("amount_paise"))["total"]
        or 0
    )
    return int(captured) + int(wallet.held_paise)


def serialize_wallet(wallet: WalletAccount) -> dict[str, Any]:
    today_used = _today_debit_paise(wallet)
    now = timezone.now()
    pin_locked = bool(wallet.pin_locked_until and wallet.pin_locked_until > now)
    return {
        "user_id": wallet.user_id,
        "currency": wallet.currency,
        "status": wallet.status,
        "freeze_reason": wallet.freeze_reason,
        "available_paise": int(wallet.available_paise),
        "held_paise": int(wallet.held_paise),
        "available": paise_to_rupees_str(wallet.available_paise),
        "held": paise_to_rupees_str(wallet.held_paise),
        "per_txn_limit_paise": int(wallet.per_txn_limit_paise),
        "per_txn_limit": paise_to_rupees_str(wallet.per_txn_limit_paise),
        "daily_debit_limit_paise": int(wallet.daily_debit_limit_paise),
        "daily_debit_limit": paise_to_rupees_str(wallet.daily_debit_limit_paise),
        "daily_used_paise": int(today_used),
        "daily_used": paise_to_rupees_str(today_used),
        "daily_remaining_paise": max(0, int(wallet.daily_debit_limit_paise) - int(today_used)),
        "min_balance_paise": int(wallet.min_balance_paise),
        "min_balance": paise_to_rupees_str(wallet.min_balance_paise),
        "has_pin": bool(wallet.wallet_pin_hash),
        "pin_locked": pin_locked,
        "pin_locked_until": wallet.pin_locked_until.isoformat() if pin_locked else "",
        "updated_at": wallet.updated_at.isoformat() if wallet.updated_at else "",
    }


def serialize_ledger_entry(entry: WalletLedgerEntry) -> dict[str, Any]:
    return {
        "entry_id": entry.entry_id,
        "direction": entry.direction,
        "entry_type": entry.entry_type,
        "amount_paise": int(entry.amount_paise),
        "amount": paise_to_rupees_str(entry.amount_paise),
        "balance_before": paise_to_rupees_str(entry.balance_before_paise),
        "balance_after": paise_to_rupees_str(entry.balance_after_paise),
        "held_before": paise_to_rupees_str(entry.held_before_paise),
        "held_after": paise_to_rupees_str(entry.held_after_paise),
        "reference": entry.reference,
        "actor": entry.actor,
        "narration": entry.narration,
        "created_at": entry.created_at.isoformat() if entry.created_at else "",
    }


def serialize_topup_request(
    row: WalletTopupRequest,
    *,
    wallet: WalletAccount | None = None,
    ledger_entry: WalletLedgerEntry | None = None,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "request_id": row.request_id,
        "user_id": row.user_id,
        "amount_paise": int(row.amount_paise),
        "amount": paise_to_rupees_str(row.amount_paise),
        "mode": row.mode,
        "utr": row.utr,
        "remarks": row.remarks,
        "status": row.status,
        "reviewed_by": row.reviewed_by,
        "review_note": row.review_note,
        "reviewed_at": row.reviewed_at.isoformat() if row.reviewed_at else "",
        "created_at": row.created_at.isoformat() if row.created_at else "",
    }
    if wallet is not None:
        out["wallet_status"] = wallet.status
        out["wallet_available"] = paise_to_rupees_str(wallet.available_paise)
        out["wallet_held"] = paise_to_rupees_str(wallet.held_paise)
        out["wallet_daily_limit"] = paise_to_rupees_str(wallet.daily_debit_limit_paise)
        out["wallet_per_txn_limit"] = paise_to_rupees_str(wallet.per_txn_limit_paise)
    if ledger_entry is not None:
        out["ledger_entry"] = {
            "entry_id": ledger_entry.entry_id,
            "direction": ledger_entry.direction,
            "entry_type": ledger_entry.entry_type,
            "balance_before": paise_to_rupees_str(ledger_entry.balance_before_paise),
            "balance_after": paise_to_rupees_str(ledger_entry.balance_after_paise),
            "created_at": ledger_entry.created_at.isoformat() if ledger_entry.created_at else "",
        }
    return out


def _pg_provider_label() -> str:
    from domain.payswap.payu_checkout import resolve_pg_provider

    return resolve_pg_provider()


def wallet_overview(user_id: str) -> dict[str, Any]:
    wallet = get_or_create_wallet(user_id)
    ledger = [
        serialize_ledger_entry(row)
        for row in WalletLedgerEntry.objects.filter(wallet=wallet).order_by("-created_at", "-id")[:30]
    ]
    topups = [
        serialize_topup_request(row)
        for row in WalletTopupRequest.objects.filter(wallet=wallet).order_by("-created_at", "-id")[:20]
    ]
    pg_orders = [
        {
            "pg_order_id": p.pg_order_id,
            "provider": p.provider,
            "purpose": p.purpose,
            "amount": paise_to_rupees_str(p.amount_paise),
            "status": p.status,
            "checkout_url": p.checkout_url or "",
            "payment_session_id": p.payment_session_id or "",
            "provider_order_id": p.provider_order_id or "",
            "provider_payment_id": p.provider_payment_id or "",
            "paid_at": p.paid_at.isoformat() if p.paid_at else "",
            "created_at": p.created_at.isoformat() if p.created_at else "",
            "updated_at": p.updated_at.isoformat() if p.updated_at else "",
        }
        for p in PgOrder.objects.filter(user_id=user_id, purpose="wallet_topup").order_by("-created_at")[:20]
    ]
    return {
        "wallet": serialize_wallet(wallet),
        "ledger": ledger,
        "topup_requests": topups,
        "pg_orders": pg_orders,
        "pg_configured": pg_configured() or payu_configured(),
        "pg_provider": _pg_provider_label(),
    }


def set_wallet_pin(user_id: str, *, new_pin: str, current_pin: str = "") -> dict[str, Any]:
    started = time.perf_counter()
    if not isinstance(new_pin, str) or not new_pin.isdigit() or not (4 <= len(new_pin) <= 6):
        raise WalletError("Wallet PIN must be 4 to 6 digits.", status=400, code="validation")
    if len(set(new_pin)) == 1 or new_pin in {"1234", "123456", "0000", "000000"}:
        raise WalletError("Choose a less predictable Wallet PIN.", status=400, code="validation")

    def _op():
        with transaction.atomic():
            wallet = WalletAccount.objects.select_for_update().get(
                pk=get_or_create_wallet(user_id).pk
            )
            if wallet.wallet_pin_hash:
                if not current_pin:
                    raise WalletError("Enter your current Wallet PIN.", status=400, code="pin_required")
                if not verify_password(current_pin, wallet.wallet_pin_hash):
                    raise WalletError("Current Wallet PIN is incorrect.", status=403, code="pin_required")
            wallet.wallet_pin_hash = hash_password(new_pin, n=2**14)
            wallet.pin_fails = 0
            wallet.pin_locked_until = None
            wallet.save(update_fields=["wallet_pin_hash", "pin_fails", "pin_locked_until", "updated_at"])
            return serialize_wallet(wallet)

    out = _with_lock_retry(_op)
    log_action(
        action="payswap.wallet.pin.set",
        outcome="ok",
        status=200,
        duration_ms=elapsed_ms(started),
        target_id=user_id,
        request="POST /api/v1/payswap/wallet/pin",
        response='HTTP 200\n{"has_pin":true}',
    )
    return {"ok": True, "wallet": out}


def _check_pin_locked(wallet: WalletAccount, pin: str) -> WalletError | None:
    if not wallet.wallet_pin_hash:
        return None
    now = timezone.now()
    if wallet.pin_locked_until and wallet.pin_locked_until > now:
        return WalletError(
            "Wallet PIN is temporarily locked after too many wrong attempts. Try again later.",
            status=423,
            code="pin_locked",
        )
    if not pin:
        return WalletError("Enter your Wallet PIN to authorize this payment.", status=400, code="pin_required")
    if not verify_password(pin, wallet.wallet_pin_hash):
        wallet.pin_fails = int(wallet.pin_fails) + 1
        if wallet.pin_fails >= PIN_MAX_FAILS:
            wallet.pin_locked_until = now + datetime.timedelta(minutes=PIN_LOCK_MINUTES)
            wallet.pin_fails = 0
        wallet.save(update_fields=["pin_fails", "pin_locked_until", "updated_at"])
        return WalletError("Wallet PIN is incorrect.", status=403, code="pin_required")
    if wallet.pin_fails or wallet.pin_locked_until:
        wallet.pin_fails = 0
        wallet.pin_locked_until = None
        wallet.save(update_fields=["pin_fails", "pin_locked_until", "updated_at"])
    return None


def reserve_hold(
    user_id: str,
    *,
    reference: str,
    service: str,
    amount_paise: int,
    fee_paise: int = 0,
    pin: str = "",
    idempotency_key: str = "",
    actor: str = "",
    narration: str = "",
) -> WalletHold:
    """Atomically verify balance/limits/PIN and move funds from available to held."""
    started = time.perf_counter()
    total_paise = int(amount_paise) + int(fee_paise)
    if amount_paise <= 0 or fee_paise < 0 or total_paise <= 0:
        raise WalletError("Amount must be greater than zero.", status=400, code="validation")

    def _op():
        pin_err: WalletError | None = None
        with transaction.atomic():
            base_wallet = get_or_create_wallet(user_id)
            wallet = WalletAccount.objects.select_for_update().get(pk=base_wallet.pk)
            if wallet.status != "active":
                raise WalletError(
                    f"Wallet is {wallet.status}. {wallet.freeze_reason or 'Contact admin.'}".strip(),
                    status=403,
                    code="wallet_frozen",
                )
            pin_err = _check_pin_locked(wallet, pin)
            if pin_err is not None:
                return pin_err
            if total_paise > int(wallet.per_txn_limit_paise):
                raise WalletError(
                    f"Amount exceeds your per-transaction limit of ₹{paise_to_rupees_str(wallet.per_txn_limit_paise)}.",
                    status=400,
                    code="limit_exceeded",
                )
            today_used = _today_debit_paise(wallet)
            if today_used + total_paise > int(wallet.daily_debit_limit_paise):
                raise WalletError(
                    f"Daily wallet debit limit of ₹{paise_to_rupees_str(wallet.daily_debit_limit_paise)} exceeded.",
                    status=400,
                    code="limit_exceeded",
                )
            if int(wallet.available_paise) - total_paise < int(wallet.min_balance_paise):
                raise WalletError(
                    f"Insufficient wallet balance. Available ₹{paise_to_rupees_str(wallet.available_paise)}.",
                    status=402,
                    code="insufficient_balance",
                )

            bal_before = int(wallet.available_paise)
            held_before = int(wallet.held_paise)
            wallet.available_paise = bal_before - total_paise
            wallet.held_paise = held_before + total_paise
            wallet.save(update_fields=["available_paise", "held_paise", "updated_at"])

            hold = WalletHold.objects.create(
                hold_id="hld-" + secrets.token_hex(10),
                wallet=wallet,
                reference=reference,
                service=service,
                amount_paise=int(amount_paise),
                fee_paise=int(fee_paise),
                status="active",
                expires_at=timezone.now() + datetime.timedelta(hours=24),
            )
            WalletLedgerEntry.objects.create(
                entry_id="led-" + secrets.token_hex(10),
                wallet=wallet,
                direction="DR",
                entry_type="HOLD_RESERVE",
                amount_paise=total_paise,
                balance_before_paise=bal_before,
                balance_after_paise=wallet.available_paise,
                held_before_paise=held_before,
                held_after_paise=wallet.held_paise,
                reference=reference,
                idempotency_key=idempotency_key,
                actor=actor or user_id,
                actor_role="retailer",
                narration=narration or f"Reserved for {service.upper()} {reference}",
                meta={"hold_id": hold.hold_id, "service": service},
            )
            return hold

    hold = _with_lock_retry(_op)
    if isinstance(hold, WalletError):
        raise hold
    log_action(
        action="payswap.wallet.hold.reserve",
        outcome="ok",
        status=200,
        duration_ms=elapsed_ms(started),
        target_id=reference,
        request=json.dumps({"reference": reference, "amount_paise": total_paise, "service": service}),
        response=json.dumps({"hold_id": hold.hold_id, "status": "active"}),
    )
    return hold


def commission_credit_reference(bill_reference: str) -> str:
    """Own reference for a commission credit, separate from the bill debit."""
    ref = str(bill_reference or "").strip()
    if ref.endswith("-CR"):
        return ref[:80]
    return f"{ref}-CR"[:80]


def capture_hold(
    hold_id: str,
    *,
    reference: str,
    actor: str = "",
    commission_paise: int = 0,
    narration: str = "",
) -> WalletAccount:
    """Capture an active hold after provider confirms success."""
    started = time.perf_counter()

    def _op():
        with transaction.atomic():
            hold = WalletHold.objects.select_for_update().get(hold_id=hold_id)
            wallet = WalletAccount.objects.select_for_update().get(pk=hold.wallet_id)
            if hold.status == "captured":
                return wallet
            if hold.status != "active":
                raise WalletError("Hold is no longer active.", status=409, code="validation")
            total = int(hold.amount_paise) + int(hold.fee_paise)
            if int(wallet.held_paise) < total:
                raise WalletError("Held balance mismatch.", status=500, code="server_error")

            bal_before = int(wallet.available_paise)
            held_before = int(wallet.held_paise)
            wallet.held_paise = held_before - total
            wallet.save(update_fields=["held_paise", "updated_at"])

            hold.status = "captured"
            hold.resolved_at = timezone.now()
            hold.save(update_fields=["status", "resolved_at"])

            WalletLedgerEntry.objects.create(
                entry_id="led-" + secrets.token_hex(10),
                wallet=wallet,
                direction="DR",
                entry_type="HOLD_CAPTURE",
                amount_paise=total,
                balance_before_paise=bal_before,
                balance_after_paise=wallet.available_paise,
                held_before_paise=held_before,
                held_after_paise=wallet.held_paise,
                reference=reference,
                actor=actor or wallet.user_id,
                actor_role="system",
                narration=narration or f"Settled {hold.service.upper()} {reference}",
                meta={"hold_id": hold.hold_id},
            )
            if commission_paise > 0:
                credit_ref = commission_credit_reference(reference)
                already = WalletLedgerEntry.objects.filter(
                    wallet=wallet,
                    entry_type="COMMISSION_CR",
                    reference__in=[credit_ref, str(reference or "")[:80]],
                ).exists()
                if not already:
                    c_before = int(wallet.available_paise)
                    wallet.available_paise = c_before + int(commission_paise)
                    wallet.save(update_fields=["available_paise", "updated_at"])
                    WalletLedgerEntry.objects.create(
                        entry_id="led-" + secrets.token_hex(10),
                        wallet=wallet,
                        direction="CR",
                        entry_type="COMMISSION_CR",
                        amount_paise=int(commission_paise),
                        balance_before_paise=c_before,
                        balance_after_paise=wallet.available_paise,
                        held_before_paise=wallet.held_paise,
                        held_after_paise=wallet.held_paise,
                        reference=credit_ref,
                        actor="system",
                        actor_role="system",
                        narration="Commission credit",
                        meta={"hold_id": hold.hold_id, "bill_reference": reference},
                    )
            return wallet

    wallet = _with_lock_retry(_op)
    log_action(
        action="payswap.wallet.hold.capture",
        outcome="ok",
        status=200,
        duration_ms=elapsed_ms(started),
        target_id=reference,
        request=json.dumps({"hold_id": hold_id, "reference": reference}),
        response=json.dumps({"available": paise_to_rupees_str(wallet.available_paise), "held": paise_to_rupees_str(wallet.held_paise)}),
    )
    return wallet


def credit_tds_refund(
    user_id: str,
    *,
    amount_paise: int,
    reference: str,
    actor: str = "",
) -> int:
    """Credit excess TDS once. The same reference does not credit again. Returns paise credited."""
    amount = int(amount_paise)
    ref = str(reference or "")[:80]
    if amount <= 0 or not ref or not user_id:
        return 0

    def _op() -> int:
        with transaction.atomic():
            wallet = WalletAccount.objects.select_for_update().get(pk=get_or_create_wallet(user_id).pk)
            if WalletLedgerEntry.objects.filter(wallet=wallet, reference=ref, entry_type="TDS_REFUND").exists():
                return 0
            before = int(wallet.available_paise)
            wallet.available_paise = before + amount
            wallet.save(update_fields=["available_paise", "updated_at"])
            WalletLedgerEntry.objects.create(
                entry_id="led-" + secrets.token_hex(10),
                wallet=wallet,
                direction="CR",
                entry_type="TDS_REFUND",
                amount_paise=amount,
                balance_before_paise=before,
                balance_after_paise=wallet.available_paise,
                held_before_paise=wallet.held_paise,
                held_after_paise=wallet.held_paise,
                reference=ref,
                actor=actor or "system",
                actor_role="admin",
                narration="TDS returned after Section 197 approval",
                meta={"user_id": user_id},
            )
            return amount

    paid = _with_lock_retry(_op)
    if paid:
        log_action(
            action="payswap.wallet.tds.refund",
            outcome="ok",
            status=200,
            duration_ms=0,
            target_id=ref,
            request=json.dumps({"user_id": user_id, "amount_paise": paid}),
            response=json.dumps({"credited_paise": paid}),
        )
    return int(paid or 0)


def credit_commission(
    user_id: str,
    *,
    amount_paise: int,
    reference: str,
    actor: str = "",
) -> int:
    """Credit retailer commission once, on its own reference. Returns paise credited."""
    amount = int(amount_paise)
    bill_ref = str(reference or "").strip()[:80]
    ref = commission_credit_reference(bill_ref)
    if amount <= 0 or not ref or not user_id:
        return 0

    def _op() -> int:
        with transaction.atomic():
            wallet = WalletAccount.objects.select_for_update().get(pk=get_or_create_wallet(user_id).pk)
            if WalletLedgerEntry.objects.filter(
                wallet=wallet, entry_type="COMMISSION_CR", reference__in=[ref, bill_ref]
            ).exists():
                return 0
            before = int(wallet.available_paise)
            wallet.available_paise = before + amount
            wallet.save(update_fields=["available_paise", "updated_at"])
            WalletLedgerEntry.objects.create(
                entry_id="led-" + secrets.token_hex(10),
                wallet=wallet,
                direction="CR",
                entry_type="COMMISSION_CR",
                amount_paise=amount,
                balance_before_paise=before,
                balance_after_paise=wallet.available_paise,
                held_before_paise=wallet.held_paise,
                held_after_paise=wallet.held_paise,
                reference=ref,
                actor=actor or "system",
                actor_role="system",
                narration="Commission credit",
                meta={"user_id": user_id, "bill_reference": bill_ref},
            )
            return amount

    paid = _with_lock_retry(_op)
    if paid:
        log_action(
            action="payswap.wallet.commission.credit",
            outcome="ok",
            status=200,
            duration_ms=0,
            target_id=ref,
            request=json.dumps({"user_id": user_id, "amount_paise": paid}),
            response=json.dumps({"credited_paise": paid}),
        )
    return int(paid or 0)


def apply_fee_debit(
    user_id: str,
    *,
    amount_paise: int,
    reference: str,
    service: str = "",
    actor: str = "",
    narration: str = "",
) -> WalletAccount:
    """Debit available float for service_charge mode (FEE_DR). Idempotent per reference."""
    started = time.perf_counter()
    fee = max(0, int(amount_paise))
    if fee <= 0:
        return get_or_create_wallet(user_id)

    def _op():
        with transaction.atomic():
            wallet = WalletAccount.objects.select_for_update().get(pk=get_or_create_wallet(user_id).pk)
            if WalletLedgerEntry.objects.filter(wallet=wallet, reference=reference, entry_type="FEE_DR").exists():
                return wallet
            if int(wallet.available_paise) < fee:
                raise WalletError("Insufficient float for service fee.", status=409, code="insufficient_funds")
            before = int(wallet.available_paise)
            wallet.available_paise = before - fee
            wallet.save(update_fields=["available_paise", "updated_at"])
            WalletLedgerEntry.objects.create(
                entry_id="led-" + secrets.token_hex(10),
                wallet=wallet,
                direction="DR",
                entry_type="FEE_DR",
                amount_paise=fee,
                balance_before_paise=before,
                balance_after_paise=wallet.available_paise,
                held_before_paise=wallet.held_paise,
                held_after_paise=wallet.held_paise,
                reference=reference,
                actor=actor or "system",
                actor_role="system",
                narration=narration or f"Service fee {service or ''} {reference}".strip(),
                meta={"service": service or ""},
            )
            return wallet

    wallet = _with_lock_retry(_op)
    log_action(
        action="payswap.wallet.fee.debit",
        outcome="ok",
        status=200,
        duration_ms=elapsed_ms(started),
        target_id=reference,
        request=json.dumps({"user_id": user_id, "amount_paise": fee, "service": service}),
        response=json.dumps({"available": paise_to_rupees_str(wallet.available_paise)}),
    )
    return wallet


def release_hold(
    hold_id: str,
    *,
    reference: str,
    actor: str = "",
    reason: str = "",
) -> WalletAccount:
    """Release an active hold back to available balance on failure/reversal."""
    started = time.perf_counter()

    def _op():
        with transaction.atomic():
            hold = WalletHold.objects.select_for_update().get(hold_id=hold_id)
            wallet = WalletAccount.objects.select_for_update().get(pk=hold.wallet_id)
            if hold.status == "released":
                return wallet
            if hold.status != "active":
                raise WalletError("Hold is already settled.", status=409, code="validation")
            total = int(hold.amount_paise) + int(hold.fee_paise)
            if int(wallet.held_paise) < total:
                raise WalletError("Held balance mismatch.", status=500, code="server_error")

            bal_before = int(wallet.available_paise)
            held_before = int(wallet.held_paise)
            wallet.held_paise = held_before - total
            wallet.available_paise = bal_before + total
            wallet.save(update_fields=["available_paise", "held_paise", "updated_at"])

            hold.status = "released"
            hold.resolved_at = timezone.now()
            hold.save(update_fields=["status", "resolved_at"])

            WalletLedgerEntry.objects.create(
                entry_id="led-" + secrets.token_hex(10),
                wallet=wallet,
                direction="CR",
                entry_type="HOLD_RELEASE",
                amount_paise=total,
                balance_before_paise=bal_before,
                balance_after_paise=wallet.available_paise,
                held_before_paise=held_before,
                held_after_paise=wallet.held_paise,
                reference=reference,
                actor=actor or wallet.user_id,
                actor_role="system",
                narration=reason or f"Auto-refund released for {reference}",
                meta={"hold_id": hold.hold_id},
            )
            return wallet

    wallet = _with_lock_retry(_op)
    log_action(
        action="payswap.wallet.hold.release",
        outcome="ok",
        status=200,
        duration_ms=elapsed_ms(started),
        target_id=reference,
        request=json.dumps({"hold_id": hold_id, "reference": reference}),
        response=json.dumps({"available": paise_to_rupees_str(wallet.available_paise), "held": paise_to_rupees_str(wallet.held_paise)}),
    )
    return wallet


def submit_topup_request(
    user_id: str,
    *,
    amount_paise: int,
    mode: str,
    utr: str,
    remarks: str = "",
) -> dict[str, Any]:
    started = time.perf_counter()
    require_retailer_service(user_id, "wallet")
    clean_utr = " ".join((utr or "").strip().upper().split())
    if len(clean_utr) < 6 or len(clean_utr) > 64:
        raise WalletError("Enter a valid UTR / bank reference (6-64 characters).", status=400, code="validation")
    if mode not in {"BANK_TRANSFER", "UPI"}:
        raise WalletError("Mode must be BANK_TRANSFER or UPI.", status=400, code="validation")
    if amount_paise < 100 or amount_paise > 50_000_000:
        raise WalletError("Top-up amount must be between ₹1.00 and ₹5,00,000.00.", status=400, code="validation")

    wallet = get_or_create_wallet(user_id)
    if wallet.status != "active":
        raise WalletError("Wallet is frozen. Contact admin.", status=403, code="wallet_frozen")

    try:
        with transaction.atomic():
            row = WalletTopupRequest.objects.create(
                request_id="top-" + secrets.token_hex(8),
                wallet=wallet,
                user_id=user_id,
                amount_paise=amount_paise,
                mode=mode,
                utr=clean_utr,
                remarks=(remarks or "").strip()[:200],
                status="pending",
            )
    except IntegrityError as exc:
        raise WalletError("This UTR reference has already been submitted.", status=409, code="validation") from exc

    out = serialize_topup_request(row)
    log_action(
        action="payswap.wallet.topup.request",
        outcome="ok",
        status=201,
        duration_ms=elapsed_ms(started),
        target_id=row.request_id,
        request=json.dumps({"mode": mode, "utr": clean_utr, "amount_paise": amount_paise}),
        response=json.dumps({"request_id": row.request_id, "status": "pending"}),
    )
    return out


def review_topup_request(
    request_id: str,
    *,
    decision: str,
    admin_email: str,
    note: str = "",
) -> dict[str, Any]:
    started = time.perf_counter()
    if decision not in {"approve", "reject"}:
        raise WalletError("Decision must be approve or reject.", status=400, code="validation")

    def _op():
        with transaction.atomic():
            req_row = WalletTopupRequest.objects.select_for_update().get(request_id=request_id)
            if req_row.status != "pending":
                raise WalletError(f"Request is already {req_row.status}.", status=409, code="validation")
            wallet = WalletAccount.objects.select_for_update().get(pk=req_row.wallet_id)
            req_row.reviewed_by = admin_email
            req_row.review_note = (note or "").strip()[:200]
            req_row.reviewed_at = timezone.now()

            if decision == "approve":
                if wallet.status != "active":
                    raise WalletError("Cannot credit a frozen/closed wallet.", status=400, code="wallet_frozen")
                bal_before = int(wallet.available_paise)
                wallet.available_paise = bal_before + int(req_row.amount_paise)
                wallet.save(update_fields=["available_paise", "updated_at"])
                req_row.status = "approved"
                req_row.save(update_fields=["status", "reviewed_by", "review_note", "reviewed_at"])
                WalletLedgerEntry.objects.create(
                    entry_id="led-" + secrets.token_hex(10),
                    wallet=wallet,
                    direction="CR",
                    entry_type="TOPUP_ADMIN",
                    amount_paise=int(req_row.amount_paise),
                    balance_before_paise=bal_before,
                    balance_after_paise=wallet.available_paise,
                    held_before_paise=wallet.held_paise,
                    held_after_paise=wallet.held_paise,
                    reference=req_row.request_id,
                    actor=admin_email,
                    actor_role="admin",
                    narration=f"Float top-up approved (UTR {req_row.utr})",
                    meta={"utr": req_row.utr, "mode": req_row.mode},
                )
            else:
                req_row.status = "rejected"
                req_row.save(update_fields=["status", "reviewed_by", "review_note", "reviewed_at"])

            return serialize_topup_request(req_row), serialize_wallet(wallet)

    try:
        topup_out, wallet_out = _with_lock_retry(_op)
    except WalletTopupRequest.DoesNotExist as exc:
        raise WalletError("Top-up request not found.", status=404, code="validation") from exc

    log_action(
        action=f"desk.wallet.topup.{decision}",
        outcome="ok",
        status=200,
        duration_ms=elapsed_ms(started),
        target_id=request_id,
        request=json.dumps({"request_id": request_id, "decision": decision}),
        response=json.dumps({"status": topup_out["status"], "available": wallet_out["available"]}),
    )
    return {"topup": topup_out, "wallet": wallet_out}


# Above this, a second admin must approve when more than one admin can sign in.
ADJUST_SECOND_ADMIN_PAISE = 1_000_000


def _signing_admin_count() -> int:
    """How many admin rows exist in auth.sqlite. Missing file counts as one."""
    from pathlib import Path

    data = Path(os.environ.get("AUTH_DATA_DIR", Path(__file__).resolve().parents[2] / "data"))
    path = data / "auth.sqlite"
    if not path.is_file():
        return 1
    try:
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            row = con.execute("SELECT COUNT(*) FROM users WHERE role = 'admin'").fetchone()
        finally:
            con.close()
    except sqlite3.Error:
        return 1
    return int(row[0] or 0) if row else 0


def _adjustment_payload(row: WalletAdjustment) -> dict[str, Any]:
    return {
        "adjustment_id": row.adjustment_id,
        "user_id": row.user_id,
        "direction": row.direction,
        "amount_paise": int(row.amount_paise),
        "amount": paise_to_rupees_str(row.amount_paise),
        "reason": row.reason,
        "status": row.status,
        "requested_by": row.requested_by,
        "reviewed_by": row.reviewed_by,
    }


def pending_wallet_adjustments(user_id: str = "") -> list[dict[str, Any]]:
    qs = WalletAdjustment.objects.filter(status="pending").order_by("-created_at")
    if user_id:
        qs = qs.filter(user_id=user_id)
    return [_adjustment_payload(row) for row in qs[:50]]


def admin_adjust_wallet(
    user_id: str,
    *,
    direction: str,
    amount_paise: int,
    reason: str,
    admin_email: str,
    idempotency_key: str = "",
    apply_queued: bool = False,
) -> dict[str, Any]:
    started = time.perf_counter()
    if direction not in {"CR", "DR"}:
        raise WalletError("Direction must be CR or DR.", status=400, code="validation")
    clean_reason = (reason or "").strip()[:200]
    if len(clean_reason) < 4:
        raise WalletError("Enter a clear reason (at least 4 characters).", status=400, code="validation")
    if amount_paise <= 0 or amount_paise > 50_000_000:
        raise WalletError("Adjustment amount must be between ₹0.01 and ₹5,00,000.00.", status=400, code="validation")
    key = (idempotency_key or "").strip()
    if not key or len(key) > 200 or any(char.isspace() for char in key):
        raise WalletError("Send an Idempotency-Key.", status=400, code="validation")

    prior = WalletLedgerEntry.objects.filter(idempotency_key=key, entry_type="ADMIN_ADJUSTMENT").first()
    if prior is not None:
        if prior.direction != direction or int(prior.amount_paise) != int(amount_paise) or prior.wallet.user_id != user_id:
            raise WalletError("This Idempotency-Key was already used for a different adjustment.", status=409, code="idempotency_conflict")
        return {"wallet": serialize_wallet(prior.wallet), "entry": serialize_ledger_entry(prior), "replay": True}

    queued = WalletAdjustment.objects.filter(idempotency_key=key).first()
    if queued is not None and not apply_queued:
        if queued.user_id != user_id or queued.direction != direction or int(queued.amount_paise) != int(amount_paise):
            raise WalletError("This Idempotency-Key was already used for a different adjustment.", status=409, code="idempotency_conflict")
        return {"pending": queued.status == "pending", "adjustment": _adjustment_payload(queued), "replay": True}

    if not apply_queued and amount_paise > ADJUST_SECOND_ADMIN_PAISE and _signing_admin_count() >= 2:
        row = WalletAdjustment.objects.create(
            adjustment_id="wadj-" + secrets.token_hex(8),
            user_id=user_id,
            direction=direction,
            amount_paise=amount_paise,
            reason=clean_reason,
            idempotency_key=key,
            status="pending",
            requested_by=admin_email,
        )
        log_action(
            action="desk.wallet.adjust.queue",
            outcome="ok",
            status=200,
            duration_ms=elapsed_ms(started),
            target_id=row.adjustment_id,
            request=json.dumps({"user_id": user_id, "direction": direction, "amount_paise": amount_paise}),
            response=json.dumps({"status": "pending", "adjustment_id": row.adjustment_id}),
        )
        return {"pending": True, "adjustment": _adjustment_payload(row)}

    ref = "adj-" + secrets.token_hex(8)

    def _op():
        with transaction.atomic():
            base = get_or_create_wallet(user_id)
            wallet = WalletAccount.objects.select_for_update().get(pk=base.pk)
            again = WalletLedgerEntry.objects.filter(wallet=wallet, idempotency_key=key, entry_type="ADMIN_ADJUSTMENT").first()
            if again is not None:
                return serialize_wallet(wallet), serialize_ledger_entry(again)
            bal_before = int(wallet.available_paise)
            if direction == "DR" and bal_before < amount_paise:
                raise WalletError(
                    f"Cannot debit ₹{paise_to_rupees_str(amount_paise)}; available is ₹{paise_to_rupees_str(bal_before)}.",
                    status=400,
                    code="insufficient_balance",
                )
            wallet.available_paise = bal_before + amount_paise if direction == "CR" else bal_before - amount_paise
            wallet.save(update_fields=["available_paise", "updated_at"])
            entry = WalletLedgerEntry.objects.create(
                entry_id="led-" + secrets.token_hex(10),
                wallet=wallet,
                direction=direction,
                entry_type="ADMIN_ADJUSTMENT",
                amount_paise=amount_paise,
                balance_before_paise=bal_before,
                balance_after_paise=wallet.available_paise,
                held_before_paise=wallet.held_paise,
                held_after_paise=wallet.held_paise,
                reference=ref,
                idempotency_key=key,
                actor=admin_email,
                actor_role="admin",
                narration=clean_reason,
                meta={"admin": admin_email},
            )
            return serialize_wallet(wallet), serialize_ledger_entry(entry)

    wallet_out, entry_out = _with_lock_retry(_op)
    log_action(
        action="desk.wallet.adjust",
        outcome="ok",
        status=200,
        duration_ms=elapsed_ms(started),
        target_id=user_id,
        request=json.dumps({"user_id": user_id, "direction": direction, "amount_paise": amount_paise}),
        response=json.dumps({"entry_id": entry_out["entry_id"], "available": wallet_out["available"]}),
    )
    return {"wallet": wallet_out, "entry": entry_out}


def review_wallet_adjustment(
    adjustment_id: str,
    *,
    decision: str,
    admin_email: str,
    note: str = "",
) -> dict[str, Any]:
    """A different admin applies or rejects a queued large adjustment."""
    started = time.perf_counter()
    choice = (decision or "").strip().lower()
    if choice not in {"approve", "reject"}:
        raise WalletError("Decision must be approve or reject.", status=400, code="validation")
    row = WalletAdjustment.objects.filter(adjustment_id=adjustment_id).first()
    if row is None:
        raise WalletError("Adjustment not found.", status=404, code="validation")
    if row.status != "pending":
        return {"pending": False, "adjustment": _adjustment_payload(row), "replay": True}
    if row.requested_by == admin_email:
        raise WalletError("A different admin has to approve this adjustment.", status=403, code="forbidden_app")
    if choice == "reject":
        row.status = "rejected"
        row.reviewed_by = admin_email
        row.review_note = (note or "").strip()[:200]
        row.reviewed_at = timezone.now()
        row.save(update_fields=["status", "reviewed_by", "review_note", "reviewed_at"])
        log_action(
            action="desk.wallet.adjust.reject",
            outcome="ok",
            status=200,
            duration_ms=elapsed_ms(started),
            target_id=row.adjustment_id,
            request=json.dumps({"adjustment_id": adjustment_id}),
            response=json.dumps({"status": "rejected"}),
        )
        return {"pending": False, "adjustment": _adjustment_payload(row)}
    applied = admin_adjust_wallet(
        row.user_id,
        direction=row.direction,
        amount_paise=int(row.amount_paise),
        reason=row.reason,
        admin_email=admin_email,
        idempotency_key=row.idempotency_key,
        apply_queued=True,
    )
    row.status = "applied"
    row.reviewed_by = admin_email
    row.review_note = (note or "").strip()[:200]
    row.reviewed_at = timezone.now()
    row.save(update_fields=["status", "reviewed_by", "review_note", "reviewed_at"])
    log_action(
        action="desk.wallet.adjust.approve",
        outcome="ok",
        status=200,
        duration_ms=elapsed_ms(started),
        target_id=row.adjustment_id,
        request=json.dumps({"adjustment_id": adjustment_id, "amount_paise": int(row.amount_paise)}),
        response=json.dumps({"status": "applied"}),
    )
    return {"pending": False, "adjustment": _adjustment_payload(row), **applied}


def admin_update_wallet_controls(
    user_id: str,
    *,
    status: str | None = None,
    freeze_reason: str | None = None,
    per_txn_limit_paise: int | None = None,
    daily_debit_limit_paise: int | None = None,
    min_balance_paise: int | None = None,
    reset_pin: bool = False,
    admin_email: str = "",
) -> dict[str, Any]:
    started = time.perf_counter()

    def _op():
        with transaction.atomic():
            base = get_or_create_wallet(user_id)
            wallet = WalletAccount.objects.select_for_update().get(pk=base.pk)
            if status in {"active", "frozen", "closed"}:
                wallet.status = status
                if status == "active":
                    wallet.freeze_reason = ""
            if freeze_reason is not None:
                wallet.freeze_reason = freeze_reason.strip()[:200]
            if per_txn_limit_paise is not None and per_txn_limit_paise >= 0:
                wallet.per_txn_limit_paise = int(per_txn_limit_paise)
            if daily_debit_limit_paise is not None and daily_debit_limit_paise >= 0:
                wallet.daily_debit_limit_paise = int(daily_debit_limit_paise)
            if min_balance_paise is not None and min_balance_paise >= 0:
                wallet.min_balance_paise = int(min_balance_paise)
            if reset_pin:
                wallet.wallet_pin_hash = ""
                wallet.pin_fails = 0
                wallet.pin_locked_until = None
            wallet.save()
            return serialize_wallet(wallet)

    out = _with_lock_retry(_op)
    log_action(
        action="desk.wallet.controls.update",
        outcome="ok",
        status=200,
        duration_ms=elapsed_ms(started),
        target_id=user_id,
        request=json.dumps({"user_id": user_id, "status": status, "reset_pin": reset_pin}),
        response=json.dumps({"status": out["status"], "daily_limit": out["daily_debit_limit"]}),
    )
    return out


def create_pg_topup_order(
    user_id: str,
    *,
    amount_paise: int,
    customer_phone: str = "",
    provider: str = "",
) -> dict[str, Any]:
    started = time.perf_counter()
    require_retailer_service(user_id, "wallet")
    require_payment_rail(user_id, "pg", for_topup=True)
    wallet = get_or_create_wallet(user_id)
    if wallet.status != "active":
        raise WalletError("Wallet is frozen. Contact admin.", status=403, code="wallet_frozen")
    if amount_paise < 100 or amount_paise > 50_000_000:
        raise WalletError("Amount must be between ₹1.00 and ₹5,00,000.00.", status=400, code="validation")

    from domain.payswap.payu_checkout import initiate_payu_checkout, pick_provider

    chosen = pick_provider(prefer=provider)
    pg_order_id = "pgw-" + secrets.token_hex(8)

    if chosen == "payu":
        phone = "".join(ch for ch in (customer_phone or "") if ch.isdigit())[-10:] or "9999999999"
        order = PgOrder.objects.create(
            pg_order_id=pg_order_id,
            provider="payu",
            purpose="wallet_topup",
            user_id=user_id,
            amount_paise=amount_paise,
            status="created",
            meta={
                "firstname": user_id.split("@")[0] or "Retailer",
                "email": user_id,
                "phone": phone,
                "productinfo": "PaySwap wallet top-up",
            },
        )
        checkout = initiate_payu_checkout(order.pg_order_id, user_id=user_id)
        log_action(
            action="payswap.pg.topup.create",
            outcome="ok",
            status=201,
            duration_ms=elapsed_ms(started),
            target_id=pg_order_id,
            request=json.dumps({"amount_paise": amount_paise, "provider": "payu"}),
            response=json.dumps({"pg_order_id": pg_order_id, "status": "created"}),
        )
        return {
            "pg_order_id": order.pg_order_id,
            "purpose": order.purpose,
            "amount": paise_to_rupees_str(order.amount_paise),
            "provider": "payu",
            "action": checkout["action"],
            "params": checkout["params"],
            "payment_session_id": "",
            "checkout_url": "",
            "status": order.status,
        }

    gw = create_gateway_order(
        order_id=pg_order_id,
        amount_paise=amount_paise,
        customer_id=user_id,
        customer_email=user_id,
        customer_phone=customer_phone,
        note="PaySwap wallet top-up",
    )
    if not gw["ok"]:
        raise WalletError(gw["error"], status=gw["status"], code="server_error")

    order = PgOrder.objects.create(
        pg_order_id=pg_order_id,
        provider="cashfree",
        purpose="wallet_topup",
        user_id=user_id,
        amount_paise=amount_paise,
        status="created",
        provider_order_id=gw["provider_order_id"],
        payment_session_id=gw["payment_session_id"],
        checkout_url=gw["checkout_url"],
    )
    log_action(
        action="payswap.pg.topup.create",
        outcome="ok",
        status=201,
        duration_ms=elapsed_ms(started),
        target_id=pg_order_id,
        request=json.dumps({"amount_paise": amount_paise, "provider": "cashfree"}),
        response=json.dumps({"pg_order_id": pg_order_id, "status": "created"}),
    )
    return {
        "pg_order_id": order.pg_order_id,
        "purpose": order.purpose,
        "amount": paise_to_rupees_str(order.amount_paise),
        "provider": "cashfree",
        "payment_session_id": order.payment_session_id,
        "checkout_url": order.checkout_url,
        "cashfree_mode": str(gw.get("cashfree_mode") or "sandbox"),
        "status": order.status,
    }


def apply_pg_topup_paid(
    pg_order_id: str,
    *,
    provider_payment_id: str = "",
    signature_verified: bool = False,
    paid_amount: str = "",
) -> dict[str, Any]:
    """Credit wallet only after a verified PG path and matching paid amount.

    signature_verified defaults False so a future caller cannot credit by
    omitting the flag. Webhook, PayU settle, and server verify must pass True.
    """
    started = time.perf_counter()

    def _op():
        with transaction.atomic():
            order = PgOrder.objects.select_for_update().get(pg_order_id=pg_order_id)
            if order.purpose != "wallet_topup":
                raise WalletError("Order is not a wallet top-up.", status=400, code="validation")
            base = get_or_create_wallet(order.user_id)
            wallet = WalletAccount.objects.select_for_update().get(pk=base.pk)
            if order.status == "paid":
                return order, wallet
            if not signature_verified:
                raise WalletError("Payment signature was not verified.", status=400, code="validation")
            if not paid_rupees_match(int(order.amount_paise), paid_amount):
                raise WalletError("The paid amount does not match this order.", status=400, code="validation")
            order.status = "paid"
            order.signature_verified = True
            order.provider_payment_id = provider_payment_id or order.provider_payment_id
            order.paid_at = timezone.now()
            order.save(update_fields=["status", "signature_verified", "provider_payment_id", "paid_at", "updated_at"])

            bal_before = int(wallet.available_paise)
            wallet.available_paise = bal_before + int(order.amount_paise)
            wallet.save(update_fields=["available_paise", "updated_at"])

            WalletLedgerEntry.objects.create(
                entry_id="led-" + secrets.token_hex(10),
                wallet=wallet,
                direction="CR",
                entry_type="TOPUP_PG",
                amount_paise=int(order.amount_paise),
                balance_before_paise=bal_before,
                balance_after_paise=wallet.available_paise,
                held_before_paise=wallet.held_paise,
                held_after_paise=wallet.held_paise,
                reference=order.pg_order_id,
                actor=order.user_id,
                actor_role="retailer",
                narration=f"PG wallet top-up ({order.pg_order_id})",
                meta={"provider_payment_id": order.provider_payment_id},
            )
            return order, wallet

    order, wallet = _with_lock_retry(_op)
    log_action(
        action="payswap.pg.topup.paid",
        outcome="ok",
        status=200,
        duration_ms=elapsed_ms(started),
        target_id=pg_order_id,
        request=json.dumps({"pg_order_id": pg_order_id}),
        response=json.dumps({"available": paise_to_rupees_str(wallet.available_paise)}),
    )
    return {
        "pg_order_id": order.pg_order_id,
        "status": order.status,
        "wallet": serialize_wallet(wallet),
    }


def verify_pg_order(pg_order_id: str, *, user_id: str = "") -> dict[str, Any]:
    """Check gateway status on server; settle wallet topup or direct BBPS.

    Retailer routes must pass the actor user_id (ownership 404). Empty user_id
    is only for system reconcile / PayU verify paths that already authenticated
    the order by provider id or webhook hash.
    """
    order = PgOrder.objects.filter(pg_order_id=pg_order_id).first()
    if order is None:
        raise WalletError("Payment order not found.", status=404, code="validation")
    if user_id and order.user_id != user_id:
        raise WalletError("Payment order not found.", status=404, code="validation")
    if order.status == "paid" and order.purpose == "wallet_topup":
        wallet = get_or_create_wallet(order.user_id)
        return {"pg_order_id": order.pg_order_id, "status": "paid", "purpose": order.purpose, "wallet": serialize_wallet(wallet)}

    if order.provider == "payu":
        from domain.payswap.payu_checkout import verify_payu_order

        return verify_payu_order(order.pg_order_id, user_id=user_id)

    gw = fetch_gateway_order_status(order_id=order.pg_order_id)
    if not gw["ok"]:
        if order.status == "created" and order.created_at and order.created_at <= pg_stale_cutoff():
            # Gateway unreachable after payment window — do not leave Awaiting forever.
            hard = timezone.now() - datetime.timedelta(minutes=PG_ORDER_STALE_MINUTES * 2)
            if order.created_at <= hard:
                abandon_unpaid_pg_order(order, reason=f"gateway_unreachable_after_{PG_ORDER_STALE_MINUTES * 2}m")
                return {"pg_order_id": order.pg_order_id, "status": "failed", "purpose": order.purpose}
        raise WalletError(gw["error"], status=gw["status"], code="server_error")
    if gw["failed"]:
        abandon_unpaid_pg_order(order, reason=f"gateway:{gw.get('order_status') or 'failed'}")
        return {"pg_order_id": order.pg_order_id, "status": "failed", "purpose": order.purpose}
    if not gw["paid"]:
        if order.status == "created" and order.created_at and order.created_at <= pg_stale_cutoff():
            abandon_unpaid_pg_order(order, reason=f"no_success_after_{PG_ORDER_STALE_MINUTES}m")
            return {
                "pg_order_id": order.pg_order_id,
                "status": "failed",
                "purpose": order.purpose,
                "gateway_status": gw["order_status"],
            }
        cfg_env = ""
        try:
            from integrations.pg import _load_env

            cfg_env = (_load_env().get("CASHFREE_PG_ENV") or "sandbox").strip().lower() or "sandbox"
        except Exception:
            cfg_env = "sandbox"
        return {
            "pg_order_id": order.pg_order_id,
            "status": order.status,
            "gateway_status": gw["order_status"],
            "purpose": order.purpose,
            "provider": order.provider,
            "payment_session_id": order.payment_session_id or "",
            "checkout_url": order.checkout_url or "",
            "cashfree_mode": cfg_env if cfg_env in {"sandbox", "production"} else "sandbox",
        }

    if order.purpose == "wallet_topup":
        if not paid_rupees_match(int(order.amount_paise), gw.get("amount")):
            raise WalletError("The paid amount does not match this order.", status=400, code="validation")
        out = apply_pg_topup_paid(
            order.pg_order_id,
            provider_payment_id=gw["provider_payment_id"],
            signature_verified=True,
            paid_amount=str(gw.get("amount") or ""),
        )
        out["purpose"] = "wallet_topup"
        return out

    if not paid_rupees_match(int(order.amount_paise), gw.get("amount")):
        raise WalletError("The paid amount does not match this order.", status=400, code="validation")
    from domain.payswap.bbps import execute_pg_paid_bbps

    return execute_pg_paid_bbps(
        order.pg_order_id,
        provider_payment_id=gw["provider_payment_id"],
        paid_amount=str(gw.get("amount") or ""),
    )
