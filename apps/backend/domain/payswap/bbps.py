"""BBPS catalogue, bill fetch, wallet/PG payment, and status sync for PaySwap.

Mounted on /api/v1/payswap/bbps/* in api/v1/routes/payswap.py.
App caller: apps/payswap/features/bbps, context payswap, role retailer.
Downstream: integrations/bbps.py, domain/payswap/wallet.py, domain/payswap/entitlements.py.
"""

from __future__ import annotations

import json
import secrets
import time
from decimal import Decimal
from typing import Any

from core.actions import elapsed_ms, log_action
from django.db import transaction
from django.utils import timezone
from domain.payswap.entitlements import (
    require_bbps_category,
    require_payment_rail,
    require_retailer_service,
    resolve_bbps_categories,
)
from domain.payswap.wallet import (
    WalletError,
    capture_hold,
    commission_credit_reference,
    get_or_create_wallet,
    paise_to_rupees_str,
    release_hold,
    reserve_hold,
    rupees_to_paise,
    serialize_wallet,
)
from domain.payswap.commission import retailer_has_gstin, settle_commission
from integrations.bbps import (
    configured,
    fetch_bill,
    find_operator,
    generate_transaction_id,
    list_categories,
    list_operators,
    list_recharge_plans,
    list_telecom_circles,
    pay_bill,
    payment_status,
)
from integrations.pg import create_gateway_order
from models.models import BbpsTransaction, PgOrder, WalletAccount, WalletLedgerEntry
from rest_framework.exceptions import APIException


class BbpsServiceError(APIException):
    def __init__(self, message: str, *, status: int = 502, code: str = "server_error"):
        super().__init__(detail={"error": message, "code": code})
        self.status_code = status


def catalogue(*, category: str = "", query: str = "", limit: int = 200, user_id: str = "") -> dict[str, Any]:
    started = time.perf_counter()
    if user_id:
        require_retailer_service(user_id, "bbps")
    allowed = set(resolve_bbps_categories(user_id).get("enabled_bbps_categories") or []) if user_id else None
    categories = list_categories()
    if allowed is not None:
        categories = [c for c in categories if c.get("id") in allowed]
    target = (category or "").strip().upper()
    if target and allowed is not None and target not in allowed:
        operators = []
    else:
        operators = list_operators(category=category or None, query=query, limit=limit) if (category or query) else []
        if allowed is not None and operators:
            operators = [op for op in operators if op.get("category") in allowed]
    is_configured = configured()
    log_action(
        action="domain.payswap.bbps.catalogue",
        outcome="ok",
        status=200,
        duration_ms=elapsed_ms(started),
        target_id=category or ("search" if query else "categories"),
        request=json.dumps({"category": category, "query": query, "limit": limit}),
        response=json.dumps({"configured": is_configured, "categories": len(categories), "operators": len(operators)}),
    )
    return {
        "configured": is_configured,
        "categories": categories,
        "operators": operators,
    }


def prepaid_plans(
    *,
    biller: str,
    account: str,
    circle: str,
    user_id: str = "",
) -> dict[str, Any]:
    """Load Mobikwik prepaid plan packs for a selected operator + circle.

    Route: GET /api/v1/payswap/bbps/plans. Caller: apps/payswap Bill pay PREPAID UI.
    """
    started = time.perf_counter()
    if user_id:
        require_retailer_service(user_id, "bbps")
    op = find_operator(biller)
    if not op:
        raise BbpsServiceError("Unknown BBPS biller.", status=404, code="not_found")
    if user_id:
        require_bbps_category(user_id, op.get("category") or "")
    if str(op.get("category") or "").upper() not in {"PREPAID", "DTH"}:
        raise BbpsServiceError("Plans are only available for mobile prepaid and DTH.", status=400, code="validation")
    mobile = "".join(ch for ch in str(account or "") if ch.isdigit())
    if len(mobile) == 12 and mobile.startswith("91"):
        mobile = mobile[2:]
    if len(mobile) != 10:
        raise BbpsServiceError("Enter a valid 10-digit mobile number.", status=400, code="validation")
    cir = str(circle or "").strip()
    if not cir:
        raise BbpsServiceError("Select a telecom circle to load plans.", status=400, code="validation")

    result = list_recharge_plans(
        operator_id=op.get("op") or biller,
        circle=cir,
        customer_id=mobile,
        category="prepaid" if str(op.get("category") or "").upper() == "PREPAID" else "dth",
    )
    if not result.get("ok"):
        raise BbpsServiceError(result.get("error") or "Could not load recharge plans.", status=int(result.get("status") or 502))
    plans = result.get("plans") or []
    circles = list_telecom_circles()
    log_action(
        action="domain.payswap.bbps.plans",
        outcome="ok",
        status=200,
        duration_ms=elapsed_ms(started),
        target_id=str(op.get("op") or biller),
        request=json.dumps({"biller": biller, "circle": cir, "account_len": len(mobile)}),
        response=json.dumps({"plans": len(plans), "circles": len(circles)}),
    )
    return {
        "biller": op.get("biller_id") or biller,
        "operator_id": op.get("op") or "",
        "operator_name": op.get("name") or "",
        "category": op.get("category") or "",
        "circle": cir,
        "account": mobile,
        "plans": plans,
        "circles": circles,
    }


