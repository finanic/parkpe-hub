"""Hub relational models stored in apps/backend/data/hub.sqlite.

IdempotencyRecord and HubAction back core/idempotency.py and core/actions.py.
Wallet, entitlement, PG, BBPS transaction, and ParkPe vehicle tables live
here beside them; auth users and KYC stay in apps/backend/data/auth.sqlite.
"""

from __future__ import annotations

from django.db import models
from django.db.models import Q


class IdempotencyRecord(models.Model):
    app_context = models.CharField(max_length=16)
    user_id = models.CharField(max_length=320)
    endpoint = models.CharField(max_length=200)
    idempotency_key = models.CharField(max_length=200)
    payload_hash = models.CharField(max_length=64)
    state = models.CharField(max_length=8)
    status_code = models.PositiveSmallIntegerField(default=0)
    body = models.JSONField(default=dict)
    # Desk close writes this. body stays the original 201 payload.
    desk_state = models.CharField(max_length=20, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["app_context", "user_id", "endpoint", "idempotency_key"],
                name="uniq_idempotency_scope",
            )
        ]


class HubAction(models.Model):
    """One redacted core/actions.py line. Not an auth audit row."""

    request_id = models.CharField(max_length=80, blank=True)
    idempotency_key = models.CharField(max_length=200, blank=True)
    app_context = models.CharField(max_length=16, blank=True)
    actor = models.CharField(max_length=320, blank=True)
    role = models.CharField(max_length=16, blank=True)
    action = models.CharField(max_length=80)
    target_id = models.CharField(max_length=80, blank=True)
    outcome = models.CharField(max_length=16)
    status = models.PositiveSmallIntegerField(default=0)
    duration_ms = models.PositiveIntegerField(default=0)
    error_code = models.CharField(max_length=40, blank=True)
    error_reason = models.CharField(max_length=200, blank=True)
    request = models.TextField(blank=True, default="")
    response = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)


class DefaultServicePolicy(models.Model):
    """Default retailer service and payment-rail policy managed by Admin."""

    key = models.CharField(max_length=32, unique=True, default="payswap_default")
    enabled_services = models.JSONField(default=list)
    # Empty list = every BBPS category is allowed. Non-empty = allow-list.
    enabled_bbps_categories = models.JSONField(default=list, blank=True)
    # category_id -> [biller_id, ...]. Missing key = all billers in that category.
    bbps_biller_allowlist = models.JSONField(default=dict, blank=True)
    allow_wallet_pay = models.BooleanField(default=True)
    allow_pg_pay = models.BooleanField(default=True)
    allow_pg_topup = models.BooleanField(default=True)
    # cashfree | payu | both — which PG provider(s) are live for top-up and direct pay.
    pg_provider = models.CharField(max_length=16, default="both")
    # BBPS provider pipe for fetch/pay: mobikwik | pipe_b
    bbps_pipe = models.CharField(max_length=32, default="mobikwik")
    bbps_bulk_enabled = models.BooleanField(default=False)
    default_per_txn_limit_paise = models.BigIntegerField(default=5_000_000)
    default_daily_debit_limit_paise = models.BigIntegerField(default=20_000_000)
    default_min_balance_paise = models.BigIntegerField(default=0)
    updated_by = models.CharField(max_length=320, blank=True, default="")
    updated_at = models.DateTimeField(auto_now=True)


class RetailerEntitlement(models.Model):
    """Per-retailer overrides on top of DefaultServicePolicy."""

    user_id = models.CharField(max_length=320, unique=True)
    service_overrides = models.JSONField(default=dict)
    # category_id -> bool. Missing key inherits default policy allow-list.
    bbps_category_overrides = models.JSONField(default=dict, blank=True)
    allow_wallet_pay = models.BooleanField(null=True, blank=True)
    allow_pg_pay = models.BooleanField(null=True, blank=True)
    allow_pg_topup = models.BooleanField(null=True, blank=True)
    # Empty string = inherit default policy pipe. Otherwise mobikwik | pipe_b.
    bbps_pipe = models.CharField(max_length=32, blank=True, default="")
    bbps_bulk_enabled = models.BooleanField(null=True, blank=True)
    updated_by = models.CharField(max_length=320, blank=True, default="")
    updated_at = models.DateTimeField(auto_now=True)


