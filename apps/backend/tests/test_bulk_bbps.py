"""Bulk BBPS pipe entitlement, upload/parse, proceed idempotency, pipe_b refusal."""

from __future__ import annotations

import io
from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIClient

from domain.payswap.bbps_pipes import get_pipe_adapter, normalize_pipe, pipe_configured
from domain.payswap.bulk_bbps import create_batch_from_upload, proceed_batch, process_fetch_queue
from domain.payswap.entitlements import (
    resolve_bbps_pipe,
    resolve_retailer_entitlements,
    update_default_policy,
    update_retailer_entitlements,
)
from domain.payswap.wallet import get_or_create_wallet, set_wallet_pin
from models.models import BulkBbpsRow


def session_for(token: str) -> dict:
    known = {
        "retailer-token": {"email": "shop@payswap.test", "role": "retailer"},
        "admin-token": {"email": "ops@hub.test", "role": "admin"},
    }
    if token not in known:
        from core.security import SessionRejected

        raise SessionRejected(401, "Sign in again.")
    return known[token]


class BulkBbpsPipeTests(TestCase):
    def test_normalize_and_pipe_b_unconfigured(self):
        self.assertEqual(normalize_pipe("Mobikwik"), "mobikwik")
        self.assertEqual(normalize_pipe("pipe_b"), "pipe_b")
        self.assertFalse(pipe_configured("pipe_b"))
        from rest_framework.exceptions import PermissionDenied

        with self.assertRaises(PermissionDenied) as ctx:
            get_pipe_adapter("pipe_b")
        self.assertEqual(ctx.exception.detail.get("code"), "bulk_pipe_unavailable")

    def test_default_and_retailer_pipe_override(self):
        update_default_policy(bbps_pipe="mobikwik", bbps_bulk_enabled=True, admin_email="ops@hub.test")
        self.assertEqual(resolve_bbps_pipe("shop@payswap.test"), "mobikwik")
        ent = resolve_retailer_entitlements("shop@payswap.test")
        self.assertTrue(ent["bbps_bulk_enabled"])
        self.assertEqual(ent["bbps_pipe"], "mobikwik")

        update_retailer_entitlements(
            "shop@payswap.test",
            bbps_pipe="pipe_b",
            bbps_bulk_enabled=False,
            admin_email="ops@hub.test",
        )
        self.assertEqual(resolve_bbps_pipe("shop@payswap.test"), "pipe_b")
        ent2 = resolve_retailer_entitlements("shop@payswap.test")
        self.assertFalse(ent2["bbps_bulk_enabled"])
        self.assertEqual(ent2["bbps_pipe_override"], "pipe_b")


