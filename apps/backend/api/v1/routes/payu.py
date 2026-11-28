"""PayU Hosted Checkout HTTP surface.

Mounted at /api/payu/ (config/urls.py):
  POST /initiate  — { order_id } → { action, params }
  POST /success   — PayU surl (form-urlencoded)
  POST /failure   — PayU furl (form-urlencoded)
  GET  /verify/<order_id>
"""

from __future__ import annotations

import time

from django.http import HttpResponseRedirect
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from api.v1.deps import payswap_only
from core.actions import bind_action, elapsed_ms, log_action
from domain.payswap.payu_checkout import (
    frontend_result_url,
    handle_payu_callback,
    initiate_payu_checkout,
    verify_payu_order,
)
from domain.payswap.wallet import WalletError


def _form_dict(request) -> dict:
    data = {}
    if hasattr(request, "POST") and request.POST:
        for key in request.POST:
            data[key] = request.POST.get(key)
    elif isinstance(getattr(request, "data", None), dict):
        data = dict(request.data)
    return data


@payswap_only
@method_decorator(csrf_exempt, name="dispatch")
class PayUInitiateView(APIView):
    def post(self, request):
        started = time.perf_counter()
        bind_action(
            app_context=getattr(request.user, "app_context", "payswap"),
            actor=getattr(request.user, "user_id", ""),
            role=getattr(request.user, "role", "retailer"),
        )
        body = request.data if isinstance(request.data, dict) else {}
        order_id = str(body.get("order_id") or "").strip()
        try:
            out = initiate_payu_checkout(order_id, user_id=request.user.user_id)
        except WalletError as err:
            request._hub_logged = True
            log_action(
                action="payswap.payu.initiate",
                outcome="error",
                status=err.status,
                duration_ms=elapsed_ms(started),
                target_id=order_id,
                error_code=err.code,
                error_reason=str(err),
                request=f"order_id={order_id}",
                response=f"HTTP {err.status}",
            )
            return Response({"error": str(err), "code": err.code}, status=err.status)
        request._hub_logged = True
        return Response(out, status=200)


@method_decorator(csrf_exempt, name="dispatch")
class PayUSuccessView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        return HttpResponseRedirect(frontend_result_url(None, ok=False))

    def post(self, request):
        out = handle_payu_callback(_form_dict(request))
        return HttpResponseRedirect(out["redirect"])


@method_decorator(csrf_exempt, name="dispatch")
class PayUFailureView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        return HttpResponseRedirect(frontend_result_url(None, ok=False))

    def post(self, request):
        out = handle_payu_callback(_form_dict(request))
        return HttpResponseRedirect(out["redirect"])


@payswap_only
@method_decorator(csrf_exempt, name="dispatch")
class PayUVerifyView(APIView):
    def get(self, request, order_id: str = ""):
        started = time.perf_counter()
        bind_action(
            app_context=getattr(request.user, "app_context", "payswap"),
            actor=getattr(request.user, "user_id", ""),
            role=getattr(request.user, "role", "retailer"),
        )
        try:
            out = verify_payu_order(order_id, user_id=request.user.user_id)
        except WalletError as err:
            request._hub_logged = True
            log_action(
                action="payswap.payu.verify",
                outcome="error",
                status=err.status,
                duration_ms=elapsed_ms(started),
                target_id=order_id,
                error_code=err.code,
                error_reason=str(err),
                request=f"order_id={order_id}",
                response=f"HTTP {err.status}",
            )
            return Response({"error": str(err), "code": err.code}, status=err.status)
        request._hub_logged = True
        log_action(
            action="payswap.payu.verify",
            outcome="ok",
            status=200,
            duration_ms=elapsed_ms(started),
            target_id=order_id,
            request=f"order_id={order_id}",
            response=f"HTTP 200\nstatus={out.get('status')}",
        )
        return Response(out, status=200)
