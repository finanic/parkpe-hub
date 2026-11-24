"""One stored response for a mutating /api/v1 call.

Written by core/idempotency.py. The unique row is
(app_context, user_id, endpoint, idempotency_key). user_id is the email
from GET /api/auth/me (apps/backend/auth/server.py); that payload has no
separate account id. A second caller, a second endpoint, or a second app
does not reuse this row.

The table is apps/backend/data/hub.sqlite, not apps/backend/data/auth.sqlite.
"""

from django.db import models


class IdempotencyRecord(models.Model):
    app_context = models.CharField(max_length=16)
    user_id = models.CharField(max_length=320)
    endpoint = models.CharField(max_length=200)
    idempotency_key = models.CharField(max_length=200)
    payload_hash = models.CharField(max_length=64)
    state = models.CharField(max_length=8)
    status_code = models.PositiveSmallIntegerField(default=0)
    body = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["app_context", "user_id", "endpoint", "idempotency_key"],
                name="uniq_idempotency_scope",
            )
        ]
