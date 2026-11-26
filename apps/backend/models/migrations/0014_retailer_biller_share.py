from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("hub_models", "0013_tds_certificate_approval"),
    ]

    operations = [
        migrations.AddField(
            model_name="retailerserviceoverride",
            name="share_overrides",
            field=models.JSONField(blank=True, default=list),
        ),
    ]
