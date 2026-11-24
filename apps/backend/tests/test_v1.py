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
from domain.parkpe import sessions as parkpe_sessions
from domain.payswap import vouchers as payswap_vouchers


def session_for(token: str) -> dict:
    known = {
        "customer-token": {"email": "driver@parkpe.test", "role": "customer"},
        "retailer-token": {"email": "shop@payswap.test", "role": "retailer"},
        "operator-token": {"email": "ops@hub.test", "role": "operator"},
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
        self.client.cookies["auth_access"] = "retailer-token"
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
