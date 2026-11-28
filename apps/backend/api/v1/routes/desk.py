"""Product, wallet, entitlement, and transaction endpoints for the operator console.

Caller: apps/backend/auth/server.py proxies these paths from the console
on port 4600 and sends only auth_access. config/cors.py rejects these
paths when the request has an Origin, so ParkPe and PaySwap cannot call them.
"""

from __future__ import annotations

import datetime
import json

from core.actions import bind_action, log_action
from core.security import ACCESS_COOKIE, SessionRejected, fetch_session
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from domain.payswap.bbps import check_status
from domain.payswap.commission import (
    create_monthly_invoice,
    get_retailer_override,
    import_vendor_sheet,
    list_rates,
    mark_tds_deposited,
    retailer_commission_sheet,
    retailer_gstin,
    revenue_report,
    serialize_invoice,
    serialize_policy,
    serialize_retailer_override,
    approve_tds_certificate,
    list_tds_certificates,
    reject_tds_certificate,
    tds_month_report,
    TAN_RE,
    update_policy,
    update_retailer_override,
    retailer_service_catalogue,
    update_retailer_biller_share,
    update_retailer_service_share,
)
from domain.payswap.entitlements import (
    list_default_bbps_billers,
    resolve_retailer_entitlements,
    serialize_default_policy,
    update_default_policy,
    update_retailer_entitlements,
)
from domain.payswap.transactions import list_admin_transactions
from domain.payswap.wallet import (
    admin_adjust_wallet,
    admin_update_wallet_controls,
    pending_wallet_adjustments,
    review_wallet_adjustment,
    paise_to_rupees_str,
    review_topup_request,
    rupees_to_paise,
    serialize_ledger_entry,
    serialize_topup_request,
    serialize_wallet,
    verify_pg_order,
    wallet_overview,
)
from pathlib import Path

from models.models import (
    BbpsTransaction,
    CommissionInvoice,
    HubAction,
    IdempotencyRecord,
    PgOrder,
    WalletAccount,
    WalletHold,
    WalletLedgerEntry,
    WalletTopupRequest,
)
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied
from rest_framework.permissions import BasePermission
from rest_framework.response import Response
from rest_framework.views import APIView

SESSION_PATH = "/api/v1/parkpe/sessions/initiate"
ORDER_PATH = "/api/v1/payswap/vouchers/order"
ADMIN_ROLE = "admin"
class AdminAuthentication(BaseAuthentication):
    def authenticate_header(self, request):
        return 'Cookie realm="hub"'

    def authenticate(self, request):
        token = request.COOKIES.get(ACCESS_COOKIE, "")
        if not token:
            raise AuthenticationFailed(detail={"error": "Sign in again.", "code": "unauthenticated"})
        try:
            session = fetch_session(token)
        except SessionRejected as exc:
            detail = {"error": exc.message, "code": "unauthenticated"}
            if exc.status == 403:
                raise PermissionDenied(detail=detail) from exc
            raise AuthenticationFailed(detail=detail) from exc
        if session.get("role") != ADMIN_ROLE:
            raise PermissionDenied(detail={"error": "Admin session required.", "code": "forbidden_app"})
        return _Admin(session["email"], session["role"]), token


class AdminOnly(BasePermission):
    def has_permission(self, request, view):
        return getattr(request.user, "role", "") == ADMIN_ROLE


class _Admin:
    def __init__(self, email: str, role: str):
        self.email = email
        self.user_id = email
        self.role = role
        self.is_authenticated = True


class DeskView(APIView):
    authentication_classes = [AdminAuthentication]
    permission_classes = [AdminOnly]


class DeskActionsView(DeskView):
    """Recent HubAction rows for the console Logs screen (auth proxies this)."""

    def get(self, request):
        try:
            limit = min(200, max(1, int(request.query_params.get("limit") or 80)))
        except (TypeError, ValueError):
            limit = 80
        rows = HubAction.objects.order_by("-id")[:limit]
        entries = []
        for row in rows:
            at = row.created_at
            if timezone.is_aware(at):
                stamp = int(at.timestamp())
            else:
                stamp = int(timezone.make_aware(at, timezone.get_current_timezone()).timestamp())
            entries.append(
                {
                    "id": row.id,
                    "at": stamp,
                    "action": row.action,
                    "actor": row.actor,
                    "role": row.role,
                    "target_id": row.target_id,
                    "outcome": row.outcome,
                    "status": row.status,
                    "duration_ms": row.duration_ms,
                    "error_code": row.error_code,
                    "error_reason": row.error_reason,
                    "request": row.request,
                    "response": row.response,
                }
            )
        return Response({"entries": entries})


