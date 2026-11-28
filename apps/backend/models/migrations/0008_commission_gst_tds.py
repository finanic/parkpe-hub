from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("hub_models", "0007_bbps_category_entitlements"),
    ]

    operations = [
        migrations.AddField(
            model_name="bbpstransaction",
            name="admin_revenue_paise",
            field=models.BigIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="bbpstransaction",
            name="commission_rate_snapshot",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="bbpstransaction",
            name="gst_paise",
            field=models.BigIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="bbpstransaction",
            name="retailer_commission_paise",
            field=models.BigIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="bbpstransaction",
            name="tds_paise",
            field=models.BigIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="bbpstransaction",
            name="vendor_commission_paise",
            field=models.BigIntegerField(default=0),
        ),
        migrations.CreateModel(
            name="VendorCommissionRate",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("operator_id", models.CharField(db_index=True, max_length=32)),
                ("operator_name", models.CharField(blank=True, default="", max_length=160)),
                ("category", models.CharField(blank=True, db_index=True, default="", max_length=80)),
                ("rate_value", models.DecimalField(decimal_places=6, max_digits=12)),
                ("rate_type", models.CharField(default="flat", max_length=16)),
                ("min_txn_paise", models.BigIntegerField(default=0)),
                ("bbps_enabled", models.BooleanField(default=True)),
                ("effective_from", models.DateField(blank=True, null=True)),
                ("source_file", models.CharField(blank=True, default="", max_length=200)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "constraints": [
                    models.UniqueConstraint(fields=("operator_id", "category"), name="uniq_vendor_commission_op_cat"),
                ],
            },
        ),
        migrations.CreateModel(
            name="CommissionPolicy",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("key", models.CharField(default="payswap_default", max_length=32, unique=True)),
                ("admin_share_bps", models.PositiveIntegerField(default=3000)),
                ("tds_rate_bps", models.PositiveIntegerField(default=200)),
                ("gst_rate_bps", models.PositiveIntegerField(default=1800)),
                ("tds_threshold_paise", models.BigIntegerField(default=2000000)),
                ("withhold_tds_always", models.BooleanField(default=True)),
                ("updated_by", models.CharField(blank=True, default="", max_length=320)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.CreateModel(
            name="RetailerCommissionOverride",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("user_id", models.CharField(max_length=320, unique=True)),
                ("admin_share_bps", models.PositiveIntegerField(blank=True, null=True)),
                ("operator_overrides", models.JSONField(blank=True, default=list)),
                ("active", models.BooleanField(default=True)),
                ("updated_by", models.CharField(blank=True, default="", max_length=320)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.CreateModel(
            name="TdsAccrual",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("accrual_id", models.CharField(max_length=64, unique=True)),
                ("user_id", models.CharField(db_index=True, max_length=320)),
                ("reference", models.CharField(db_index=True, max_length=80)),
                ("month", models.CharField(db_index=True, max_length=7)),
                ("tds_paise", models.BigIntegerField(default=0)),
                ("commission_paise", models.BigIntegerField(default=0)),
                ("status", models.CharField(default="open", max_length=16)),
                ("deposited_at", models.DateTimeField(blank=True, null=True)),
                ("deposited_by", models.CharField(blank=True, default="", max_length=320)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "constraints": [
                    models.UniqueConstraint(fields=("reference",), name="uniq_tds_accrual_reference"),
                ],
            },
        ),
        migrations.CreateModel(
            name="CommissionInvoice",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("invoice_id", models.CharField(max_length=64, unique=True)),
                ("invoice_no", models.CharField(max_length=40, unique=True)),
                ("user_id", models.CharField(db_index=True, max_length=320)),
                ("gstin", models.CharField(blank=True, default="", max_length=20)),
                ("month", models.CharField(db_index=True, max_length=7)),
                ("taxable_paise", models.BigIntegerField(default=0)),
                ("cgst_paise", models.BigIntegerField(default=0)),
                ("sgst_paise", models.BigIntegerField(default=0)),
                ("igst_paise", models.BigIntegerField(default=0)),
                ("total_paise", models.BigIntegerField(default=0)),
                ("lines", models.JSONField(blank=True, default=list)),
                ("status", models.CharField(default="draft", max_length=16)),
                ("created_by", models.CharField(blank=True, default="", max_length=320)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
        ),
        migrations.RunPython(
            code=lambda apps, schema_editor: apps.get_model("hub_models", "CommissionPolicy").objects.get_or_create(
                key="payswap_default",
                defaults={
                    "admin_share_bps": 3000,
                    "tds_rate_bps": 200,
                    "gst_rate_bps": 1800,
                    "tds_threshold_paise": 2_000_000,
                    "withhold_tds_always": True,
                },
            ),
            reverse_code=migrations.RunPython.noop,
        ),
    ]
