from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("hub_models", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="HubAction",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("request_id", models.CharField(blank=True, max_length=80)),
                ("idempotency_key", models.CharField(blank=True, max_length=200)),
                ("app_context", models.CharField(blank=True, max_length=16)),
                ("actor", models.CharField(blank=True, max_length=320)),
                ("role", models.CharField(blank=True, max_length=16)),
                ("action", models.CharField(max_length=80)),
                ("target_id", models.CharField(blank=True, max_length=80)),
                ("outcome", models.CharField(max_length=16)),
                ("status", models.PositiveSmallIntegerField(default=0)),
                ("duration_ms", models.PositiveIntegerField(default=0)),
                ("error_code", models.CharField(blank=True, max_length=40)),
                ("error_reason", models.CharField(blank=True, max_length=200)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
        ),
    ]