class OverviewView(DeskView):
    def get(self, request):
        now = timezone.localtime(timezone.now())
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        today_bbps = BbpsTransaction.objects.filter(created_at__gte=today_start)
        today_success = today_bbps.filter(state="success")
        today_volume_paise = today_success.aggregate(total=Sum("amount_paise"))["total"] or 0
        today_pending_count = today_bbps.filter(state="pending").count()
        today_failed_count = today_bbps.filter(state="failed").count()

        wallet_totals = WalletAccount.objects.aggregate(
            avail=Sum("available_paise"),
            held=Sum("held_paise"),
        )
        total_avail = int(wallet_totals["avail"] or 0)
        total_held = int(wallet_totals["held"] or 0)
        pending_topups = WalletTopupRequest.objects.filter(status="pending").count()

        # Last 7 days daily BBPS success volume for chart
        series = []
        for delta in range(6, -1, -1):
            day_start = today_start - datetime.timedelta(days=delta)
            day_end = day_start + datetime.timedelta(days=1)
            day_paise = (
                BbpsTransaction.objects.filter(
                    created_at__gte=day_start,
                    created_at__lt=day_end,
                    state="success",
                ).aggregate(total=Sum("amount_paise"))["total"]
                or 0
            )
            series.append(
                {
                    "date": day_start.strftime("%d %b"),
                    "amount_paise": int(day_paise),
                    "amount": paise_to_rupees_str(day_paise),
                }
            )

        return Response(
            {
                "today_bbps_volume_paise": int(today_volume_paise),
                "today_bbps_volume": paise_to_rupees_str(today_volume_paise),
                "today_bbps_count": today_bbps.count(),
                "today_bbps_success": today_success.count(),
                "today_bbps_pending": today_pending_count,
                "today_bbps_failed": today_failed_count,
                "total_wallet_available_paise": total_avail,
                "total_wallet_available": paise_to_rupees_str(total_avail),
                "total_wallet_held_paise": total_held,
                "total_wallet_held": paise_to_rupees_str(total_held),
                "pending_topup_count": pending_topups,
                "active_holds_count": WalletHold.objects.filter(status="active").count(),
                "daily_series": series,
            }
        )


class ParkPeSessionsView(DeskView):
    def get(self, request):
        rows = _actor_filter(
            IdempotencyRecord.objects.filter(app_context="parkpe", endpoint=SESSION_PATH, state="done"),
            request,
        ).order_by("-created_at")[:50]
        return Response({"sessions": [_session_row(row) for row in rows]})


class ParkPeSessionCloseView(DeskView):
    def post(self, request):
        reference = request.data.get("reference") if isinstance(request.data, dict) else ""
        if not isinstance(reference, str) or not reference.startswith("sess-"):
            return Response({"error": "Check the session reference.", "code": "validation"}, status=400)
        match_id = None
        for row in IdempotencyRecord.objects.filter(app_context="parkpe", endpoint=SESSION_PATH, state="done"):
            body = row.body if isinstance(row.body, dict) else {}
            if body.get("reference") == reference:
                match_id = row.pk
                break
        if match_id is None:
            return Response({"error": "That session is not stored.", "code": "validation"}, status=404)
        with transaction.atomic():
            match = IdempotencyRecord.objects.select_for_update().get(pk=match_id)
            if match.desk_state != "closed":
                match.desk_state = "closed"
                match.save(update_fields=["desk_state"])
                bind_action(actor=request.user.email, role=ADMIN_ROLE, app_context="parkpe")
                request._hub_logged = True
                log_action(
                    action="parkpe.session.close",
                    outcome="ok",
                    status=200,
                    duration_ms=0,
                    target_id=reference,
                    request=f'POST /api/v1/desk/parkpe/sessions/close\n{{"reference":"{reference}"}}',
                    response=f'HTTP 200\n{{"reference":"{reference}","state":"closed"}}',
                )
        return Response(_session_row(match))


