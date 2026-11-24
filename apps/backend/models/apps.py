"""Django app for hub.sqlite. Not the auth database.

apps/backend/auth/store.py keeps users and sessions in apps/backend/data/auth.sqlite.
This app stores idempotency rows for /api/v1 money writes only.
"""

from django.apps import AppConfig


class HubModelsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "models"
    label = "hub_models"
