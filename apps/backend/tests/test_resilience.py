"""Chaos, restore, and graceful-degradation checks for the local hub.

No Redis and no separate queue broker exist in this stack. Vendor and gateway
faults are injected with mocks. SQLite restore uses a copy under /tmp.
"""

from __future__ import annotations

import os
import shutil
import sqlite3
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase, override_settings
from rest_framework.test import APIClient

from core.security import SessionRejected


def session_for(token: str) -> dict:
    known = {
        "retailer-token": {"email": "shop@payswap.test", "role": "retailer"},
        "admin-token": {"email": "ops@hub.test", "role": "admin"},
    }
    if token not in known:
        raise SessionRejected(401, "Sign in again.")
    return known[token]


class VendorFaultTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.patcher = patch("api.v1.deps.fetch_session", side_effect=session_for)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        self.client.cookies["auth_access"] = "retailer-token"

    def test_gateway_timeout_does_not_credit_wallet(self):
        from domain.payswap.wallet import create_pg_topup_order, wallet_overview
        from models.models import PgOrder

        with patch(
            "domain.payswap.wallet.create_gateway_order",
            return_value={
                "ok": True,
                "provider_order_id": "cf-chaos-1",
                "payment_session_id": "sess-chaos",
                "checkout_url": "",
                "cashfree_mode": "sandbox",
            },
        ):
            order = create_pg_topup_order("shop@payswap.test", amount_paise=25000, customer_phone="9876543210")
        before = wallet_overview("shop@payswap.test")["wallet"]["available_paise"]

        with patch(
            "domain.payswap.wallet.fetch_gateway_order_status",
            return_value={"ok": False, "status": 504, "error": "Gateway timed out after 10 seconds."},
        ):
            res = self.client.post(
                "/api/v1/payswap/pg/verify",
                {"pg_order_id": order["pg_order_id"]},
                format="json",
                HTTP_X_APP_CONTEXT="payswap",
                HTTP_IDEMPOTENCY_KEY="chaos-gw-timeout",
            )
        self.assertIn(res.status_code, (502, 503, 504))
        body = res.json()
        self.assertEqual(body["code"], "server_error")
        self.assertNotIn("Traceback", res.content.decode())
        row = PgOrder.objects.get(pg_order_id=order["pg_order_id"])
        self.assertEqual(row.status, "created")
        self.assertEqual(wallet_overview("shop@payswap.test")["wallet"]["available_paise"], before)

    def test_vendor_down_on_wallet_pay_releases_hold(self):
        from domain.payswap.wallet import admin_adjust_wallet, wallet_overview

        admin_adjust_wallet(
            "shop@payswap.test",
            direction="CR",
            amount_paise=100000,
            reason="Chaos float",
            admin_email="ops@hub.test",
            idempotency_key="chaos-float-1000",
        )
        failed = {
            "ok": False,
            "status": 502,
            "error": "Biller unreachable",
            "reference": "T19CHAOS001",
            "transaction_id": "",
            "vendor_status": "FAILED",
            "phase": "failed",
        }
        with patch("domain.payswap.bbps.pipe_pay_bill", return_value=failed):
            res = self.client.post(
                "/api/v1/payswap/bbps/pay",
                {"biller": "65", "account": "1029384756", "amount": "100.00"},
                format="json",
                HTTP_X_APP_CONTEXT="payswap",
                HTTP_IDEMPOTENCY_KEY="chaos-vendor-down",
            )
        self.assertEqual(res.status_code, 502)
        snap = wallet_overview("shop@payswap.test")["wallet"]
        self.assertEqual(snap["available"], "1000.00")
        self.assertEqual(snap["held"], "0.00")


class SqliteRestoreTests(SimpleTestCase):
    def test_hub_sqlite_backup_restore_recovers_rows(self):
        src = Path(__file__).resolve().parents[1] / "data" / "hub.sqlite"
        if not src.exists():
            self.skipTest("hub.sqlite is not present on this machine")

        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            live = work / "live.sqlite"
            backup = work / "backup.sqlite"
            restored = work / "restored.sqlite"
            shutil.copy2(src, live)

            conn = sqlite3.connect(live)
            try:
                conn.execute(
                    "CREATE TABLE IF NOT EXISTS chaos_probe (id INTEGER PRIMARY KEY, note TEXT NOT NULL)"
                )
                conn.execute("INSERT INTO chaos_probe(note) VALUES (?)", ("before-backup",))
                conn.commit()
                before = conn.execute("SELECT COUNT(*) FROM chaos_probe").fetchone()[0]
            finally:
                conn.close()

            started = time.perf_counter()
            shutil.copy2(live, backup)
            backup_ms = (time.perf_counter() - started) * 1000

            conn = sqlite3.connect(live)
            try:
                conn.execute("DELETE FROM chaos_probe")
                conn.commit()
                wiped = conn.execute("SELECT COUNT(*) FROM chaos_probe").fetchone()[0]
            finally:
                conn.close()
            self.assertEqual(wiped, 0)

            restore_started = time.perf_counter()
            shutil.copy2(backup, restored)
            restore_ms = (time.perf_counter() - restore_started) * 1000

            conn = sqlite3.connect(restored)
            try:
                after = conn.execute("SELECT COUNT(*) FROM chaos_probe").fetchone()[0]
                note = conn.execute("SELECT note FROM chaos_probe ORDER BY id DESC LIMIT 1").fetchone()[0]
            finally:
                conn.close()

            self.assertEqual(before, after)
            self.assertEqual(note, "before-backup")
            self.assertLess(backup_ms, 2000)
            self.assertLess(restore_ms, 2000)
            # Local RTO/RPO for a file copy restore of this ledger size.
            self.assertGreaterEqual(os.path.getsize(backup), 1)