class PaySwapOrdersView(DeskView):
    def get(self, request):
        rows = _actor_filter(
            IdempotencyRecord.objects.filter(app_context="payswap", endpoint=ORDER_PATH, state="done"),
            request,
        ).order_by("-created_at")[:50]
        return Response({"orders": [_order_row(row) for row in rows]})


class DefaultEntitlementsView(DeskView):
    def get(self, request):
        return Response(serialize_default_policy())

    def post(self, request):
        bind_action(actor=request.user.email, role=ADMIN_ROLE, app_context="payswap")
        data = request.data if isinstance(request.data, dict) else {}
        per_txn = rupees_to_paise(data["default_per_txn_limit"]) if data.get("default_per_txn_limit") not in (None, "") else None
        daily = rupees_to_paise(data["default_daily_debit_limit"]) if data.get("default_daily_debit_limit") not in (None, "") else None
        min_bal = int(round(float(data["default_min_balance"]) * 100)) if data.get("default_min_balance") not in (None, "") else None
        out = update_default_policy(
            enabled_services=data.get("enabled_services") if isinstance(data.get("enabled_services"), list) else None,
            enabled_bbps_categories=(
                data.get("enabled_bbps_categories") if isinstance(data.get("enabled_bbps_categories"), list) else None
            ),
            bbps_biller_allowlist=(
                data.get("bbps_biller_allowlist") if isinstance(data.get("bbps_biller_allowlist"), dict) else None
            ),
            allow_wallet_pay=data.get("allow_wallet_pay") if "allow_wallet_pay" in data else None,
            allow_pg_pay=data.get("allow_pg_pay") if "allow_pg_pay" in data else None,
            allow_pg_topup=data.get("allow_pg_topup") if "allow_pg_topup" in data else None,
            pg_provider=data.get("pg_provider") if "pg_provider" in data else None,
            bbps_pipe=data.get("bbps_pipe") if "bbps_pipe" in data else None,
            bbps_bulk_enabled=data.get("bbps_bulk_enabled") if "bbps_bulk_enabled" in data else None,
            default_per_txn_limit_paise=per_txn,
            default_daily_debit_limit_paise=daily,
            default_min_balance_paise=min_bal,
            admin_email=request.user.email,
        )
        request._hub_logged = True
        return Response(out)


class DefaultBbpsBillersView(DeskView):
    def get(self, request):
        category = (request.query_params.get("category") or "").strip()
        query = (request.query_params.get("q") or "").strip()
        try:
            limit = int(request.query_params.get("limit") or 400)
        except (TypeError, ValueError):
            limit = 400
        if not category:
            return Response({"error": "Send ?category=ELECTRICITY", "code": "validation"}, status=400)
        return Response(list_default_bbps_billers(category=category, query=query, limit=limit))


class RetailerEntitlementsView(DeskView):
    def get(self, request):
        email = (request.query_params.get("email") or "").strip().lower()
        if not email:
            return Response({"error": "Send ?email=retailer@...", "code": "validation"}, status=400)
        return Response(resolve_retailer_entitlements(email))

    def post(self, request):
        bind_action(actor=request.user.email, role=ADMIN_ROLE, app_context="payswap")
        data = request.data if isinstance(request.data, dict) else {}
        email = str(data.get("email") or "").strip().lower()
        if not email or "@" not in email:
            return Response({"error": "Send a valid retailer email.", "code": "validation"}, status=400)
        overrides = data.get("service_overrides") if isinstance(data.get("service_overrides"), dict) else None
        bbps_overrides = (
            data.get("bbps_category_overrides") if isinstance(data.get("bbps_category_overrides"), dict) else None
        )
        kwargs: dict = {
            "service_overrides": overrides,
            "bbps_category_overrides": bbps_overrides,
            "clear_payment_overrides": bool(data.get("clear_payment_overrides", False)),
            "admin_email": request.user.email,
        }
        for key in ("allow_wallet_pay", "allow_pg_pay", "allow_pg_topup", "bbps_pipe", "bbps_bulk_enabled"):
            if key in data:
                kwargs[key] = data[key]
        out = update_retailer_entitlements(email, **kwargs)
        request._hub_logged = True
        return Response(out)