class WalletAccount(models.Model):
    """Retailer (or system) float account. All values stored in integer paise."""

    app_context = models.CharField(max_length=16, default="payswap")
    user_id = models.CharField(max_length=320)
    role = models.CharField(max_length=16, default="retailer")
    currency = models.CharField(max_length=8, default="INR")
    status = models.CharField(max_length=16, default="active")
    freeze_reason = models.CharField(max_length=200, blank=True, default="")
    available_paise = models.BigIntegerField(default=0)
    held_paise = models.BigIntegerField(default=0)
    per_txn_limit_paise = models.BigIntegerField(default=5_000_000)
    daily_debit_limit_paise = models.BigIntegerField(default=20_000_000)
    min_balance_paise = models.BigIntegerField(default=0)
    wallet_pin_hash = models.CharField(max_length=255, blank=True, default="")
    pin_fails = models.PositiveSmallIntegerField(default=0)
    pin_locked_until = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["app_context", "user_id"],
                name="uniq_wallet_owner",
            ),
            models.CheckConstraint(
                condition=Q(available_paise__gte=0),
                name="chk_wallet_avail_nonneg",
            ),
            models.CheckConstraint(
                condition=Q(held_paise__gte=0),
                name="chk_wallet_held_nonneg",
            ),
        ]


class WalletHold(models.Model):
    """Reserved balance held before an external provider call settles."""

    hold_id = models.CharField(max_length=64, unique=True)
    wallet = models.ForeignKey(WalletAccount, on_delete=models.PROTECT, related_name="holds")
    reference = models.CharField(max_length=80, db_index=True)
    service = models.CharField(max_length=32)
    amount_paise = models.BigIntegerField()
    fee_paise = models.BigIntegerField(default=0)
    status = models.CharField(max_length=16, default="active")
    expires_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class WalletLedgerEntry(models.Model):
    """Append-only double-entry wallet ledger."""

    entry_id = models.CharField(max_length=64, unique=True)
    wallet = models.ForeignKey(WalletAccount, on_delete=models.PROTECT, related_name="ledger_entries")
    direction = models.CharField(max_length=4)
    entry_type = models.CharField(max_length=32)
    amount_paise = models.BigIntegerField()
    balance_before_paise = models.BigIntegerField()
    balance_after_paise = models.BigIntegerField()
    held_before_paise = models.BigIntegerField()
    held_after_paise = models.BigIntegerField()
    reference = models.CharField(max_length=80, db_index=True)
    idempotency_key = models.CharField(max_length=200, blank=True, default="")
    actor = models.CharField(max_length=320, blank=True, default="")
    actor_role = models.CharField(max_length=16, blank=True, default="")
    narration = models.CharField(max_length=200, blank=True, default="")
    meta = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["wallet", "reference", "entry_type"],
                name="uniq_wallet_ref_entry_type",
            ),
            models.UniqueConstraint(
                fields=["wallet", "idempotency_key", "entry_type"],
                condition=~Q(idempotency_key=""),
                name="uniq_ledger_idempotency_entry",
            ),
            models.CheckConstraint(
                condition=Q(amount_paise__gt=0),
                name="chk_ledger_amount_pos",
            ),
        ]


class WalletTopupRequest(models.Model):
    """Retailer bank/UPI float top-up request requiring Admin review."""

    request_id = models.CharField(max_length=64, unique=True)
    wallet = models.ForeignKey(WalletAccount, on_delete=models.PROTECT, related_name="topup_requests")
    user_id = models.CharField(max_length=320, db_index=True)
    amount_paise = models.BigIntegerField()
    mode = models.CharField(max_length=24, default="BANK_TRANSFER")
    utr = models.CharField(max_length=80, unique=True)
    remarks = models.CharField(max_length=200, blank=True, default="")
    status = models.CharField(max_length=16, default="pending")
    reviewed_by = models.CharField(max_length=320, blank=True, default="")
    review_note = models.CharField(max_length=200, blank=True, default="")
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class WalletAdjustment(models.Model):
    """Large desk credit or debit waiting for a second admin."""

    adjustment_id = models.CharField(max_length=64, unique=True)
    user_id = models.CharField(max_length=320, db_index=True)
    direction = models.CharField(max_length=4)
    amount_paise = models.BigIntegerField()
    reason = models.CharField(max_length=200)
    idempotency_key = models.CharField(max_length=200, unique=True)
    status = models.CharField(max_length=16, default="pending")
    requested_by = models.CharField(max_length=320)
    reviewed_by = models.CharField(max_length=320, blank=True, default="")
    review_note = models.CharField(max_length=200, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)


