"""Multi-service economics spine: ServiceSettlement, fee mode, BBPS dual-write."""

from __future__ import annotations

from decimal import Decimal

from django.test import TestCase

from domain.payswap.economics.policy import get_or_create_service_policy, update_service_policy
from domain.payswap.economics.settle import settle_success
from domain.payswap.economics.split import compute_economics
from domain.payswap.wallet import apply_fee_debit, get_or_create_wallet
from models.models import (
    BbpsTransaction,
    ServiceFeeRule,
    ServiceRateRow,
    ServiceSettlement,
    TdsAccrual,
    WalletLedgerEntry,
)


class EconomicsVendorShareTests(TestCase):
    def setUp(self):
        get_or_create_service_policy("bbps")
        ServiceRateRow.objects.create(
            service="bbps",
            external_id="101",
            category="Electricity",
            name="Sample Electricity",
            rate_value=Decimal("2.025"),
            rate_type="flat",
            min_txn_paise=0,
            enabled=True,
        )

    def test_update_rate_row_edits_catalogue(self):
        from domain.payswap.economics.catalogue import update_rate_row
        from models.models import VendorCommissionRate

        out = update_rate_row(
            service="bbps",
            external_id="101",
            category="Electricity",
            rate_value="3.5",
            rate_type="flat",
            min_txn="10",
            enabled=True,
            actor="test",
        )
        self.assertEqual(Decimal(out["rate_value"]), Decimal("3.5"))
        self.assertEqual(out["min_txn_paise"], 1000)
        row = ServiceRateRow.objects.get(service="bbps", external_id="101", category="Electricity")
        self.assertEqual(row.rate_value, Decimal("3.5"))
        mirror = VendorCommissionRate.objects.get(operator_id="101", category="Electricity")
        self.assertEqual(mirror.rate_value, Decimal("3.5"))

    def test_vendor_discount_is_split_even_when_the_sheet_rate_is_off(self):
        ServiceRateRow.objects.filter(external_id="101").update(enabled=False, min_txn_paise=5000)
        out = compute_economics(
            service="bbps",
            amount_paise=1000,
            external_id="101",
            category="Electricity",
            retailer_id="shop@payswap.test",
            vendor_paise=5,
        )
        self.assertEqual(out["vendor_commission_paise"], 5)
        self.assertEqual(out["admin_revenue_paise"], 2)
        self.assertEqual(out["retailer_commission_paise"], 3)
        self.assertEqual(out["net_to_retailer_paise"], 3)
        self.assertEqual(out["rate_source"], "vendor_discount")
        missed = compute_economics(
            service="bbps",
            amount_paise=1000,
            external_id="101",
            category="Electricity",
            retailer_id="shop@payswap.test",
        )
        self.assertEqual(missed["vendor_commission_paise"], 0)

    def test_settle_success_writes_settlement_and_dual_writes_bbps(self):
        tx = BbpsTransaction.objects.create(
            reference="TECON001",
            user_id="shop@payswap.test",
            operator_id="101",
            biller_name="Sample Electricity",
            category="Electricity",
            account_mask="****1",
            amount_paise=50_000,
            state="success",
            payment_channel="wallet",
        )
        out = settle_success(
            service="bbps",
            reference=tx.reference,
            user_id=tx.user_id,
            amount_paise=int(tx.amount_paise),
            external_id=tx.operator_id,
            category=tx.category,
            has_gstin=False,
            bbps_tx=tx,
        )
        self.assertTrue(out["applied"])
        self.assertEqual(out["vendor_commission_paise"], 203)
        self.assertEqual(out["net_to_retailer_paise"], 139)
        stl = ServiceSettlement.objects.get(service="bbps", reference="TECON001")
        self.assertEqual(stl.net_to_retailer_paise, 139)
        tx.refresh_from_db()
        self.assertEqual(tx.commission_paise, 139)
        self.assertEqual(TdsAccrual.objects.get(service="bbps", reference="TECON001").tds_paise, 3)


class EconomicsServiceChargeTests(TestCase):
    def setUp(self):
        update_service_policy("vouchers", monetization_mode="service_charge", admin_share_bps=0, actor="test")
        # 100% of fee retained by admin in this fixture (retailer share 0 of fee).
        ServiceFeeRule.objects.create(
            service="vouchers",
            match_key="*",
            fee_type="flat",
            fee_value=Decimal("10"),
            admin_retain_bps=10000,
            who_pays="wallet",
            active=True,
        )
        get_or_create_wallet("shop@payswap.test")
        from domain.payswap.wallet import admin_adjust_wallet

        admin_adjust_wallet(
            "shop@payswap.test",
            direction="CR",
            amount_paise=50_000,
            admin_email="ops@hub.test",
            reason="seed float for fee test",
        )

    def test_fee_mode_and_fee_dr_ledger(self):
        split = compute_economics(
            service="vouchers",
            amount_paise=10_000,
            external_id="brand-x",
            has_gstin=False,
        )
        self.assertEqual(split["monetization_mode"], "service_charge")
        self.assertEqual(split["service_charge_paise"], 1000)  # ₹10
        self.assertEqual(split["admin_revenue_paise"], 1000)
        self.assertEqual(split["retailer_commission_paise"], 0)
        self.assertEqual(split["net_to_retailer_paise"], 0)

        out = settle_success(
            service="vouchers",
            reference="VCH-FEE-1",
            user_id="shop@payswap.test",
            amount_paise=10_000,
            external_id="brand-x",
            has_gstin=False,
        )
        self.assertTrue(out["applied"])
        apply_fee_debit(
            "shop@payswap.test",
            amount_paise=out["fee_paise"],
            reference="VCH-FEE-1",
            service="vouchers",
        )
        entry = WalletLedgerEntry.objects.get(reference="VCH-FEE-1", entry_type="FEE_DR")
        self.assertEqual(entry.amount_paise, 1000)
        self.assertEqual(entry.direction, "DR")


class SettlementSetViewTests(TestCase):
    def test_sheet_rate_and_discount_price_stay_distinct(self):
        from domain.payswap.economics.invoices import settlement_set_view

        sheet = settlement_set_view(
            {"rate": {"rate_value": "0.531", "rate_type": "percent", "source": "sheet"}, "admin_share_bps": 3000}
        )
        self.assertEqual(sheet["set_label"], "0.531%")
        self.assertEqual(sheet["set_share"], "30%")
        discount = settlement_set_view(
            {"rate": {"rate_value": "0", "source": "vendor_discount"}, "admin_share_bps": 3000}
        )
        self.assertEqual(discount["set_label"], "Discount price")
        self.assertEqual(discount["set_share"], "30%")
