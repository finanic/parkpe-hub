"""PaySwap /api/v1 routes.

Callers: apps/payswap/js/hub.js via packages/sdk-client
(X-App-Context: payswap, role retailer from packages/contracts).
payswap_only rejects a parkpe context with 403 before domain runs.
Every service/payment-rail view enforces domain/payswap/entitlements.py.
"""

from __future__ import annotations

import json
import re
import time

from api.v1.deps import payswap_only
from api.v1.routes.support import post_mutation
from core.actions import bind_action, elapsed_ms, log_action
from core.idempotency import IDEMPOTENCY_HEADER
from domain.payswap.bbps import (
    catalogue,
    check_status,
    collect,
    mask_consumer_account,
    execute_pg_paid_bbps,
    fetch_bill_details,
    prepaid_plans,
    telecom_circles,
)
from domain.payswap.commission import retailer_commission_summary, retailer_tds_position, submit_tds_certificate
from domain.payswap.entitlements import require_retailer_service, resolve_retailer_entitlements
from domain.payswap.transactions import list_retailer_transactions
from domain.payswap.wallet import (
    apply_pg_topup_paid,
    create_pg_topup_order,
    paid_rupees_match,
    rupees_to_paise,
    set_wallet_pin,
    submit_topup_request,
    verify_pg_order,
    wallet_overview,
)
from domain.payswap.vouchers import order_voucher
from integrations.pg import verify_webhook_signature
from models.models import PgOrder
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from schemas.serializers import (
    BbpsFetchBillSerializer,
    BbpsPaymentSerializer,
    PgOrderCreateSerializer,
    PgOrderVerifySerializer,
    VoucherOrderSerializer,
    WalletPinSerializer,
    WalletTopupRequestSerializer,
)

_REF_RE = re.compile(r"^[A-Za-z0-9._-]{4,80}$")


@payswap_only
class EntitlementsView(APIView):
    def get(self, request):
        bind_action(
            app_context=request.user.app_context,
            actor=request.user.user_id,
            role=request.user.role,
        )
        return Response(resolve_retailer_entitlements(request.user.user_id), status=200)


@payswap_only
class WalletView(APIView):
    def get(self, request):
        bind_action(
            app_context=request.user.app_context,
            actor=request.user.user_id,
            role=request.user.role,
        )
        require_retailer_service(request.user.user_id, "wallet")
        data = wallet_overview(request.user.user_id)
        data["entitlements"] = resolve_retailer_entitlements(request.user.user_id)["payment_modes"]
        data["commission"] = retailer_commission_summary(user_id=request.user.user_id)
        return Response(data, status=200)


@payswap_only
class CommissionSummaryView(APIView):
    def get(self, request):
        bind_action(
            app_context=request.user.app_context,
            actor=request.user.user_id,
            role=request.user.role,
        )
        service = str(request.query_params.get("service") or "all").strip().lower() or "all"
        if service == "all":
            require_retailer_service(request.user.user_id, "wallet")
        else:
            require_retailer_service(request.user.user_id, service if service in {"bbps", "aeps", "dmt", "recharge", "vouchers"} else "bbps")
        month = str(request.query_params.get("month") or "").strip()
        return Response(
            retailer_commission_summary(user_id=request.user.user_id, month=month, service=service),
            status=200,
        )


@payswap_only
class RetailerTdsCertificateView(APIView):
    """Retailer files a Section 197 certificate. Approval stays on the admin desk."""

    def get(self, request):
        bind_action(
            app_context=request.user.app_context,
            actor=request.user.user_id,
            role=request.user.role,
        )
        return Response(retailer_tds_position(request.user.user_id), status=200)

    def post(self, request):
        bind_action(
            app_context=request.user.app_context,
            actor=request.user.user_id,
            role=request.user.role,
        )
        data = request.data if isinstance(request.data, dict) else {}
        rate = data.get("rate_bps")
        if rate is None and data.get("rate_percent") is not None:
            rate = int(round(float(data.get("rate_percent") or 0) * 100))
        try:
            out = submit_tds_certificate(
                user_id=request.user.user_id,
                actor=request.user.user_id,
                certificate_no=data.get("certificate_no"),
                rate_bps=rate,
                valid_from=data.get("valid_from"),
                valid_to=data.get("valid_to"),
            )
        except ValueError as exc:
            request._hub_logged = True
            return Response({"error": str(exc), "code": "validation"}, status=400)
        request._hub_logged = True
        return Response(out, status=200)


