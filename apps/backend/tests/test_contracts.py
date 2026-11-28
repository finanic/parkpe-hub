"""Shared contract vs Django mount and serializer surface.

packages/contracts/index.js is the browser/sdk list. This file checks the
Django process still mounts those HubPath strings and keeps the shared
error-code spellings.
"""

from __future__ import annotations

import re
from pathlib import Path

from django.test import SimpleTestCase, TestCase
from django.urls import get_resolver
from rest_framework.test import APIClient


ROOT = Path(__file__).resolve().parents[3]
CONTRACTS = (ROOT / "packages" / "contracts" / "index.js").read_text(encoding="utf-8")


def _frozen_object(name: str) -> dict[str, str]:
    match = re.search(rf"export const {name} = Object\.freeze\(\{{(.*?)\}}\);", CONTRACTS, re.S)
    if not match:
        raise AssertionError(f"missing Object.freeze for {name}")
    return dict(re.findall(r'([A-Z0-9_]+):\s*"([^"]+)"', match.group(1)))


class ContractMountTests(SimpleTestCase):
    def test_hub_paths_are_mounted_on_django(self):
        paths = _frozen_object("HubPath")
        self.assertGreaterEqual(len(paths), 10)
        resolver = get_resolver()
        for key, path in paths.items():
            match = resolver.resolve(path if path.startswith("/") else f"/{path}")
            self.assertTrue(match, f"{key} {path} is not mounted")

    def test_error_codes_are_the_shared_spellings(self):
        codes = set(_frozen_object("ErrorCode").values())
        required = {
            "unauthenticated",
            "forbidden_app",
            "validation",
            "idempotency_conflict",
            "server_error",
            "service_disabled",
        }
        self.assertTrue(required.issubset(codes))

    def test_payment_rail_matches_the_bbps_serializer(self):
        from schemas.serializers import BbpsPaymentSerializer

        rails = set(_frozen_object("PaymentRail").values())
        field = BbpsPaymentSerializer().fields["payment_rail"]
        choices = set(field.choices)
        self.assertEqual(rails, choices)

    def test_app_copies_of_contracts_match_the_package(self):
        for rel in (
            "apps/parkpe/packages/contracts/index.js",
            "apps/payswap/packages/contracts/index.js",
        ):
            copy = (ROOT / rel).read_text(encoding="utf-8")
            self.assertEqual(copy, CONTRACTS, rel)


class ContractResponseShapeTests(TestCase):
    def test_health_and_unauth_errors_use_the_shared_shape(self):
        client = APIClient()
        health = client.get("/api/v1/health/")
        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.json(), {"ok": True})

        wallet = client.get("/api/v1/payswap/wallet", HTTP_X_APP_CONTEXT="payswap")
        self.assertEqual(wallet.status_code, 401)
        body = wallet.json()
        self.assertEqual(set(body.keys()), {"error", "code"})
        self.assertEqual(body["code"], "unauthenticated")
        self.assertIsInstance(body["error"], str)
