"""/api/v1 routes.

health/ is open. The two money routes require deps.py.
ParkPe and PaySwap handlers stay in separate modules.
The routes that answer on port 4600 are still apps/backend/auth/contract.py Paths.
"""

from django.urls import path

from api.v1.routes.health import HealthView
from api.v1.routes.parkpe import SessionInitiateView
from api.v1.routes.payswap import VoucherOrderView

urlpatterns = [
    path("health/", HealthView.as_view(), name="v1-health"),
    path("parkpe/sessions/initiate", SessionInitiateView.as_view(), name="v1-parkpe-session-initiate"),
    path("payswap/vouchers/order", VoucherOrderView.as_view(), name="v1-payswap-voucher-order"),
]
