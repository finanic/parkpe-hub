from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("hub_models", "0002_hubaction"),
    ]

    operations = [
        migrations.AddField(
            model_name="idempotencyrecord",
            name="desk_state",
            field=models.CharField(blank=True, default="", max_length=20),
        ),
    ]