class WalletsView(DeskView):
    def get(self, request):
        email = (request.query_params.get("email") or "").strip().lower()
        if email:
            data = wallet_overview(email)
            data["entitlements"] = resolve_retailer_entitlements(email)
            data["pending_adjustments"] = pending_wallet_adjustments(email)
            return Response(data)
        wallets = [serialize_wallet(w) for w in WalletAccount.objects.all().order_by("-updated_at")[:200]]
        topup_rows = list(WalletTopupRequest.objects.select_related("wallet").order_by("-created_at", "-id")[:200])
        topup_ids = [r.request_id for r in topup_rows]
        topup_ledgers = (
            {
                e.reference: e
                for e in WalletLedgerEntry.objects.filter(reference__in=topup_ids, entry_type="TOPUP_ADMIN")
            }
            if topup_ids
            else {}
        )
        topups = [
            serialize_topup_request(r, wallet=r.wallet, ledger_entry=topup_ledgers.get(r.request_id))
            for r in topup_rows
        ]
        pg_topups = [
            {
                "pg_order_id": p.pg_order_id,
                "user_id": p.user_id,
                "provider": p.provider,
                "amount": paise_to_rupees_str(p.amount_paise),
                "status": p.status,
                "provider_order_id": p.provider_order_id,
                "provider_payment_id": p.provider_payment_id,
                "checkout_url": p.checkout_url or "",
                "signature_verified": bool(p.signature_verified),
                "paid_at": p.paid_at.isoformat() if p.paid_at else "",
                "created_at": p.created_at.isoformat() if p.created_at else "",
                "updated_at": p.updated_at.isoformat() if p.updated_at else "",
            }
            for p in PgOrder.objects.filter(purpose="wallet_topup").order_by("-created_at")[:100]
        ]
        recent_ledger = [
            {
                **serialize_ledger_entry(e),
                "user_id": e.wallet.user_id,
            }
            for e in WalletLedgerEntry.objects.select_related("wallet").order_by("-created_at", "-id")[:200]
        ]
        return Response(
            {
                "wallets": wallets,
                "topup_requests": topups,
                "pg_topups": pg_topups,
                "ledger": recent_ledger,
            }
        )


class WalletTopupReviewView(DeskView):
    def post(self, request):
        bind_action(actor=request.user.email, role=ADMIN_ROLE, app_context="payswap")
        data = request.data if isinstance(request.data, dict) else {}
        request_id = str(data.get("request_id") or "").strip()
        decision = str(data.get("decision") or "").strip().lower()
        note = str(data.get("note") or "")
        out = review_topup_request(
            request_id,
            decision=decision,
            admin_email=request.user.email,
            note=note,
        )
        request._hub_logged = True
        return Response(out)


class WalletAdjustView(DeskView):
    def post(self, request):
        bind_action(actor=request.user.email, role=ADMIN_ROLE, app_context="payswap")
        data = request.data if isinstance(request.data, dict) else {}
        email = str(data.get("email") or "").strip().lower()
        if not email or "@" not in email:
            return Response({"error": "Send a valid retailer email.", "code": "validation"}, status=400)
        direction = str(data.get("direction") or "CR").strip().upper()
        amount_paise = rupees_to_paise(data.get("amount", 0))
        reason = str(data.get("reason") or "")
        out = admin_adjust_wallet(
            email,
            direction=direction,
            amount_paise=amount_paise,
            reason=reason,
            admin_email=request.user.email,
            idempotency_key=request.headers.get("Idempotency-Key", ""),
        )
        request._hub_logged = True
        return Response(out)


class WalletAdjustReviewView(DeskView):
    def post(self, request):
        bind_action(actor=request.user.email, role=ADMIN_ROLE, app_context="payswap")
        data = request.data if isinstance(request.data, dict) else {}
        out = review_wallet_adjustment(
            str(data.get("adjustment_id") or "").strip(),
            decision=str(data.get("decision") or ""),
            admin_email=request.user.email,
            note=str(data.get("note") or ""),
        )
        request._hub_logged = True
        return Response(out)


