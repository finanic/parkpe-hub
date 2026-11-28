"""Site URLs. Product routes live under /api/v1/ (api/v1/urls.py).

Auth routes (/api/auth/login, /api/auth/me, and the rest of Paths) stay on
apps/backend/auth/server.py. This file does not include them.
"""

from django.urls import include, path

from api.v1.routes.payu import (
    PayUFailureView,
    PayUInitiateView,
    PayUSuccessView,
    PayUVerifyView,
)

urlpatterns = [
    path("api/v1/", include("api.v1.urls")),
    # PayU Hosted Checkout callbacks + initiate (skill paths under /api/payu/).
    path("api/payu/initiate", PayUInitiateView.as_view(), name="payu-initiate"),
    path("api/payu/success", PayUSuccessView.as_view(), name="payu-success"),
    path("api/payu/failure", PayUFailureView.as_view(), name="payu-failure"),
    path("api/payu/verify/<str:order_id>", PayUVerifyView.as_view(), name="payu-verify"),
]