class PgOrder(models.Model):
    """Payment gateway order for wallet_topup or bbps_direct."""

    pg_order_id = models.CharField(max_length=64, unique=True)
    provider = models.CharField(max_length=32, default="cashfree")
    purpose = models.CharField(max_length=24)
    user_id = models.CharField(max_length=320, db_index=True)
    amount_paise = models.BigIntegerField()
    currency = models.CharField(max_length=8, default="INR")
    status = models.CharField(max_length=16, default="created")
    service_ref = models.CharField(max_length=80, blank=True, default="", db_index=True)
    provider_order_id = models.CharField(max_length=120, blank=True, default="")
    provider_payment_id = models.CharField(max_length=120, blank=True, default="")
    payment_session_id = models.CharField(max_length=200, blank=True, default="")
    checkout_url = models.CharField(max_length=400, blank=True, default="")
    signature_verified = models.BooleanField(default=False)
    service_payload = models.JSONField(default=dict)
    meta = models.JSONField(default=dict)
    paid_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class BbpsTransaction(models.Model):
    """Recorded BBPS bill payment backed by a WalletHold or verified PgOrder."""

    reference = models.CharField(max_length=80, unique=True)
    user_id = models.CharField(max_length=320, db_index=True)
    operator_id = models.CharField(max_length=32)
    biller_name = models.CharField(max_length=120)
    category = models.CharField(max_length=80, blank=True, default="")
    account_mask = models.CharField(max_length=80)
    amount_paise = models.BigIntegerField()
    fee_paise = models.BigIntegerField(default=0)
    # Net commission credited to retailer wallet (after TDS). Kept for older serializers.
    commission_paise = models.BigIntegerField(default=0)
    vendor_commission_paise = models.BigIntegerField(default=0)
    admin_revenue_paise = models.BigIntegerField(default=0)
    retailer_commission_paise = models.BigIntegerField(default=0)
    tds_paise = models.BigIntegerField(default=0)
    gst_paise = models.BigIntegerField(default=0)
    commission_rate_snapshot = models.JSONField(default=dict, blank=True)
    payment_channel = models.CharField(max_length=16, default="wallet")
    payment_mode = models.CharField(max_length=32, default="Cash")
    bbps_pipe = models.CharField(max_length=32, blank=True, default="mobikwik")
    bulk_batch_id = models.CharField(max_length=64, blank=True, default="", db_index=True)
    bulk_row_id = models.CharField(max_length=64, blank=True, default="")
    state = models.CharField(max_length=16, default="pending")
    vendor_status = models.CharField(max_length=80, blank=True, default="")
    vendor_txn_id = models.CharField(max_length=80, blank=True, default="")
    error_message = models.CharField(max_length=240, blank=True, default="")
    wallet_hold_id = models.CharField(max_length=64, blank=True, default="")
    pg_order_id = models.CharField(max_length=64, blank=True, default="")
    idempotency_key = models.CharField(max_length=200, blank=True, default="")
    last_checked_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class BulkBbpsBatch(models.Model):
    """Retailer Excel bulk BBPS job: fetch → verify → wallet auto-pay."""

    batch_id = models.CharField(max_length=64, unique=True)
    user_id = models.CharField(max_length=320, db_index=True)
    pipe = models.CharField(max_length=32, default="mobikwik")
    # Locked when retailer picks a biller before download/upload (one biller per batch).
    operator_id = models.CharField(max_length=32, blank=True, default="")
    biller_id = models.CharField(max_length=64, blank=True, default="")
    biller_name = models.CharField(max_length=120, blank=True, default="")
    category = models.CharField(max_length=80, blank=True, default="")
    source_filename = models.CharField(max_length=200, blank=True, default="")
    status = models.CharField(max_length=24, default="uploaded", db_index=True)
    row_count = models.PositiveIntegerField(default=0)
    fetch_ok = models.PositiveIntegerField(default=0)
    fetch_fail = models.PositiveIntegerField(default=0)
    pay_ok = models.PositiveIntegerField(default=0)
    pay_fail = models.PositiveIntegerField(default=0)
    pay_skipped = models.PositiveIntegerField(default=0)
    fetch_due_total_paise = models.BigIntegerField(default=0)
    pay_total_paise = models.BigIntegerField(default=0)
    paid_paise = models.BigIntegerField(default=0)
    error_message = models.CharField(max_length=240, blank=True, default="")
    verified_at = models.DateTimeField(null=True, blank=True)
    proceed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class BulkBbpsRow(models.Model):
    """One Excel line inside a BulkBbpsBatch."""

    row_id = models.CharField(max_length=64, unique=True)
    batch = models.ForeignKey(BulkBbpsBatch, on_delete=models.CASCADE, related_name="rows")
    row_no = models.PositiveIntegerField()
    operator_id = models.CharField(max_length=32, blank=True, default="")
    biller_id = models.CharField(max_length=64, blank=True, default="")
    biller_name = models.CharField(max_length=120, blank=True, default="")
    category = models.CharField(max_length=80, blank=True, default="")
    account = models.CharField(max_length=120, blank=True, default="")
    account_norm = models.CharField(max_length=120, blank=True, default="")
    customer_mobile = models.CharField(max_length=20, blank=True, default="")
    circle = models.CharField(max_length=40, blank=True, default="")
    ad_params = models.JSONField(default=dict, blank=True)
    declared_amount_paise = models.BigIntegerField(default=0)
    fetch_state = models.CharField(max_length=24, default="pending", db_index=True)
    due_amount_paise = models.BigIntegerField(default=0)
    bill_date = models.CharField(max_length=40, blank=True, default="")
    due_date = models.CharField(max_length=40, blank=True, default="")
    bill_number = models.CharField(max_length=80, blank=True, default="")
    customer_name = models.CharField(max_length=160, blank=True, default="")
    fetch_raw = models.JSONField(default=dict, blank=True)
    fetch_error = models.CharField(max_length=240, blank=True, default="")
    fetched_at = models.DateTimeField(null=True, blank=True)
    pay_state = models.CharField(max_length=24, default="blocked", db_index=True)
    pay_amount_paise = models.BigIntegerField(default=0)
    bbps_reference = models.CharField(max_length=80, blank=True, default="")
    pay_error = models.CharField(max_length=240, blank=True, default="")
    paid_at = models.DateTimeField(null=True, blank=True)
    parse_error = models.CharField(max_length=240, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["batch", "row_no"], name="uniq_bulk_bbps_batch_row_no"),
            models.UniqueConstraint(
                fields=["batch", "operator_id", "account_norm"],
                name="uniq_bulk_bbps_batch_op_account",
            ),
        ]
        indexes = [
            models.Index(fields=["batch", "fetch_state"]),
            models.Index(fields=["batch", "pay_state"]),
        ]


