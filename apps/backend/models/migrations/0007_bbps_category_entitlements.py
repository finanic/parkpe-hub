from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("hub_models", "0006_backfill_legacy_bbps"),
    ]

    operations = [
        migrations.AddField(
            model_name="defaultservicepolicy",
            name="enabled_bbps_categories",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="retailerentitlement",
            name="bbps_category_overrides",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