class BulkBbpsFlowTests(TestCase):
    def setUp(self):
        update_default_policy(
            enabled_services=["bbps", "wallet", "transactions", "profile", "support"],
            bbps_pipe="mobikwik",
            bbps_bulk_enabled=True,
            admin_email="ops@hub.test",
        )
        wallet = get_or_create_wallet("shop@payswap.test")
        wallet.available_paise = 500_00
        wallet.save(update_fields=["available_paise", "updated_at"])
        set_wallet_pin("shop@payswap.test", new_pin="4829")

    def _csv(self, rows: list[str]) -> io.BytesIO:
        body = "biller_id,consumer_number,customer_mobile,amount,circle\n" + "\n".join(rows)
        buf = io.BytesIO(body.encode("utf-8"))
        buf.name = "bulk.csv"
        return buf

    @patch("domain.payswap.bulk_bbps.process_fetch_queue", return_value=0)
    @patch("domain.payswap.bulk_bbps.pipe_configured", return_value=True)
    @patch("domain.payswap.bulk_bbps.find_operator")
    def test_upload_partial_accept_and_not_required(self, find_op, _cfg, _fetch_q):
        def _find(raw):
            key = str(raw or "")
            if key == "GOOD1":
                return {
                    "op": "GOOD1",
                    "biller_id": "GOOD1",
                    "name": "Good Power",
                    "category": "ELECTRICITY",
                    "bill_fetch": "MANDATORY",
                }
            if key == "NR1":
                return {
                    "op": "NR1",
                    "biller_id": "NR1",
                    "name": "No Fetch",
                    "category": "ELECTRICITY",
                    "bill_fetch": "NOT_REQUIRED",
                }
            return None

        find_op.side_effect = _find
        upload = self._csv(
            [
                "GOOD1,ACC100,9876543210,,",
                "UNKNOWN,ACC200,9876543210,,",
                "NR1,ACC300,9876543210,150.00,",
            ]
        )
        batch = create_batch_from_upload(user_id="shop@payswap.test", upload=upload)
        self.assertTrue(batch["batch_id"].startswith("bbulk-"))
        rows = list(BulkBbpsRow.objects.filter(batch__batch_id=batch["batch_id"]).order_by("row_no"))
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0].fetch_state, "pending")
        self.assertEqual(rows[1].fetch_state, "failed")
        self.assertEqual(rows[2].fetch_state, "not_required")
        self.assertEqual(rows[2].pay_state, "ready")
        self.assertEqual(rows[2].pay_amount_paise, 15000)

    def test_rejects_macro_workbook_and_oversized_file(self):
        from domain.payswap.bbps import BbpsServiceError
        from domain.payswap.bulk_bbps import _read_tabular

        macro = io.BytesIO(b"not a workbook")
        macro.name = "bulk.xlsm"
        with self.assertRaises(BbpsServiceError):
            _read_tabular(macro)
        huge = io.BytesIO(b"a" * 1_000_001)
        huge.name = "bulk.csv"
        with self.assertRaises(BbpsServiceError):
            _read_tabular(huge)

    @patch("domain.payswap.bulk_bbps.pipe_configured", return_value=True)
    @patch("domain.payswap.bulk_bbps.pipe_fetch_bill")
    @patch("domain.payswap.bulk_bbps.find_operator")
    def test_fetch_then_proceed_idempotent_pay(self, find_op, fetch_bill, _cfg):
        find_op.return_value = {
            "op": "65",
            "biller_id": "65",
            "name": "Test Elec",
            "category": "ELECTRICITY",
            "bill_fetch": "MANDATORY",
            "default_payment_mode": "Cash",
        }
        fetch_bill.return_value = {
            "ok": True,
            "bill": {"amount": "100.00", "dueDate": "2099-01-15", "billNumber": "B1", "customerName": "A"},
        }
        upload = self._csv(["65,ACC900,9876543210,,"])
        batch = create_batch_from_upload(user_id="shop@payswap.test", upload=upload)
        batch_id = batch["batch_id"]
        process_fetch_queue(limit=5, batch_id=batch_id)
        row = BulkBbpsRow.objects.get(batch__batch_id=batch_id)
        self.assertEqual(row.fetch_state, "ok")
        self.assertEqual(row.pay_state, "ready")
        self.assertEqual(row.pay_amount_paise, 10000)

        with patch("domain.payswap.bulk_bbps.collect") as collect:
            collect.return_value = {"state": "success", "reference": "TREF1"}
            out1 = proceed_batch(batch_id, user_id="shop@payswap.test", wallet_pin="4829")
            self.assertIn(out1["status"], {"paying", "completed"})
            self.assertEqual(collect.call_count, 1)
            kwargs = collect.call_args.kwargs
            self.assertEqual(kwargs["idempotency_key"], f"bulk:{batch_id}:{row.row_id}")
            self.assertEqual(kwargs["payment_rail"], "wallet")
            self.assertEqual(kwargs["bulk_batch_id"], batch_id)

            # Second proceed while completed is a no-op / returns same batch.
            out2 = proceed_batch(batch_id, user_id="shop@payswap.test", wallet_pin="4829")
            self.assertEqual(out2["batch_id"], batch_id)
            self.assertEqual(collect.call_count, 1)

        row.refresh_from_db()
        self.assertEqual(row.pay_state, "success")
        self.assertEqual(row.bbps_reference, "TREF1")

    @patch("domain.payswap.bulk_bbps.pipe_configured", return_value=True)
    @patch("domain.payswap.bulk_bbps.find_operator")
    def test_insufficient_float_blocks_proceed(self, find_op, _cfg):
        find_op.return_value = {
            "op": "NR1",
            "biller_id": "NR1",
            "name": "No Fetch",
            "category": "ELECTRICITY",
            "bill_fetch": "NOT_REQUIRED",
        }
        wallet = get_or_create_wallet("shop@payswap.test")
        wallet.available_paise = 1000
        wallet.save(update_fields=["available_paise", "updated_at"])
        upload = self._csv(["NR1,ACC1,9876543210,500.00,"])
        batch = create_batch_from_upload(user_id="shop@payswap.test", upload=upload)
        from domain.payswap.bbps import BbpsServiceError

        with self.assertRaises(BbpsServiceError) as ctx:
            proceed_batch(batch["batch_id"], user_id="shop@payswap.test", wallet_pin="4829")
        detail = ctx.exception.detail if isinstance(ctx.exception.detail, dict) else {}
        self.assertEqual(detail.get("code"), "bulk_insufficient_float")

    @patch("domain.payswap.bulk_bbps.process_fetch_queue", return_value=0)
    @patch("domain.payswap.bulk_bbps.pipe_configured", return_value=True)
    @patch("domain.payswap.bulk_bbps.require_bbps_biller")
    @patch("domain.payswap.bulk_bbps.find_operator")
    def test_locked_biller_upload_without_biller_column(self, find_op, require_biller, _cfg, _fetch):
        find_op.return_value = {
            "op": "65",
            "biller_id": "TSELECUATTSN00",
            "name": "TSSPDCL",
            "category": "ELECTRICITY",
            "bill_fetch": "MANDATORY",
        }
        body = "consumer_number,customer_mobile,amount,circle\nACC111,9876543210,,\nACC222,9876543211,,\n"
        buf = io.BytesIO(body.encode("utf-8"))
        buf.name = "bulk.csv"
        batch = create_batch_from_upload(
            user_id="shop@payswap.test",
            upload=buf,
            locked_op="65",
        )
        self.assertEqual(batch["operator_id"], "65")
        self.assertEqual(batch["biller_name"], "TSSPDCL")
        rows = list(BulkBbpsRow.objects.filter(batch__batch_id=batch["batch_id"]).order_by("row_no"))
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0].operator_id, "65")
        self.assertEqual(rows[0].account, "ACC111")
        require_biller.assert_called()

        # Mismatched sheet biller is rejected when locked.
        find_op.side_effect = lambda raw: (
            {
                "op": "65",
                "biller_id": "TSELECUATTSN00",
                "name": "TSSPDCL",
                "category": "ELECTRICITY",
                "bill_fetch": "MANDATORY",
            }
            if str(raw) in {"65", "TSELECUATTSN00"}
            else {
                "op": "99",
                "biller_id": "OTHER",
                "name": "Other",
                "category": "ELECTRICITY",
                "bill_fetch": "MANDATORY",
            }
        )
        mixed = self._csv(["OTHER,ACC333,9876543210,,"])
        mixed_batch = create_batch_from_upload(
            user_id="shop@payswap.test",
            upload=mixed,
            locked_op="65",
        )
        bad = BulkBbpsRow.objects.get(batch__batch_id=mixed_batch["batch_id"])
        self.assertEqual(bad.fetch_state, "failed")
        self.assertIn("does not match", bad.parse_error)


class BulkBbpsApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.patcher = patch("api.v1.deps.fetch_session", side_effect=session_for)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        self.desk_patcher = patch("api.v1.routes.desk.fetch_session", side_effect=session_for)
        self.desk_patcher.start()
        self.addCleanup(self.desk_patcher.stop)
        update_default_policy(
            enabled_services=["bbps", "wallet", "transactions", "profile", "support"],
            bbps_pipe="mobikwik",
            bbps_bulk_enabled=True,
            admin_email="ops@hub.test",
        )

    @patch("domain.payswap.bulk_bbps.pipe_configured", return_value=True)
    def test_template_and_bulk_disabled(self, _cfg):
        self.client.cookies["auth_access"] = "retailer-token"
        ok = self.client.get("/api/v1/payswap/bbps/bulk/template", HTTP_X_APP_CONTEXT="payswap")
        self.assertEqual(ok.status_code, 200)
        self.assertIn(b"biller_id", ok.content)

        update_default_policy(bbps_bulk_enabled=False, admin_email="ops@hub.test")
        blocked = self.client.get("/api/v1/payswap/bbps/bulk/template", HTTP_X_APP_CONTEXT="payswap")
        self.assertEqual(blocked.status_code, 403)

    @patch("domain.payswap.bulk_bbps.pipe_configured", return_value=True)
    @patch("domain.payswap.bulk_bbps.find_operator")
    @patch("domain.payswap.bulk_bbps.require_bbps_biller")
    def test_template_locked_to_biller(self, require_biller, find_op, _cfg):
        find_op.return_value = {
            "op": "65",
            "biller_id": "TSELECUATTSN00",
            "name": "TSSPDCL",
            "category": "ELECTRICITY",
        }
        self.client.cookies["auth_access"] = "retailer-token"
        res = self.client.get(
            "/api/v1/payswap/bbps/bulk/template?op=65",
            HTTP_X_APP_CONTEXT="payswap",
        )
        self.assertEqual(res.status_code, 200, res.content)
        self.assertIn(b"TSELECUATTSN00", res.content)
        self.assertIn("bulk-TSSPDCL.csv", res.get("Content-Disposition", ""))
        require_biller.assert_called()
        find_op.return_value = None
        bad = self.client.get(
            "/api/v1/payswap/bbps/bulk/template?op=missing",
            HTTP_X_APP_CONTEXT="payswap",
        )
        self.assertEqual(bad.status_code, 400)

    @patch("domain.payswap.bulk_bbps.pipe_configured", return_value=True)
    @patch("domain.payswap.bulk_bbps.find_operator")
    @patch("domain.payswap.bulk_bbps.require_bbps_biller")
    def test_template_plan_multi_biller_counts(self, require_biller, find_op, _cfg):
        def _find(raw):
            key = str(raw or "")
            if key in {"65", "A"}:
                return {"op": "65", "biller_id": "A", "name": "PowerA", "category": "ELECTRICITY"}
            if key in {"99", "B"}:
                return {"op": "99", "biller_id": "B", "name": "PowerB", "category": "ELECTRICITY"}
            return None

        find_op.side_effect = _find
        self.client.cookies["auth_access"] = "retailer-token"
        res = self.client.post(
            "/api/v1/payswap/bbps/bulk/template",
            {"billers": [{"op": "65", "count": 3}, {"op": "99", "count": 2}]},
            format="json",
            HTTP_X_APP_CONTEXT="payswap",
            HTTP_IDEMPOTENCY_KEY="bulk-tmpl-multi-1",
        )
        self.assertEqual(res.status_code, 200, res.content)
        text = res.content.decode("utf-8")
        lines = [line for line in text.strip().splitlines() if line.strip()]
        self.assertEqual(lines[0], "biller_id,consumer_number,customer_mobile,amount,circle")
        self.assertEqual(len(lines) - 1, 5)
        self.assertEqual(sum(1 for line in lines[1:] if line.startswith("A,")), 3)
        self.assertEqual(sum(1 for line in lines[1:] if line.startswith("B,")), 2)
        self.assertIn("bulk-2-billers.csv", res.get("Content-Disposition", ""))
        self.assertEqual(require_biller.call_count, 2)

    @patch("domain.payswap.bulk_bbps.pipe_configured", return_value=True)
    @patch("domain.payswap.bulk_bbps.find_operator")
    @patch("domain.payswap.bulk_bbps.require_bbps_biller")
    def test_template_plan_get_query(self, require_biller, find_op, _cfg):
        def _find(raw):
            key = str(raw or "")
            if key in {"65", "A"}:
                return {"op": "65", "biller_id": "A", "name": "PowerA", "category": "ELECTRICITY"}
            if key in {"99", "B"}:
                return {"op": "99", "biller_id": "B", "name": "PowerB", "category": "ELECTRICITY"}
            return None

        find_op.side_effect = _find
        self.client.cookies["auth_access"] = "retailer-token"
        res = self.client.get(
            "/api/v1/payswap/bbps/bulk/template?plan=65:3,99:2",
            HTTP_X_APP_CONTEXT="payswap",
        )
        self.assertEqual(res.status_code, 200, res.content)
        lines = [line for line in res.content.decode("utf-8").strip().splitlines() if line.strip()]
        self.assertEqual(len(lines) - 1, 5)
        self.assertEqual(sum(1 for line in lines[1:] if line.startswith("A,")), 3)
        self.assertEqual(sum(1 for line in lines[1:] if line.startswith("B,")), 2)

    def test_pipe_b_refuses_bulk(self):
        update_retailer_entitlements(
            "shop@payswap.test",
            bbps_pipe="pipe_b",
            bbps_bulk_enabled=True,
            admin_email="ops@hub.test",
        )
        self.client.cookies["auth_access"] = "retailer-token"
        with patch("domain.payswap.bbps_pipes.pipe_configured", return_value=False):
            res = self.client.get("/api/v1/payswap/bbps/bulk/template", HTTP_X_APP_CONTEXT="payswap")
        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.json().get("code"), "bulk_pipe_unavailable")

    def test_desk_bulk_list_admin(self):
        self.client.cookies["auth_access"] = "admin-token"
        res = self.client.get("/api/v1/desk/bbps/bulk")
        self.assertEqual(res.status_code, 200)
        self.assertIn("batches", res.json())
