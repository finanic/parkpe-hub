"""/api/v1 checks. The auth server is not started.

fetch_session is patched here. test_fetch_session_reads_auth_me talks to a
local stand-in of GET /api/auth/me (apps/backend/auth/contract.py Paths.ME).
apps/backend/tests/test_auth.py still covers apps/backend/auth/server.py.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase, TransactionTestCase
from rest_framework.test import APIClient

from core.security import fetch_session


def _log_record(line: str) -> dict:
    return json.loads(line.split(":", 2)[-1])
from domain.parkpe import sessions as parkpe_sessions
from domain.payswap import vouchers as payswap_vouchers


def session_for(token: str) -> dict:
    known = {
        "customer-token": {"email": "driver@parkpe.test", "role": "customer"},
        "retailer-token": {"email": "shop@payswap.test", "role": "retailer"},
        "admin-token": {"email": "ops@hub.test", "role": "admin"},
    }
    if token not in known:
        from core.security import SessionRejected

        raise SessionRejected(401, "Sign in again.")
    return known[token]


class HealthTests(TestCase):
    def test_health_is_open(self):
        response = APIClient().get("/api/v1/health/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"ok": True})


class ScopedRouteTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.patcher = patch("api.v1.deps.fetch_session", side_effect=session_for)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def test_missing_context_is_validation(self):
        self.client.cookies["auth_access"] = "customer-token"
        response = self._session(None, "key-missing-context")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "validation")

    def test_invalid_context_is_validation(self):
        self.client.cookies["auth_access"] = "customer-token"
        response = self._session("operator", "key-bad-context")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "validation")

    def test_payswap_context_cannot_open_a_parkpe_session(self):
        self.client.cookies["auth_access"] = "retailer-token"
        response = self._session("payswap", "key-cross")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "forbidden_app")

    def test_parkpe_context_cannot_order_a_payswap_voucher(self):
        self.client.cookies["auth_access"] = "customer-token"
        response = self._voucher("parkpe", "key-cross", "Amazon", "100.00")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "forbidden_app")

    def test_same_key_and_body_does_not_run_the_domain_twice(self):
        self.client.cookies["auth_access"] = "customer-token"
        with patch("api.v1.routes.parkpe.initiate_session", wraps=parkpe_sessions.initiate_session) as start:
            first = self._session("parkpe", "key-session")
            second = self._session("parkpe", "key-session")
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)
        self.assertEqual(first.json(), second.json())
        self.assertEqual(first.json()["state"], "initiated")
        self.assertEqual(start.call_count, 1)

    def test_same_key_and_different_body_conflicts(self):
        self.client.cookies["auth_access"] = "customer-token"
        self._session("parkpe", "key-once", bay="A1")
        response = self._session("parkpe", "key-once", bay="B2")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "idempotency_conflict")

    def test_voucher_replay_does_not_order_twice(self):
        from domain.payswap.entitlements import update_retailer_entitlements

        self.client.cookies["auth_access"] = "retailer-token"
        blocked = self._voucher("payswap", "key-voucher-blocked", "Amazon", "100.00")
        self.assertEqual(blocked.status_code, 403)
        self.assertEqual(blocked.json()["code"], "service_disabled")

        update_retailer_entitlements("shop@payswap.test", service_overrides={"vouchers": True}, admin_email="ops@hub.test")
        with patch("api.v1.routes.payswap.order_voucher", wraps=payswap_vouchers.order_voucher) as order:
            first = self._voucher("payswap", "key-voucher", "Amazon", "100.00")
            second = self._voucher("payswap", "key-voucher", "Amazon", "100.00")
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.json(), first.json())
        self.assertEqual(order.call_count, 1)

    def test_foreign_owner_is_rejected(self):
        self.client.cookies["auth_access"] = "customer-token"
        response = self.client.post(
            "/api/v1/parkpe/sessions/initiate",
            {"site_code": "HUB1", "bay": "A1", "vehicle": "DL01AB1234", "user_id": "other@parkpe.test"},
            format="json",
            HTTP_X_APP_CONTEXT="parkpe",
            HTTP_IDEMPOTENCY_KEY="key-owner",
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "forbidden_app")

    def test_foreign_origin_is_blocked(self):
        response = self.client.options("/api/v1/health/", HTTP_ORIGIN="https://evil.example")
        self.assertEqual(response.status_code, 403)
        self.assertNotIn("Access-Control-Allow-Origin", response)

    def test_parkpe_origin_is_reflected(self):
        response = self.client.options("/api/v1/health/", HTTP_ORIGIN="http://127.0.0.1:4310")
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response["Access-Control-Allow-Origin"], "http://127.0.0.1:4310")

    def test_foreign_origin_post_does_not_mutate(self):
        # config/cors.py rejects this before api/v1/deps.py and the domain.
        self.client.cookies["auth_access"] = "customer-token"
        with patch("api.v1.routes.parkpe.initiate_session", wraps=parkpe_sessions.initiate_session) as start:
            response = self.client.post(
                "/api/v1/parkpe/sessions/initiate",
                {"site_code": "HUB1", "bay": "A1", "vehicle": "DL01AB1234"},
                format="json",
                HTTP_X_APP_CONTEXT="parkpe",
                HTTP_IDEMPOTENCY_KEY="key-csrf",
                HTTP_ORIGIN="http://127.0.0.1:9999",
            )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "forbidden_app")
        self.assertEqual(start.call_count, 0)

    def test_allowlisted_origin_can_initiate(self):
        self.client.cookies["auth_access"] = "customer-token"
        response = self.client.post(
            "/api/v1/parkpe/sessions/initiate",
            {"site_code": "HUB1", "bay": "A1", "vehicle": "DL01AB1234"},
            format="json",
            HTTP_X_APP_CONTEXT="parkpe",
            HTTP_IDEMPOTENCY_KEY="key-origin-ok",
            HTTP_ORIGIN="http://127.0.0.1:4310",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response["Access-Control-Allow-Origin"], "http://127.0.0.1:4310")

    def test_session_log_keeps_context_and_drops_the_cookie(self):
        self.client.cookies["auth_access"] = "customer-token"
        with self.assertLogs("hub.actions", level="INFO") as captured:
            response = self._session("parkpe", "key-log")
        self.assertEqual(response.status_code, 201)
        lines = [_log_record(item) for item in captured.output]
        http = next(line for line in lines if line["action"] == "parkpe.session.initiate")
        self.assertEqual(http["app_context"], "parkpe")
        self.assertEqual(http["actor"], "driver@parkpe.test")
        self.assertEqual(http["role"], "customer")
        self.assertEqual(http["idempotency_key"], "key-log")
        self.assertEqual(http["outcome"], "ok")
        self.assertEqual(http["status"], 201)
        self.assertTrue(http["request_id"])
        self.assertTrue(http["target_id"].startswith("sess-"))
        self.assertGreaterEqual(http["duration_ms"], 0)
        self.assertTrue(any(line["action"] == "domain.parkpe.session.initiate" for line in lines))
        blob = "\n".join(captured.output)
        self.assertNotIn("customer-token", blob)
        self.assertNotIn("auth_access", blob)
        self.assertNotIn("DL01AB1234", blob)

    def test_caller_request_id_is_kept_on_the_action_line(self):
        self.client.cookies["auth_access"] = "customer-token"
        with self.assertLogs("hub.actions", level="INFO") as captured:
            response = self.client.post(
                "/api/v1/parkpe/sessions/initiate",
                {"site_code": "HUB1", "bay": "A1", "vehicle": "DL01AB1234"},
                format="json",
                HTTP_X_APP_CONTEXT="parkpe",
                HTTP_IDEMPOTENCY_KEY="key-request-id",
                HTTP_X_REQUEST_ID="req-client-1",
            )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response["X-Request-Id"], "req-client-1")
        lines = [_log_record(item) for item in captured.output]
        http = next(line for line in lines if line["action"] == "parkpe.session.initiate")
        self.assertEqual(http["request_id"], "req-client-1")
        self.assertNotIn("customer-token", "\n".join(captured.output))

    def test_redact_drops_secrets_from_the_action_line(self):
        from core.actions import bind_action, log_action, redact, reset_action

        cleaned = redact(
            {
                "password": "hunter2",
                "cookie": "auth_access=sekret",
                "otp": "123456",
                "token": "raw-token",
                "secret": "top",
                "body": {"vehicle": "DL01AB1234"},
                "site_code": "HUB1",
            }
        )
        self.assertEqual(cleaned, {"site_code": "HUB1"})
        reset_action()
        bind_action(
            request_id="req-log-1",
            app_context="parkpe",
            actor="driver@parkpe.test",
            role="customer",
            idempotency_key="key-safe",
        )
        try:
            with self.assertLogs("hub.actions", level="INFO") as captured:
                log_action(
                    action="parkpe.session.initiate",
                    outcome="error",
                    status=400,
                    duration_ms=3,
                    target_id="sess-1",
                    error_code="validation",
                    error_reason="auth_access=sekret Bearer abc.def password=hunter2 otp=123456 token=raw-token secret=top",
                )
        finally:
            reset_action()
        text = "\n".join(captured.output)
        for secret in ("sekret", "hunter2", "123456", "raw-token", "abc.def"):
            self.assertNotIn(secret, text)
        self.assertIn("[redacted]", text)
        self.assertIn("key-safe", text)
        self.assertIn("req-log-1", text)
        self.assertIn("validation", text)

    def _session(self, context, key, bay="A1"):
        headers = {"HTTP_IDEMPOTENCY_KEY": key}
        if context is not None:
            headers["HTTP_X_APP_CONTEXT"] = context
        return self.client.post(
            "/api/v1/parkpe/sessions/initiate",
            {"site_code": "HUB1", "bay": bay, "vehicle": "DL01AB1234"},
            format="json",
            **headers,
        )

    def _voucher(self, context, key, brand, amount):
        return self.client.post(
            "/api/v1/payswap/vouchers/order",
            {"brand": brand, "amount": amount},
            format="json",
            HTTP_X_APP_CONTEXT=context,
            HTTP_IDEMPOTENCY_KEY=key,
        )


class AuthMeClientTests(SimpleTestCase):
    def test_fetch_session_reads_auth_me(self):
        seen = {}

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                seen["path"] = self.path
                seen["header"] = self.headers.get("X-Auth-Request")
                seen["cookie"] = self.headers.get("Cookie")
                body = json.dumps({"email": "driver@parkpe.test", "role": "customer"}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, fmt, *args):
                return

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.shutdown)
        base = f"http://127.0.0.1:{server.server_address[1]}"
        session = fetch_session("abc", base_url=base)
        self.assertEqual(session["role"], "customer")
        self.assertEqual(seen["path"], "/api/auth/me")
        self.assertEqual(seen["header"], "1")
        self.assertEqual(seen["cookie"], "auth_access=abc")


class OverlappingIdempotencyTests(TransactionTestCase):
    """Two in-flight posts share one Idempotency-Key.

    The second connection has to read the row core/idempotency.py commits
    inside transaction.atomic (select_for_update). SQLite needs a busy
    timeout so that wait becomes a retry instead of an immediate lock error.
    """

    def setUp(self):
        self.patcher = patch("api.v1.deps.fetch_session", side_effect=session_for)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def test_overlapping_duplicate_runs_domain_once(self):
        from django.db import connection
        from django.db import connections

        import core.idempotency as idempotency

        with connection.cursor() as cursor:
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=5000")
        connection.close()

        in_produce = threading.Event()
        release = threading.Event()
        overlap = threading.Event()
        domain_calls = []
        producer = []
        real_locked = idempotency._locked

        def counting_locked(*args, **kwargs):
            if in_produce.is_set() and producer and threading.get_ident() != producer[0]:
                overlap.set()
            return real_locked(*args, **kwargs)

        def slow(**kwargs):
            producer.append(threading.get_ident())
            domain_calls.append(1)
            in_produce.set()
            if not release.wait(5):
                raise TimeoutError("overlap release timed out")
            return parkpe_sessions.initiate_session(**kwargs)

        def worker(box):
            connections.close_all()
            local = connections["default"]
            with local.cursor() as cursor:
                cursor.execute("PRAGMA busy_timeout=5000")
            client = APIClient()
            client.cookies["auth_access"] = "customer-token"
            try:
                box.append(
                    client.post(
                        "/api/v1/parkpe/sessions/initiate",
                        {"site_code": "HUB1", "bay": "A1", "vehicle": "DL01AB1234"},
                        format="json",
                        HTTP_X_APP_CONTEXT="parkpe",
                        HTTP_IDEMPOTENCY_KEY="key-overlap",
                    )
                )
            finally:
                connections.close_all()

        boxes = [[], []]
        threads = []
        try:
            with patch("core.idempotency._locked", side_effect=counting_locked), patch(
                "api.v1.routes.parkpe.initiate_session",
                side_effect=slow,
            ):
                threads = [threading.Thread(target=worker, args=(box,)) for box in boxes]
                for thread in threads:
                    thread.start()
                self.assertTrue(in_produce.wait(5))
                self.assertTrue(overlap.wait(5))
                release.set()
                for thread in threads:
                    thread.join(5)
                    self.assertFalse(thread.is_alive())
        finally:
            release.set()
            for thread in threads:
                thread.join(5)

        self.assertEqual(len(domain_calls), 1)
        self.assertEqual([len(box) for box in boxes], [1, 1])
        self.assertEqual(boxes[0][0].status_code, 201)
        self.assertEqual(boxes[1][0].status_code, 201)
        self.assertEqual(boxes[0][0].json(), boxes[1][0].json())


class DeskRouteTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.patcher = patch("api.v1.routes.desk.fetch_session", side_effect=session_for)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def test_browser_origin_cannot_open_the_desk(self):
        self.client.cookies["auth_access"] = "admin-token"
        response = self.client.get(
            "/api/v1/desk/parkpe/sessions",
            HTTP_ORIGIN="http://127.0.0.1:4310",
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "forbidden_app")
        self.assertNotIn("Access-Control-Allow-Origin", response)

    def test_a_customer_cannot_read_desk_rows(self):
        self.client.cookies["auth_access"] = "customer-token"
        response = self.client.get("/api/v1/desk/parkpe/sessions")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "forbidden_app")

    def test_admin_lists_a_session_and_marks_it_closed(self):
        from models.models import IdempotencyRecord

        IdempotencyRecord.objects.create(
            app_context="parkpe",
            user_id="driver@parkpe.test",
            endpoint="/api/v1/parkpe/sessions/initiate",
            idempotency_key="key-desk-1",
            payload_hash="a" * 64,
            state="done",
            status_code=200,
            body={
                "reference": "sess-desk0001",
                "site_code": "site-1",
                "bay": "A1",
                "vehicle": "DL01AB1234",
                "state": "initiated",
            },
        )
        self.client.cookies["auth_access"] = "admin-token"
        listed = self.client.get("/api/v1/desk/parkpe/sessions")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.json()["sessions"][0]["reference"], "sess-desk0001")
        self.assertEqual(listed.json()["sessions"][0]["vehicle"], "DL01AB1234")
        closed = self.client.post(
            "/api/v1/desk/parkpe/sessions/close",
            {"reference": "sess-desk0001"},
            format="json",
        )
        self.assertEqual(closed.status_code, 200)
        self.assertEqual(closed.json()["state"], "closed")
        stored = IdempotencyRecord.objects.get(idempotency_key="key-desk-1")
        self.assertEqual(stored.body["state"], "initiated")
        self.assertEqual(stored.desk_state, "closed")
        again = self.client.post(
            "/api/v1/desk/parkpe/sessions/close",
            {"reference": "sess-desk0001"},
            format="json",
        )
        self.assertEqual(again.status_code, 200)
        self.assertEqual(again.json()["state"], "closed")
        missing = self.client.post("/api/v1/desk/parkpe/sessions/close", {"reference": "nope"}, format="json")
        self.assertEqual(missing.status_code, 400)
        unknown = self.client.post(
            "/api/v1/desk/parkpe/sessions/close",
            {"reference": "sess-missing"},
            format="json",
        )
        self.assertEqual(unknown.status_code, 404)

    def test_admin_can_limit_sessions_to_one_email(self):
        from models.models import IdempotencyRecord

        IdempotencyRecord.objects.create(
            app_context="parkpe",
            user_id="driver@parkpe.test",
            endpoint="/api/v1/parkpe/sessions/initiate",
            idempotency_key="key-desk-keep",
            payload_hash="c" * 64,
            state="done",
            status_code=200,
            body={"reference": "sess-keep0001", "site_code": "site-1", "bay": "A1", "vehicle": "DL01AB1234", "state": "initiated"},
        )
        IdempotencyRecord.objects.create(
            app_context="parkpe",
            user_id="other@parkpe.test",
            endpoint="/api/v1/parkpe/sessions/initiate",
            idempotency_key="key-desk-other",
            payload_hash="d" * 64,
            state="done",
            status_code=200,
            body={"reference": "sess-other001", "site_code": "site-2", "bay": "B2", "vehicle": "MH01AB1234", "state": "initiated"},
        )
        self.client.cookies["auth_access"] = "admin-token"
        listed = self.client.get("/api/v1/desk/parkpe/sessions?email=driver@parkpe.test")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual([row["reference"] for row in listed.json()["sessions"]], ["sess-keep0001"])

    def test_admin_reads_orders_without_the_reason(self):
        from models.models import IdempotencyRecord

        IdempotencyRecord.objects.create(
            app_context="payswap",
            user_id="shop@payswap.test",
            endpoint="/api/v1/payswap/vouchers/order",
            idempotency_key="key-desk-2",
            payload_hash="b" * 64,
            state="done",
            status_code=200,
            body={"reference": "vch-desk0001", "brand": "Amazon", "amount": "100.00", "state": "ordered"},
        )
        self.client.cookies["auth_access"] = "admin-token"
        orders = self.client.get("/api/v1/desk/payswap/orders")
        self.assertEqual(orders.status_code, 200)
        self.assertEqual(orders.json()["orders"][0]["reference"], "vch-desk0001")


class BbpsRouteTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.patcher = patch("api.v1.deps.fetch_session", side_effect=session_for)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def test_parkpe_context_cannot_access_bbps_routes(self):
        self.client.cookies["auth_access"] = "customer-token"
        headers = {"HTTP_X_APP_CONTEXT": "parkpe"}
        self.assertEqual(self.client.get("/api/v1/payswap/bbps/operators", **headers).status_code, 403)
        self.assertEqual(
            self.client.post(
                "/api/v1/payswap/bbps/fetch-bill",
                {"biller": "65", "account": "1029384756"},
                format="json",
                HTTP_IDEMPOTENCY_KEY="bbps-cross-1",
                **headers,
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(
                "/api/v1/payswap/bbps/pay",
                {"biller": "65", "account": "1029384756", "amount": "250.00"},
                format="json",
                HTTP_IDEMPOTENCY_KEY="bbps-cross-2",
                **headers,
            ).status_code,
            403,
        )
        self.assertEqual(self.client.get("/api/v1/payswap/bbps/status?reference=T1234", **headers).status_code, 403)

    def test_operators_catalogue_returns_categories_and_filtered_billers(self):
        self.client.cookies["auth_access"] = "retailer-token"
        cats = self.client.get("/api/v1/payswap/bbps/operators", HTTP_X_APP_CONTEXT="payswap")
        self.assertEqual(cats.status_code, 200)
        body = cats.json()
        self.assertTrue(len(body["categories"]) > 0)
        self.assertEqual(body["operators"], [])
        cat_ids = {c["id"] for c in body["categories"]}
        self.assertIn("LPG_BOOKING", cat_ids)

        elec = self.client.get("/api/v1/payswap/bbps/operators?category=ELECTRICITY&limit=5", HTTP_X_APP_CONTEXT="payswap")
        self.assertEqual(elec.status_code, 200)
        ops = elec.json()["operators"]
        self.assertTrue(0 < len(ops) <= 5)
        self.assertTrue(all(op["category"] == "ELECTRICITY" for op in ops))

        lpg = self.client.get("/api/v1/payswap/bbps/operators?category=LPG_BOOKING&limit=10", HTTP_X_APP_CONTEXT="payswap")
        self.assertEqual(lpg.status_code, 200)
        lpg_ops = lpg.json()["operators"]
        self.assertEqual(len(lpg_ops), 3)
        self.assertTrue(all(op["category"] == "LPG_BOOKING" for op in lpg_ops))
        names = " ".join(op["name"].lower() for op in lpg_ops)
        self.assertIn("indane", names)
        self.assertIn("bharat gas", names)
        self.assertIn("hp gas", names)

        indane = self.client.get("/api/v1/payswap/bbps/operators?q=inden&limit=10", HTTP_X_APP_CONTEXT="payswap")
        self.assertEqual(indane.status_code, 200)
        self.assertTrue(any("indane" in op["name"].lower() for op in indane.json()["operators"]))

    def test_prepaid_circles_and_plans_route(self):
        from integrations.bbps import parse_recharge_plans

        plans = parse_recharge_plans(
            {
                "success": True,
                "data": {
                    "plans": {
                        "TOPUP": [{"rs": "10", "desc": "Talktime", "validity": "N/A"}],
                        "3G/4G": [{"amount": 299, "description": "1.5GB/day", "validity": "28 days", "planId": "p299"}],
                    }
                },
            }
        )
        self.assertEqual(len(plans), 2)
        self.assertEqual(plans[0]["amount"], "10.00")
        self.assertEqual(plans[1]["id"], "p299")

        self.client.cookies["auth_access"] = "retailer-token"
        circles = self.client.get("/api/v1/payswap/bbps/circles", HTTP_X_APP_CONTEXT="payswap")
        self.assertEqual(circles.status_code, 200)
        self.assertTrue(len(circles.json()["circles"]) >= 20)

        missing = self.client.get("/api/v1/payswap/bbps/plans", HTTP_X_APP_CONTEXT="payswap")
        self.assertEqual(missing.status_code, 400)

        prepaid = self.client.get(
            "/api/v1/payswap/bbps/operators?category=PREPAID&limit=5",
            HTTP_X_APP_CONTEXT="payswap",
        )
        self.assertEqual(prepaid.status_code, 200)
        ops = prepaid.json()["operators"]
        self.assertTrue(len(ops) >= 1)
        biller = ops[0]["biller_id"] or ops[0]["op"]

        with patch("domain.payswap.bbps.list_recharge_plans") as mocked:
            mocked.return_value = {
                "ok": True,
                "status": 200,
                "error": "",
                "plans": [
                    {
                        "id": "u199",
                        "amount": "199.00",
                        "validity": "18 days",
                        "description": "Unlimited",
                        "category": "Unlimited",
                        "label": "₹199.00 · 18 days · Unlimited",
                    }
                ],
            }
            loaded = self.client.get(
                f"/api/v1/payswap/bbps/plans?biller={biller}&account=9876543210&circle=19",
                HTTP_X_APP_CONTEXT="payswap",
            )
        self.assertEqual(loaded.status_code, 200)
        body = loaded.json()
        self.assertEqual(body["circle"], "19")
        self.assertTrue(len(body["plans"]) >= 1)
        self.assertEqual(body["plans"][0]["amount"], "199.00")

    def test_fetch_bill_and_pay_idempotency_and_status(self):
        from models.models import HubAction

        self.client.cookies["auth_access"] = "retailer-token"
        fake_bill = {
            "ok": True,
            "status": 200,
            "error": "",
            "bill": {
                "amount": "1840.00",
                "customer_name": "A. Sharma",
                "bill_number": "INV-99",
                "bill_date": "2026-11-01",
                "due_date": "2026-11-28",
            },
        }
        with self.captureOnCommitCallbacks(execute=True):
            with patch("domain.payswap.bbps.fetch_bill", return_value=fake_bill) as mocked_fetch:
                fetched = self.client.post(
                    "/api/v1/payswap/bbps/fetch-bill",
                    {"biller": "65", "account": "1029384756"},
                    format="json",
                    HTTP_X_APP_CONTEXT="payswap",
                    HTTP_IDEMPOTENCY_KEY="bbps-fetch-1",
                )
        self.assertEqual(fetched.status_code, 200, fetched.json())
        self.assertEqual(fetched.json()["bill"]["amount"], "1840.00")
        self.assertEqual(mocked_fetch.call_count, 1)

        from domain.payswap.wallet import admin_adjust_wallet, wallet_overview

        admin_adjust_wallet("shop@payswap.test", direction="CR", amount_paise=500000, reason="Test float", admin_email="ops@hub.test")
        fake_pay = {
            "ok": True,
            "status": 200,
            "error": "",
            "reference": "T19AB000001",
            "transaction_id": "MKW998877",
            "vendor_status": "SUCCESS",
            "phase": "success",
        }
        with self.captureOnCommitCallbacks(execute=True):
            with patch("domain.payswap.bbps.pay_bill", return_value=fake_pay) as mocked_pay:
                first = self.client.post(
                    "/api/v1/payswap/bbps/pay",
                    {"biller": "65", "account": "1029384756", "amount": "1840.00"},
                    format="json",
                    HTTP_X_APP_CONTEXT="payswap",
                    HTTP_IDEMPOTENCY_KEY="bbps-pay-1",
                )
                replay = self.client.post(
                    "/api/v1/payswap/bbps/pay",
                    {"biller": "65", "account": "1029384756", "amount": "1840.00"},
                    format="json",
                    HTTP_X_APP_CONTEXT="payswap",
                    HTTP_IDEMPOTENCY_KEY="bbps-pay-1",
                )
                conflict = self.client.post(
                    "/api/v1/payswap/bbps/pay",
                    {"biller": "65", "account": "1029384756", "amount": "1900.00"},
                    format="json",
                    HTTP_X_APP_CONTEXT="payswap",
                    HTTP_IDEMPOTENCY_KEY="bbps-pay-1",
                )
        self.assertEqual(first.status_code, 201, first.json())
        self.assertEqual(replay.status_code, 201)
        self.assertEqual(first.json(), replay.json())
        ref = first.json()["reference"]
        self.assertTrue(ref.startswith("T"))
        self.assertEqual(mocked_pay.call_count, 1)
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(conflict.json()["code"], "idempotency_conflict")
        snap = wallet_overview("shop@payswap.test")["wallet"]
        self.assertEqual(snap["available"], "3160.00")
        self.assertEqual(snap["held"], "0.00")

        with self.captureOnCommitCallbacks(execute=True):
            with patch(
                "domain.payswap.bbps.payment_status",
                return_value={
                    "ok": True,
                    "status": 200,
                    "error": "",
                    "reference": ref,
                    "vendor_status": "SUCCESS",
                    "phase": "success",
                },
            ):
                status_res = self.client.get(
                    f"/api/v1/payswap/bbps/status?reference={ref}",
                    HTTP_X_APP_CONTEXT="payswap",
                )
        self.assertEqual(status_res.status_code, 200)
        self.assertEqual(status_res.json()["state"], "success")
        actions = set(HubAction.objects.values_list("action", flat=True))
        self.assertIn("payswap.bbps.fetch_bill", actions)
        self.assertIn("payswap.bbps.pay", actions)
        self.assertIn("payswap.bbps.status", actions)

    def test_failed_pay_returns_error_and_does_not_cache_idempotency(self):
        from domain.payswap.wallet import admin_adjust_wallet, wallet_overview

        admin_adjust_wallet("shop@payswap.test", direction="CR", amount_paise=200000, reason="Test float", admin_email="ops@hub.test")
        self.client.cookies["auth_access"] = "retailer-token"
        failed = {
            "ok": False,
            "status": 502,
            "error": "Insufficient float balance.",
            "reference": "T19AB000002",
            "transaction_id": "",
            "vendor_status": "FAILED",
            "phase": "failed",
        }
        with patch("domain.payswap.bbps.pay_bill", return_value=failed):
            res = self.client.post(
                "/api/v1/payswap/bbps/pay",
                {"biller": "65", "account": "1029384756", "amount": "500.00"},
                format="json",
                HTTP_X_APP_CONTEXT="payswap",
                HTTP_IDEMPOTENCY_KEY="bbps-pay-fail-1",
            )
        self.assertEqual(res.status_code, 502)
        self.assertEqual(res.json()["code"], "server_error")
        # Hold was released cleanly on failure
        self.assertEqual(wallet_overview("shop@payswap.test")["wallet"]["available"], "2000.00")
        self.assertEqual(wallet_overview("shop@payswap.test")["wallet"]["held"], "0.00")

        succeeded = {
            "ok": True,
            "status": 200,
            "error": "",
            "reference": "T19AB000003",
            "transaction_id": "MKW112233",
            "vendor_status": "SUCCESS",
            "phase": "success",
        }
        with patch("domain.payswap.bbps.pay_bill", return_value=succeeded):
            retry = self.client.post(
                "/api/v1/payswap/bbps/pay",
                {"biller": "65", "account": "1029384756", "amount": "500.00"},
                format="json",
                HTTP_X_APP_CONTEXT="payswap",
                HTTP_IDEMPOTENCY_KEY="bbps-pay-fail-1",
            )
        self.assertEqual(retry.status_code, 201)
        self.assertTrue(retry.json()["reference"].startswith("T"))
        self.assertEqual(wallet_overview("shop@payswap.test")["wallet"]["available"], "1500.00")

    def test_mobikwik_envelope_encryption_round_trip(self):
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import padding as asym_padding, rsa
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        from integrations.bbps import _encrypt_payload
        import base64

        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        pem = private_key.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode("utf-8")
        envelope = _encrypt_payload({"cn": "1029384756", "op": "65"}, {"pem": pem, "key_version": "1.0"})
        aes_key = private_key.decrypt(base64.b64decode(envelope["encryptedSessionKey"]), asym_padding.PKCS1v15())
        plaintext = AESGCM(aes_key).decrypt(
            base64.b64decode(envelope["iv"]),
            base64.b64decode(envelope["encryptedPayload"]),
            None,
        )
        self.assertEqual(json.loads(plaintext.decode("utf-8")), {"cn": "1029384756", "op": "65"})

    def test_fastag_biller_id_maps_to_numeric_op_and_bankname_and_timeout_is_pending(self):
        from integrations.bbps import fetch_bill, find_operator, pay_bill

        icici = find_operator("TOLL00000NAT72")
        self.assertIsNotNone(icici)
        self.assertEqual(icici["op"], "294")
        self.assertEqual(icici["default_payment_mode"], "UPI")

        captured = []

        def fake_post(url, body, headers, timeout):
            captured.append((url, body))
            return 200, json.dumps({"success": True, "billDetails": {"billAmount": "500.00"}}).encode("utf-8")

        with patch("integrations.bbps._config", return_value={
            "base": "https://rapi-b2b.mobikwik.com",
            "client_id": "",
            "client_secret": "",
            "merchant_id": "M1",
            "member_id": "",
            "agent_id": "MK01MK94AGTU00000001",
            "api_key": "K1",
            "secret_key": "S1",
            "use_encryption": False,
            "token_encrypted": False,
            "pem": "",
            "key_version": "1.0",
            "timeout": 10.0,
            "environment": "PRODUCTION",
        }):
            fetched = fetch_bill(operator_id="TOLL00000NAT72", customer_id="24BH8017B", transport=fake_post)
            self.assertTrue(fetched["ok"], fetched)
            self.assertEqual(captured[-1][1]["op"], "294")
            self.assertIn("bankName", captured[-1][1]["adParams"])

            def raise_timeout(url, body, headers, timeout):
                captured.append((url, body))
                raise TimeoutError("timed out")

            timed_out = pay_bill(
                operator_id="TOLL00000NAT72",
                customer_id="24BH8017B",
                amount="500.00",
                op_row=icici,
                transport=raise_timeout,
            )
            self.assertTrue(timed_out["ok"])
            self.assertEqual(timed_out["phase"], "pending")
            self.assertEqual(timed_out["vendor_status"], "PENDING")
            self.assertEqual(captured[-1][1]["op"], "294")
            self.assertEqual(captured[-1][1]["paymentMode"], "UPI")
            self.assertEqual(captured[-1][1]["paymentAccountInfo"], "24BH8017B@UPI")
            self.assertIn("ad1", captured[-1][1])

            from integrations.bbps import payment_status

            def fake_nested_status(url, body, headers, timeout):
                captured.append((url, body))
                return 200, json.dumps({
                    "success": True,
                    "data": {"txStatus": "RECHARGESUCCESS", "mobikwikrefno": "MKW555"},
                }).encode("utf-8")

            checked = payment_status(reference="T1A21264B6569A2F4E6F120D", transport=fake_nested_status)
            self.assertTrue(checked["ok"])
            self.assertEqual(checked["vendor_status"], "RECHARGESUCCESS")
            self.assertEqual(checked["phase"], "success")
            self.assertEqual(captured[-1][1], {"txId": "T1A21264B6569A2F4E6F120D"})

    def test_token_reuses_until_23h_renews_on_error_and_enforces_daily_cap(self):
        import os
        import tempfile
        from integrations import bbps as bbps_mod

        with tempfile.TemporaryDirectory() as tmp:
            old_dir = os.environ.get("AUTH_DATA_DIR")
            os.environ["AUTH_DATA_DIR"] = tmp
            bbps_mod._MEM_TOKEN.clear()
            try:
                now = 1_800_000_000.0
                calls = []

                def fake_post(url, body, headers, timeout):
                    calls.append((url, headers.get("Authorization", "")))
                    if url.endswith("/verify/retailer"):
                        return 200, json.dumps({
                            "success": True,
                            "data": {"token": f"tok-{len(calls)}", "expiryTime": now + 86400.0},
                        }).encode("utf-8")
                    if headers.get("Authorization") == "tok-1" and len(calls) == 4:
                        return 200, json.dumps({
                            "success": False,
                            "message": {"code": "401", "text": "Token is expired"},
                        }).encode("utf-8")
                    return 200, json.dumps({"success": True, "data": {"balance": 100.0}}).encode("utf-8")

                cfg = {
                    "base": "https://rapi-b2b.mobikwik.com",
                    "client_id": "C1",
                    "client_secret": "S1",
                    "merchant_id": "",
                    "member_id": "",
                    "agent_id": "MK01MK94AGTU00000001",
                    "api_key": "",
                    "secret_key": "",
                    "use_encryption": False,
                    "token_encrypted": False,
                    "pem": "",
                    "key_version": "1.0",
                    "timeout": 10.0,
                    "environment": "PRODUCTION",
                }
                with patch("integrations.bbps._config", return_value=cfg), patch(
                    "integrations.bbps._today_ist", return_value="2026-11-25"
                ):
                    with patch("integrations.bbps.time.time", return_value=now):
                        self.assertTrue(bbps_mod.balance_check(transport=fake_post)["ok"])
                    with patch("integrations.bbps.time.time", return_value=now + 22 * 3600):
                        self.assertTrue(bbps_mod.balance_check(transport=fake_post)["ok"])
                    token_calls = [c for c in calls if c[0].endswith("/verify/retailer")]
                    self.assertEqual(len(token_calls), 1)

                    # Force token-expired response on call #4 -> re-mints once and retries
                    with patch("integrations.bbps.time.time", return_value=now + 22.5 * 3600):
                        self.assertTrue(bbps_mod.balance_check(transport=fake_post)["ok"])
                    token_calls = [c for c in calls if c[0].endswith("/verify/retailer")]
                    self.assertEqual(len(token_calls), 2)

                    # At 23 hours past second mint -> auto-renews once more
                    with patch("integrations.bbps.time.time", return_value=now + 45.5 * 3600 + 10):
                        self.assertTrue(bbps_mod.balance_check(transport=fake_post)["ok"])
                    token_calls = [c for c in calls if c[0].endswith("/verify/retailer")]
                    self.assertEqual(len(token_calls), 3)

                    # Daily cap enforced on same day
                    with patch.dict(os.environ, {"MOBIKWIK_BBPS_TOKEN_MAX_MINTS_PER_DAY": "3"}):
                        bbps_mod._MEM_TOKEN.clear()
                        with patch("integrations.bbps.time.time", return_value=now + 70 * 3600):
                            blocked = bbps_mod.balance_check(transport=fake_post)
                        self.assertFalse(blocked["ok"])
                        self.assertIn("Daily Mobikwik token limit", blocked["error"])
            finally:
                bbps_mod._MEM_TOKEN.clear()
                if old_dir is None:
                    os.environ.pop("AUTH_DATA_DIR", None)
                else:
                    os.environ["AUTH_DATA_DIR"] = old_dir

    def test_bbps_logs_capture_redacted_request_and_response(self):
        from integrations import bbps as bbps_mod
        from models.models import HubAction

        cfg = {
            "base": "https://rapi-b2b.mobikwik.com",
            "client_id": "C1",
            "client_secret": "super-secret-client",
            "merchant_id": "",
            "member_id": "",
            "agent_id": "MK01MK94AGTU00000001",
            "api_key": "",
            "secret_key": "",
            "use_encryption": False,
            "token_encrypted": False,
            "pem": "",
            "key_version": "1.0",
            "timeout": 10.0,
            "environment": "PRODUCTION",
        }

        def fake_post(url, body, headers, timeout):
            return 200, json.dumps({
                "success": True,
                "token": "super-secret-jwt",
                "billDetails": {
                    "billAmount": "1450.00",
                    "customerName": "Asha",
                    "billdate": "2026-11-01",
                    "dueDate": "2026-11-30",
                    "billNumber": "BILL9088",
                },
            }).encode("utf-8")

        op_row = {
            "biller_id": "FASTAG01",
            "op": "294",
            "name": "FASTag Test",
            "category": "FASTag",
            "supports_fetch": True,
            "ad_params": [{"key": "bankName", "fetch_key": "bankName", "pay_key": "ad1", "default_value": "14"}],
            "payment_modes": ["UPI"],
        }

        self.client.cookies["auth_access"] = "retailer-token"
        with self.captureOnCommitCallbacks(execute=True):
            with patch.object(bbps_mod, "_config", return_value=cfg), patch.object(
                bbps_mod, "_ensure_token", return_value=("tok-live", "")
            ), patch.object(bbps_mod, "_http_post", side_effect=fake_post), patch(
                "domain.payswap.bbps.find_operator", return_value=op_row
            ), patch.object(bbps_mod, "find_operator", return_value=op_row):
                res = self.client.post(
                    "/api/v1/payswap/bbps/fetch-bill",
                    {"biller": "294", "account": "24BH8017B", "circle": "14"},
                    format="json",
                    HTTP_X_APP_CONTEXT="payswap",
                )
        self.assertEqual(res.status_code, 200)
        route_row = HubAction.objects.filter(action="payswap.bbps.fetch_bill").latest("id")
        domain_row = HubAction.objects.filter(action="domain.payswap.bbps.fetch_bill").latest("id")
        integ_row = HubAction.objects.filter(action="integration.bbps.view_bill").latest("id")

        self.assertIn("POST /api/v1/payswap/bbps/fetch-bill", route_row.request)
        self.assertIn("24BH8017B", route_row.request)
        self.assertIn("1450.00", route_row.response)
        self.assertIn("2026-11-30", route_row.response)

        self.assertIn('"op": "294"', domain_row.request)
        self.assertIn("BILL9088", domain_row.response)

        self.assertIn("POST https://rapi-b2b.mobikwik.com/recharge/v3/retailerViewbill", integ_row.request)
        self.assertIn('"bankName": "14"', integ_row.request)
        self.assertIn("1450.00", integ_row.response)
        self.assertNotIn("super-secret-jwt", integ_row.response)
        self.assertNotIn("tok-live", integ_row.request)


    def test_forbidden_app_logs_request_and_response(self):
        from models.models import HubAction

        self.client.cookies["auth_access"] = "admin-token"
        with self.captureOnCommitCallbacks(execute=True):
            res = self.client.post(
                "/api/v1/payswap/bbps/pay",
                {"biller": "294", "account": "24BH8017B", "amount": "100.00"},
                format="json",
                HTTP_X_APP_CONTEXT="payswap",
                HTTP_IDEMPOTENCY_KEY="forbidden-pay-1",
            )
        self.assertEqual(res.status_code, 403)
        row = HubAction.objects.filter(action="payswap.bbps.pay", outcome="error").latest("id")
        self.assertEqual(row.status, 403)
        self.assertEqual(row.actor, "ops@hub.test")
        self.assertEqual(row.role, "admin")
        self.assertIn("POST /api/v1/payswap/bbps/pay", row.request)
        self.assertIn("This account cannot use that app.", row.response)
        self.assertNotIn("admin-token", row.request)


class EntitlementsWalletPgParkpeTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.auth_patch = patch("api.v1.deps.fetch_session", side_effect=session_for)
        self.auth_patch.start()

    def tearDown(self):
        self.auth_patch.stop()

    def test_entitlements_default_and_retailer_overrides(self):
        from domain.payswap.entitlements import update_default_policy, update_retailer_entitlements

        self.client.cookies["auth_access"] = "retailer-token"
        ent = self.client.get("/api/v1/payswap/entitlements", HTTP_X_APP_CONTEXT="payswap")
        self.assertEqual(ent.status_code, 200)
        self.assertIn("bbps", ent.json()["enabled_services"])
        self.assertNotIn("vouchers", ent.json()["enabled_services"])
        self.assertIn("bbps_categories", ent.json())

        # Admin disables BBPS globally -> retailer gets 403 service_disabled
        update_default_policy(enabled_services=["wallet", "transactions", "profile", "support"], admin_email="ops@hub.test")
        blocked = self.client.post(
            "/api/v1/payswap/bbps/pay",
            {"biller": "65", "account": "1029384756", "amount": "100.00"},
            format="json",
            HTTP_X_APP_CONTEXT="payswap",
            HTTP_IDEMPOTENCY_KEY="ent-block-1",
        )
        self.assertEqual(blocked.status_code, 403)
        self.assertEqual(blocked.json()["code"], "service_disabled")

        # Admin grants BBPS specifically to this retailer + blocks PG pay
        update_retailer_entitlements(
            "shop@payswap.test",
            service_overrides={"bbps": True},
            allow_pg_pay=False,
            admin_email="ops@hub.test",
        )
        pg_blocked = self.client.post(
            "/api/v1/payswap/bbps/pay",
            {"biller": "65", "account": "1029384756", "amount": "100.00", "payment_rail": "pg"},
            format="json",
            HTTP_X_APP_CONTEXT="payswap",
            HTTP_IDEMPOTENCY_KEY="ent-pg-block-1",
        )
        self.assertEqual(pg_blocked.status_code, 403)
        self.assertEqual(pg_blocked.json()["code"], "payment_mode_disabled")

        # Default BBPS category allow-list filters the retailer catalogue.
        update_default_policy(
            enabled_services=["bbps", "wallet", "transactions", "profile", "support"],
            enabled_bbps_categories=["ELECTRICITY"],
            admin_email="ops@hub.test",
        )
        cats = self.client.get("/api/v1/payswap/bbps/operators", HTTP_X_APP_CONTEXT="payswap")
        self.assertEqual(cats.status_code, 200)
        self.assertEqual({c["id"] for c in cats.json()["categories"]}, {"ELECTRICITY"})

        # Fetch/pay must enforce the same allow-list (not only the catalogue).
        from integrations.bbps import list_operators

        water_ops = list_operators(category="WATER", limit=1)
        if water_ops:
            blocked_fetch = self.client.post(
                "/api/v1/payswap/bbps/fetch-bill",
                {"biller": water_ops[0]["op"], "account": "1029384756"},
                format="json",
                HTTP_X_APP_CONTEXT="payswap",
            )
            self.assertEqual(blocked_fetch.status_code, 403)
            self.assertEqual(blocked_fetch.json()["code"], "bbps_category_disabled")

        update_retailer_entitlements(
            "shop@payswap.test",
            bbps_category_overrides={"WATER": True},
            admin_email="ops@hub.test",
        )
        widened = self.client.get("/api/v1/payswap/bbps/operators", HTTP_X_APP_CONTEXT="payswap")
        self.assertEqual(widened.status_code, 200)
        wide_ids = {c["id"] for c in widened.json()["categories"]}
        self.assertIn("ELECTRICITY", wide_ids)
        self.assertIn("WATER", wide_ids)

    def test_wallet_topup_pin_lockout_freeze_and_limits(self):
        from domain.payswap.wallet import admin_update_wallet_controls, review_topup_request

        self.client.cookies["auth_access"] = "retailer-token"

        # Set wallet PIN
        pin_res = self.client.post(
            "/api/v1/payswap/wallet/pin",
            {"new_pin": "4829"},
            format="json",
            HTTP_X_APP_CONTEXT="payswap",
            HTTP_IDEMPOTENCY_KEY="pin-set-1",
        )
        self.assertEqual(pin_res.status_code, 200, pin_res.json())

        # Submit UTR top-up
        top1 = self.client.post(
            "/api/v1/payswap/wallet/topup-request",
            {"amount": "3000.00", "utr": "UTR9988776655", "mode": "BANK_TRANSFER"},
            format="json",
            HTTP_X_APP_CONTEXT="payswap",
            HTTP_IDEMPOTENCY_KEY="topup-1",
        )
        self.assertEqual(top1.status_code, 201, top1.json())
        topup_id = top1.json()["request_id"]

        # Duplicate UTR is rejected with 409
        top_dup = self.client.post(
            "/api/v1/payswap/wallet/topup-request",
            {"amount": "3000.00", "utr": "UTR9988776655", "mode": "BANK_TRANSFER"},
            format="json",
            HTTP_X_APP_CONTEXT="payswap",
            HTTP_IDEMPOTENCY_KEY="topup-2",
        )
        self.assertEqual(top_dup.status_code, 409)

        # Admin approves UTR top-up
        review_topup_request(topup_id, decision="approve", note="Verified", admin_email="ops@hub.test")
        w = self.client.get("/api/v1/payswap/wallet", HTTP_X_APP_CONTEXT="payswap").json()["wallet"]
        self.assertEqual(w["available"], "3000.00")

        # 5 wrong PIN attempts trigger PIN lockout
        for idx in range(5):
            bad = self.client.post(
                "/api/v1/payswap/bbps/pay",
                {"biller": "65", "account": "1029384756", "amount": "100.00", "wallet_pin": "0000"},
                format="json",
                HTTP_X_APP_CONTEXT="payswap",
                HTTP_IDEMPOTENCY_KEY=f"pin-bad-{idx}",
            )
            self.assertEqual(bad.status_code, 403)
        locked = self.client.post(
            "/api/v1/payswap/bbps/pay",
            {"biller": "65", "account": "1029384756", "amount": "100.00", "wallet_pin": "4829"},
            format="json",
            HTTP_X_APP_CONTEXT="payswap",
            HTTP_IDEMPOTENCY_KEY="pin-locked-check",
        )
        self.assertEqual(locked.status_code, 423)
        self.assertEqual(locked.json()["code"], "pin_locked")

        # Reset PIN & freeze wallet
        admin_update_wallet_controls("shop@payswap.test", status="frozen", freeze_reason="Audit", reset_pin=True, admin_email="ops@hub.test")
        frozen_res = self.client.post(
            "/api/v1/payswap/bbps/pay",
            {"biller": "65", "account": "1029384756", "amount": "100.00"},
            format="json",
            HTTP_X_APP_CONTEXT="payswap",
            HTTP_IDEMPOTENCY_KEY="freeze-check-1",
        )
        self.assertEqual(frozen_res.status_code, 403)
        self.assertEqual(frozen_res.json()["code"], "wallet_frozen")

        # Unfreeze & enforce per-txn limit (500.00 = 50000 paise)
        admin_update_wallet_controls(
            "shop@payswap.test",
            status="active",
            per_txn_limit_paise=50000,
            admin_email="ops@hub.test",
        )
        lim_res = self.client.post(
            "/api/v1/payswap/bbps/pay",
            {"biller": "65", "account": "1029384756", "amount": "600.00"},
            format="json",
            HTTP_X_APP_CONTEXT="payswap",
            HTTP_IDEMPOTENCY_KEY="limit-check-1",
        )
        self.assertEqual(lim_res.status_code, 400)
        self.assertEqual(lim_res.json()["code"], "limit_exceeded")

    def test_bbps_pending_hold_captures_or_releases_on_status_sync(self):
        from domain.payswap.wallet import admin_adjust_wallet, wallet_overview

        admin_adjust_wallet("shop@payswap.test", direction="CR", amount_paise=100000, reason="Float", admin_email="ops@hub.test")
        self.client.cookies["auth_access"] = "retailer-token"
        pending_res = {
            "ok": True,
            "status": 202,
            "error": "",
            "reference": "T19PEND0001",
            "transaction_id": "",
            "vendor_status": "PENDING",
            "phase": "pending",
        }
        with patch("domain.payswap.bbps.pay_bill", return_value=pending_res):
            res = self.client.post(
                "/api/v1/payswap/bbps/pay",
                {"biller": "65", "account": "1029384756", "amount": "400.00"},
                format="json",
                HTTP_X_APP_CONTEXT="payswap",
                HTTP_IDEMPOTENCY_KEY="pend-1",
            )
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.json()["state"], "pending")
        pend_ref = res.json()["reference"]
        snap = wallet_overview("shop@payswap.test")["wallet"]
        self.assertEqual(snap["available"], "600.00")
        self.assertEqual(snap["held"], "400.00")

        # Status resolves to FAILED -> hold released back to 1000.00
        with patch(
            "domain.payswap.bbps.payment_status",
            return_value={
                "ok": True,
                "status": 200,
                "error": "",
                "reference": pend_ref,
                "vendor_status": "FAILED",
                "phase": "failed",
            },
        ):
            st = self.client.get(f"/api/v1/payswap/bbps/status?reference={pend_ref}", HTTP_X_APP_CONTEXT="payswap")
        self.assertEqual(st.status_code, 200)
        self.assertEqual(st.json()["state"], "failed")
        snap_after = wallet_overview("shop@payswap.test")["wallet"]
        self.assertEqual(snap_after["available"], "1000.00")
        self.assertEqual(snap_after["held"], "0.00")

    def test_pg_direct_bbps_refunds_wallet_if_bbps_fails_after_pg_paid(self):
        from domain.payswap.wallet import wallet_overview

        self.client.cookies["auth_access"] = "retailer-token"
        with patch(
            "domain.payswap.bbps.create_gateway_order",
            return_value={"ok": True, "provider_order_id": "cf_1", "payment_session_id": "sess_1", "checkout_url": ""},
        ):
            init = self.client.post(
                "/api/v1/payswap/bbps/pay",
                {"biller": "65", "account": "1029384756", "amount": "750.00", "payment_rail": "pg"},
                format="json",
                HTTP_X_APP_CONTEXT="payswap",
                HTTP_IDEMPOTENCY_KEY="pg-bbps-1",
            )
        self.assertEqual(init.status_code, 201, init.json())
        order_id = init.json()["pg_order_id"]

        with patch(
            "domain.payswap.wallet.fetch_gateway_order_status",
            return_value={"ok": True, "order_status": "PAID", "paid": True, "failed": False, "provider_payment_id": "pay_99"},
        ), patch(
            "domain.payswap.bbps.pay_bill",
            return_value={"ok": False, "status": 502, "error": "Biller down", "reference": "T19PGFAIL1", "phase": "failed"},
        ):
            ver = self.client.post(
                "/api/v1/payswap/pg/verify",
                {"pg_order_id": order_id},
                format="json",
                HTTP_X_APP_CONTEXT="payswap",
                HTTP_IDEMPOTENCY_KEY="pg-ver-1",
            )
        self.assertEqual(ver.status_code, 200, ver.json())
        # Since PG was PAID and BBPS failed, ₹750.00 is automatically credited to retailer wallet
        self.assertEqual(wallet_overview("shop@payswap.test")["wallet"]["available"], "750.00")

    def test_parkpe_customer_vehicles_crud_and_isolation(self):
        self.client.cookies["auth_access"] = "customer-token"
        added = self.client.post(
            "/api/v1/parkpe/vehicles",
            {"registration": "dl 01 ab 1234", "make_model": "Tata Nexon EV", "color": "White"},
            format="json",
            HTTP_X_APP_CONTEXT="parkpe",
            HTTP_IDEMPOTENCY_KEY="veh-1",
        )
        self.assertEqual(added.status_code, 201, added.json())
        vid = added.json()["vehicle_id"]
        self.assertEqual(added.json()["registration"], "DL01AB1234")

        listed = self.client.get("/api/v1/parkpe/vehicles", HTTP_X_APP_CONTEXT="parkpe")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(len(listed.json()["vehicles"]), 1)

        # Retailer cannot access ParkPe vehicles
        self.client.cookies["auth_access"] = "retailer-token"
        denied = self.client.get("/api/v1/parkpe/vehicles", HTTP_X_APP_CONTEXT="parkpe")
        self.assertEqual(denied.status_code, 403)

        self.client.cookies["auth_access"] = "customer-token"
        deleted = self.client.delete(f"/api/v1/parkpe/vehicles?vehicle_id={vid}", HTTP_X_APP_CONTEXT="parkpe")
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(len(self.client.get("/api/v1/parkpe/vehicles", HTTP_X_APP_CONTEXT="parkpe").json()["vehicles"]), 0)

    def test_legacy_bbps_backfill_and_admin_user_filter(self):
        import importlib
        from django.apps import apps as django_apps
        from django.db import connection
        from domain.payswap.transactions import list_admin_transactions, list_retailer_transactions
        from models.models import BbpsTransaction, HubAction, IdempotencyRecord, PgOrder

        IdempotencyRecord.objects.create(
            app_context="payswap",
            user_id="shop@payswap.test",
            endpoint="/api/v1/payswap/bbps/pay",
            idempotency_key="legacy-bbps-1",
            payload_hash="h1",
            state="done",
            status_code=201,
            body={
                "reference": "T1LEG0001",
                "operator_id": "294",
                "biller": "ICICI Bank FASTag",
                "account": "24BH8017B",
                "amount": "100.00",
                "payment_mode": "Cash",
                "state": "pending",
                "vendor_status": "PENDING",
            },
        )
        HubAction.objects.create(
            app_context="payswap",
            actor="shop@payswap.test",
            role="retailer",
            action="integration.bbps.pay",
            target_id="T1LEG0001",
            outcome="ok",
            status=200,
            response='200 OK\n\n{"success": true, "data": {"status": "SUCCESS", "txId": "MK_LEG_1"}}',
        )
        HubAction.objects.create(
            app_context="payswap",
            actor="shop@payswap.test",
            role="retailer",
            action="integration.bbps.status",
            target_id="T1LEG0001",
            outcome="ok",
            status=200,
            response='200 OK\n\n{"success": true, "data": {"txStatus": "RECHARGESUCCESS", "mobikwikrefno": "MK_LEG_1"}}',
        )

        mod = importlib.import_module("models.migrations.0006_backfill_legacy_bbps")
        mod.backfill_legacy_bbps(django_apps, None)

        row = BbpsTransaction.objects.get(reference="T1LEG0001")
        self.assertEqual(row.state, "success")
        self.assertEqual(row.vendor_status, "RECHARGESUCCESS")
        self.assertEqual(row.vendor_txn_id, "MK_LEG_1")
        self.assertEqual(row.amount_paise, 10000)

        PgOrder.objects.create(
            pg_order_id="pg_other_1",
            user_id="other@payswap.test",
            purpose="wallet_topup",
            amount_paise=50000,
            status="created",
        )
        ret = list_retailer_transactions("shop@payswap.test")
        self.assertTrue(any(r["reference"] == "T1LEG0001" for r in ret["transactions"]))

        adm = list_admin_transactions(user_id="shop@payswap.test")
        self.assertTrue(any(r["reference"] == "T1LEG0001" for r in adm["bbps_transactions"]))
        self.assertFalse(any(r["user_id"] == "other@payswap.test" for r in adm["pg_orders"]))

    def test_commission_credit_stays_out_of_pending(self):
        from domain.payswap.transactions import list_retailer_transactions
        from models.models import BbpsTransaction, WalletAccount, WalletLedgerEntry

        wallet = WalletAccount.objects.create(user_id="shop@payswap.test", available_paise=200)
        BbpsTransaction.objects.create(
            reference="T1PEND0001",
            user_id="shop@payswap.test",
            operator_id="1",
            biller_name="Airtel",
            account_mask="98••••10",
            amount_paise=1000,
            state="pending",
            vendor_txn_id="BBPS-PEND-1",
        )
        WalletLedgerEntry.objects.create(
            entry_id="led-cr-1",
            wallet=wallet,
            direction="CR",
            entry_type="COMMISSION_CR",
            amount_paise=2,
            balance_before_paise=200,
            balance_after_paise=202,
            held_before_paise=0,
            held_after_paise=0,
            reference="T1A216AF89AB1B1DB46CF4ED-CR",
            narration="Commission credit",
        )
        pending = list_retailer_transactions("shop@payswap.test", state="pending")
        self.assertTrue(any(r["reference"] == "T1PEND0001" and r["direction"] == "DR" for r in pending["transactions"]))
        self.assertFalse(any(r["direction"] == "CR" for r in pending["transactions"]))
        settled = list_retailer_transactions("shop@payswap.test", state="success")
        self.assertTrue(any(r["reference"].endswith("-CR") and r["state"] == "credited" for r in settled["transactions"]))
        self.assertFalse(any(r["reference"] == "T1PEND0001" for r in settled["transactions"]))