class VendorCommissionRate(models.Model):
    """Mobikwik B2B commission row imported from the vendor Excel sheet."""

    operator_id = models.CharField(max_length=32, db_index=True)
    operator_name = models.CharField(max_length=160, blank=True, default="")
    category = models.CharField(max_length=80, blank=True, default="", db_index=True)
    rate_value = models.DecimalField(max_digits=12, decimal_places=6)
    rate_type = models.CharField(max_length=16, default="flat")  # percent | flat
    min_txn_paise = models.BigIntegerField(default=0)
    bbps_enabled = models.BooleanField(default=True)
    effective_from = models.DateField(null=True, blank=True)
    source_file = models.CharField(max_length=200, blank=True, default="")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["operator_id", "category"],
                name="uniq_vendor_commission_op_cat",
            )
        ]


class CommissionPolicy(models.Model):
    """Global commission / TDS / GST defaults for PaySwap retailers."""

    key = models.CharField(max_length=32, unique=True, default="payswap_default")
    admin_share_bps = models.PositiveIntegerField(default=3000)  # 30% of vendor commission
    tds_rate_bps = models.PositiveIntegerField(default=200)  # 2% u/s 194H
    gst_rate_bps = models.PositiveIntegerField(default=1800)  # 18%
    tds_threshold_paise = models.BigIntegerField(default=2_000_000)  # ₹20,000 FY (informational)
    withhold_tds_always = models.BooleanField(default=True)
    # One company TAN for every service. Economics → TDS reads this before a challan can be saved.
    deductor_tan = models.CharField(max_length=10, blank=True, default="")
    # Section 206AA when that retailer's account has no PAN. Statute default is 20%.
    no_pan_tds_rate_bps = models.PositiveIntegerField(default=2000)
    # Stamp for ensure_commission_catalogue() vs apps/backend/data/mobikwik/commission-b2b.xlsx.
    rates_file_mtime = models.FloatField(default=0)
    rates_imported_at = models.DateTimeField(null=True, blank=True)
    updated_by = models.CharField(max_length=320, blank=True, default="")
    updated_at = models.DateTimeField(auto_now=True)