class WalletControlsView(DeskView):
    def post(self, request):
        bind_action(actor=request.user.email, role=ADMIN_ROLE, app_context="payswap")
        data = request.data if isinstance(request.data, dict) else {}
        email = str(data.get("email") or "").strip().lower()
        if not email or "@" not in email:
            return Response({"error": "Send a valid retailer email.", "code": "validation"}, status=400)
        per_txn = rupees_to_paise(data["per_txn_limit"]) if data.get("per_txn_limit") not in (None, "") else None
        daily = rupees_to_paise(data["daily_debit_limit"]) if data.get("daily_debit_limit") not in (None, "") else None
        min_bal = int(round(float(data["min_balance"]) * 100)) if data.get("min_balance") not in (None, "") else None
        out = admin_update_wallet_controls(
            email,
            status=data.get("status"),
            freeze_reason=data.get("freeze_reason"),
            per_txn_limit_paise=per_txn,
            daily_debit_limit_paise=daily,
            min_balance_paise=min_bal,
            reset_pin=bool(data.get("reset_pin", False)),
            admin_email=request.user.email,
        )
        request._hub_logged = True
        return Response({"wallet": out})


class AdminTransactionsView(DeskView):
    def get(self, request):
        email = (request.query_params.get("email") or "").strip().lower()
        state = (request.query_params.get("state") or "all").strip().lower()
        channel = (request.query_params.get("channel") or "all").strip().lower()
        query = (request.query_params.get("q") or "").strip()
        source = (request.query_params.get("source") or "all").strip().lower()
        batch_id = (request.query_params.get("batch_id") or "").strip()
        try:
            limit = int(request.query_params.get("limit") or 200)
        except (TypeError, ValueError):
            limit = 200
        return Response(
            list_admin_transactions(
                user_id=email,
                state=state,
                channel=channel,
                query=query,
                source=source,
                batch_id=batch_id,
                limit=limit,
            )
        )


class AdminBbpsSyncView(DeskView):
    def post(self, request):
        bind_action(actor=request.user.email, role=ADMIN_ROLE, app_context="payswap")
        data = request.data if isinstance(request.data, dict) else {}
        ref = str(data.get("reference") or "").strip()
        if not ref:
            return Response({"error": "Send transaction reference.", "code": "validation"}, status=400)
        out = check_status(reference=ref, user_id=request.user.email, actor_role=ADMIN_ROLE)
        request._hub_logged = True
        return Response(out)


class AdminBulkBbpsView(DeskView):
    def get(self, request):
        from domain.payswap.bulk_bbps import admin_list_batches

        bind_action(actor=request.user.email, role=ADMIN_ROLE, app_context="payswap")
        q = (request.query_params.get("q") or "").strip()
        try:
            limit = int(request.query_params.get("limit") or 50)
        except (TypeError, ValueError):
            limit = 50
        return Response(admin_list_batches(limit=limit, q=q))


class AdminBulkBbpsBatchView(DeskView):
    def get(self, request, batch_id: str):
        from domain.payswap.bulk_bbps import list_rows, process_fetch_queue, serialize_batch

        bind_action(actor=request.user.email, role=ADMIN_ROLE, app_context="payswap")
        process_fetch_queue(limit=5, batch_id=batch_id)
        return Response(
            {
                "batch": serialize_batch(batch_id, admin=True),
                "rows": list_rows(batch_id, admin=True, limit=200).get("rows") or [],
            }
        )

    def post(self, request, batch_id: str):
        from domain.payswap.bulk_bbps import process_fetch_queue, serialize_batch

        bind_action(actor=request.user.email, role=ADMIN_ROLE, app_context="payswap")
        data = request.data if isinstance(request.data, dict) else {}
        action = str(data.get("action") or "sync").strip().lower()
        if action in {"sync", "fetch"}:
            done = process_fetch_queue(limit=20, batch_id=batch_id)
            request._hub_logged = True
            log_action(
                action="desk.bbps.bulk.sync",
                outcome="ok",
                status=200,
                duration_ms=0,
                target_id=batch_id,
                request=f"action={action}",
                response=f"HTTP 200\nfetched={done}",
            )
            return Response({"batch": serialize_batch(batch_id, admin=True), "fetched": done})
        return Response({"error": "Unsupported action. Use sync.", "code": "validation"}, status=400)


class AdminPgSyncView(DeskView):
    def post(self, request):
        bind_action(actor=request.user.email, role=ADMIN_ROLE, app_context="payswap")
        data = request.data if isinstance(request.data, dict) else {}
        pg_order_id = str(data.get("pg_order_id") or "").strip()
        if not pg_order_id:
            return Response({"error": "Send pg_order_id.", "code": "validation"}, status=400)
        out = verify_pg_order(pg_order_id)
        request._hub_logged = True
        return Response(out)


