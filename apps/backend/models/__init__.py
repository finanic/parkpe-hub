"""Persistence shapes for domain/common, domain/parkpe, and domain/payswap.

The database that exists today is apps/backend/auth/store.py
(apps/backend/data/auth.sqlite). That file is local and gitignored.
Do not open it from a feature module to bypass the store.

IdempotencyRecord lives in models/models.py so this package can load
before the app registry is ready. It uses apps/backend/data/hub.sqlite
(models/apps.py), not auth.sqlite. core/idempotency.py is the only writer.
"""