@payswap_only
class WalletTopupRequestView(APIView):
    def post(self, request):
        return post_mutation(
            request,
            WalletTopupRequestSerializer,
            lambda data, user_id: submit_topup_request(
                user_id,
                amount_paise=rupees_to_paise(data["amount"]),
                mode=data["mode"],
                utr=data["utr"],
                remarks=data.get("remarks", ""),
            ),
            action="payswap.wallet.topup.request",
            external=True,
        )


@payswap_only
class WalletPinView(APIView):
    def post(self, request):
        started = time.perf_counter()
        bind_action(
            app_context=request.user.app_context,
            actor=request.user.user_id,
            role=request.user.role,
        )
        require_retailer_service(request.user.user_id, "wallet")
        serializer = WalletPinSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        out = set_wallet_pin(
            request.user.user_id,
            new_pin=data["new_pin"],
            current_pin=data.get("current_pin", ""),
        )
        request._hub_logged = True
        log_action(
            action="payswap.wallet.pin",
            outcome="ok",
            status=200,
            duration_ms=elapsed_ms(started),
            target_id=request.user.user_id,
            request="POST /api/v1/payswap/wallet/pin",
            response='HTTP 200\n{"ok":true}',
        )
        return Response(out, status=200)


@payswap_only
class PgOrderCreateView(APIView):
    def post(self, request):
        return post_mutation(
            request,
            PgOrderCreateSerializer,
            lambda data, user_id: create_pg_topup_order(
                user_id,
                amount_paise=rupees_to_paise(data["amount"]),
                customer_phone=data.get("customer_phone", ""),
            ),
            action="payswap.pg.order.create",
            external=True,
        )


@payswap_only
class PgOrderVerifyView(APIView):
    def post(self, request):
        started = time.perf_counter()
        bind_action(
            app_context=request.user.app_context,
            actor=request.user.user_id,
            role=request.user.role,
        )
        serializer = PgOrderVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        out = verify_pg_order(serializer.validated_data["pg_order_id"], user_id=request.user.user_id)
        request._hub_logged = True
        log_action(
            action="payswap.pg.order.verify",
            outcome="ok",
            status=200,
            duration_ms=elapsed_ms(started),
            target_id=serializer.validated_data["pg_order_id"],
            request=f"POST /api/v1/payswap/pg/verify\norder={serializer.validated_data['pg_order_id']}",
            response=f"HTTP 200\nstatus={out.get('status', '')}",
        )
        return Response(out, status=200)


class PgWebhookView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        sig = request.headers.get("x-webhook-signature", "")
        ts = request.headers.get("x-webhook-timestamp", "")
        if not verify_webhook_signature(request.body or b"", ts, sig):
            return Response({"error": "Invalid webhook signature.", "code": "unauthenticated"}, status=401)
        payload = request.data if isinstance(request.data, dict) else {}
        data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        order_info = data.get("order") if isinstance(data.get("order"), dict) else {}
        payment_info = data.get("payment") if isinstance(data.get("payment"), dict) else {}
        order_id = str(order_info.get("order_id") or "").strip()
        payment_status = str(payment_info.get("payment_status") or "").upper()
        cf_payment_id = str(payment_info.get("cf_payment_id") or "")
        order = PgOrder.objects.filter(pg_order_id=order_id).first()
        if not order:
            return Response({"ok": True, "ignored": True}, status=200)
        if payment_status == "SUCCESS":
            reported = (payment_info.get("payment_amount"), order_info.get("order_amount"))
            if not paid_rupees_match(int(order.amount_paise), *reported):
                log_action(
                    action="payswap.pg.webhook",
                    outcome="error",
                    status=400,
                    duration_ms=0,
                    target_id=order.pg_order_id,
                    error_code="validation",
                    error_reason="amount mismatch",
                    request=f"order={order.pg_order_id}",
                    response="HTTP 200\nignored amount",
                )
                return Response({"ok": True, "ignored": True}, status=200)
            paid_amount = str(payment_info.get("payment_amount") or order_info.get("order_amount") or "")
            if order.purpose == "wallet_topup":
                apply_pg_topup_paid(
                    order.pg_order_id,
                    provider_payment_id=cf_payment_id,
                    signature_verified=True,
                    paid_amount=paid_amount,
                )
            elif order.purpose == "bbps_direct":
                # Mark paid + ACK webhook; vendor pay continues in a daemon thread.
                execute_pg_paid_bbps(
                    order.pg_order_id,
                    provider_payment_id=cf_payment_id,
                    paid_amount=paid_amount,
                    defer_vendor_pay=True,
                )
        elif payment_status in {"FAILED", "USER_DROPPED"} and order.status == "created":
            order.status = "failed"
            order.save(update_fields=["status", "updated_at"])
        return Response({"ok": True}, status=200)


