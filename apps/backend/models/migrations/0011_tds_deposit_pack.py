from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("hub_models", "0010_service_economics_spine"),
    ]

    operations = [
        migrations.AddField(
            model_name="commissionpolicy",
            name="deductor_tan",
            field=models.CharField(blank=True, default="", max_length=10),
        ),
        migrations.AddField(
            model_name="tdsaccrual",
            name="challan_amount_paise",
            field=models.BigIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="tdsaccrual",
            name="challan_bsr",
            field=models.CharField(blank=True, default="", max_length=7),
        ),
        migrations.AddField(
            model_name="tdsaccrual",
            name="challan_on",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="tdsaccrual",
            name="challan_serial",
            field=models.CharField(blank=True, default="", max_length=10),
        ),
    ]
