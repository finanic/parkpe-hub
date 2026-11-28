from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("hub_models", "0016_wallet_adjustment_idempotency"),
    ]

    operations = [
        migrations.AddField(
            model_name="defaultservicepolicy",
            name="bbps_pipe",
            field=models.CharField(default="mobikwik", max_length=32),
        ),
        migrations.AddField(
            model_name="defaultservicepolicy",
            name="bbps_bulk_enabled",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="retailerentitlement",
            name="bbps_pipe",
            field=models.CharField(blank=True, default="", max_length=32),
        ),
        migrations.AddField(
            model_name="retailerentitlement",
            name="bbps_bulk_enabled",
            field=models.BooleanField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="bbpstransaction",
            name="bbps_pipe",
            field=models.CharField(blank=True, default="mobikwik", max_length=32),
        ),
        migrations.AddField(
            model_name="bbpstransaction",
            name="bulk_batch_id",
            field=models.CharField(blank=True, db_index=True, default="", max_length=64),
        ),
        migrations.AddField(
            model_name="bbpstransaction",
            name="bulk_row_id",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
        migrations.CreateModel(
            name="BulkBbpsBatch",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("batch_id", models.CharField(max_length=64, unique=True)),
                ("user_id", models.CharField(db_index=True, max_length=320)),
                ("pipe", models.CharField(default="mobikwik", max_length=32)),
                ("source_filename", models.CharField(blank=True, default="", max_length=200)),
                ("status", models.CharField(db_index=True, default="uploaded", max_length=24)),
                ("row_count", models.PositiveIntegerField(default=0)),
                ("fetch_ok", models.PositiveIntegerField(default=0)),
                ("fetch_fail", models.PositiveIntegerField(default=0)),
                ("pay_ok", models.PositiveIntegerField(default=0)),
                ("pay_fail", models.PositiveIntegerField(default=0)),
                ("pay_skipped", models.PositiveIntegerField(default=0)),
                ("fetch_due_total_paise", models.BigIntegerField(default=0)),
                ("pay_total_paise", models.BigIntegerField(default=0)),
                ("paid_paise", models.BigIntegerField(default=0)),
                ("error_message", models.CharField(blank=True, default="", max_length=240)),
                ("verified_at", models.DateTimeField(blank=True, null=True)),
                ("proceed_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.CreateModel(
            name="BulkBbpsRow",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("row_id", models.CharField(max_length=64, unique=True)),
                ("row_no", models.PositiveIntegerField()),
                ("operator_id", models.CharField(blank=True, default="", max_length=32)),
                ("biller_id", models.CharField(blank=True, default="", max_length=64)),
                ("biller_name", models.CharField(blank=True, default="", max_length=120)),
                ("category", models.CharField(blank=True, default="", max_length=80)),
                ("account", models.CharField(blank=True, default="", max_length=120)),
                ("account_norm", models.CharField(blank=True, default="", max_length=120)),
                ("customer_mobile", models.CharField(blank=True, default="", max_length=20)),
                ("circle", models.CharField(blank=True, default="", max_length=40)),
                ("ad_params", models.JSONField(blank=True, default=dict)),
                ("declared_amount_paise", models.BigIntegerField(default=0)),
                ("fetch_state", models.CharField(db_index=True, default="pending", max_length=24)),
                ("due_amount_paise", models.BigIntegerField(default=0)),
                ("bill_date", models.CharField(blank=True, default="", max_length=40)),
                ("due_date", models.CharField(blank=True, default="", max_length=40)),
                ("bill_number", models.CharField(blank=True, default="", max_length=80)),
                ("customer_name", models.CharField(blank=True, default="", max_length=160)),
                ("fetch_raw", models.JSONField(blank=True, default=dict)),
                ("fetch_error", models.CharField(blank=True, default="", max_length=240)),
                ("fetched_at", models.DateTimeField(blank=True, null=True)),
                ("pay_state", models.CharField(db_index=True, default="blocked", max_length=24)),
                ("pay_amount_paise", models.BigIntegerField(default=0)),
                ("bbps_reference", models.CharField(blank=True, default="", max_length=80)),
                ("pay_error", models.CharField(blank=True, default="", max_length=240)),
                ("paid_at", models.DateTimeField(blank=True, null=True)),
                ("parse_error", models.CharField(blank=True, default="", max_length=240)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "batch",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="rows",
                        to="hub_models.bulkbbpsbatch",
                    ),
                ),
            ],
        ),
        migrations.AddConstraint(
            model_name="bulkbbpsrow",
            constraint=models.UniqueConstraint(fields=("batch", "row_no"), name="uniq_bulk_bbps_batch_row_no"),
        ),
        migrations.AddConstraint(
            model_name="bulkbbpsrow",
            constraint=models.UniqueConstraint(
                fields=("batch", "operator_id", "account_norm"),
                name="uniq_bulk_bbps_batch_op_account",
            ),
        ),
        migrations.AddIndex(
            model_name="bulkbbpsrow",
            index=models.Index(fields=["batch", "fetch_state"], name="hub_models__batch_i_7fbbps_idx"),
        ),
        migrations.AddIndex(
            model_name="bulkbbpsrow",
            index=models.Index(fields=["batch", "pay_state"], name="hub_models__batch_i_8fbbps_idx"),
        ),
    ]