class RetailerCommissionOverride(models.Model):
    """Per-retailer share and/or operator rate overrides on top of VendorCommissionRate."""

    user_id = models.CharField(max_length=320, unique=True)
    admin_share_bps = models.PositiveIntegerField(null=True, blank=True)
    # [{operator_id, category, rate_value, rate_type, min_txn_paise}]
    operator_overrides = models.JSONField(default=list, blank=True)
    active = models.BooleanField(default=True)
    updated_by = models.CharField(max_length=320, blank=True, default="")
    updated_at = models.DateTimeField(auto_now=True)


class TdsAccrual(models.Model):
    """Per-transaction TDS withheld on retailer commission (Section 194H)."""

    accrual_id = models.CharField(max_length=64, unique=True)
    user_id = models.CharField(max_length=320, db_index=True)
    service = models.CharField(max_length=32, default="bbps", db_index=True)
    reference = models.CharField(max_length=80, db_index=True)
    month = models.CharField(max_length=7, db_index=True)  # YYYY-MM
    tds_paise = models.BigIntegerField(default=0)
    tds_paise_withheld = models.BigIntegerField(default=0)
    refund_paise = models.BigIntegerField(default=0)
    commission_paise = models.BigIntegerField(default=0)
    tds_rate_bps = models.PositiveIntegerField(default=0)
    tds_basis = models.CharField(max_length=16, default="194h")  # 194h | 197 | 206aa
    status = models.CharField(max_length=16, default="open")  # open | deposited
    deposited_at = models.DateTimeField(null=True, blank=True)
    deposited_by = models.CharField(max_length=320, blank=True, default="")
    # The challan that covered this row. Amount is the challan total, not this row's share.
    challan_bsr = models.CharField(max_length=7, blank=True, default="")
    challan_serial = models.CharField(max_length=10, blank=True, default="")
    challan_on = models.DateField(null=True, blank=True)
    challan_amount_paise = models.BigIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["service", "reference"], name="uniq_tds_accrual_service_ref"),
        ]


class CommissionInvoice(models.Model):
    """Monthly draft GST invoice for a GSTIN retailer’s accrued commission (all services)."""

    invoice_id = models.CharField(max_length=64, unique=True)
    invoice_no = models.CharField(max_length=40, unique=True)
    user_id = models.CharField(max_length=320, db_index=True)
    gstin = models.CharField(max_length=20, blank=True, default="")
    month = models.CharField(max_length=7, db_index=True)
    taxable_paise = models.BigIntegerField(default=0)
    cgst_paise = models.BigIntegerField(default=0)
    sgst_paise = models.BigIntegerField(default=0)
    igst_paise = models.BigIntegerField(default=0)
    total_paise = models.BigIntegerField(default=0)
    lines = models.JSONField(default=list, blank=True)  # includes service per line
    status = models.CharField(max_length=16, default="draft")  # draft | issued
    created_by = models.CharField(max_length=320, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)


class ServiceEconomicsPolicy(models.Model):
    """Per-service monetization + TDS/GST defaults (bbps, aeps, dmt, …)."""

    service = models.CharField(max_length=32, unique=True)
    monetization_mode = models.CharField(max_length=32, default="vendor_share")  # vendor_share | service_charge
    admin_share_bps = models.PositiveIntegerField(default=3000)
    tds_rate_bps = models.PositiveIntegerField(default=200)
    gst_rate_bps = models.PositiveIntegerField(default=1800)
    tds_threshold_paise = models.BigIntegerField(default=2_000_000)
    withhold_tds_always = models.BooleanField(default=True)
    rates_file_mtime = models.FloatField(default=0)
    rates_imported_at = models.DateTimeField(null=True, blank=True)
    active = models.BooleanField(default=True)
    updated_by = models.CharField(max_length=320, blank=True, default="")
    updated_at = models.DateTimeField(auto_now=True)


class ServiceRateRow(models.Model):
    """Generic vendor-share rate catalogue row (one sheet per service)."""

    service = models.CharField(max_length=32, db_index=True)
    external_id = models.CharField(max_length=64, db_index=True)  # op / bank / corridor
    category = models.CharField(max_length=80, blank=True, default="", db_index=True)
    name = models.CharField(max_length=160, blank=True, default="")
    rate_value = models.DecimalField(max_digits=12, decimal_places=6)
    rate_type = models.CharField(max_length=16, default="flat")  # percent | flat
    min_txn_paise = models.BigIntegerField(default=0)
    enabled = models.BooleanField(default=True)
    meta = models.JSONField(default=dict, blank=True)
    source_file = models.CharField(max_length=200, blank=True, default="")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["service", "external_id", "category"],
                name="uniq_service_rate_row",
            )
        ]


