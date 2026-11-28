from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("hub_models", "0019_bulkbbpsrow_index_rename"),
    ]

    operations = [
        migrations.AddField(
            model_name="bulkbbpsbatch",
            name="operator_id",
            field=models.CharField(blank=True, default="", max_length=32),
        ),
        migrations.AddField(
            model_name="bulkbbpsbatch",
            name="biller_id",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
        migrations.AddField(
            model_name="bulkbbpsbatch",
            name="biller_name",
            field=models.CharField(blank=True, default="", max_length=120),
        ),
        migrations.AddField(
            model_name="bulkbbpsbatch",
            name="category",
            field=models.CharField(blank=True, default="", max_length=80),
        ),
    ]