class CommissionPolicyView(DeskView):
    def get(self, request):
        from domain.payswap.economics.policy import serialize_service_policy

        service = str(request.query_params.get("service") or "bbps").strip().lower() or "bbps"
        if service == "all":
            service = "bbps"
        return Response(serialize_service_policy(service=service))

    def post(self, request):
        from domain.payswap.economics.policy import update_service_policy

        bind_action(actor=request.user.email, role=ADMIN_ROLE, app_context="payswap")
        data = request.data if isinstance(request.data, dict) else {}
        service = str(data.get("service") or request.query_params.get("service") or "bbps").strip().lower() or "bbps"
        if service == "all":
            service = "bbps"
        raw_tan = data.get("deductor_tan")
        if raw_tan is not None and str(raw_tan).strip() and not TAN_RE.fullmatch(str(raw_tan).strip().upper()):
            return Response(
                {"error": "TAN must be 4 letters, 5 digits, and 1 letter.", "code": "validation"},
                status=400,
            )
        out = update_service_policy(
            service,
            actor=request.user.email,
            monetization_mode=data.get("monetization_mode"),
            admin_share_bps=data.get("admin_share_bps"),
            tds_rate_bps=data.get("tds_rate_bps"),
            gst_rate_bps=data.get("gst_rate_bps"),
            tds_threshold_paise=data.get("tds_threshold_paise"),
            withhold_tds_always=data.get("withhold_tds_always"),
        )
        # TAN and the 206AA rate are company-wide. BBPS still mirrors the 194H rate fields.
        if service == "bbps" or raw_tan is not None or data.get("no_pan_tds_rate_bps") is not None:
            try:
                saved = update_policy(
                    actor=request.user.email,
                    sync_bbps=service == "bbps",
                    admin_share_bps=data.get("admin_share_bps") if service == "bbps" else None,
                    tds_rate_bps=data.get("tds_rate_bps") if service == "bbps" else None,
                    gst_rate_bps=data.get("gst_rate_bps") if service == "bbps" else None,
                    tds_threshold_paise=data.get("tds_threshold_paise") if service == "bbps" else None,
                    withhold_tds_always=data.get("withhold_tds_always") if service == "bbps" else None,
                    deductor_tan=raw_tan,
                    no_pan_tds_rate_bps=data.get("no_pan_tds_rate_bps"),
                )
            except ValueError as exc:
                return Response({"error": str(exc), "code": "validation"}, status=400)
            out["deductor_tan"] = saved.get("deductor_tan") or ""
            out["no_pan_tds_rate_bps"] = saved.get("no_pan_tds_rate_bps")
            out["no_pan_tds_rate_percent"] = saved.get("no_pan_tds_rate_percent")
        request._hub_logged = True
        return Response(out)


class CommissionRatesView(DeskView):
    def get(self, request):
        return Response(
            list_rates(
                service=str(request.query_params.get("service") or "bbps"),
                category=str(request.query_params.get("category") or ""),
                q=str(request.query_params.get("q") or ""),
                limit=int(request.query_params.get("limit") or 200),
            )
        )

    def post(self, request):
        """Save one editable commission-table row (ServiceRateRow)."""
        from domain.payswap.economics.catalogue import update_rate_row

        bind_action(actor=request.user.email, role=ADMIN_ROLE, app_context="payswap")
        data = request.data if isinstance(request.data, dict) else {}
        try:
            out = update_rate_row(
                service=str(data.get("service") or "bbps"),
                external_id=str(data.get("external_id") or data.get("operator_id") or ""),
                category=str(data.get("category") or ""),
                actor=request.user.email,
                name=data.get("name") if "name" in data else None,
                rate_value=data.get("rate_value"),
                rate_type=data.get("rate_type"),
                min_txn_paise=data.get("min_txn_paise"),
                min_txn=data.get("min_txn"),
                enabled=data.get("enabled") if "enabled" in data else None,
            )
        except ValueError as exc:
            return Response({"error": str(exc), "code": "validation"}, status=400)
        request._hub_logged = True
        return Response({"ok": True, "rate": out})


class CommissionRatesImportView(DeskView):
    def post(self, request):
        bind_action(actor=request.user.email, role=ADMIN_ROLE, app_context="payswap")
        data = request.data if isinstance(request.data, dict) else {}
        raw = str(data.get("path") or "").strip()
        if raw:
            path = Path(raw).expanduser()
        else:
            path = Path(__file__).resolve().parents[3] / "data" / "mobikwik" / "commission-b2b.xlsx"
        try:
            out = import_vendor_sheet(path, actor=request.user.email)
        except ValueError as exc:
            return Response({"error": str(exc), "code": "validation"}, status=400)
        request._hub_logged = True
        return Response(out)