def telecom_circles(*, user_id: str = "") -> dict[str, Any]:
    if user_id:
        require_retailer_service(user_id, "bbps")
    return {"circles": list_telecom_circles()}


def fetch_bill_details(
    *,
    biller: str,
    account: str,
    circle: str = "",
    payment_mode: str = "",
    ad_params: dict[str, Any] | None = None,
    user_id: str = "",
) -> dict[str, Any]:
    started = time.perf_counter()
    if user_id:
        require_retailer_service(user_id, "bbps")
    op = find_operator(biller)
    if user_id:
        require_bbps_category(user_id, (op or {}).get("category") or "")
    operator_id = op["op"] if op else str(biller).strip()
    result = fetch_bill(
        operator_id=operator_id,
        customer_id=account,
        circle=circle,
        ad_params=ad_params,
        payment_mode=payment_mode,
        op_row=op,
    )
    req_summary = json.dumps(
        {"biller": biller, "op": operator_id, "account": account, "circle": circle, "ad_params": ad_params or {}},
        separators=(",", ":"),
    )
    if not result["ok"]:
        status = result["status"] if result["status"] >= 400 else 502
        code = "validation" if 400 <= status < 500 else "server_error"
        log_action(
            action="domain.payswap.bbps.fetch_bill",
            outcome="error",
            status=status,
            duration_ms=elapsed_ms(started),
            target_id=operator_id,
            error_code=code,
            error_reason=result["error"],
            request=req_summary,
            response=json.dumps({"error": result["error"], "status": status}, separators=(",", ":")),
        )
        raise BbpsServiceError(result["error"] or "Could not fetch bill.", status=status, code=code)

    out_body = {
        "operator_id": operator_id,
        "biller": op["name"] if op else biller,
        "account": account,
        "bill": result["bill"],
    }
    log_action(
        action="domain.payswap.bbps.fetch_bill",
        outcome="ok",
        status=200,
        duration_ms=elapsed_ms(started),
        target_id=operator_id,
        request=req_summary,
        response=json.dumps(out_body, separators=(",", ":")),
    )
    return out_body