@payswap_only
class TransactionsView(APIView):
    def get(self, request):
        bind_action(
            app_context=request.user.app_context,
            actor=request.user.user_id,
            role=request.user.role,
        )
        require_retailer_service(request.user.user_id, "transactions")
        service = str(request.query_params.get("service") or "all").strip().lower()
        state = str(request.query_params.get("state") or "all").strip().lower()
        query = str(request.query_params.get("q") or "").strip()[:80]
        source = str(request.query_params.get("source") or "all").strip().lower()
        batch_id = str(request.query_params.get("batch_id") or "").strip()[:64]
        return Response(
            list_retailer_transactions(
                request.user.user_id,
                service=service,
                state=state,
                query=query,
                source=source,
                batch_id=batch_id,
            ),
            status=200,
        )


@payswap_only
class VoucherOrderView(APIView):
    def post(self, request):
        require_retailer_service(request.user.user_id, "vouchers")
        return post_mutation(
            request,
            VoucherOrderSerializer,
            lambda data, user_id: order_voucher(
                user_id=user_id,
                brand=data["brand"],
                amount=data["amount"],
            ),
            action="payswap.voucher.order",
        )


@payswap_only
class BbpsOperatorsView(APIView):
    def get(self, request):
        started = time.perf_counter()
        bind_action(
            app_context=request.user.app_context,
            actor=request.user.user_id,
            role=request.user.role,
        )
        require_retailer_service(request.user.user_id, "bbps")
        category = str(request.query_params.get("category") or "").strip()[:64]
        query = str(request.query_params.get("q") or "").strip()[:80]
        raw_limit = str(request.query_params.get("limit") or "200").strip()
        try:
            limit = max(1, min(int(raw_limit), 500))
        except ValueError:
            limit = 200
        body = catalogue(category=category, query=query, limit=limit, user_id=request.user.user_id)
        request._hub_logged = True
        log_action(
            action="payswap.bbps.operators",
            outcome="ok",
            status=200,
            duration_ms=elapsed_ms(started),
            target_id=category or ("search" if query else "categories"),
            request=f"GET {request.path}\n" + json.dumps({"category": category, "q": query, "limit": limit}, separators=(",", ":")),
            response="HTTP 200\n" + json.dumps(
                {
                    "configured": bool(body.get("configured")),
                    "categories": len(body.get("categories") or []),
                    "operators": len(body.get("operators") or []),
                },
                separators=(",", ":"),
            ),
        )
        return Response(body, status=200)


@payswap_only
class BbpsPlansView(APIView):
    """GET /api/v1/payswap/bbps/plans — prepaid/DTH packs from Mobikwik rechargePlansAPI."""

    def get(self, request):
        started = time.perf_counter()
        bind_action(
            app_context=request.user.app_context,
            actor=request.user.user_id,
            role=request.user.role,
        )
        require_retailer_service(request.user.user_id, "bbps")
        biller = str(request.query_params.get("biller") or "").strip()
        account = str(request.query_params.get("account") or request.query_params.get("mobile") or "").strip()
        circle = str(request.query_params.get("circle") or request.query_params.get("cir") or "").strip()
        if not biller or not account or not circle:
            raise ValidationError(detail={"error": "biller, account, and circle are required.", "code": "validation"})
        req_text = "GET /api/v1/payswap/bbps/plans\n" + json.dumps(
            {"biller": biller, "circle": circle, "account_len": len(account)},
            separators=(",", ":"),
        )
        try:
            body = prepaid_plans(biller=biller, account=account, circle=circle, user_id=request.user.user_id)
        except Exception as exc:
            request._hub_logged = True
            status_code = getattr(exc, "status_code", 502)
            detail = getattr(exc, "detail", None)
            reason = str(detail.get("error") if isinstance(detail, dict) else exc)
            code = str(detail.get("code") if isinstance(detail, dict) else "server_error")
            log_action(
                action="payswap.bbps.plans",
                outcome="error",
                status=status_code,
                duration_ms=elapsed_ms(started),
                target_id=biller,
                error_code=code,
                error_reason=reason,
                request=req_text,
                response=f"HTTP {status_code}\n{reason}",
            )
            raise
        request._hub_logged = True
        log_action(
            action="payswap.bbps.plans",
            outcome="ok",
            status=200,
            duration_ms=elapsed_ms(started),
            target_id=str(body.get("operator_id") or biller),
            request=req_text,
            response="HTTP 200\n" + json.dumps({"plans": len(body.get("plans") or [])}, separators=(",", ":")),
        )
        return Response(body, status=200)