class CommissionRetailerView(DeskView):
    def get(self, request):
        email = (request.query_params.get("email") or "").strip().lower()
        if not email:
            return Response({"error": "email is required.", "code": "validation"}, status=400)
        entitlements = resolve_retailer_entitlements(email)
        out = serialize_retailer_override(get_retailer_override(email), user_id=email)
        out["sheet"] = retailer_commission_sheet(
            email,
            enabled_services=entitlements.get("enabled_services") or [],
        )
        out["enabled_services"] = entitlements.get("enabled_services") or []
        sheet_service = str(request.query_params.get("sheet") or "").strip().lower()
        if sheet_service:
            try:
                limit = int(request.query_params.get("limit") or 200)
            except (TypeError, ValueError):
                limit = 200
            try:
                out["catalogue"] = retailer_service_catalogue(
                    email,
                    sheet_service,
                    category=str(request.query_params.get("category") or ""),
                    query=str(request.query_params.get("q") or ""),
                    limit=limit,
                )
            except ValueError as exc:
                return Response({"error": str(exc), "code": "validation"}, status=400)
        return Response(out)

    def post(self, request):
        bind_action(actor=request.user.email, role=ADMIN_ROLE, app_context="payswap")
        data = request.data if isinstance(request.data, dict) else {}
        email = str(data.get("email") or "").strip().lower()
        if not email:
            return Response({"error": "email is required.", "code": "validation"}, status=400)
        service = str(data.get("service") or "").strip().lower()
        external_id = str(data.get("external_id") or "").strip()
        if service and external_id:
            try:
                retailer_service_catalogue_out = update_retailer_biller_share(
                    email,
                    service,
                    external_id,
                    str(data.get("category") or ""),
                    actor=request.user.email,
                    admin_share_bps=data.get("admin_share_bps"),
                    clear_share=bool(data.get("clear_share")),
                )
            except ValueError as exc:
                return Response({"error": str(exc), "code": "validation"}, status=400)
            entitlements = resolve_retailer_entitlements(email)
            out = serialize_retailer_override(get_retailer_override(email), user_id=email)
            out["sheet"] = retailer_commission_sheet(
                email,
                enabled_services=entitlements.get("enabled_services") or [],
            )
            out["catalogue"] = retailer_service_catalogue_out
            request._hub_logged = True
            return Response(out)
        if service:
            try:
                update_retailer_service_share(
                    email,
                    service,
                    actor=request.user.email,
                    admin_share_bps=data.get("admin_share_bps"),
                    clear_share=bool(data.get("clear_share")),
                )
            except ValueError as exc:
                return Response({"error": str(exc), "code": "validation"}, status=400)
            entitlements = resolve_retailer_entitlements(email)
            out = serialize_retailer_override(get_retailer_override(email), user_id=email)
            out["sheet"] = retailer_commission_sheet(
                email,
                enabled_services=entitlements.get("enabled_services") or [],
            )
            request._hub_logged = True
            return Response(out)
        out = update_retailer_override(
            email,
            actor=request.user.email,
            admin_share_bps=data.get("admin_share_bps"),
            operator_overrides=data.get("operator_overrides"),
            active=data.get("active"),
            clear_share=bool(data.get("clear_share")),
        )
        entitlements = resolve_retailer_entitlements(email)
        out["sheet"] = retailer_commission_sheet(
            email,
            enabled_services=entitlements.get("enabled_services") or [],
        )
        request._hub_logged = True
        return Response(out)


class CommissionRevenueView(DeskView):
    def get(self, request):
        month = str(request.query_params.get("month") or "").strip()
        service = str(request.query_params.get("service") or "all").strip() or "all"
        try:
            limit = int(request.query_params.get("limit") or 50)
        except (TypeError, ValueError):
            limit = 50
        return Response(revenue_report(month=month, service=service, limit=limit))


