"""Tests for apps/backend.

Run from the repo root:

  python apps/backend/manage.py test tests

Auth behavior that already runs is apps/backend/tests/test_auth.py.
test_v1.py covers X-App-Context, role scope, validation, and idempotency.
It does not boot apps/backend/auth/server.py.
"""
