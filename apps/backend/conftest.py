"""Pytest fixtures for Django API defensive checks.

Session cookies are mocked via api.v1.deps.fetch_session. External vendors
(Mobikwik, Cashfree, PayU, Kaleyra) stay patched in individual tests.
"""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from core.security import SessionRejected


def _session_for(token: str) -> dict:
    known = {
        "customer-token": {"email": "driver@parkpe.test", "role": "customer"},
        "other-customer": {"email": "other@parkpe.test", "role": "customer"},
        "retailer-token": {"email": "shop@payswap.test", "role": "retailer"},
        "other-retailer": {"email": "other@payswap.test", "role": "retailer"},
        "admin-token": {"email": "ops@hub.test", "role": "admin"},
    }
    if token not in known:
        raise SessionRejected(401, "Sign in again.")
    return known[token]


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def mock_sessions(monkeypatch):
    monkeypatch.setattr("api.v1.deps.fetch_session", _session_for)
    monkeypatch.setattr("api.v1.routes.desk.fetch_session", _session_for)
    return _session_for


@pytest.fixture
def as_retailer(api_client, mock_sessions):
    api_client.cookies["auth_access"] = "retailer-token"
    return api_client


@pytest.fixture
def as_customer(api_client, mock_sessions):
    api_client.cookies["auth_access"] = "customer-token"
    return api_client


@pytest.fixture
def as_admin(api_client, mock_sessions):
    api_client.cookies["auth_access"] = "admin-token"
    return api_client