@payswap_only
class BbpsCirclesView(APIView):
    """GET /api/v1/payswap/bbps/circles — Mobikwik prepaid telecom circle codes."""

    def get(self, request):
        started = time.perf_counter()
        bind_action(
            app_context=request.user.app_context,
            actor=request.user.user_id,
            role=request.user.role,
        )
        require_retailer_service(request.user.user_id, "bbps")
        body = telecom_circles(user_id=request.user.user_id)
        request._hub_logged = True
        log_action(
            action="payswap.bbps.circles",
            outcome="ok",
            status=200,
            duration_ms=elapsed_ms(started),
            target_id="circles",
            request=f"GET {request.path}",
            response="HTTP 200\n" + json.dumps({"circles": len(body.get("circles") or [])}, separators=(",", ":")),
        )
        return Response(body, status=200)


@payswap_only
class BbpsFetchBillView(APIView):
    def post(self, request):
        started = time.perf_counter()
        bind_action(
            app_context=request.user.app_context,
            actor=request.user.user_id,
            role=request.user.role,
        )
        require_retailer_service(request.user.user_id, "bbps")
        serializer = BbpsFetchBillSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        req_text = "POST /api/v1/payswap/bbps/fetch-bill\n" + json.dumps(
            {
                "biller": data["biller"],
                "account": mask_consumer_account(data["account"]),
                "circle": data.get("circle", ""),
                "payment_mode": data.get("payment_mode", ""),
                "ad_params": data.get("ad_params") or {},
            },
            separators=(",", ":"),
        )
        try:
            body = fetch_bill_details(
                biller=data["biller"],
                account=data["account"],
                circle=data.get("circle", ""),
                payment_mode=data.get("payment_mode", ""),
                ad_params=data.get("ad_params") or {},
                user_id=request.user.user_id,
            )
        except Exception as exc:
            request._hub_logged = True
            status_code = getattr(exc, "status_code", 502)
            detail = getattr(exc, "detail", None)
            reason = str(detail.get("error") if isinstance(detail, dict) else exc)
            code = str(detail.get("code") if isinstance(detail, dict) else "server_error")
            log_action(
                action="payswap.bbps.fetch_bill",
                outcome="error",
                status=status_code,
                duration_ms=elapsed_ms(started),
                target_id=str(data["biller"]),
                error_code=code,
                error_reason=reason,
                request=req_text,
                response=f"HTTP {status_code}\n{reason}",
            )
            raise
        request._hub_logged = True
        log_action(
            action="payswap.bbps.fetch_bill",
            outcome="ok",
            status=200,
            duration_ms=elapsed_ms(started),
            target_id=str(body.get("operator_id") or data["biller"]),
            request=req_text,
            response="HTTP 200\n" + json.dumps(
                {**body, "account": mask_consumer_account(body.get("account", ""))},
                separators=(",", ":"),
            ),
        )
        return Response(body, status=200)


def _summarize_bbps_pay(data, body):
    req = "POST /api/v1/payswap/bbps/pay\n" + json.dumps(
        {
            "biller": data["biller"],
            "account": mask_consumer_account(data["account"]),
            "amount": f"{data['amount']:.2f}",
            "payment_mode": data.get("payment_mode", "Cash"),
            "payment_rail": data.get("payment_rail", "wallet"),
        },
        separators=(",", ":"),
    )
    logged = dict(body) if isinstance(body, dict) else None
    if logged is not None and "account" in logged:
        logged["account"] = mask_consumer_account(logged.get("account", ""))
    resp = ("HTTP 201\n" + json.dumps(logged, separators=(",", ":"))) if logged is not None else ""
    return req, resp


