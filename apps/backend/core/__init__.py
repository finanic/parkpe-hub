"""Cross-cutting helpers for the unified API.

security.py: app-scope checks for this process.
idempotency.py: safe retry for money movement.
Password hashing and session tokens stay in apps/backend/auth/security.py.
"""
