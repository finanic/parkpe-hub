"""Django app for hub.sqlite. Not the auth database.

apps/backend/auth/store.py keeps users and sessions in apps/backend/data/auth.sqlite.
This app stores idempotency rows and the redacted action lines for /api/v1.

After migrate, Mobikwik commission-b2b.xlsx is ensured into VendorCommissionRate
when empty or newer than the last import stamp (skipped under manage.py test).
Runtime refresh also runs from ensure_commission_catalogue on settle/list_rates.
"""

from django.apps import AppConfig
from django.db.models.signals import post_migrate


def _ensure_commission_after_migrate(sender, **kwargs):
    import sys

    if "test" in sys.argv:
        return
    try:
        from django.db.utils import OperationalError, ProgrammingError
        from domain.payswap.economics.catalogue import ensure_catalogue

        ensure_catalogue(service="bbps", actor="post_migrate")
    except (OperationalError, ProgrammingError, ImportError):
        pass


class HubModelsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "models"
    label = "hub_models"

    def ready(self):
        post_migrate.connect(_ensure_commission_after_migrate, sender=self)
