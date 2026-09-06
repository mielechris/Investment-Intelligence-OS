from __future__ import annotations

import json
import unittest
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from expansion_wing.listed_security_source import (
    AUTHORITY, LicenseDecision, ListedSecurityAdapter, ListedSecurityEvidence, PRODUCTS,
    parse_mu_fixture, product_classifications, unavailable_projection,
)

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "superbatch23_listed_security.json").read_text())
NOW = datetime(2026, 9, 4, 20, 5, tzinfo=timezone.utc)


class Transport:
    def __init__(self, payload=None): self.payload = payload or FIXTURE["mu"]; self.calls = 0
    def fetch(self, ticker): self.calls += 1; return self.payload.copy()


def license(**changes):
    value = LicenseDecision("FINANCIAL_DATASETS", "SYNTHETIC_FIXTURE_TIER", True, True, False,
        True, True, True, True)
    return replace(value, **changes)


class LicensingTests(unittest.TestCase):
    def test_account_tier_and_each_right_fail_closed(self):
        self.assertEqual(license(account_tier=None).gate(), "ACCOUNT_TIER_UNVERIFIED")
        for field in ("internal_use", "browser_display", "redistribution", "realtime_entitled",
                      "historical_entitled", "attribution_required"):
            with self.subTest(field=field): self.assertEqual(license(**{field: None}).gate(), "LICENSE_TERMS_INCOMPLETE")
        self.assertEqual(license(request_cost_known=False).gate(), "LICENSE_TERMS_INCOMPLETE")
        self.assertEqual(license(internal_use=False).gate(), "LICENSE_PROHIBITED")

    def test_license_gate_precedes_transport(self):
        transport = Transport()
        with self.assertRaisesRegex(PermissionError, "ACCOUNT_TIER_UNVERIFIED"):
            ListedSecurityAdapter(transport, license(account_tier=None)).fetch_mu(now=NOW)
        self.assertEqual(transport.calls, 0)


class EvidenceTests(unittest.TestCase):
    def test_strict_mu_identity_freshness_and_products(self):
        evidence = parse_mu_fixture(FIXTURE["mu"], now=NOW, license_decision=license())
        self.assertEqual((evidence.instrument_id, evidence.security_type), ("NASDAQ:MU", "COMMON_STOCK"))
        self.assertEqual(evidence.freshness_state, "CURRENT")
        self.assertEqual(evidence.products, ("US_LARGE_CAP_EQUITIES", "SECTOR_THEMATIC_ETFS", "BROAD_FACTOR_ETFS"))
        self.assertTrue(set(evidence.products) <= set(PRODUCTS))
        self.assertFalse(evidence.paper_eligible); self.assertEqual(evidence.authority, AUTHORITY)
        self.assertEqual(evidence.spread_slippage_state, "UNAVAILABLE")

    def test_stale_future_and_provider_timestamp_handling(self):
        self.assertEqual(parse_mu_fixture(FIXTURE["mu"], now=datetime(2026,9,5,tzinfo=timezone.utc),
            license_decision=license()).freshness_state, "STALE")
        future = FIXTURE["mu"] | {"observed_at":"2026-09-05T00:00:00Z"}
        with self.assertRaises(ValueError): parse_mu_fixture(future, now=NOW, license_decision=license())
        missing = FIXTURE["mu"].copy(); missing.pop("provider_timestamp")
        evidence = parse_mu_fixture(missing, now=NOW, license_decision=license())
        self.assertIsNone(evidence.provider_timestamp)

    def test_schema_bounds_identity_and_nested_private_content(self):
        for payload in (FIXTURE["mu"] | {"ticker":"AMD"}, FIXTURE["mu"] | {"exchange":"NYSE"},
                        FIXTURE["mu"] | {"prompt":{"private":"value"}},
                        {key:value for key,value in FIXTURE["mu"].items() if key != "session"}):
            with self.subTest(keys=tuple(payload)), self.assertRaises(ValueError):
                parse_mu_fixture(payload, now=NOW, license_decision=license())

    def test_no_adjustment_volume_or_liquidity_inference(self):
        absent = FIXTURE["mu"].copy(); absent.pop("price"); absent.pop("volume"); absent["liquidity"]="UNAVAILABLE"
        evidence = parse_mu_fixture(absent, now=NOW, license_decision=license())
        self.assertFalse(evidence.price_available); self.assertFalse(evidence.volume_available)
        self.assertEqual(evidence.liquidity_state, "UNAVAILABLE")

    def test_browser_projection_exposes_no_values_or_private_fields(self):
        projection = parse_mu_fixture(FIXTURE["mu"], now=NOW, license_decision=license()).browser_safe()
        encoded = json.dumps(projection, sort_keys=True)
        for prohibited in ("101.25", "123456", "source_hash", "provider_timestamp", "retrieved_at", "fields", "prompt"):
            self.assertNotIn(prohibited, encoded)
        self.assertFalse(projection["paper_eligible"]); self.assertTrue(all(value is False for value in projection["authority"].values()))
        blocked = unavailable_projection(); self.assertEqual(blocked["source_state"], "NOT_ACTIVATED")
        self.assertEqual(blocked["product_readiness"]["CRYPTO_ETFS_LISTED_PROXIES"], "UNAVAILABLE")

    def test_proxy_separation_and_browser_cannot_invoke_provider(self):
        evidence = parse_mu_fixture(FIXTURE["mu"], now=NOW, license_decision=license())
        readiness = product_classifications(evidence)
        self.assertEqual(readiness["US_LARGE_CAP_EQUITIES"], "PAPER_TEST_READY")
        self.assertEqual(readiness["CRYPTO_ETFS_LISTED_PROXIES"], "PROXY_ONLY")
        self.assertNotIn("fetch", evidence.browser_safe())
        self.assertNotIn("endpoint", json.dumps(evidence.browser_safe()))

    def test_invalid_authority_and_paper_eligibility_rejected(self):
        evidence = parse_mu_fixture(FIXTURE["mu"], now=NOW, license_decision=license())
        with self.assertRaisesRegex(ValueError, "AUTHORITY_INVALID"):
            replace(evidence, authority=AUTHORITY | {"broker":True}).validate()
        with self.assertRaisesRegex(ValueError, "ELIGIBILITY_INVALID"):
            replace(evidence, paper_eligible=True).validate()

    def test_fixture_only_adapter_and_deterministic_hash(self):
        transport=Transport(); adapter=ListedSecurityAdapter(transport, license())
        first=adapter.fetch_mu(now=NOW); second=adapter.fetch_mu(now=NOW)
        self.assertEqual(first.source_hash, second.source_hash); self.assertEqual(transport.calls, 2)
        self.assertTrue(FIXTURE["fixture"]); self.assertEqual(FIXTURE["label"], "SYNTHETIC / NON-LIVE")


if __name__ == "__main__": unittest.main()
