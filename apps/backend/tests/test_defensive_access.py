"""Pytest coverage for authz, context, validation, and contract error shapes.

Does not call Mobikwik, Cashfree, PayU, or Kaleyra. Does not change HubPath
or ErrorCode spellings in packages/contracts.
"""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest
from django.test import override_settings


@pytest.mark.django_db
class TestUnauthorizedAccess:
    def test_wallet_without_cookie_is_401(self, api_client, mock_sessions):
        res = api_client.get("/api/v1/payswap/wallet", HTTP_X_APP_CONTEXT="payswap")
        assert res.status_code == 401
        body = res.json()
        assert body["code"] == "unauthenticated"
        assert set(body.keys()) == {"error", "code"}
        assert "Traceback" not in res.content.decode()

    def test_desk_without_admin_is_401(self, api_client, mock_sessions):
        res = api_client.get("/api/v1/desk/overview")
        assert res.status_code == 401
        assert res.json()["code"] == "unauthenticated"

    def test_retailer_cannot_use_parkpe_context(self, as_retailer):
        res = as_retailer.get("/api/v1/parkpe/vehicles", HTTP_X_APP_CONTEXT="parkpe")
        assert res.status_code == 403
        assert res.json()["code"] == "forbidden_app"

    def test_customer_cannot_read_payswap_wallet(self, as_customer):
        res = as_customer.get("/api/v1/payswap/wallet", HTTP_X_APP_CONTEXT="payswap")
        assert res.status_code == 403
        assert res.json()["code"] == "forbidden_app"

    def test_retailer_cannot_open_desk(self, as_retailer):
        res = as_retailer.get("/api/v1/desk/overview", HTTP_X_APP_CONTEXT="payswap")
        assert res.status_code == 403
        assert res.json()["code"] == "forbidden_app"

    def test_cross_app_context_on_payswap_is_forbidden(self, as_retailer):
        res = as_retailer.get("/api/v1/payswap/wallet", HTTP_X_APP_CONTEXT="parkpe")
        assert res.status_code == 403
        assert res.json()["code"] == "forbidden_app"

    def test_foreign_pg_order_verify_is_404(self, as_retailer):
        from models.models import PgOrder

        PgOrder.objects.create(
            pg_order_id="pgw-def-other",
            user_id="other@payswap.test",
            purpose="wallet_topup",
            amount_paise=10000,
            status="created",
            provider="cashfree",
        )
        res = as_retailer.post(
            "/api/v1/payswap/pg/verify",
            {"pg_order_id": "pgw-def-other"},
            format="json",
            HTTP_X_APP_CONTEXT="payswap",
            HTTP_IDEMPOTENCY_KEY="def-pg-other",
        )
        assert res.status_code == 404
        assert PgOrder.objects.get(pg_order_id="pgw-def-other").status == "created"


@pytest.mark.django_db
class TestInvalidInput:
    def test_missing_app_context_is_validation(self, as_retailer):
        res = as_retailer.get("/api/v1/payswap/wallet")
        assert res.status_code == 400
        assert res.json()["code"] == "validation"

    def test_unknown_app_context_is_validation(self, as_retailer):
        res = as_retailer.get("/api/v1/payswap/wallet", HTTP_X_APP_CONTEXT="admin")
        assert res.status_code == 400
        assert res.json()["code"] == "validation"

    def test_bbps_pay_without_body_is_validation(self, as_retailer):
        with patch("api.v1.routes.payswap.require_retailer_service"):
            res = as_retailer.post(
                "/api/v1/payswap/bbps/pay",
                {},
                format="json",
                HTTP_X_APP_CONTEXT="payswap",
                HTTP_IDEMPOTENCY_KEY="def-bbps-empty",
            )
        assert res.status_code == 400
        body = res.json()
        assert body["code"] == "validation"
        assert "error" in body

    def test_session_initiate_without_idempotency_key_is_validation(self, as_customer):
        res = as_customer.post(
            "/api/v1/parkpe/sessions/initiate",
            {"site_code": "HUB1", "bay": "A1"},
            format="json",
            HTTP_X_APP_CONTEXT="parkpe",
        )
        assert res.status_code == 400
        assert res.json()["code"] == "validation"

    def test_vehicle_add_rejects_empty_registration(self, as_customer):
        res = as_customer.post(
            "/api/v1/parkpe/vehicles",
            {"registration": ""},
            format="json",
            HTTP_X_APP_CONTEXT="parkpe",
            HTTP_IDEMPOTENCY_KEY="def-veh-empty",
        )
        assert res.status_code == 400
        assert res.json()["code"] == "validation"