def collect(
    *,
    biller: str,
    account: str,
    amount: Decimal,
    user_id: str = "",
    circle: str = "",
    customer_mobile: str = "",
    remitter_name: str = "",
    payment_mode: str = "Cash",
    payment_rail: str = "wallet",
    wallet_pin: str = "",
    idempotency_key: str = "",
    ad_params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    if not user_id:
        raise BbpsServiceError("Authenticated retailer required.", status=401, code="unauthenticated")

    require_retailer_service(user_id, "bbps")
    rail = (payment_rail or "wallet").strip().lower()
    if rail not in {"wallet", "pg"}:
        raise BbpsServiceError("payment_rail must be wallet or pg.", status=400, code="validation")
    require_payment_rail(user_id, rail)

    op = find_operator(biller)
    operator_id = op["op"] if op else str(biller).strip()
    biller_name = op["name"] if op else str(biller).strip()
    category = op["category"] if op else ""
    require_bbps_category(user_id, category)
    amount_paise = rupees_to_paise(amount)
    mode = payment_mode or (op.get("default_payment_mode") if op else "") or "Cash"

    if rail == "pg":
        return _initiate_bbps_pg(
            user_id=user_id,
            operator_id=operator_id,
            biller_name=biller_name,
            category=category,
            account=account,
            amount=amount,
            amount_paise=amount_paise,
            circle=circle,
            customer_mobile=customer_mobile,
            remitter_name=remitter_name,
            payment_mode=mode,
            ad_params=ad_params or {},
        )

    # Wallet-backed payment: 3-step hold-first -> Mobikwik HTTP -> settle/release.
    reference = generate_transaction_id()
    hold = reserve_hold(
        user_id,
        reference=reference,
        service="bbps",
        amount_paise=amount_paise,
        pin=wallet_pin,
        idempotency_key=idempotency_key,
        actor=user_id,
        narration=f"BBPS {biller_name} ({account})",
    )
    tx = BbpsTransaction.objects.create(
        reference=reference,
        user_id=user_id,
        operator_id=operator_id,
        biller_name=biller_name,
        category=category,
        account_mask=account,
        amount_paise=amount_paise,
        payment_channel="wallet",
        payment_mode=mode,
        state="pending",
        vendor_status="SUBMITTED",
        wallet_hold_id=hold.hold_id,
        idempotency_key=idempotency_key,
    )

    result = pay_bill(
        operator_id=operator_id,
        customer_id=account,
        amount=amount,
        reqid=reference,
        circle=circle,
        customer_mobile=customer_mobile,
        remitter_name=remitter_name or user_id,
        payment_mode=mode,
        ad_params=ad_params,
        op_row=op,
    )
    req_summary = json.dumps(
        {"biller": biller, "op": operator_id, "account": account, "amount": f"{amount:.2f}", "payment_rail": "wallet"},
        separators=(",", ":"),
    )

    if not result["ok"] or result["phase"] == "failed":
        reason = result.get("error") or "Bill payment failed."
        wallet = release_hold(hold.hold_id, reference=reference, actor=user_id, reason=f"Auto-refund: {reason}")
        tx.state = "failed"
        tx.vendor_status = result.get("vendor_status") or "FAILED"
        tx.vendor_txn_id = result.get("transaction_id") or ""
        tx.error_message = reason[:240]
        tx.save(update_fields=["state", "vendor_status", "vendor_txn_id", "error_message", "updated_at"])

        status = result["status"] if result["status"] >= 400 else 502
        code = "validation" if 400 <= status < 500 else "server_error"
        log_action(
            action="domain.payswap.bbps.collect",
            outcome="error",
            status=status,
            duration_ms=elapsed_ms(started),
            target_id=reference,
            error_code=code,
            error_reason=reason,
            request=req_summary,
            response=json.dumps({"error": reason, "status": status, "refunded": True, "available": paise_to_rupees_str(wallet.available_paise)}, separators=(",", ":")),
        )
        raise BbpsServiceError(f"{reason} Wallet hold was released back to your balance.", status=status, code=code)

    if result["phase"] == "success":
        tx.state = "success"
        tx.vendor_status = result["vendor_status"]
        tx.vendor_txn_id = result["transaction_id"]
        tx.save(update_fields=["state", "vendor_status", "vendor_txn_id", "updated_at"])
        settled = settle_commission(
            tx,
            has_gstin=retailer_has_gstin(user_id),
            vendor_paise=result.get("vendor_commission_paise"),
        )
        wallet = capture_hold(
            hold.hold_id,
            reference=reference,
            actor=user_id,
            commission_paise=int(settled.get("net_credit_paise") or 0),
            narration=f"BBPS {biller_name} ({account})",
        )
    else:
        wallet = get_or_create_wallet(user_id)
        tx.state = "pending"
        tx.vendor_status = result["vendor_status"]
        tx.vendor_txn_id = result["transaction_id"]
        tx.save(update_fields=["state", "vendor_status", "vendor_txn_id", "updated_at"])

    out_body = {
        "biller": biller_name,
        "operator_id": operator_id,
        "account": account,
        "amount": f"{amount:.2f}",
        "reference": reference,
        "transaction_id": tx.vendor_txn_id or reference,
        "vendor_status": tx.vendor_status,
        "state": tx.state,
        "payment_channel": "wallet",
        "commission": paise_to_rupees_str(int(tx.retailer_commission_paise or 0)),
        "tds": paise_to_rupees_str(int(tx.tds_paise or 0)),
        "net_commission": paise_to_rupees_str(int(tx.commission_paise or 0)),
        "wallet": serialize_wallet(wallet),
    }
    log_action(
        action="domain.payswap.bbps.collect",
        outcome="ok",
        status=200,
        duration_ms=elapsed_ms(started),
        target_id=reference,
        request=req_summary,
        response=json.dumps({"reference": reference, "state": tx.state, "vendor_status": tx.vendor_status}, separators=(",", ":")),
    )
    return out_body


def _initiate_bbps_pg(
    *,
    user_id: str,
    operator_id: str,
    biller_name: str,
    category: str,
    account: str,
    amount: Decimal,
    amount_paise: int,
    circle: str,
    customer_mobile: str,
    remitter_name: str,
    payment_mode: str,
    ad_params: dict[str, Any],
) -> dict[str, Any]:
    started = time.perf_counter()
    pg_order_id = "pgb-" + secrets.token_hex(8)
    reference = generate_transaction_id()
    gw = create_gateway_order(
        order_id=pg_order_id,
        amount_paise=amount_paise,
        customer_id=user_id,
        customer_email=user_id,
        customer_phone=customer_mobile,
        note=f"BBPS {biller_name} ({account})",
        return_url="http://127.0.0.1:4500/#bills",
    )
    if not gw["ok"]:
        raise BbpsServiceError(gw["error"], status=gw["status"], code="server_error")

    order = PgOrder.objects.create(
        pg_order_id=pg_order_id,
        provider="cashfree",
        purpose="bbps_direct",
        user_id=user_id,
        amount_paise=amount_paise,
        status="created",
        service_ref=reference,
        provider_order_id=gw["provider_order_id"],
        payment_session_id=gw["payment_session_id"],
        checkout_url=gw["checkout_url"],
        service_payload={
            "biller": biller_name,
            "operator_id": operator_id,
            "category": category,
            "account": account,
            "amount": f"{amount:.2f}",
            "circle": circle,
            "customer_mobile": customer_mobile,
            "remitter_name": remitter_name or user_id,
            "payment_mode": payment_mode,
            "ad_params": ad_params,
        },
    )
    log_action(
        action="domain.payswap.bbps.pg.init",
        outcome="ok",
        status=201,
        duration_ms=elapsed_ms(started),
        target_id=pg_order_id,
        request=json.dumps({"operator_id": operator_id, "account": account, "amount": f"{amount:.2f}"}),
        response=json.dumps({"pg_order_id": pg_order_id, "reference": reference}),
    )
    return {
        "payment_channel": "pg",
        "state": "pg_pending",
        "pg_order_id": order.pg_order_id,
        "reference": reference,
        "payment_session_id": order.payment_session_id,
        "checkout_url": order.checkout_url,
        "biller": biller_name,
        "amount": f"{amount:.2f}",
    }


def execute_pg_paid_bbps(pg_order_id: str, *, provider_payment_id: str = "") -> dict[str, Any]:
    """Called ONLY after server-side PG verification confirms order PAID."""
    started = time.perf_counter()
    with transaction.atomic():
        order = PgOrder.objects.select_for_update().get(pg_order_id=pg_order_id)
        if order.purpose != "bbps_direct":
            raise BbpsServiceError("Invalid PG order purpose.", status=400, code="validation")
        existing = BbpsTransaction.objects.filter(pg_order_id=pg_order_id).first()
        if existing is not None:
            return {
                "pg_order_id": order.pg_order_id,
                "purpose": "bbps_direct",
                "status": "paid",
                "reference": existing.reference,
                "state": existing.state,
                "vendor_status": existing.vendor_status,
                "biller": existing.biller_name,
                "amount": paise_to_rupees_str(existing.amount_paise),
            }
        order.status = "paid"
        order.signature_verified = True
        order.provider_payment_id = provider_payment_id or order.provider_payment_id
        order.paid_at = timezone.now()
        order.save(update_fields=["status", "signature_verified", "provider_payment_id", "paid_at", "updated_at"])

        spec = order.service_payload or {}
        ref = order.service_ref or generate_transaction_id()
        tx = BbpsTransaction.objects.create(
            reference=ref,
            user_id=order.user_id,
            operator_id=str(spec.get("operator_id") or ""),
            biller_name=str(spec.get("biller") or "BBPS"),
            category=str(spec.get("category") or ""),
            account_mask=str(spec.get("account") or ""),
            amount_paise=int(order.amount_paise),
            payment_channel="pg",
            payment_mode=str(spec.get("payment_mode") or "Online"),
            state="pending",
            vendor_status="SUBMITTED",
            pg_order_id=order.pg_order_id,
        )

    spec = order.service_payload or {}
    op = find_operator(str(spec.get("operator_id") or ""))
    result = pay_bill(
        operator_id=str(spec.get("operator_id") or ""),
        customer_id=str(spec.get("account") or ""),
        amount=Decimal(str(spec.get("amount") or paise_to_rupees_str(order.amount_paise))),
        reqid=tx.reference,
        circle=str(spec.get("circle") or ""),
        customer_mobile=str(spec.get("customer_mobile") or ""),
        remitter_name=str(spec.get("remitter_name") or order.user_id),
        payment_mode=str(spec.get("payment_mode") or "Online"),
        ad_params=spec.get("ad_params") or {},
        op_row=op,
    )

    if not result["ok"] or result["phase"] == "failed":
        # PG payment succeeded, BBPS failed -> safely credit retailer wallet so funds are never lost.
        reason = result.get("error") or "BBPS provider failed after PG payment."
        with transaction.atomic():
            base = get_or_create_wallet(order.user_id)
            wallet = WalletAccount.objects.select_for_update().get(pk=base.pk)
            bal_before = int(wallet.available_paise)
            wallet.available_paise = bal_before + int(order.amount_paise)
            wallet.save(update_fields=["available_paise", "updated_at"])
            WalletLedgerEntry.objects.create(
                entry_id="led-" + secrets.token_hex(10),
                wallet=wallet,
                direction="CR",
                entry_type="REFUND",
                amount_paise=int(order.amount_paise),
                balance_before_paise=bal_before,
                balance_after_paise=wallet.available_paise,
                held_before_paise=wallet.held_paise,
                held_after_paise=wallet.held_paise,
                reference=tx.reference,
                actor="system",
                actor_role="system",
                narration=f"PG BBPS failed ({tx.reference}); credited to wallet",
                meta={"pg_order_id": order.pg_order_id},
            )
            tx.state = "failed"
            tx.vendor_status = result.get("vendor_status") or "FAILED"
            tx.error_message = reason[:240]
            tx.save(update_fields=["state", "vendor_status", "error_message", "updated_at"])
    else:
        tx.state = "success" if result["phase"] == "success" else "pending"
        tx.vendor_status = result["vendor_status"]
        tx.vendor_txn_id = result["transaction_id"]
        tx.save(update_fields=["state", "vendor_status", "vendor_txn_id", "updated_at"])
        if tx.state == "success":
            # PG path: bill already paid via gateway; credit commission as wallet top-up style credit.
            settled = settle_commission(
                tx,
                has_gstin=retailer_has_gstin(order.user_id),
                vendor_paise=result.get("vendor_commission_paise"),
            )
            net = int(settled.get("net_credit_paise") or 0)
            if net > 0:
                with transaction.atomic():
                    base = get_or_create_wallet(order.user_id)
                    wallet = WalletAccount.objects.select_for_update().get(pk=base.pk)
                    before = int(wallet.available_paise)
                    wallet.available_paise = before + net
                    wallet.save(update_fields=["available_paise", "updated_at"])
                    WalletLedgerEntry.objects.create(
                        entry_id="led-" + secrets.token_hex(10),
                        wallet=wallet,
                        direction="CR",
                        entry_type="COMMISSION_CR",
                        amount_paise=net,
                        balance_before_paise=before,
                        balance_after_paise=wallet.available_paise,
                        held_before_paise=wallet.held_paise,
                        held_after_paise=wallet.held_paise,
                        reference=commission_credit_reference(tx.reference),
                        actor="system",
                        actor_role="system",
                        narration="Commission credit",
                        meta={"pg_order_id": order.pg_order_id, "bill_reference": tx.reference},
                    )

    log_action(
        action="domain.payswap.bbps.pg.execute",
        outcome="ok" if tx.state != "failed" else "error",
        status=200 if tx.state != "failed" else 502,
        duration_ms=elapsed_ms(started),
        target_id=tx.reference,
        request=json.dumps({"pg_order_id": pg_order_id}),
        response=json.dumps({"reference": tx.reference, "state": tx.state}),
    )
    return {
        "pg_order_id": order.pg_order_id,
        "purpose": "bbps_direct",
        "status": "paid",
        "reference": tx.reference,
        "state": tx.state,
        "vendor_status": tx.vendor_status,
        "biller": tx.biller_name,
        "amount": paise_to_rupees_str(tx.amount_paise),
        "error_message": tx.error_message,
    }


def check_status(*, reference: str, user_id: str = "", actor_role: str = "retailer") -> dict[str, Any]:
    started = time.perf_counter()
    tx = BbpsTransaction.objects.filter(reference=reference).first()
    if tx is not None and actor_role == "retailer" and user_id and tx.user_id != user_id:
        raise BbpsServiceError("Transaction reference not found for this account.", status=404, code="validation")

    result = payment_status(reference=reference)
    if not result["ok"]:
        status = result["status"] if result["status"] >= 400 else 502
        log_action(
            action="domain.payswap.bbps.status",
            outcome="error",
            status=status,
            duration_ms=elapsed_ms(started),
            target_id=reference,
            error_code="server_error",
            error_reason=result["error"],
            request=json.dumps({"reference": reference}, separators=(",", ":")),
            response=json.dumps({"error": result["error"], "status": status}, separators=(",", ":")),
        )
        raise BbpsServiceError(result["error"] or "Could not check payment status.", status=status, code="server_error")

    wallet_settled = None
    if tx is not None:
        tx.last_checked_at = timezone.now()
        tx.vendor_status = result["vendor_status"]
        if result.get("vendor_txn_id") and not tx.vendor_txn_id:
            tx.vendor_txn_id = str(result["vendor_txn_id"])[:80]
        if tx.state == "pending":
            if result["phase"] == "success":
                tx.state = "success"
                tx.vendor_status = result["vendor_status"]
                tx.save(update_fields=["state", "vendor_status", "vendor_txn_id", "last_checked_at", "updated_at"])
                settled = settle_commission(
                    tx,
                    has_gstin=retailer_has_gstin(tx.user_id),
                    vendor_paise=result.get("vendor_commission_paise"),
                )
                net = int(settled.get("net_credit_paise") or 0)
                if tx.wallet_hold_id:
                    wallet_settled = capture_hold(
                        tx.wallet_hold_id,
                        reference=tx.reference,
                        actor=user_id or "system",
                        commission_paise=net,
                        narration=f"BBPS {tx.biller_name} settled on status sync",
                    )
                elif net > 0:
                    with transaction.atomic():
                        base = get_or_create_wallet(tx.user_id)
                        wallet = WalletAccount.objects.select_for_update().get(pk=base.pk)
                        before = int(wallet.available_paise)
                        wallet.available_paise = before + net
                        wallet.save(update_fields=["available_paise", "updated_at"])
                        WalletLedgerEntry.objects.create(
                            entry_id="led-" + secrets.token_hex(10),
                            wallet=wallet,
                            direction="CR",
                            entry_type="COMMISSION_CR",
                            amount_paise=net,
                            balance_before_paise=before,
                            balance_after_paise=wallet.available_paise,
                            held_before_paise=wallet.held_paise,
                            held_after_paise=wallet.held_paise,
                            reference=commission_credit_reference(tx.reference),
                            actor="system",
                            actor_role="system",
                            narration="Commission credit",
                            meta={"bill_reference": tx.reference},
                        )
                        wallet_settled = wallet
            elif result["phase"] == "failed":
                if tx.wallet_hold_id:
                    wallet_settled = release_hold(
                        tx.wallet_hold_id,
                        reference=tx.reference,
                        actor=user_id or "system",
                        reason="BBPS failed on status sync",
                    )
                tx.state = "failed"
                tx.save(update_fields=["state", "vendor_status", "vendor_txn_id", "last_checked_at", "updated_at"])
            else:
                tx.save(update_fields=["state", "vendor_status", "vendor_txn_id", "last_checked_at", "updated_at"])
        else:
            tx.save(update_fields=["state", "vendor_status", "vendor_txn_id", "last_checked_at", "updated_at"])

    out_body: dict[str, Any] = {
        "reference": result["reference"],
        "vendor_status": result["vendor_status"],
        "vendor_txn_id": (tx.vendor_txn_id if tx is not None else result.get("vendor_txn_id", "")) or "",
        "state": tx.state if tx is not None else result["phase"],
    }
    if tx is not None:
        out_body["biller"] = tx.biller_name
        out_body["amount"] = paise_to_rupees_str(tx.amount_paise)
        out_body["last_checked_at"] = tx.last_checked_at.isoformat() if tx.last_checked_at else ""
    if wallet_settled is not None:
        out_body["wallet"] = serialize_wallet(wallet_settled)

    log_action(
        action="domain.payswap.bbps.status",
        outcome="ok",
        status=200,
        duration_ms=elapsed_ms(started),
        target_id=reference,
        request=json.dumps({"reference": reference}, separators=(",", ":")),
        response=json.dumps(out_body, separators=(",", ":")),
    )
    return out_body