@payswap_only
class BbpsPayView(APIView):
    def post(self, request):
        require_retailer_service(request.user.user_id, "bbps")
        idem_key = request.headers.get(IDEMPOTENCY_HEADER, "")
        return post_mutation(
            request,
            BbpsPaymentSerializer,
            lambda data, user_id: collect(
                biller=data["biller"],
                account=data["account"],
                amount=data["amount"],
                user_id=user_id,
                circle=data.get("circle", ""),
                customer_mobile=data.get("customer_mobile", ""),
                remitter_name=data.get("remitter_name", ""),
                payment_mode=data.get("payment_mode", "Cash"),
                payment_rail=data.get("payment_rail", "wallet"),
                wallet_pin=data.get("wallet_pin", ""),
                idempotency_key=idem_key,
                ad_params=data.get("ad_params") or {},
            ),
            action="payswap.bbps.pay",
            summarize=_summarize_bbps_pay,
            external=True,
        )


@payswap_only
class BbpsStatusView(APIView):
    def get(self, request):
        started = time.perf_counter()
        bind_action(
            app_context=request.user.app_context,
            actor=request.user.user_id,
            role=request.user.role,
        )
        require_retailer_service(request.user.user_id, "bbps")
        reference = str(request.query_params.get("reference") or "").strip()
        if not _REF_RE.fullmatch(reference):
            raise ValidationError(detail={"error": "Send a valid payment reference.", "code": "validation"})
        try:
            body = check_status(reference=reference, user_id=request.user.user_id, actor_role="retailer")
        except Exception as exc:
            request._hub_logged = True
            status_code = getattr(exc, "status_code", 502)
            detail = getattr(exc, "detail", None)
            reason = str(detail.get("error") if isinstance(detail, dict) else exc)
            code = str(detail.get("code") if isinstance(detail, dict) else "server_error")
            log_action(
                action="payswap.bbps.status",
                outcome="error",
                status=status_code,
                duration_ms=elapsed_ms(started),
                target_id=reference,
                error_code=code,
                error_reason=reason,
                request=f"GET {request.path}\n" + json.dumps({"reference": reference}, separators=(",", ":")),
                response=f"HTTP {status_code}\n{reason}",
            )
            raise
        request._hub_logged = True
        log_action(
            action="payswap.bbps.status",
            outcome="ok",
            status=200,
            duration_ms=elapsed_ms(started),
            target_id=reference,
            request=f"GET {request.path}\n" + json.dumps({"reference": reference}, separators=(",", ":")),
            response="HTTP 200\n" + json.dumps(body, separators=(",", ":")),
        )
        return Response(body, status=200)


@payswap_only
class BulkBbpsTemplateView(APIView):
    def get(self, request):
        from domain.payswap.bulk_bbps import template_response
        from domain.payswap.entitlements import require_bbps_bulk

        bind_action(app_context=request.user.app_context, actor=request.user.user_id, role=request.user.role)
        require_bbps_bulk(request.user.user_id)
        op = str(request.query_params.get("op") or "").strip()
        biller_id = str(request.query_params.get("biller_id") or "").strip()
        # Browser download uses GET plan=65:3,99:2 (sdk-client download). POST kept for tests/tools.
        plan_raw = str(request.query_params.get("plan") or "").strip()
        return template_response(
            user_id=request.user.user_id,
            op=op,
            biller_id=biller_id,
            plan_raw=plan_raw,
        )

    def post(self, request):
        """Multi-biller plan: { billers: [{ op, count }, ...] } → CSV with that many blank rows."""
        from domain.payswap.bulk_bbps import template_plan_response
        from domain.payswap.entitlements import require_bbps_bulk

        bind_action(app_context=request.user.app_context, actor=request.user.user_id, role=request.user.role)
        require_bbps_bulk(request.user.user_id)
        data = request.data if isinstance(request.data, dict) else {}
        billers = data.get("billers") if isinstance(data.get("billers"), list) else []
        return template_plan_response(user_id=request.user.user_id, billers=billers)


