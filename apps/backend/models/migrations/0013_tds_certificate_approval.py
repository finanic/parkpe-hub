from django.db import migrations, models


def mark_existing_certificates_approved(apps, schema_editor):
    Certificate = apps.get_model("hub_models", "RetailerTdsCertificate")
    Certificate.objects.filter(active=True).update(status="approved")


def copy_withheld_tds(apps, schema_editor):
    Accrual = apps.get_model("hub_models", "TdsAccrual")
    Accrual.objects.filter(tds_paise_withheld=0).update(tds_paise_withheld=models.F("tds_paise"))


class Migration(migrations.Migration):
    dependencies = [
        ("hub_models", "0012_tds_197_206aa"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="retailertdscertificate",
            name="uniq_retailer_tds_certificate",
        ),
        migrations.AddField(
            model_name="retailertdscertificate",
            name="approved_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="retailertdscertificate",
            name="refunded_paise",
            field=models.BigIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="retailertdscertificate",
            name="reject_reason",
            field=models.CharField(blank=True, default="", max_length=200),
        ),
        migrations.AddField(
            model_name="retailertdscertificate",
            name="status",
            field=models.CharField(default="pending", max_length=16),
        ),
        migrations.AddField(
            model_name="retailertdscertificate",
            name="submitted_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="retailertdscertificate",
            name="active",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="tdsaccrual",
            name="refund_paise",
            field=models.BigIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="tdsaccrual",
            name="tds_paise_withheld",
            field=models.BigIntegerField(default=0),
        ),
        migrations.RunPython(mark_existing_certificates_approved, migrations.RunPython.noop),
        migrations.RunPython(copy_withheld_tds, migrations.RunPython.noop),
    ]
