from django.db import migrations, models


def forwards_seed(apps, schema_editor):
    CommissionPolicy = apps.get_model("hub_models", "CommissionPolicy")
    VendorCommissionRate = apps.get_model("hub_models", "VendorCommissionRate")
    ServiceEconomicsPolicy = apps.get_model("hub_models", "ServiceEconomicsPolicy")
    ServiceRateRow = apps.get_model("hub_models", "ServiceRateRow")
    RetailerCommissionOverride = apps.get_model("hub_models", "RetailerCommissionOverride")
    RetailerServiceOverride = apps.get_model("hub_models", "RetailerServiceOverride")
    TdsAccrual = apps.get_model("hub_models", "TdsAccrual")

    legacy = CommissionPolicy.objects.filter(key="payswap_default").first()
    defaults = {
        "monetization_mode": "vendor_share",
        "admin_share_bps": int(legacy.admin_share_bps) if legacy else 3000,
        "tds_rate_bps": int(legacy.tds_rate_bps) if legacy else 200,
        "gst_rate_bps": int(legacy.gst_rate_bps) if legacy else 1800,
        "tds_threshold_paise": int(legacy.tds_threshold_paise) if legacy else 2_000_000,
        "withhold_tds_always": bool(legacy.withhold_tds_always) if legacy else True,
        "rates_file_mtime": float(legacy.rates_file_mtime) if legacy else 0,
        "rates_imported_at": legacy.rates_imported_at if legacy else None,
        "active": True,
        "updated_by": (legacy.updated_by if legacy else "") or "migration",
    }
    ServiceEconomicsPolicy.objects.update_or_create(service="bbps", defaults=defaults)
    for svc in ("aeps", "dmt", "recharge", "vouchers"):
        mode = "service_charge" if svc == "vouchers" else "vendor_share"
        ServiceEconomicsPolicy.objects.get_or_create(
            service=svc,
            defaults={
                "monetization_mode": mode,
                "admin_share_bps": 3000,
                "tds_rate_bps": 200,
                "gst_rate_bps": 1800,
                "tds_threshold_paise": 2_000_000,
                "withhold_tds_always": True,
                "active": True,
                "updated_by": "migration",
            },
        )

    for row in VendorCommissionRate.objects.all().iterator():
        ServiceRateRow.objects.update_or_create(
            service="bbps",
            external_id=row.operator_id,
            category=row.category,
            defaults={
                "name": row.operator_name,
                "rate_value": row.rate_value,
                "rate_type": row.rate_type,
                "min_txn_paise": row.min_txn_paise,
                "enabled": bool(row.bbps_enabled),
                "meta": {},
                "source_file": row.source_file,
            },
        )

    for row in RetailerCommissionOverride.objects.all():
        overrides = []
        for item in row.operator_overrides or []:
            if not isinstance(item, dict):
                continue
            overrides.append(
                {
                    "external_id": str(item.get("operator_id") or item.get("external_id") or ""),
                    "category": str(item.get("category") or ""),
                    "rate_value": str(item.get("rate_value") or "0"),
                    "rate_type": str(item.get("rate_type") or "flat"),
                    "min_txn_paise": int(item.get("min_txn_paise") or 0),
                }
            )
        RetailerServiceOverride.objects.update_or_create(
            user_id=row.user_id,
            service="bbps",
            defaults={
                "admin_share_bps": row.admin_share_bps,
                "rate_overrides": overrides,
                "active": bool(row.active),
                "updated_by": row.updated_by or "",
            },
        )

    TdsAccrual.objects.filter(service="").update(service="bbps")


def backwards_noop(apps, schema_editor):
    """Data forward-fill cannot be reversed safely; keep schema reverse only."""
    return None


