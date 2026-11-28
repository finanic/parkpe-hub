from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):
    dependencies = [
        ("hub_models", "0015_defaultservicepolicy_pg_provider"),
    ]

    operations = [
        migrations.CreateModel(
            name="WalletAdjustment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("adjustment_id", models.CharField(max_length=64, unique=True)),
                ("user_id", models.CharField(db_index=True, max_length=320)),
                ("direction", models.CharField(max_length=4)),
                ("amount_paise", models.BigIntegerField()),
                ("reason", models.CharField(max_length=200)),
                ("idempotency_key", models.CharField(max_length=200, unique=True)),
                ("status", models.CharField(default="pending", max_length=16)),
                ("requested_by", models.CharField(max_length=320)),
                ("reviewed_by", models.CharField(blank=True, default="", max_length=320)),
                ("review_note", models.CharField(blank=True, default="", max_length=200)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("reviewed_at", models.DateTimeField(blank=True, null=True)),
            ],
        ),
        migrations.AddConstraint(
            model_name="walletledgerentry",
            constraint=models.UniqueConstraint(
                condition=~Q(idempotency_key=""),
                fields=("wallet", "idempotency_key", "entry_type"),
                name="uniq_ledger_idempotency_entry",
            ),
        ),
    ]