class CommissionTdsView(DeskView):
    def get(self, request):
        month = str(request.query_params.get("month") or "").strip()
        return Response(tds_month_report(month=month))

    def post(self, request):
        bind_action(actor=request.user.email, role=ADMIN_ROLE, app_context="payswap")
        data = request.data if isinstance(request.data, dict) else {}
        month = str(data.get("month") or "").strip()
        if not month:
            return Response({"error": "month is required (YYYY-MM).", "code": "validation"}, status=400)
        try:
            out = mark_tds_deposited(
                month=month,
                user_id=str(data.get("email") or data.get("user_id") or "").strip().lower(),
                actor=request.user.email,
                challan_bsr=str(data.get("challan_bsr") or ""),
                challan_serial=str(data.get("challan_serial") or ""),
                challan_date=str(data.get("challan_date") or ""),
                challan_amount=data.get("challan_amount"),
            )
        except ValueError as exc:
            request._hub_logged = True
            return Response({"error": str(exc), "code": "validation"}, status=400)
        request._hub_logged = True
        return Response(out)


class CommissionTdsCertificateView(DeskView):
    def get(self, request):
        return Response(list_tds_certificates())

    def post(self, request):
        bind_action(actor=request.user.email, role=ADMIN_ROLE, app_context="payswap")
        data = request.data if isinstance(request.data, dict) else {}
        decision = str(data.get("decision") or "").strip().lower()
        try:
            if decision == "approve":
                out = approve_tds_certificate(certificate_id=data.get("id"), actor=request.user.email)
            elif decision == "reject":
                out = reject_tds_certificate(
                    certificate_id=data.get("id"),
                    actor=request.user.email,
                    reason=str(data.get("reason") or ""),
                )
            else:
                raise ValueError("Choose approve or reject.")
        except ValueError as exc:
            request._hub_logged = True
            return Response({"error": str(exc), "code": "validation"}, status=400)
        request._hub_logged = True
        return Response(out)


class CommissionInvoiceView(DeskView):
    def get(self, request):
        email = (request.query_params.get("email") or "").strip().lower()
        month = str(request.query_params.get("month") or "").strip()
        qs = CommissionInvoice.objects.all().order_by("-created_at")
        if email:
            qs = qs.filter(user_id=email)
        if month:
            qs = qs.filter(month=month)
        return Response({"invoices": [serialize_invoice(r) for r in qs[:100]]})

    def post(self, request):
        bind_action(actor=request.user.email, role=ADMIN_ROLE, app_context="payswap")
        data = request.data if isinstance(request.data, dict) else {}
        email = str(data.get("email") or "").strip().lower()
        month = str(data.get("month") or "").strip()
        if not email or not month:
            return Response({"error": "email and month are required.", "code": "validation"}, status=400)
        gstin = str(data.get("gstin") or retailer_gstin(email) or "").strip()
        if not gstin:
            return Response({"error": "Retailer has no GSTIN on profile.", "code": "validation"}, status=400)
        try:
            out = create_monthly_invoice(
                user_id=email,
                month=month,
                gstin=gstin,
                actor=request.user.email,
                place_of_supply_same_state=bool(data.get("same_state", True)),
            )
        except ValueError as exc:
            return Response({"error": str(exc), "code": "validation"}, status=400)
        request._hub_logged = True
        return Response(out)


def _actor_filter(rows, request):
    email = (request.query_params.get("email") or "").strip().lower()
    if not email:
        return rows
    return rows.filter(user_id=email)


def _session_row(row) -> dict:
    body = row.body if isinstance(row.body, dict) else {}
    return {
        "actor": row.user_id,
        "reference": _clip(body.get("reference"), 80),
        "site_code": _clip(body.get("site_code"), 40),
        "bay": _clip(body.get("bay"), 20),
        "vehicle": _clip(body.get("vehicle"), 20),
        "state": _clip(row.desk_state or body.get("state") or row.state, 20),
        "status": row.status_code,
        "at": row.created_at.isoformat(),
    }


def _order_row(row) -> dict:
    body = row.body if isinstance(row.body, dict) else {}
    return {
        "actor": row.user_id,
        "reference": _clip(body.get("reference"), 80),
        "brand": _clip(body.get("brand"), 40),
        "amount": _clip(body.get("amount"), 20),
        "state": _clip(body.get("state") or row.state, 20),
        "status": row.status_code,
        "at": row.created_at.isoformat(),
    }


def _clip(value, limit: int) -> str:
    if not isinstance(value, str):
        return ""
    return value[:limit]
