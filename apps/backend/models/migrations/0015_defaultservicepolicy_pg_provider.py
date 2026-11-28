from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("hub_models", "0014_retailer_biller_share"),
    ]

    operations = [
        migrations.AddField(
            model_name="defaultservicepolicy",
            name="pg_provider",
            field=models.CharField(default="both", max_length=16),
        ),
    ]
