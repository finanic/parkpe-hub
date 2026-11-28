from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("hub_models", "0017_bulk_bbps_and_pipes"),
    ]

    operations = [
        migrations.AddField(
            model_name="defaultservicepolicy",
            name="bbps_biller_allowlist",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