class ServiceFeeRule(models.Model):
    """Service-charge mode fee rule (charged to wallet/customer)."""

    service = models.CharField(max_length=32, db_index=True)
    match_key = models.CharField(max_length=64, blank=True, default="")  # external id or *
    category = models.CharField(max_length=80, blank=True, default="")
    fee_type = models.CharField(max_length=16, default="flat")  # percent | flat
    fee_value = models.DecimalField(max_digits=12, decimal_places=6, default=0)
    min_fee_paise = models.BigIntegerField(default=0)
    max_fee_paise = models.BigIntegerField(default=0)  # 0 = no cap
    who_pays = models.CharField(max_length=16, default="wallet")  # wallet | customer
    admin_retain_bps = models.PositiveIntegerField(default=10000)  # share of fee kept by admin
    active = models.BooleanField(default=True)
    updated_by = models.CharField(max_length=320, blank=True, default="")
    updated_at = models.DateTimeField(auto_now=True)


class RetailerTdsCertificate(models.Model):
    """Section 197 request. Rate applies only after admin approval, and only for that retailer."""

    user_id = models.CharField(max_length=320, db_index=True)
    section = models.CharField(max_length=8, default="194H")
    certificate_no = models.CharField(max_length=40, blank=True, default="")
    rate_bps = models.PositiveIntegerField(default=0)
    valid_from = models.DateField(null=True, blank=True)
    valid_to = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=16, default="pending")  # pending | approved | rejected
    active = models.BooleanField(default=False)
    reject_reason = models.CharField(max_length=200, blank=True, default="")
    refunded_paise = models.BigIntegerField(default=0)
    submitted_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    updated_by = models.CharField(max_length=320, blank=True, default="")
    updated_at = models.DateTimeField(auto_now=True)


class RetailerServiceOverride(models.Model):
    """Per-retailer economics override for one service."""

    user_id = models.CharField(max_length=320, db_index=True)
    service = models.CharField(max_length=32, db_index=True)
    admin_share_bps = models.PositiveIntegerField(null=True, blank=True)
    # [{external_id, category, rate_value, rate_type, min_txn_paise}]
    rate_overrides = models.JSONField(default=list, blank=True)
    # [{external_id, category, admin_share_bps}] — this retailer's split on one sheet row.
    share_overrides = models.JSONField(default=list, blank=True)
    active = models.BooleanField(default=True)
    updated_by = models.CharField(max_length=320, blank=True, default="")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user_id", "service"], name="uniq_retailer_service_override"),
        ]


class ServiceSettlement(models.Model):
    """One money outcome per successful product txn (any PaySwap service)."""

    settlement_id = models.CharField(max_length=64, unique=True)
    service = models.CharField(max_length=32, db_index=True)
    reference = models.CharField(max_length=80, db_index=True)
    user_id = models.CharField(max_length=320, db_index=True)
    amount_paise = models.BigIntegerField(default=0)
    vendor_commission_paise = models.BigIntegerField(default=0)
    admin_revenue_paise = models.BigIntegerField(default=0)
    retailer_commission_paise = models.BigIntegerField(default=0)
    service_charge_paise = models.BigIntegerField(default=0)
    tds_paise = models.BigIntegerField(default=0)
    gst_paise = models.BigIntegerField(default=0)
    net_to_retailer_paise = models.BigIntegerField(default=0)
    rate_snapshot = models.JSONField(default=dict, blank=True)
    state = models.CharField(max_length=16, default="settled")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["service", "reference"], name="uniq_service_settlement_ref"),
        ]


class CustomerVehicle(models.Model):
    """Saved ParkPe customer vehicles (replaces hardcoded sample vehicles)."""

    vehicle_id = models.CharField(max_length=64, unique=True)
    user_id = models.CharField(max_length=320, db_index=True)
    registration = models.CharField(max_length=20)
    make_model = models.CharField(max_length=80, blank=True, default="")
    color = models.CharField(max_length=40, blank=True, default="")
    fastag_linked = models.BooleanField(default=False)
    is_primary = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user_id", "registration"],
                name="uniq_customer_vehicle",
            )
        ]
