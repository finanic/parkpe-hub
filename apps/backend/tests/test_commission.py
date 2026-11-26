"""BBPS commission split, TDS, GST, settle, and desk policy checks.

Covers domain/payswap/commission.py math used by bbps success and desk routes.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

import os
import sqlite3
import tempfile

from domain.payswap.economics.split import compute_economics
from domain.payswap.commission import (
    compute_split,
    create_monthly_invoice,
    ensure_commission_catalogue,
    fiscal_period,
    generate_monthly_invoices,
    get_or_create_policy,
    mark_tds_deposited,
    previous_calendar_month,
    resolve_rate,
    retailer_commission_sheet,
    settle_commission,
    update_retailer_biller_share,
    tds_month_report,
    update_policy,
    update_retailer_service_share,
    vendor_commission_paise,
)
from models.models import (
    BbpsTransaction,
    CommissionInvoice,
    CommissionPolicy,
    RetailerCommissionOverride,
    RetailerServiceOverride,
    ServiceEconomicsPolicy,
    ServiceRateRow,
    ServiceSettlement,
    TdsAccrual,
    VendorCommissionRate,
)


def session_for(token: str) -> dict:
    known = {
        "retailer-token": {"email": "shop@payswap.test", "role": "retailer"},
        "admin-token": {"email": "ops@hub.test", "role": "admin"},
    }
    if token not in known:
        from core.security import SessionRejected

        raise SessionRejected(401, "Sign in again.")
    return known[token]


class CommissionMathTests(TestCase):
    def setUp(self):
        get_or_create_policy()
        for kwargs in (
            {
                "external_id": "101",
                "name": "Sample Electricity",
                "category": "Electricity",
                "rate_value": Decimal("2.025"),
                "rate_type": "flat",
                "min_txn_paise": 100,
            },
            {
                "external_id": "11",
                "name": "Airtel Prepaid",
                "category": "Prepaid",
                "rate_value": Decimal("0.531"),
                "rate_type": "percent",
                "min_txn_paise": 0,
            },
        ):
            ServiceRateRow.objects.create(service="bbps", enabled=True, **kwargs)
            VendorCommissionRate.objects.create(
                operator_id=kwargs["external_id"],
                operator_name=kwargs["name"],
                category=kwargs["category"],
                rate_value=kwargs["rate_value"],
                rate_type=kwargs["rate_type"],
                min_txn_paise=kwargs["min_txn_paise"],
            )

    def test_flat_rate_and_30_70_split_with_tds(self):
        rate = resolve_rate(operator_id="101", category="Electricity", retailer_id="")
        vendor = vendor_commission_paise(amount_paise=50_000, rate=rate)
        self.assertEqual(vendor, 203)  # ₹2.025
        split = compute_split(vendor_paise=vendor, has_gstin=False)
        self.assertEqual(split["admin_revenue_paise"], 61)
        self.assertEqual(split["retailer_commission_paise"], 142)
        self.assertEqual(split["tds_paise"], 3)  # 2% of 142
        self.assertEqual(split["gst_paise"], 0)
        self.assertEqual(split["net_credit_paise"], 139)

    def test_percent_rate_on_prepaid(self):
        rate = resolve_rate(operator_id="11", category="Prepaid", retailer_id="")
        vendor = vendor_commission_paise(amount_paise=29_900, rate=rate)  # ₹299
        self.assertEqual(vendor, 159)
        split = compute_split(vendor_paise=vendor, has_gstin=False)
        self.assertEqual(split["admin_revenue_paise"], 48)
        self.assertEqual(split["retailer_commission_paise"], 111)
        self.assertEqual(split["tds_paise"], 2)
        self.assertEqual(split["net_credit_paise"], 109)

    def test_min_txn_blocks_commission(self):
        rate = resolve_rate(operator_id="101", category="Electricity", retailer_id="")
        self.assertEqual(vendor_commission_paise(amount_paise=50, rate=rate), 0)

    def test_gst_only_when_gstin(self):
        split = compute_split(vendor_paise=1000, has_gstin=True)
        self.assertEqual(split["retailer_commission_paise"], 700)
        self.assertEqual(split["gst_paise"], 126)  # 18% of 700
        self.assertEqual(split["tds_paise"], 14)  # 2% ex-GST
        self.assertEqual(split["net_credit_paise"], 686)

    def test_retailer_override_beats_default_share(self):
        RetailerCommissionOverride.objects.create(
            user_id="shop@payswap.test",
            admin_share_bps=1000,  # 10% admin / 90% retailer
            active=True,
        )
        RetailerServiceOverride.objects.create(
            user_id="shop@payswap.test",
            service="bbps",
            admin_share_bps=1000,
            active=True,
        )
        split = compute_split(vendor_paise=1000, retailer_id="shop@payswap.test", has_gstin=False)
        self.assertEqual(split["admin_share_bps"], 1000)
        self.assertEqual(split["admin_revenue_paise"], 100)
        self.assertEqual(split["retailer_commission_paise"], 900)

    def test_retailer_commission_sheet_per_service(self):
        sheet = retailer_commission_sheet(
            "shop@payswap.test",
            enabled_services=["bbps", "dmt"],
        )
        by_svc = {row["service"]: row for row in sheet["rows"]}
        self.assertTrue(by_svc["bbps"]["enabled"])
        self.assertTrue(by_svc["dmt"]["enabled"])
        self.assertFalse(by_svc["aeps"]["enabled"])
        self.assertTrue(by_svc["bbps"]["inherits"])
        update_retailer_service_share(
            "shop@payswap.test",
            "dmt",
            actor="ops@hub.test",
            admin_share_bps=1500,
        )
        sheet2 = retailer_commission_sheet(
            "shop@payswap.test",
            enabled_services=["bbps", "dmt"],
        )
        dmt = {row["service"]: row for row in sheet2["rows"]}["dmt"]
        self.assertFalse(dmt["inherits"])
        self.assertEqual(dmt["override_admin_share_bps"], 1500)
        self.assertEqual(dmt["effective_retailer_share_percent"], 85.0)
        update_retailer_service_share(
            "shop@payswap.test",
            "dmt",
            actor="ops@hub.test",
            clear_share=True,
        )
        sheet3 = retailer_commission_sheet(
            "shop@payswap.test",
            enabled_services=["bbps", "dmt"],
        )
        self.assertTrue({row["service"]: row for row in sheet3["rows"]}["dmt"]["inherits"])

    def test_biller_share_beats_service_share_on_settlement(self):
        RetailerServiceOverride.objects.create(
            user_id="shop@payswap.test",
            service="bbps",
            admin_share_bps=2000,
            share_overrides=[{"external_id": "1", "category": "PREPAID", "admin_share_bps": 1000}],
            active=True,
        )
        hit = compute_economics(
            service="bbps",
            amount_paise=1000,
            external_id="1",
            category="PREPAID",
            retailer_id="shop@payswap.test",
            vendor_paise=100,
            has_gstin=False,
        )
        self.assertEqual(hit["admin_revenue_paise"], 10)
        self.assertEqual(hit["snapshot"]["share_source"], "biller")
        other = compute_economics(
            service="bbps",
            amount_paise=1000,
            external_id="2",
            category="PREPAID",
            retailer_id="shop@payswap.test",
            vendor_paise=100,
            has_gstin=False,
        )
        self.assertEqual(other["admin_revenue_paise"], 20)
        self.assertEqual(other["snapshot"]["share_source"], "service")
        update_retailer_biller_share(
            "shop@payswap.test",
            "bbps",
            "1",
            "PREPAID",
            actor="ops@hub.test",
            clear_share=True,
        )
        cleared = compute_economics(
            service="bbps",
            amount_paise=1000,
            external_id="1",
            category="PREPAID",
            retailer_id="shop@payswap.test",
            vendor_paise=100,
            has_gstin=False,
        )
        self.assertEqual(cleared["admin_revenue_paise"], 20)
        plain = compute_economics(
            service="bbps",
            amount_paise=1000,
            external_id="1",
            category="PREPAID",
            retailer_id="other@payswap.test",
            vendor_paise=100,
            has_gstin=False,
        )
        self.assertEqual(plain["admin_revenue_paise"], 30)
        self.assertEqual(plain["snapshot"]["share_source"], "policy")


class CommissionSettleTests(TestCase):
    def setUp(self):
        get_or_create_policy()
        ServiceRateRow.objects.create(
            service="bbps",
            external_id="101",
            name="Sample Electricity",
            category="Electricity",
            rate_value=Decimal("2.025"),
            rate_type="flat",
            min_txn_paise=0,
            enabled=True,
        )

    def test_settle_writes_fields_and_tds_accrual(self):
        tx = BbpsTransaction.objects.create(
            reference="TCOMM0001",
            user_id="shop@payswap.test",
            operator_id="101",
            biller_name="Sample Electricity",
            category="Electricity",
            account_mask="****1234",
            amount_paise=50_000,
            state="success",
            payment_channel="wallet",
        )
        out = settle_commission(tx, has_gstin=False)
        self.assertTrue(out["applied"])
        tx.refresh_from_db()
        self.assertEqual(tx.vendor_commission_paise, 203)
        self.assertEqual(tx.admin_revenue_paise, 61)
        self.assertEqual(tx.retailer_commission_paise, 142)
        self.assertEqual(tx.tds_paise, 3)
        self.assertEqual(tx.commission_paise, 139)
        accrual = TdsAccrual.objects.get(reference="TCOMM0001")
        self.assertEqual(accrual.tds_paise, 3)
        self.assertEqual(accrual.status, "open")

        again = settle_commission(tx, has_gstin=False)
        self.assertFalse(again["applied"])
        self.assertEqual(TdsAccrual.objects.filter(reference="TCOMM0001").count(), 1)

    def test_monthly_invoice_for_gstin_retailer(self):
        tx = BbpsTransaction.objects.create(
            reference="TCOMMINV1",
            user_id="shop@payswap.test",
            operator_id="101",
            biller_name="Sample Electricity",
            category="Electricity",
            account_mask="****1234",
            amount_paise=50_000,
            state="success",
            payment_channel="wallet",
        )
        settle_commission(tx, has_gstin=True)
        month = timezone.localdate().strftime("%Y-%m")
        inv = create_monthly_invoice(
            user_id="shop@payswap.test",
            month=month,
            gstin="29AAAAA0000A1Z5",
            actor="ops@hub.test",
        )
        self.assertEqual(inv["month"], month)
        self.assertGreater(int(Decimal(inv["taxable"]) * 100), 0)
        self.assertIn("Commission tax invoice", inv["html"])
        self.assertEqual(CommissionInvoice.objects.filter(user_id="shop@payswap.test").count(), 1)


class CommissionDeskApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.desk_patch = patch("api.v1.routes.desk.fetch_session", side_effect=session_for)
        self.desk_patch.start()
        self.addCleanup(self.desk_patch.stop)
        self.deps_patch = patch("api.v1.deps.fetch_session", side_effect=session_for)
        self.deps_patch.start()
        self.addCleanup(self.deps_patch.stop)
        get_or_create_policy()

    def test_desk_policy_get_and_post(self):
        self.client.cookies["auth_access"] = "admin-token"
        got = self.client.get("/api/v1/desk/commission/policy")
        self.assertEqual(got.status_code, 200)
        self.assertEqual(got.json()["admin_share_bps"], 3000)

        post = self.client.post(
            "/api/v1/desk/commission/policy",
            {"admin_share_bps": 2500, "tds_rate_bps": 200, "gst_rate_bps": 1800},
            format="json",
        )
        self.assertEqual(post.status_code, 200)
        self.assertEqual(post.json()["admin_share_bps"], 2500)
        update_policy(admin_share_bps=3000, actor="ops@hub.test")

    def test_retailer_summary(self):
        from domain.payswap.entitlements import update_retailer_entitlements

        update_retailer_entitlements(
            "shop@payswap.test",
            service_overrides={"bbps": True, "wallet": True},
            admin_email="ops@hub.test",
        )
        self.client.cookies["auth_access"] = "retailer-token"
        res = self.client.get(
            "/api/v1/payswap/commission/summary?service=all",
            HTTP_X_APP_CONTEXT="payswap",
        )
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertIn("commission", body)
        self.assertIn("tds", body)
        self.assertIn("invoices", body)


class CommissionAutoEnsureTests(TestCase):
    def test_ensure_skips_under_tests_without_force(self):
        get_or_create_policy()
        out = ensure_commission_catalogue(actor="test")
        self.assertFalse(out["imported"])
        self.assertEqual(out["reason"], "test_skip")

    def test_ensure_imports_when_forced_with_sheet(self):
        import openpyxl

        get_or_create_policy()
        VendorCommissionRate.objects.all().delete()
        path = Path(self._temp_dir()) / "commission-b2b.xlsx"
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["Operator Id", "Name", "b2b comm", "Minimum Txn", "Category", "BBPS", "Commission Type"])
        ws.append([901, "Auto Power", 2.025, 1, "Electricity", True, "Per Txn"])
        wb.save(path)

        out = ensure_commission_catalogue(path=path, force=True, actor="test")
        self.assertTrue(out["imported"])
        self.assertEqual(ServiceRateRow.objects.filter(service="bbps", external_id="901").count(), 1)
        self.assertEqual(VendorCommissionRate.objects.filter(operator_id="901").count(), 1)
        policy = ServiceEconomicsPolicy.objects.get(service="bbps")
        self.assertGreater(float(policy.rates_file_mtime or 0), 0)
        self.assertIsNotNone(policy.rates_imported_at)

        again = ensure_commission_catalogue(path=path, force=False, actor="test")
        # Still under manage.py test → skip unless force
        self.assertEqual(again["reason"], "test_skip")

        fresh = ensure_commission_catalogue(path=path, force=True, actor="test")
        self.assertTrue(fresh["imported"])

    def test_settle_zero_when_no_rate(self):
        get_or_create_policy()
        VendorCommissionRate.objects.all().delete()
        tx = BbpsTransaction.objects.create(
            reference="TCOMMZERO1",
            user_id="shop@payswap.test",
            operator_id="missing-op",
            biller_name="Unknown",
            category="Electricity",
            account_mask="****0000",
            amount_paise=10_000,
            state="success",
            payment_channel="wallet",
        )
        out = settle_commission(tx, has_gstin=False)
        self.assertTrue(out["applied"])
        self.assertEqual(out["vendor_commission_paise"], 0)
        self.assertEqual(out["net_credit_paise"], 0)
        tx.refresh_from_db()
        self.assertEqual(tx.commission_rate_snapshot.get("rate", {}).get("source"), "none")

    def _temp_dir(self) -> str:
        import tempfile

        d = tempfile.mkdtemp(prefix="comm-sheet-")
        self.addCleanup(lambda: __import__("shutil").rmtree(d, ignore_errors=True))
        return d


class CommissionInvoiceBatchTests(TestCase):
    def test_previous_calendar_month(self):
        self.assertEqual(previous_calendar_month(date(2026, 11, 25)), "2026-10")
        self.assertEqual(previous_calendar_month(date(2026, 1, 5)), "2025-12")

    def test_generate_monthly_invoices_idempotent(self):
        get_or_create_policy()
        ServiceRateRow.objects.create(
            service="bbps",
            external_id="101",
            name="Sample Electricity",
            category="Electricity",
            rate_value=Decimal("2.025"),
            rate_type="flat",
            min_txn_paise=0,
            enabled=True,
        )
        tx = BbpsTransaction.objects.create(
            reference="TCOMMBATCH1",
            user_id="gst-shop@payswap.test",
            operator_id="101",
            biller_name="Sample Electricity",
            category="Electricity",
            account_mask="****9999",
            amount_paise=50_000,
            state="success",
            payment_channel="wallet",
        )
        settle_commission(tx, has_gstin=True)
        month = timezone.localdate().strftime("%Y-%m")
        with patch("domain.payswap.commission.retailer_gstin", return_value="29AAAAA0000A1Z5"):
            first = generate_monthly_invoices(month=month, actor="test")
            second = generate_monthly_invoices(month=month, actor="test")
        self.assertEqual(first["created"], 1)
        self.assertEqual(second["created"], 0)
        self.assertEqual(second["reused"], 1)
        self.assertEqual(CommissionInvoice.objects.filter(user_id="gst-shop@payswap.test", month=month).count(), 1)
        self.assertEqual(first["invoices"][0]["invoice_no"], second["invoices"][0]["invoice_no"])


class TdsDepositPackTests(TestCase):
    def test_fiscal_period_follows_april_year(self):
        self.assertEqual(
            fiscal_period("2026-04"),
            {"section": "194H", "quarter": "Q1", "financial_year": "2026-27"},
        )
        self.assertEqual(fiscal_period("2026-11")["quarter"], "Q3")
        self.assertEqual(fiscal_period("2026-03")["quarter"], "Q4")
        self.assertEqual(fiscal_period("2026-03")["financial_year"], "2025-26")

    def test_deposit_needs_tan_identity_and_matching_challan(self):
        TdsAccrual.objects.create(
            accrual_id="tds-pack-1",
            user_id="shop@payswap.test",
            service="bbps",
            reference="TDSPACK1",
            month="2026-11",
            tds_paise=300,
            commission_paise=15000,
            status="open",
        )
        with self.assertRaises(ValueError):
            update_policy(actor="ops@hub.test", deductor_tan="NOT-A-TAN")
        report = tds_month_report(month="2026-11")
        self.assertEqual(report["section"], "194H")
        self.assertEqual(report["quarter"], "Q3")
        self.assertEqual(report["financial_year"], "2026-27")
        self.assertTrue(any("TAN" in line for line in report["missing"]))
        self.assertTrue(any("PAN" in line for line in report["missing"]))
        with self.assertRaises(ValueError):
            mark_tds_deposited(
                month="2026-11",
                actor="ops@hub.test",
                challan_bsr="0001234",
                challan_serial="99",
                challan_date="2026-11-07",
                challan_amount="3.00",
            )
        update_policy(actor="ops@hub.test", deductor_tan="BLRP12345E")
        with tempfile.TemporaryDirectory() as folder:
            db = Path(folder) / "auth.sqlite"
            with sqlite3.connect(db) as conn:
                conn.execute("CREATE TABLE users (id TEXT PRIMARY KEY, email TEXT)")
                conn.execute(
                    """CREATE TABLE account_profiles (
                        user_id TEXT, role TEXT, display_name TEXT, pan_name TEXT,
                        pan_name_hint TEXT, pan TEXT, pan_mask TEXT
                    )"""
                )
                conn.execute("INSERT INTO users VALUES ('u1', 'shop@payswap.test')")
                conn.execute(
                    "INSERT INTO account_profiles VALUES (?, ?, ?, ?, ?, ?, ?)",
                    ("u1", "retailer", "Sharma Stores", "RAHUL SHARMA", "", "ABCDE1234F", "ABCDE····F"),
                )
            previous = os.environ.get("AUTH_DATA_DIR")
            os.environ["AUTH_DATA_DIR"] = folder
            try:
                with self.assertRaises(ValueError) as mismatch:
                    mark_tds_deposited(
                        month="2026-11",
                        user_id="shop@payswap.test",
                        actor="ops@hub.test",
                        challan_bsr="0001234",
                        challan_serial="99",
                        challan_date="2026-11-07",
                        challan_amount="2.00",
                    )
                self.assertIn("3.00", str(mismatch.exception))
                with self.assertLogs("hub.actions", level="INFO") as captured:
                    out = mark_tds_deposited(
                        month="2026-11",
                        user_id="shop@payswap.test",
                        actor="ops@hub.test",
                        challan_bsr="0001234",
                        challan_serial="99",
                        challan_date="2026-11-07",
                        challan_amount="3.00",
                    )
                self.assertEqual(out["updated"], 1)
                self.assertNotIn("ABCDE1234F", "\n".join(captured.output))
                packed = tds_month_report(month="2026-11")
            finally:
                if previous is None:
                    os.environ.pop("AUTH_DATA_DIR", None)
                else:
                    os.environ["AUTH_DATA_DIR"] = previous
        self.assertEqual(packed["retailers"][0]["name"], "Sharma Stores")
        self.assertEqual(packed["retailers"][0]["pan"], "ABCDE1234F")
        self.assertEqual(packed["retailers"][0]["challan_bsr"], "0001234")
        self.assertEqual(packed["retailers"][0]["challan_date"], "2026-11-07")
        self.assertEqual(packed["deductor_tan"], "BLRP12345E")
        self.assertEqual(packed["missing"], [])
        row = TdsAccrual.objects.get(reference="TDSPACK1")
        self.assertEqual(row.status, "deposited")
        self.assertEqual(row.challan_amount_paise, 300)


class TdsRateChoiceTests(TestCase):
    def setUp(self):
        get_or_create_policy()
        ServiceRateRow.objects.create(
            service="bbps",
            external_id="101",
            name="Sample Electricity",
            category="Electricity",
            rate_value=Decimal("2.025"),
            rate_type="flat",
            min_txn_paise=0,
            enabled=True,
        )

    def _identities(self, folder: str) -> None:
        db = Path(folder) / "auth.sqlite"
        with sqlite3.connect(db) as conn:
            conn.execute("CREATE TABLE users (id TEXT PRIMARY KEY, email TEXT)")
            conn.execute(
                """CREATE TABLE account_profiles (
                    user_id TEXT, role TEXT, display_name TEXT, pan_name TEXT,
                    pan_name_hint TEXT, pan TEXT, pan_mask TEXT
                )"""
            )
            conn.executemany(
                "INSERT INTO users VALUES (?, ?)",
                [("u-pan", "pan@payswap.test"), ("u-none", "nopan@payswap.test"), ("u-other", "other@payswap.test")],
            )
            conn.executemany(
                "INSERT INTO account_profiles VALUES (?, ?, ?, ?, ?, ?, ?)",
                [
                    ("u-pan", "retailer", "Pan Shop", "PAN SHOP", "", "ABCDE1234F", "ABCDE····F"),
                    ("u-none", "retailer", "No Pan Shop", "NO PAN", "", "", ""),
                    ("u-other", "retailer", "Other Shop", "OTHER SHOP", "", "BBBBB1111B", "BBBBB····B"),
                ],
            )

    def test_197_applies_after_approval_and_206aa_stays_without_pan(self):
        from datetime import datetime

        from domain.payswap.commission import approve_tds_certificate, submit_tds_certificate
        from domain.payswap.economics.split import compute_economics
        from domain.payswap.wallet import get_or_create_wallet

        with self.assertRaises(ValueError):
            submit_tds_certificate(
                user_id="pan@payswap.test",
                actor="pan@payswap.test",
                certificate_no="197/2026/0001",
                rate_bps=500,
                valid_from="2026-04-01",
                valid_to="2027-03-31",
            )
        with tempfile.TemporaryDirectory() as folder:
            self._identities(folder)
            previous = os.environ.get("AUTH_DATA_DIR")
            os.environ["AUTH_DATA_DIR"] = folder
            try:
                plain = compute_economics(service="bbps", amount_paise=50_000, external_id="101", category="Electricity", retailer_id="other@payswap.test")
                self.assertEqual(plain["tds_basis"], "194h")
                self.assertEqual(plain["tds_paise"], 3)
                missing = compute_economics(service="bbps", amount_paise=50_000, external_id="101", category="Electricity", retailer_id="nopan@payswap.test")
                self.assertEqual(missing["tds_basis"], "206aa")
                self.assertEqual(missing["tds_paise"], 28)
                tx = BbpsTransaction.objects.create(
                    reference="TDS206AA",
                    user_id="nopan@payswap.test",
                    operator_id="101",
                    biller_name="Sample Electricity",
                    category="Electricity",
                    account_mask="****1234",
                    amount_paise=50_000,
                    state="success",
                    payment_channel="wallet",
                )
                settled = settle_commission(tx, has_gstin=False)
                self.assertEqual(settled["tds_paise"], 28)
                self.assertEqual(TdsAccrual.objects.get(reference="TDS206AA").tds_basis, "206aa")
                waiting = submit_tds_certificate(
                    user_id="nopan@payswap.test",
                    actor="nopan@payswap.test",
                    certificate_no="197/2026/0099",
                    rate_bps=0,
                    valid_from="2026-04-01",
                    valid_to="2027-03-31",
                )
                self.assertEqual(waiting["pending"]["status"], "pending")
                self.assertEqual(
                    compute_economics(service="bbps", amount_paise=50_000, external_id="101", category="Electricity", retailer_id="nopan@payswap.test")["tds_basis"],
                    "206aa",
                )
                with self.assertRaises(ValueError):
                    approve_tds_certificate(certificate_id=waiting["pending"]["id"], actor="ops@hub.test")
                today = TdsAccrual.objects.create(
                    accrual_id="tds-today",
                    user_id="pan@payswap.test",
                    service="bbps",
                    reference="TDSTODAY",
                    month="2026-11",
                    tds_paise=3,
                    tds_paise_withheld=3,
                    commission_paise=142,
                    tds_rate_bps=200,
                    tds_basis="194h",
                    status="open",
                )
                old = TdsAccrual.objects.create(
                    accrual_id="tds-old",
                    user_id="pan@payswap.test",
                    service="bbps",
                    reference="TDSOLD",
                    month="2020-01",
                    tds_paise=3,
                    tds_paise_withheld=3,
                    commission_paise=142,
                    tds_rate_bps=200,
                    tds_basis="194h",
                    status="open",
                )
                TdsAccrual.objects.filter(pk=old.pk).update(created_at=timezone.make_aware(datetime(2020, 1, 15, 10, 0, 0)))
                settlement = ServiceSettlement.objects.create(
                    settlement_id="set-today",
                    service="bbps",
                    reference="TDSTODAY",
                    user_id="pan@payswap.test",
                    retailer_commission_paise=142,
                    tds_paise=3,
                    net_to_retailer_paise=139,
                )
                BbpsTransaction.objects.create(
                    reference="TDSTODAY",
                    user_id="pan@payswap.test",
                    operator_id="101",
                    biller_name="Sample Electricity",
                    category="Electricity",
                    account_mask="****1234",
                    amount_paise=50_000,
                    commission_paise=139,
                    retailer_commission_paise=142,
                    tds_paise=3,
                    state="success",
                    payment_channel="wallet",
                )
                filed = submit_tds_certificate(
                    user_id="pan@payswap.test",
                    actor="pan@payswap.test",
                    certificate_no="197/2026/0001",
                    rate_bps=50,
                    valid_from="2026-04-01",
                    valid_to="2027-03-31",
                )
                self.assertEqual(
                    compute_economics(service="bbps", amount_paise=50_000, external_id="101", category="Electricity", retailer_id="pan@payswap.test")["tds_basis"],
                    "194h",
                )
                approved = approve_tds_certificate(certificate_id=filed["pending"]["id"], actor="ops@hub.test")
                self.assertEqual(approved["refunded_paise"], 2)
                lowered = compute_economics(service="bbps", amount_paise=50_000, external_id="101", category="Electricity", retailer_id="pan@payswap.test")
                untouched = compute_economics(service="bbps", amount_paise=50_000, external_id="101", category="Electricity", retailer_id="other@payswap.test")
                today.refresh_from_db()
                old.refresh_from_db()
                settlement.refresh_from_db()
                booked = BbpsTransaction.objects.get(reference="TDSTODAY")
                wallet = get_or_create_wallet("pan@payswap.test")
            finally:
                if previous is None:
                    os.environ.pop("AUTH_DATA_DIR", None)
                else:
                    os.environ["AUTH_DATA_DIR"] = previous
        self.assertEqual(lowered["tds_basis"], "197")
        self.assertEqual(lowered["tds_paise"], 1)
        self.assertEqual(untouched["tds_basis"], "194h")
        self.assertEqual(untouched["tds_paise"], 3)
        self.assertEqual(today.tds_paise, 1)
        self.assertEqual(today.refund_paise, 2)
        self.assertEqual(today.tds_basis, "197")
        self.assertEqual(old.tds_paise, 3)
        self.assertEqual(old.refund_paise, 0)
        self.assertEqual(settlement.tds_paise, 1)
        self.assertEqual(settlement.net_to_retailer_paise, 141)
        self.assertEqual(booked.tds_paise, 1)
        self.assertEqual(booked.commission_paise, 141)
        self.assertEqual(wallet.available_paise, 2)
        with self.assertRaises(ValueError):
            approve_tds_certificate(certificate_id=filed["pending"]["id"], actor="ops@hub.test")
