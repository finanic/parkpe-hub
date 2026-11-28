"""BBPS catalogue, bill fetch, wallet/PG payment, and status sync for PaySwap.

Mounted on /api/v1/payswap/bbps/* in api/v1/routes/payswap.py.
App caller: apps/payswap/features/bbps, context payswap, role retailer.
Downstream: integrations/bbps.py, domain/payswap/wallet.py, domain/payswap/entitlements.py.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import time
from datetime import timedelta
from decimal import Decimal
from typing import Any

from core.actions import elapsed_ms, log_action
from core.errors import retailer_message
from django.db import transaction
from django.utils import timezone
from domain.payswap.bbps_pipes import pipe_fetch_bill, pipe_pay_bill, pipe_payment_status
from domain.payswap.entitlements import (
    allowed_billers_for_category,
    require_bbps_biller,
    require_bbps_category,
    require_payment_rail,
    require_retailer_service,
    resolve_bbps_categories,
    resolve_bbps_pipe,
)
from domain.payswap.wallet import (
    WalletError,
    capture_hold,
    commission_credit_reference,
    get_or_create_wallet,
    paise_to_rupees_str,
    paid_rupees_match,
    release_hold,
    reserve_hold,
    rupees_to_paise,
    serialize_wallet,
)
from domain.payswap.commission import retailer_has_gstin, settle_commission
from integrations.bbps import (
    configured,
    find_operator,
    generate_transaction_id,
    list_categories,
    list_operators,
    list_recharge_plans,
    list_telecom_circles,
)
from integrations.pg import create_gateway_order
from models.models import BbpsTransaction, HubAction, PgOrder, WalletAccount, WalletHold, WalletLedgerEntry
from rest_framework.exceptions import APIException


def mask_consumer_account(value: str) -> str:
    """Last four characters only. Logs and account_mask never keep the full number."""
    raw = str(value or "").strip()
    if len(raw) <= 4:
        return "••••"
    return ("•" * (len(raw) - 4)) + raw[-4:]


def _reserve_vendor_read(user_id: str, kind: str, *parts: str, seconds: int = 8) -> None:
    """One Mobikwik catalogue or bill read per retailer and target inside the window.

    The row lives in HubAction so every API process sees it. The target is a hash.
    """
    if not user_id:
        return
    fingerprint = hashlib.sha256("|".join((kind, *parts)).encode()).hexdigest()[:24]
    action = f"payswap.bbps.read.{kind}"
    since = timezone.now() - timedelta(seconds=seconds)
    if HubAction.objects.filter(actor=user_id, action=action, target_id=fingerprint, created_at__gte=since).exists():
        raise BbpsServiceError(
            "Wait a few seconds before trying again.",
            status=429,
            code="rate_limited",
        )
    since_user = timezone.now() - timedelta(seconds=2)
    if HubAction.objects.filter(actor=user_id, action=action, created_at__gte=since_user).exists():
        raise BbpsServiceError(
            "Wait a few seconds before trying again.",
            status=429,
            code="rate_limited",
        )
    log_action(
        action=action,
        outcome="ok",
        status=200,
        duration_ms=0,
        target_id=fingerprint,
        request="{}",
        response="reserved",
    )


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
        if user_id and operators:
            filtered = []
            for op in operators:
                cat = str(op.get("category") or "").strip().upper()
                bid = str(op.get("biller_id") or "").strip()
                allow = allowed_billers_for_category(cat, user_id=user_id)
                if allow is None or bid in allow:
                    filtered.append(op)
            operators = filtered
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
    circle: str = "",
    user_id: str = "",
) -> dict[str, Any]:
    """Load one Mobikwik plan catalogue for the selected operator and circle.

    B2B rechargePlansAPI needs op and cir. It does not detect the operator
    from the mobile number. Route: GET /api/v1/payswap/bbps/plans.
    """
    started = time.perf_counter()
    if user_id:
        require_retailer_service(user_id, "bbps")
    op = find_operator(biller)
    if not op:
        raise BbpsServiceError("Unknown BBPS biller.", status=404, code="not_found")
    if user_id:
        require_bbps_biller(user_id, category=op.get("category") or "", biller_id=op.get("biller_id") or "")
    category = str(op.get("category") or "").upper()
    if category not in {"PREPAID", "DTH"}:
        raise BbpsServiceError("Plans are only available for mobile prepaid and DTH.", status=400, code="validation")
    mobile = "".join(ch for ch in str(account or "") if ch.isdigit())
    if len(mobile) == 12 and mobile.startswith("91"):
        mobile = mobile[2:]
    if len(mobile) != 10:
        raise BbpsServiceError("Enter a valid 10-digit mobile number.", status=400, code="validation")
    cir = str(circle or "").strip()
    if not cir:
        raise BbpsServiceError("Select a telecom circle to load plans.", status=400, code="validation")
    _reserve_vendor_read(user_id, "plans", str(op.get("op") or biller), cir, mobile)

    result = list_recharge_plans(
        operator_id=op.get("op") or biller,
        circle=cir,
        customer_id=mobile,
        category="prepaid" if str(op.get("category") or "").upper() == "PREPAID" else "dth",
    )
    if not result.get("ok"):
        raise BbpsServiceError(retailer_message(result.get("error") or "Could not load recharge plans."), status=int(result.get("status") or 502))
    plans = result.get("plans") or []
    circles = list_telecom_circles()
    log_action(
        action="domain.payswap.bbps.plans",
        outcome="ok",
        status=200,
        duration_ms=elapsed_ms(started),
        target_id=str(op.get("op") or biller),
        request=json.dumps({"biller": op.get("op") or biller, "circle": cir, "account_len": len(mobile)}),
        response=json.dumps({"plans": len(plans), "circles": len(circles)}),
    )
    circle_label = ""
    for row in circles:
        if str(row.get("code")) == cir:
            circle_label = str(row.get("label") or "")
            break
    return {
        "biller": op.get("biller_id") or biller,
        "operator_id": op.get("op") or "",
        "operator_name": op.get("name") or "",
        "category": op.get("category") or "",
        "circle": cir,
        "circle_label": circle_label,
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
        require_bbps_biller(
            user_id,
            category=(op or {}).get("category") or "",
            biller_id=(op or {}).get("biller_id") or biller,
        )
    operator_id = op["op"] if op else str(biller).strip()
    pipe = resolve_bbps_pipe(user_id) if user_id else "mobikwik"
    _reserve_vendor_read(user_id, "fetch", pipe, operator_id, str(circle or ""), str(account or ""))
    result = pipe_fetch_bill(
        pipe,
        operator_id=operator_id,
        customer_id=account,
        circle=circle,
        ad_params=ad_params,
        payment_mode=payment_mode,
        op_row=op,
    )
    req_summary = json.dumps(
        {
            "biller": biller,
            "op": operator_id,
            "account": mask_consumer_account(account),
            "circle": circle,
            "ad_params": ad_params or {},
        },
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
        raise BbpsServiceError(retailer_message(result["error"] or "Could not fetch bill."), status=status, code=code)

    out_body = {
        "operator_id": operator_id,
        "biller": op["name"] if op else biller,
        "account": account,
        "bill": result["bill"],
    }
    logged = dict(out_body)
    logged["account"] = mask_consumer_account(account)
    log_action(
        action="domain.payswap.bbps.fetch_bill",
        outcome="ok",
        status=200,
        duration_ms=elapsed_ms(started),
        target_id=operator_id,
        request=req_summary,
        response=json.dumps(logged, separators=(",", ":")),
    )
    return out_body


def _wallet_collect_body(tx: BbpsTransaction, *, account: str, wallet, biller_name: str, operator_id: str) -> dict[str, Any]:
    return {
        "biller": biller_name,
        "operator_id": operator_id,
        "account": account,
        "amount": paise_to_rupees_str(int(tx.amount_paise)),
        "reference": tx.reference,
        "transaction_id": tx.vendor_txn_id or tx.reference,
        "vendor_status": tx.vendor_status,
        "state": tx.state,
        "payment_channel": "wallet",
        "commission": paise_to_rupees_str(int(tx.retailer_commission_paise or 0)),
        "tds": paise_to_rupees_str(int(tx.tds_paise or 0)),
        "net_commission": paise_to_rupees_str(int(tx.commission_paise or 0)),
        "wallet": serialize_wallet(wallet),
    }


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
    bulk_batch_id: str = "",
    bulk_row_id: str = "",
    pipe: str = "",
) -> dict[str, Any]:
    started = time.perf_counter()
    if not user_id:
        raise BbpsServiceError("Authenticated retailer required.", status=401, code="unauthenticated")

    require_retailer_service(user_id, "bbps")
    rail = (payment_rail or "wallet").strip().lower()
    if rail not in {"wallet", "pg"}:
        raise BbpsServiceError("payment_rail must be wallet or pg.", status=400, code="validation")
    require_payment_rail(user_id, rail)
    active_pipe = (pipe or "").strip() or resolve_bbps_pipe(user_id)

    op = find_operator(biller)
    operator_id = op["op"] if op else str(biller).strip()
    biller_name = op["name"] if op else str(biller).strip()
    category = op["category"] if op else ""
    require_bbps_biller(user_id, category=category, biller_id=(op or {}).get("biller_id") or biller)
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
    # The same idempotency key always reuses the first reference, so a retry
    # cannot mint a second Mobikwik reqid.
    masked = mask_consumer_account(account)
    existing = None
    if idempotency_key:
        existing = (
            BbpsTransaction.objects.filter(
                user_id=user_id,
                idempotency_key=idempotency_key,
                payment_channel="wallet",
            )
            .order_by("id")
            .first()
        )
    if existing is not None and existing.state == "failed":
        raise BbpsServiceError(
            existing.error_message or "Bill payment failed.",
            status=502,
            code="server_error",
        )
    if existing is not None and (existing.state == "success" or existing.vendor_txn_id):
        wallet = get_or_create_wallet(user_id)
        return _wallet_collect_body(existing, account=account, wallet=wallet, biller_name=existing.biller_name, operator_id=existing.operator_id)
    if existing is not None:
        reference = existing.reference
        tx = existing
        hold = WalletHold.objects.filter(hold_id=existing.wallet_hold_id).first()
        if hold is None or hold.status not in {"active", "captured"}:
            raise BbpsServiceError(
                "This payment is already in progress. Check status before trying again.",
                status=409,
                code="idempotency_conflict",
            )
    else:
        reference = generate_transaction_id()
        hold = reserve_hold(
            user_id,
            reference=reference,
            service="bbps",
            amount_paise=amount_paise,
            pin=wallet_pin,
            idempotency_key=idempotency_key,
            actor=user_id,
            narration=f"BBPS {biller_name} ({masked})",
        )
        try:
            tx = BbpsTransaction.objects.create(
                reference=reference,
                user_id=user_id,
                operator_id=operator_id,
                biller_name=biller_name,
                category=category,
                account_mask=masked,
                amount_paise=amount_paise,
                payment_channel="wallet",
                payment_mode=mode,
                bbps_pipe=active_pipe,
                bulk_batch_id=str(bulk_batch_id or "")[:64],
                bulk_row_id=str(bulk_row_id or "")[:64],
                state="pending",
                vendor_status="SUBMITTED",
                wallet_hold_id=hold.hold_id,
                idempotency_key=idempotency_key,
            )
        except Exception:
            release_hold(hold.hold_id, reference=reference, actor=user_id, reason="Payment record was not saved.")
            raise

    result = pipe_pay_bill(
        active_pipe,
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
        {"biller": biller, "op": operator_id, "account": masked, "amount": f"{amount:.2f}", "payment_rail": "wallet"},
        separators=(",", ":"),
    )

    if not result["ok"] or result["phase"] == "failed":
        reason = result.get("error") or "Bill payment failed."
        shown = retailer_message(reason)
        wallet = release_hold(hold.hold_id, reference=reference, actor=user_id, reason=f"Auto-refund: {shown}")
        tx.state = "failed"
        tx.vendor_status = result.get("vendor_status") or "FAILED"
        tx.vendor_txn_id = result.get("transaction_id") or ""
        tx.error_message = shown[:240]
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
        raise BbpsServiceError(f"{shown} The amount is back in the wallet.", status=status, code=code)

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
            narration=f"BBPS {biller_name} ({masked})",
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
    from domain.payswap.payu_checkout import initiate_payu_checkout, pick_provider

    chosen = pick_provider()
    payload = {
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
    }

    if chosen == "payu":
        phone = "".join(ch for ch in (customer_mobile or "") if ch.isdigit())[-10:] or "9999999999"
        order = PgOrder.objects.create(
            pg_order_id=pg_order_id,
            provider="payu",
            purpose="bbps_direct",
            user_id=user_id,
            amount_paise=amount_paise,
            status="created",
            service_ref=reference,
            service_payload=payload,
            meta={
                "firstname": (remitter_name or user_id.split("@")[0] or "Retailer")[:60],
                "email": user_id,
                "phone": phone,
                "productinfo": f"BBPS {biller_name}"[:100],
            },
        )
        checkout = initiate_payu_checkout(order.pg_order_id, user_id=user_id)
        log_action(
            action="domain.payswap.bbps.pg.init",
            outcome="ok",
            status=201,
            duration_ms=elapsed_ms(started),
            target_id=pg_order_id,
            request=json.dumps({"operator_id": operator_id, "account": mask_consumer_account(account), "amount": f"{amount:.2f}", "provider": "payu"}),
            response=json.dumps({"pg_order_id": pg_order_id, "reference": reference}),
        )
        return {
            "payment_channel": "pg",
            "state": "pg_pending",
            "provider": "payu",
            "pg_order_id": order.pg_order_id,
            "reference": reference,
            "action": checkout["action"],
            "params": checkout["params"],
            "payment_session_id": "",
            "checkout_url": "",
            "biller": biller_name,
            "amount": f"{amount:.2f}",
        }

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
        raise BbpsServiceError(retailer_message(gw["error"]), status=gw["status"], code="server_error")

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
        service_payload=payload,
    )
    log_action(
        action="domain.payswap.bbps.pg.init",
        outcome="ok",
        status=201,
        duration_ms=elapsed_ms(started),
        target_id=pg_order_id,
        request=json.dumps({"operator_id": operator_id, "account": mask_consumer_account(account), "amount": f"{amount:.2f}", "provider": "cashfree"}),
        response=json.dumps({"pg_order_id": pg_order_id, "reference": reference}),
    )
    return {
        "payment_channel": "pg",
        "state": "pg_pending",
        "provider": "cashfree",
        "pg_order_id": order.pg_order_id,
        "reference": reference,
        "payment_session_id": order.payment_session_id,
        "checkout_url": order.checkout_url,
        "cashfree_mode": str(gw.get("cashfree_mode") or "sandbox"),
        "biller": biller_name,
        "amount": f"{amount:.2f}",
    }


def _pg_bbps_snapshot(order: PgOrder, tx: BbpsTransaction) -> dict[str, Any]:
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


def _finish_pg_paid_bbps(order: PgOrder, tx: BbpsTransaction, started: float) -> dict[str, Any]:
    """Vendor pay + refund/commission after the PG order is already marked paid."""
    spec = order.service_payload or {}
    op = find_operator(str(spec.get("operator_id") or ""))
    pg_pipe = resolve_bbps_pipe(order.user_id)
    if not tx.bbps_pipe:
        tx.bbps_pipe = pg_pipe
        tx.save(update_fields=["bbps_pipe", "updated_at"])
    result = pipe_pay_bill(
        pg_pipe,
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
            tx.error_message = retailer_message(reason)[:240]
            tx.save(update_fields=["state", "vendor_status", "error_message", "updated_at"])
    else:
        tx.state = "success" if result["phase"] == "success" else "pending"
        tx.vendor_status = result["vendor_status"]
        tx.vendor_txn_id = result["transaction_id"]
        tx.save(update_fields=["state", "vendor_status", "vendor_txn_id", "updated_at"])
        if tx.state == "success":
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
        request=json.dumps({"pg_order_id": order.pg_order_id}),
        response=json.dumps({"reference": tx.reference, "state": tx.state}),
    )
    return _pg_bbps_snapshot(order, tx)


def _defer_pg_bbps_vendor_pay(pg_order_id: str) -> None:
    """Background vendor pay so Cashfree webhooks can ACK without waiting on Mobikwik."""
    import threading

    def run() -> None:
        try:
            order = PgOrder.objects.filter(pg_order_id=pg_order_id).first()
            tx = BbpsTransaction.objects.filter(pg_order_id=pg_order_id).first()
            if order is None or tx is None or tx.state != "pending":
                return
            _finish_pg_paid_bbps(order, tx, time.perf_counter())
        except Exception as exc:
            log_action(
                action="domain.payswap.bbps.pg.execute.deferred",
                outcome="error",
                status=500,
                duration_ms=0,
                target_id=pg_order_id,
                error_code="server_error",
                error_reason=str(exc)[:200],
                request=f"pg_order_id={pg_order_id}",
                response="HTTP 500\ndeferred vendor pay failed",
            )

    threading.Thread(target=run, name=f"pg-bbps-{pg_order_id[:12]}", daemon=True).start()


def execute_pg_paid_bbps(
    pg_order_id: str,
    *,
    provider_payment_id: str = "",
    paid_amount: str = "",
    defer_vendor_pay: bool = False,
) -> dict[str, Any]:
    """Called ONLY after server-side PG verification confirms order PAID."""
    started = time.perf_counter()
    with transaction.atomic():
        order = PgOrder.objects.select_for_update().get(pg_order_id=pg_order_id)
        if order.purpose != "bbps_direct":
            raise BbpsServiceError("Invalid PG order purpose.", status=400, code="validation")
        existing = BbpsTransaction.objects.filter(pg_order_id=pg_order_id).first()
        if existing is not None:
            if defer_vendor_pay and existing.state == "pending":
                _defer_pg_bbps_vendor_pay(pg_order_id)
            return _pg_bbps_snapshot(order, existing)
        if not paid_rupees_match(int(order.amount_paise), paid_amount):
            raise BbpsServiceError("The paid amount does not match this order.", status=400, code="validation")
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
            account_mask=mask_consumer_account(str(spec.get("account") or "")),
            amount_paise=int(order.amount_paise),
            payment_channel="pg",
            payment_mode=str(spec.get("payment_mode") or "Online"),
            state="pending",
            vendor_status="SUBMITTED",
            pg_order_id=order.pg_order_id,
        )

    if defer_vendor_pay:
        _defer_pg_bbps_vendor_pay(order.pg_order_id)
        log_action(
            action="domain.payswap.bbps.pg.execute",
            outcome="ok",
            status=200,
            duration_ms=elapsed_ms(started),
            target_id=tx.reference,
            request=json.dumps({"pg_order_id": pg_order_id, "deferred": True}),
            response=json.dumps({"reference": tx.reference, "state": tx.state, "deferred": True}),
        )
        return _pg_bbps_snapshot(order, tx)

    return _finish_pg_paid_bbps(order, tx, started)


def check_status(*, reference: str, user_id: str = "", actor_role: str = "retailer") -> dict[str, Any]:
    started = time.perf_counter()
    tx = BbpsTransaction.objects.filter(reference=reference).first()
    if tx is None or (actor_role == "retailer" and user_id and tx.user_id != user_id):
        raise BbpsServiceError("Transaction reference not found for this account.", status=404, code="validation")

    status_pipe = tx.bbps_pipe or resolve_bbps_pipe(tx.user_id)
    result = pipe_payment_status(status_pipe, reference=reference)
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
            request=json.dumps({"reference": reference, "pipe": status_pipe}, separators=(",", ":")),
            response=json.dumps({"error": result["error"], "status": status}, separators=(",", ":")),
        )
        raise BbpsServiceError(retailer_message(result["error"] or "Could not check payment status."), status=status, code="server_error")

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