@payswap_only
class BulkBbpsBatchesView(APIView):
    def get(self, request):
        from domain.payswap.bulk_bbps import list_batches

        bind_action(app_context=request.user.app_context, actor=request.user.user_id, role=request.user.role)
        limit = int(request.query_params.get("limit") or 40)
        return Response(list_batches(user_id=request.user.user_id, limit=limit), status=200)

    def post(self, request):
        from domain.payswap.bulk_bbps import create_batch_from_upload

        started = time.perf_counter()
        bind_action(app_context=request.user.app_context, actor=request.user.user_id, role=request.user.role)
        upload = request.FILES.get("file") or request.FILES.get("upload")
        if upload is None:
            raise ValidationError({"error": "Upload a CSV or Excel file as file.", "code": "validation"})
        locked_op = str(request.data.get("op") or request.data.get("operator_id") or "").strip()
        locked_biller = str(request.data.get("biller_id") or "").strip()
        body = create_batch_from_upload(
            user_id=request.user.user_id,
            upload=upload,
            locked_op=locked_op,
            locked_biller_id=locked_biller,
        )
        request._hub_logged = True
        log_action(
            action="payswap.bbps.bulk.create",
            outcome="ok",
            status=201,
            duration_ms=elapsed_ms(started),
            target_id=body.get("batch_id", ""),
            request=f"POST {request.path}\nfile={getattr(upload, 'name', '')} op={locked_op or '-'}",
            response=f"HTTP 201\nbatch={body.get('batch_id')}",
        )
        return Response(body, status=201)


@payswap_only
class BulkBbpsBatchDetailView(APIView):
    def get(self, request, batch_id: str):
        from domain.payswap.bulk_bbps import serialize_batch

        bind_action(app_context=request.user.app_context, actor=request.user.user_id, role=request.user.role)
        return Response(serialize_batch(batch_id, user_id=request.user.user_id), status=200)


@payswap_only
class BulkBbpsBatchRowsView(APIView):
    def get(self, request, batch_id: str):
        from domain.payswap.bulk_bbps import list_rows

        bind_action(app_context=request.user.app_context, actor=request.user.user_id, role=request.user.role)
        return Response(
            list_rows(
                batch_id,
                user_id=request.user.user_id,
                fetch_state=request.query_params.get("fetch_state") or "",
                pay_state=request.query_params.get("pay_state") or "",
                due_bucket=request.query_params.get("due_bucket") or "",
                q=request.query_params.get("q") or "",
                limit=int(request.query_params.get("limit") or 200),
                offset=int(request.query_params.get("offset") or 0),
            ),
            status=200,
        )


@payswap_only
class BulkBbpsRefetchView(APIView):
    def post(self, request, batch_id: str):
        from domain.payswap.bulk_bbps import refetch_rows

        bind_action(app_context=request.user.app_context, actor=request.user.user_id, role=request.user.role)
        data = request.data if isinstance(request.data, dict) else {}
        row_ids = data.get("row_ids") if isinstance(data.get("row_ids"), list) else None
        return Response(refetch_rows(batch_id, user_id=request.user.user_id, row_ids=row_ids), status=200)


@payswap_only
class BulkBbpsProceedView(APIView):
    def post(self, request, batch_id: str):
        from domain.payswap.bulk_bbps import proceed_batch
        from schemas.serializers import BulkBbpsProceedSerializer

        return post_mutation(
            request,
            BulkBbpsProceedSerializer,
            lambda data, user_id: proceed_batch(
                batch_id,
                user_id=user_id,
                wallet_pin=str(data.get("wallet_pin") or ""),
                row_ids=data.get("row_ids") if isinstance(data.get("row_ids"), list) else None,
                exclude_row_ids=data.get("exclude_row_ids") if isinstance(data.get("exclude_row_ids"), list) else None,
            ),
            action="payswap.bbps.bulk.proceed",
            external=True,
        )


@payswap_only
class BulkBbpsCancelView(APIView):
    def post(self, request, batch_id: str):
        from domain.payswap.bulk_bbps import cancel_batch

        bind_action(app_context=request.user.app_context, actor=request.user.user_id, role=request.user.role)
        return Response(cancel_batch(batch_id, user_id=request.user.user_id), status=200)


@payswap_only
class BulkBbpsExportView(APIView):
    def get(self, request, batch_id: str):
        from domain.payswap.bulk_bbps import export_batch_csv

        bind_action(app_context=request.user.app_context, actor=request.user.user_id, role=request.user.role)
        return export_batch_csv(batch_id, user_id=request.user.user_id)
