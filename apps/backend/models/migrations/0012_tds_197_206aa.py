from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("hub_models", "0011_tds_deposit_pack"),
    ]

    operations = [
        migrations.AddField(
            model_name="commissionpolicy",
            name="no_pan_tds_rate_bps",
            field=models.PositiveIntegerField(default=2000),
        ),
        migrations.AddField(
            model_name="tdsaccrual",
            name="tds_basis",
            field=models.CharField(default="194h", max_length=16),
        ),
        migrations.AddField(
            model_name="tdsaccrual",
            name="tds_rate_bps",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.CreateModel(
            name="RetailerTdsCertificate",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("user_id", models.CharField(db_index=True, max_length=320)),
                ("section", models.CharField(default="194H", max_length=8)),
                ("certificate_no", models.CharField(blank=True, default="", max_length=40)),
                ("rate_bps", models.PositiveIntegerField(default=0)),
                ("valid_from", models.DateField(blank=True, null=True)),
                ("valid_to", models.DateField(blank=True, null=True)),
                ("active", models.BooleanField(default=True)),
                ("updated_by", models.CharField(blank=True, default="", max_length=320)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "constraints": [
                    models.UniqueConstraint(fields=("user_id", "section"), name="uniq_retailer_tds_certificate"),
                ],
            },
        ),
    ]
