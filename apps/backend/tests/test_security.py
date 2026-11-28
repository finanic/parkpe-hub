"""Defensive checks for auth, ownership, cookies, webhooks, and abuse limits.

These tests call the local Django process and the auth cookie builder.
They do not call Mobikwik, Cashfree, or PayU.
"""

from __future__ import annotations

import io
import tempfile
import threading
from pathlib import Path
from unittest.mock import patch

from django.db import connections
from django.test import TestCase, TransactionTestCase
from rest_framework.test import APIClient

from core.security import SessionRejected


def session_for(token: str) -> dict:
    known = {
        "customer-token": {"email": "driver@parkpe.test", "role": "customer"},
        "other-customer": {"email": "other@parkpe.test", "role": "customer"},
        "retailer-token": {"email": "shop@payswap.test", "role": "retailer"},
        "other-retailer": {"email": "other@payswap.test", "role": "retailer"},
        "admin-token": {"email": "ops@hub.test", "role": "admin"},
    }
    if token not in known:
        raise SessionRejected(401, "Sign in again.")
    return known[token]


class SecurityControlTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.deps = patch("api.v1.deps.fetch_session", side_effect=session_for)
        self.desk = patch("api.v1.routes.desk.fetch_session", side_effect=session_for)
        self.deps.start()
        self.desk.start()
        self.addCleanup(self.deps.stop)
        self.addCleanup(self.desk.stop)

    def _as(self, token: str) -> None:
        self.client.cookies["auth_access"] = token

    def test_missing_and_unknown_session_are_unauthorized(self):
        missing = self.client.get("/api/v1/payswap/wallet", HTTP_X_APP_CONTEXT="payswap")
        self.assertEqual(missing.status_code, 401)
        self.assertEqual(missing.json()["code"], "unauthenticated")

        self._as("not-a-real-session")
        bad = self.client.get("/api/v1/payswap/wallet", HTTP_X_APP_CONTEXT="payswap")
        self.assertEqual(bad.status_code, 401)
        self.assertNotIn("Traceback", bad.content.decode())

        self.client.cookies["auth_access"] = ""
        desk = self.client.get("/api/v1/desk/overview")
        self.assertEqual(desk.status_code, 401)

    def test_retailer_cannot_read_another_wallet_order_or_vehicle(self):
        from domain.payswap.wallet import admin_adjust_wallet
        from models.models import BbpsTransaction, PgOrder

        admin_adjust_wallet(
            "other@payswap.test",
            direction="CR",
            amount_paise=50000,
            reason="Other shop float",
            admin_email="ops@hub.test",
            idempotency_key="sec-other-float",
        )
        BbpsTransaction.objects.create(
            reference="T19SECOTHER1",
            user_id="other@payswap.test",
            operator_id="65",
            biller_name="Other bill",
            account_mask="****4756",
            amount_paise=1000,
            state="success",
        )
        PgOrder.objects.create(
            pg_order_id="pgw-other-1",
            user_id="other@payswap.test",
            purpose="wallet_topup",
            amount_paise=10000,
            status="created",
            provider="cashfree",
        )

        self._as("retailer-token")
        wallet = self.client.get(
            "/api/v1/payswap/wallet?user_id=other@payswap.test",
            HTTP_X_APP_CONTEXT="payswap",
        )
        self.assertEqual(wallet.status_code, 200, wallet.content)
        self.assertEqual(wallet.json()["wallet"]["user_id"], "shop@payswap.test")
        self.assertEqual(wallet.json()["wallet"]["available_paise"], 0)

        with patch("domain.payswap.bbps.pipe_payment_status") as vendor:
            status = self.client.get(
                "/api/v1/payswap/bbps/status?reference=T19SECOTHER1",
                HTTP_X_APP_CONTEXT="payswap",
            )
        self.assertEqual(status.status_code, 404)
        self.assertEqual(vendor.call_count, 0)

        verify = self.client.post(
            "/api/v1/payswap/pg/verify",
            {"pg_order_id": "pgw-other-1"},
            format="json",
            HTTP_X_APP_CONTEXT="payswap",
            HTTP_IDEMPOTENCY_KEY="sec-pg-other",
        )
        self.assertEqual(verify.status_code, 404)
        self.assertEqual(PgOrder.objects.get(pg_order_id="pgw-other-1").status, "created")

        self._as("customer-token")
        added = self.client.post(
            "/api/v1/parkpe/vehicles",
            {"registration": "DL01AB1234"},
            format="json",
            HTTP_X_APP_CONTEXT="parkpe",
        )
        self.assertEqual(added.status_code, 201, added.content)
        vehicle_id = added.json()["vehicle_id"]
        self._as("other-customer")
        stolen = self.client.delete(
            f"/api/v1/parkpe/vehicles?vehicle_id={vehicle_id}",
            HTTP_X_APP_CONTEXT="parkpe",
        )
        self.assertEqual(stolen.status_code, 400)
        self.assertEqual(stolen.json()["code"], "validation")
        self._as("customer-token")
        listed = self.client.get("/api/v1/parkpe/vehicles", HTTP_X_APP_CONTEXT="parkpe")
        self.assertEqual(len(listed.json()["vehicles"]), 1)

    def test_retailer_and_customer_cannot_open_admin_routes(self):
        self._as("retailer-token")
        retailer = self.client.get("/api/v1/desk/overview", HTTP_X_APP_CONTEXT="payswap")
        self.assertEqual(retailer.status_code, 403)
        self.assertEqual(retailer.json()["code"], "forbidden_app")

        adjust = self.client.post(
            "/api/v1/desk/wallets/adjust",
            {
                "user_id": "shop@payswap.test",
                "direction": "CR",
                "amount": "100.00",
                "reason": "self credit",
                "role": "admin",
                "is_superadmin": True,
            },
            format="json",
            HTTP_IDEMPOTENCY_KEY="sec-self-credit",
        )
        self.assertEqual(adjust.status_code, 403)

        self._as("customer-token")
        customer = self.client.get("/api/v1/desk/overview")
        self.assertEqual(customer.status_code, 403)

    def test_malicious_input_and_bad_uploads_do_not_execute(self):
        from domain.payswap.bbps import BbpsServiceError
        from domain.payswap.bulk_bbps import _read_tabular

        self._as("retailer-token")
        for amount in ("0", "-10.00", "9999999.00"):
            res = self.client.post(
                "/api/v1/payswap/bbps/pay",
                {"biller": "65", "account": "1029384756", "amount": amount},
                format="json",
                HTTP_X_APP_CONTEXT="payswap",
                HTTP_IDEMPOTENCY_KEY=f"sec-amt-{amount}",
            )
            body = res.content.decode()
            self.assertEqual(res.status_code, 400, body)
            self.assertNotIn("Traceback", body)
            self.assertNotIn("sqlite", body.lower())

        injected = self.client.post(
            "/api/v1/payswap/bbps/pay",
            {
                "biller": "65' OR '1'='1",
                "account": "1029384756",
                "amount": "10.00",
                "remitter_name": "<script>alert(1)</script>",
            },
            format="json",
            HTTP_X_APP_CONTEXT="payswap",
            HTTP_IDEMPOTENCY_KEY="sec-inject-1",
        )
        text = injected.content.decode()
        self.assertGreaterEqual(injected.status_code, 400)
        self.assertLess(injected.status_code, 500)
        self.assertNotIn("Traceback", text)
        self.assertNotIn("<script>", injected.get("Content-Type", ""))

        upload = io.BytesIO(b"MZ")
        upload.name = "payload.exe"
        with self.assertRaises(BbpsServiceError):
            _read_tabular(upload)
        macro = io.BytesIO(b"PK")
        macro.name = "book.xlsm"
        with self.assertRaises(BbpsServiceError):
            _read_tabular(macro)

    def test_foreign_origin_is_refused_and_cookies_are_http_only(self):
        from auth.server import AuthApp

        self._as("customer-token")
        blocked = self.client.post(
            "/api/v1/parkpe/sessions/initiate",
            {"site_code": "HUB1", "bay": "A1"},
            format="json",
            HTTP_X_APP_CONTEXT="parkpe",
            HTTP_IDEMPOTENCY_KEY="sec-origin",
            HTTP_ORIGIN="https://evil.example",
        )
        self.assertEqual(blocked.status_code, 403)
        self.assertNotIn("Access-Control-Allow-Origin", blocked)

        with tempfile.TemporaryDirectory() as tmp:
            app = AuthApp(Path(tmp), {"http://127.0.0.1:4500"}, 2**15, False, "Lax")
            try:
                local = app._cookie("auth_access", "session-value", 60, "/")
            finally:
                app.close()
        self.assertIn("HttpOnly", local)
        self.assertIn("SameSite=Lax", local)
        self.assertNotIn("Secure", local)

        with tempfile.TemporaryDirectory() as tmp:
            app = AuthApp(Path(tmp), {"https://payswap.example"}, 2**15, True, "Lax")
            try:
                hosted = app._cookie("auth_access", "session-value", 60, "/")
            finally:
                app.close()
        self.assertIn("HttpOnly", hosted)
        self.assertIn("Secure", hosted)

    def test_repeated_vendor_reads_are_limited(self):
        from core.actions import bind_action
        from domain.payswap.bbps import BbpsServiceError, _reserve_vendor_read

        bind_action(app_context="payswap", actor="shop@payswap.test", role="retailer")
        with self.captureOnCommitCallbacks(execute=True):
            _reserve_vendor_read("shop@payswap.test", "plans", "65", "9876543210", "Rajasthan")
        with self.assertRaises(BbpsServiceError) as caught:
            _reserve_vendor_read("shop@payswap.test", "plans", "65", "9876543210", "Rajasthan")
        self.assertEqual(caught.exception.status_code, 429)

    def test_unsigned_webhook_and_bad_payu_hash_do_not_settle(self):
        from domain.payswap.payu_checkout import handle_payu_callback
        from models.models import PgOrder

        cashfree = PgOrder.objects.create(
            pg_order_id="pgw-hook-1",
            user_id="shop@payswap.test",
            purpose="wallet_topup",
            amount_paise=10000,
            status="created",
            provider="cashfree",
        )
        forged = self.client.post(
            "/api/v1/payswap/pg/webhook",
            {
                "data": {
                    "order": {"order_id": "pgw-hook-1", "order_amount": "100.00"},
                    "payment": {"payment_status": "SUCCESS", "payment_amount": "100.00", "cf_payment_id": "fake"},
                }
            },
            format="json",
            HTTP_X_WEBHOOK_SIGNATURE="not-a-signature",
            HTTP_X_WEBHOOK_TIMESTAMP="1700000000",
        )
        self.assertEqual(forged.status_code, 401)
        cashfree.refresh_from_db()
        self.assertEqual(cashfree.status, "created")

        payu = PgOrder.objects.create(
            pg_order_id="pgw-payu-1",
            user_id="shop@payswap.test",
            purpose="wallet_topup",
            amount_paise=10000,
            status="created",
            provider="payu",
            provider_order_id="txn-sec-1",
        )
        with patch("domain.payswap.payu_checkout.verify_payment", return_value={"ok": False}):
            out = handle_payu_callback(
                {
                    "txnid": "txn-sec-1",
                    "status": "success",
                    "amount": "100.00",
                    "udf1": "pgw-payu-1",
                    "hash": "deadbeef",
                }
            )
        self.assertNotEqual(out["status"], "paid")
        payu.refresh_from_db()
        self.assertEqual(payu.status, "created")
        self.assertFalse(payu.signature_verified)

    def test_uncaught_error_hides_the_exception_and_logs_drop_secrets(self):
        from core.actions import redact

        self._as("retailer-token")
        self.client.raise_request_exception = False
        with patch(
            "api.v1.routes.payswap.wallet_overview",
            side_effect=RuntimeError("Traceback password=super-secret token=session-value"),
        ):
            res = self.client.get("/api/v1/payswap/wallet", HTTP_X_APP_CONTEXT="payswap")
        body = res.content.decode()
        self.assertEqual(res.status_code, 500)
        self.assertEqual(res.json()["code"], "server_error")
        self.assertNotIn("Traceback", body)
        self.assertNotIn("super-secret", body)
        self.assertNotIn("session-value", body)

        cleaned = redact("bearer abc.def token=session-value password=super-secret")
        self.assertNotIn("session-value", cleaned)
        self.assertNotIn("super-secret", cleaned)
        self.assertIn("[redacted]", cleaned)

    def test_oversized_json_is_a_validation_error_and_payu_form_still_parses(self):
        self._as("retailer-token")
        self.client.raise_request_exception = False
        wide = "A" * (70 * 1024)
        oversized = self.client.post(
            "/api/v1/payswap/bbps/pay",
            {"biller": "65", "account": "1029384756", "amount": "10.00", "note": wide},
            format="json",
            HTTP_X_APP_CONTEXT="payswap",
            HTTP_IDEMPOTENCY_KEY="sec-too-large",
        )
        self.assertEqual(oversized.status_code, 400)
        self.assertEqual(oversized.json()["code"], "validation")
        self.assertNotIn("Traceback", oversized.content.decode())

        fields = {f"field{i}": "x" for i in range(40)}
        fields.update({"txnid": "missing", "status": "success", "amount": "10.00", "hash": "deadbeef"})
        callback = self.client.post("/api/payu/success", fields)
        self.assertNotEqual(callback.status_code, 500)
        self.assertIn(callback.status_code, (302, 400))

    def test_stale_webhook_timestamp_is_rejected(self):
        import base64
        import hashlib
        import hmac
        import time

        from integrations.pg import verify_webhook_signature
        from models.models import PgOrder

        order = PgOrder.objects.create(
            pg_order_id="pgw-stale-hook",
            user_id="shop@payswap.test",
            purpose="wallet_topup",
            amount_paise=10000,
            status="created",
            provider="cashfree",
        )
        body = b'{"data":{"order":{"order_id":"pgw-stale-hook"}}}'
        secret = "test-webhook-secret"
        with patch.dict("os.environ", {"CASHFREE_WEBHOOK_MAX_SKEW_S": "120"}), patch(
            "integrations.pg._load_env",
            return_value={"CASHFREE_PG_SECRET": secret},
        ):
            stale = str(int(time.time()) - 600)
            self.assertFalse(verify_webhook_signature(body, stale, "unused"))
            fresh = str(int(time.time()))
            # Wrong signature still fails even when the timestamp is fresh.
            self.assertFalse(verify_webhook_signature(body, fresh, "not-the-hmac"))
            # Fresh timestamp + valid HMAC passes and leaves amount checks to the view.
            digest = hmac.new(
                secret.encode("utf-8"),
                (fresh + body.decode("utf-8")).encode("utf-8"),
                hashlib.sha256,
            ).digest()
            good_sig = base64.b64encode(digest).decode("ascii")
            self.assertTrue(verify_webhook_signature(body, fresh, good_sig))

        res = self.client.post(
            "/api/v1/payswap/pg/webhook",
            {
                "data": {
                    "order": {"order_id": "pgw-stale-hook", "order_amount": "100.00"},
                    "payment": {"payment_status": "SUCCESS", "payment_amount": "100.00", "cf_payment_id": "p1"},
                }
            },
            format="json",
            HTTP_X_WEBHOOK_SIGNATURE="x",
            HTTP_X_WEBHOOK_TIMESTAMP=str(int(time.time()) - 10_000),
        )
        self.assertEqual(res.status_code, 401)
        order.refresh_from_db()
        self.assertEqual(order.status, "created")

    def test_signed_webhook_with_wrong_amount_does_not_credit(self):
        from domain.payswap.wallet import wallet_overview
        from models.models import PgOrder

        order = PgOrder.objects.create(
            pg_order_id="pgw-amt-hook",
            user_id="shop@payswap.test",
            purpose="wallet_topup",
            amount_paise=10000,
            status="created",
            provider="cashfree",
        )
        before = wallet_overview("shop@payswap.test")["wallet"]["available_paise"]
        with patch("api.v1.routes.payswap.verify_webhook_signature", return_value=True):
            res = self.client.post(
                "/api/v1/payswap/pg/webhook",
                {
                    "data": {
                        "order": {"order_id": "pgw-amt-hook", "order_amount": "1.00"},
                        "payment": {
                            "payment_status": "SUCCESS",
                            "payment_amount": "1.00",
                            "cf_payment_id": "pay-wrong",
                        },
                    }
                },
                format="json",
                HTTP_X_WEBHOOK_SIGNATURE="ok",
                HTTP_X_WEBHOOK_TIMESTAMP="1700000000",
            )
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json().get("ignored"))
        order.refresh_from_db()
        self.assertEqual(order.status, "created")
        self.assertEqual(wallet_overview("shop@payswap.test")["wallet"]["available_paise"], before)

    def test_pg_topup_refuses_credit_without_signature_flag(self):
        from domain.payswap.wallet import WalletError, apply_pg_topup_paid
        from models.models import PgOrder

        order = PgOrder.objects.create(
            pg_order_id="pgw-nosig-1",
            user_id="shop@payswap.test",
            purpose="wallet_topup",
            amount_paise=5000,
            status="created",
            provider="cashfree",
        )
        with self.assertRaises(WalletError):
            apply_pg_topup_paid(order.pg_order_id, paid_amount="50.00")
        order.refresh_from_db()
        self.assertEqual(order.status, "created")
        self.assertFalse(order.signature_verified)

    def test_auth_base_url_must_be_http_or_https(self):
        from core.security import fetch_session

        with self.assertRaises(SessionRejected):
            fetch_session("any-token", base_url="file:///tmp")
        with self.assertRaises(SessionRejected):
            fetch_session("any-token", base_url="ftp://127.0.0.1:4600")


class IdempotencyRaceTests(TransactionTestCase):
    def test_eight_parallel_calls_with_one_key_run_once(self):
        from core.idempotency import payload_hash, run_once

        calls = {"n": 0}
        lock = threading.Lock()

        def produce():
            with lock:
                calls["n"] += 1
            return 201, {"ok": True, "reference": "once"}

        body_hash = payload_hash({"site_code": "HUB1"})
        errors: list[BaseException] = []

        def worker():
            try:
                run_once(
                    app_context="parkpe",
                    user_id="driver@parkpe.test",
                    endpoint="/api/v1/parkpe/sessions/initiate",
                    key="sec-race-1",
                    body_hash=body_hash,
                    produce=produce,
                )
            except BaseException as exc:
                errors.append(exc)
            finally:
                connections.close_all()

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)
        self.assertFalse(any(thread.is_alive() for thread in threads))
        self.assertEqual(errors, [])
        self.assertEqual(calls["n"], 1)