class Migration(migrations.Migration):

    dependencies = [
        ("hub_models", "0009_commission_auto_stamp"),
    ]

    operations = [
        migrations.CreateModel(
            name="ServiceEconomicsPolicy",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("service", models.CharField(max_length=32, unique=True)),
                ("monetization_mode", models.CharField(default="vendor_share", max_length=32)),
                ("admin_share_bps", models.PositiveIntegerField(default=3000)),
                ("tds_rate_bps", models.PositiveIntegerField(default=200)),
                ("gst_rate_bps", models.PositiveIntegerField(default=1800)),
                ("tds_threshold_paise", models.BigIntegerField(default=2000000)),
                ("withhold_tds_always", models.BooleanField(default=True)),
                ("rates_file_mtime", models.FloatField(default=0)),
                ("rates_imported_at", models.DateTimeField(blank=True, null=True)),
                ("active", models.BooleanField(default=True)),
                ("updated_by", models.CharField(blank=True, default="", max_length=320)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.CreateModel(
            name="ServiceRateRow",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("service", models.CharField(db_index=True, max_length=32)),
                ("external_id", models.CharField(db_index=True, max_length=64)),
                ("category", models.CharField(blank=True, db_index=True, default="", max_length=80)),
                ("name", models.CharField(blank=True, default="", max_length=160)),
                ("rate_value", models.DecimalField(decimal_places=6, max_digits=12)),
                ("rate_type", models.CharField(default="flat", max_length=16)),
                ("min_txn_paise", models.BigIntegerField(default=0)),
                ("enabled", models.BooleanField(default=True)),
                ("meta", models.JSONField(blank=True, default=dict)),
                ("source_file", models.CharField(blank=True, default="", max_length=200)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "constraints": [
                    models.UniqueConstraint(fields=("service", "external_id", "category"), name="uniq_service_rate_row"),
                ],
            },
        ),
        migrations.CreateModel(
            name="ServiceFeeRule",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("service", models.CharField(db_index=True, max_length=32)),
                ("match_key", models.CharField(blank=True, default="", max_length=64)),
                ("category", models.CharField(blank=True, default="", max_length=80)),
                ("fee_type", models.CharField(default="flat", max_length=16)),
                ("fee_value", models.DecimalField(decimal_places=6, default=0, max_digits=12)),
                ("min_fee_paise", models.BigIntegerField(default=0)),
                ("max_fee_paise", models.BigIntegerField(default=0)),
                ("who_pays", models.CharField(default="wallet", max_length=16)),
                ("admin_retain_bps", models.PositiveIntegerField(default=10000)),
                ("active", models.BooleanField(default=True)),
                ("updated_by", models.CharField(blank=True, default="", max_length=320)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.CreateModel(
            name="RetailerServiceOverride",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("user_id", models.CharField(db_index=True, max_length=320)),
                ("service", models.CharField(db_index=True, max_length=32)),
                ("admin_share_bps", models.PositiveIntegerField(blank=True, null=True)),
                ("rate_overrides", models.JSONField(blank=True, default=list)),
                ("active", models.BooleanField(default=True)),
                ("updated_by", models.CharField(blank=True, default="", max_length=320)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "constraints": [
                    models.UniqueConstraint(fields=("user_id", "service"), name="uniq_retailer_service_override"),
                ],
            },
        ),
        migrations.CreateModel(
            name="ServiceSettlement",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("settlement_id", models.CharField(max_length=64, unique=True)),
                ("service", models.CharField(db_index=True, max_length=32)),
                ("reference", models.CharField(db_index=True, max_length=80)),
                ("user_id", models.CharField(db_index=True, max_length=320)),
                ("amount_paise", models.BigIntegerField(default=0)),
                ("vendor_commission_paise", models.BigIntegerField(default=0)),
                ("admin_revenue_paise", models.BigIntegerField(default=0)),
                ("retailer_commission_paise", models.BigIntegerField(default=0)),
                ("service_charge_paise", models.BigIntegerField(default=0)),
                ("tds_paise", models.BigIntegerField(default=0)),
                ("gst_paise", models.BigIntegerField(default=0)),
                ("net_to_retailer_paise", models.BigIntegerField(default=0)),
                ("rate_snapshot", models.JSONField(blank=True, default=dict)),
                ("state", models.CharField(default="settled", max_length=16)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "constraints": [
                    models.UniqueConstraint(fields=("service", "reference"), name="uniq_service_settlement_ref"),
                ],
            },
        ),
        migrations.AddField(
            model_name="tdsaccrual",
            name="service",
            field=models.CharField(db_index=True, default="bbps", max_length=32),
        ),
        migrations.RemoveConstraint(
            model_name="tdsaccrual",
            name="uniq_tds_accrual_reference",
        ),
        migrations.AddConstraint(
            model_name="tdsaccrual",
            constraint=models.UniqueConstraint(fields=("service", "reference"), name="uniq_tds_accrual_service_ref"),
        ),
        migrations.RunPython(forwards_seed, backwards_noop),
    ]
