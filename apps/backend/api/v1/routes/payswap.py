"""POST /api/v1/payswap/vouchers/order

Caller: apps/payswap/features/vouchers through packages/sdk-client
(X-App-Context: payswap, role retailer from packages/contracts).
payswap_only rejects a parkpe context with 403 before the domain runs.
Auth cookie is checked by api/v1/deps.py against GET /api/auth/me.
Body: schemas.VoucherOrderSerializer.
Service: domain/payswap/vouchers.py. Retry: core/idempotency.py.
"""

from api.v1.deps import payswap_only
from api.v1.routes.support import post_mutation
from domain.payswap.vouchers import order_voucher
from rest_framework.views import APIView
from schemas.serializers import VoucherOrderSerializer


@payswap_only
class VoucherOrderView(APIView):
    def post(self, request):
        return post_mutation(
            request,
            VoucherOrderSerializer,
            lambda data, user_id: order_voucher(
                user_id=user_id,
                brand=data["brand"],
                amount=data["amount"],
            ),
        )