@pytest.mark.django_db
class TestContractResponses:
    def test_health_ok_shape(self, api_client):
        res = api_client.get("/api/v1/health/")
        assert res.status_code == 200
        assert res.json() == {"ok": True}

    def test_wallet_success_shape_with_mocked_session(self, as_retailer):
        with patch("api.v1.routes.payswap.require_retailer_service"):
            res = as_retailer.get("/api/v1/payswap/wallet", HTTP_X_APP_CONTEXT="payswap")
        assert res.status_code == 200
        body = res.json()
        assert "wallet" in body
        assert body["wallet"]["user_id"] == "shop@payswap.test"

    def test_uncaught_api_failure_has_no_traceback(self, as_retailer):
        with patch(
            "api.v1.routes.payswap.require_retailer_service",
            side_effect=RuntimeError("secret boom token=abc"),
        ):
            res = as_retailer.get("/api/v1/payswap/wallet", HTTP_X_APP_CONTEXT="payswap")
        assert res.status_code == 500
        body = res.json()
        assert body["code"] == "server_error"
        assert "Traceback" not in res.content.decode()
        assert "token=abc" not in res.content.decode()
        assert "secret boom" not in res.content.decode()

    def test_bbps_operators_mocked_vendor(self, as_retailer):
        fake = {
            "configured": True,
            "categories": [{"id": "Electricity", "name": "Electricity"}],
            "operators": [{"op": "65", "name": "Test", "category": "Electricity"}],
        }
        with (
            patch("api.v1.routes.payswap.require_retailer_service"),
            patch("api.v1.routes.payswap.catalogue", return_value=fake) as catalogue,
        ):
            res = as_retailer.get(
                "/api/v1/payswap/bbps/operators",
                HTTP_X_APP_CONTEXT="payswap",
            )
        assert res.status_code == 200
        assert catalogue.called
        assert res.json()["configured"] is True
        assert res.json()["operators"][0]["op"] == "65"


class TestConfigHygiene:
    def test_bbps_enabled_without_base_url_is_not_configured(self, monkeypatch):
        from integrations import bbps as bbps_mod

        monkeypatch.setenv("MOBIKWIK_BBPS_ENABLED", "1")
        monkeypatch.delenv("MOBIKWIK_BBPS_BASE_URL", raising=False)
        monkeypatch.setenv("MOBIKWIK_BBPS_CLIENT_ID", "cid")
        monkeypatch.setenv("MOBIKWIK_BBPS_CLIENT_SECRET", "csec")
        assert bbps_mod.configured() is False

    def test_bbps_https_base_with_creds_is_configured(self, monkeypatch):
        from integrations import bbps as bbps_mod

        monkeypatch.setenv("MOBIKWIK_BBPS_ENABLED", "1")
        monkeypatch.setenv("MOBIKWIK_BBPS_BASE_URL", "https://example.test/bbps")
        monkeypatch.setenv("MOBIKWIK_BBPS_CLIENT_ID", "cid")
        monkeypatch.setenv("MOBIKWIK_BBPS_CLIENT_SECRET", "csec")
        monkeypatch.setenv("MOBIKWIK_BBPS_USE_ENCRYPTION", "0")
        monkeypatch.setenv("MOBIKWIK_BBPS_PLAIN_JSON_UAT", "1")
        monkeypatch.setenv("MOBIKWIK_BBPS_ENVIRONMENT", "UAT")
        assert bbps_mod.configured() is True

    def test_allowed_hosts_env_is_honoured(self):
        with override_settings(ALLOWED_HOSTS=["api.example.test"]):
            from django.conf import settings

            assert "api.example.test" in settings.ALLOWED_HOSTS

    def test_env_example_has_no_absolute_home_paths(self):
        root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        text = open(os.path.join(root, ".env.example"), encoding="utf-8").read()
        assert "/Users/" not in text
        assert "DJANGO_SECRET_KEY" in text
        assert "AUTH_ORIGINS" in text
        assert "MOBIKWIK_BBPS_BASE_URL=" in text
