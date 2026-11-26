from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("hub_models", "0008_commission_gst_tds"),
    ]

    operations = [
        migrations.AddField(
            model_name="commissionpolicy",
            name="rates_file_mtime",
            field=models.FloatField(default=0),
        ),
        migrations.AddField(
            model_name="commissionpolicy",
            name="rates_imported_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
