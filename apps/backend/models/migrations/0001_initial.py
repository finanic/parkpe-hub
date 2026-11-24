from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="IdempotencyRecord",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("app_context", models.CharField(max_length=16)),
                ("user_id", models.CharField(max_length=320)),
                ("endpoint", models.CharField(max_length=200)),
                ("idempotency_key", models.CharField(max_length=200)),
                ("payload_hash", models.CharField(max_length=64)),
                ("state", models.CharField(max_length=8)),
                ("status_code", models.PositiveSmallIntegerField(default=0)),
                ("body", models.JSONField(default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "constraints": [
                    models.UniqueConstraint(
                        fields=("app_context", "user_id", "endpoint", "idempotency_key"),
                        name="uniq_idempotency_scope",
                    )
                ],
            },
        ),
    ]
