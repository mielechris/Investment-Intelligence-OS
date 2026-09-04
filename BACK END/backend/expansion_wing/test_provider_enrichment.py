from __future__ import annotations

import json
import threading
import unittest
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from expansion_wing.fmp_adapter import (
    FMP_BASE_URL, FMP_HOST, FMP_KEYCHAIN_ACCOUNT, FMP_KEYCHAIN_SERVICE, FMPAdapter, FMPPolicy,
    FixtureHTTPResponse, credential_lifecycle_contract, summarize_license_pending_coverage,
)
from expansion_wing.market_vision_source import market_vision_registration
from expansion_wing.provider_enrichment import (
    AUTHORITY, Capability, EnrichedDatum, EnrichmentRouter, ProviderResult, canonical_hash,
    koyfin_manual_import_contract, load_capability_audit, load_watchlist,
)

FIXTURES = Path(__file__).parent / "fixtures"
NOW = datetime(2026, 8, 2, tzinfo=timezone.utc)
CUTOFF = "2026-08-01T23:59:59Z"


class FakeProvider:
    name = "FIXTURE_PROVIDER"

    def capabilities(self):
        return frozenset({Capability.COMPANY_PROFILE})

    def fetch(self, symbols, capability, *, point_in_time_cutoff):
        digest = canonical_hash([symbols, capability.value])
        datum = EnrichedDatum(symbols[0], "companyName", "Synthetic Company", "FACT", self.name,
            capability.value, "2026-08-01T12:00:00Z", "2026-08-01T12:00:00Z", NOW.isoformat(),
            point_in_time_cutoff, "CURRENT", "APPROVED_INTERNAL_USE", digest, "PRIMARY_SOURCE_REQUIRED")
        return ProviderResult(self.name, capability.value, "CURRENT", (datum,), request_count=1)


def enabled_policy(**changes):
    base = FMPPolicy(enabled=True, credential_present=True, credential_source="MACOS_SECURITY_FRAMEWORK_KEYCHAIN",
        license_approved=True, endpoint_approved=True,
        backoff_seconds=0, cache_seconds=300)
    return replace(base, **changes)


def response(body, *, status=200, host=FMP_HOST, redirects=0):
    return FixtureHTTPResponse(status, host, redirects,
        body if isinstance(body, bytes) else json.dumps(body).encode())


class ProviderNeutralTests(unittest.TestCase):
    def test_interchangeability_missing_provider_and_scanner_ownership(self):
        router = EnrichmentRouter({"fixture": FakeProvider()})
        value = router.enrich(("MU",), ("company_profile",), provider_name="fixture",
            originating_scanner="EXISTING_IIOS_519_SYMBOL_SCANNER", point_in_time_cutoff=CUTOFF)
        self.assertEqual(value["state"], "CURRENT"); self.assertFalse(value["direct_execution_route"])
        self.assertTrue(all(item is False for item in value["authority"].values()))
        missing = router.enrich(("MU",), ("company_profile",), provider_name="missing",
            originating_scanner="EXISTING_IIOS_519_SYMBOL_SCANNER", point_in_time_cutoff=CUTOFF)
        self.assertEqual(missing["failure_category"], "PROVIDER_UNAVAILABLE")
        with self.assertRaises(PermissionError):
            router.enrich(("MU",), (), provider_name="fixture", originating_scanner="NEW_SCANNER", point_in_time_cutoff=CUTOFF)

    def test_partial_provider_outage_has_no_cross_provider_substitution(self):
        value = EnrichmentRouter({"fixture": FakeProvider()}).enrich(("MU",),
            ("company_profile", "analyst_estimates"), provider_name="fixture",
            originating_scanner="EXISTING_IIOS_519_SYMBOL_SCANNER", point_in_time_cutoff=CUTOFF)
        self.assertEqual((value["state"], value["failure_category"]), ("PARTIAL", "PARTIAL_PROVIDER_OUTAGE"))
        self.assertEqual(len(value["results"]), 2)
        self.assertEqual(value["results"][1].failure_category, "CAPABILITY_UNAVAILABLE")


class FMPAdapterTests(unittest.TestCase):
    def test_disabled_missing_credential_and_license_fail_closed(self):
        self.assertEqual(FMPAdapter().fetch(("MU",), Capability.COMPANY_PROFILE,
            point_in_time_cutoff=CUTOFF).failure_category, "PROVIDER_DISABLED")
        self.assertEqual(FMPAdapter(FMPPolicy(enabled=True)).fetch(("MU",), Capability.COMPANY_PROFILE,
            point_in_time_cutoff=CUTOFF).failure_category, "CREDENTIAL_UNAVAILABLE")
        policy = FMPPolicy(enabled=True, credential_present=True,
            credential_source="MACOS_SECURITY_FRAMEWORK_KEYCHAIN")
        self.assertEqual(FMPAdapter(policy).fetch(("MU",), Capability.COMPANY_PROFILE,
            point_in_time_cutoff=CUTOFF).failure_category, "LICENSE_NOT_APPROVED")
        with self.assertRaises(ValueError):
            FMPPolicy(enabled=True, credential_present=True, credential_source="ENVIRONMENT").validate()

    def test_persistent_keychain_lifecycle_is_metadata_only_and_not_disposable(self):
        value = credential_lifecycle_contract()
        self.assertEqual((value["service"], value["account"]),
            (FMP_KEYCHAIN_SERVICE, FMP_KEYCHAIN_ACCOUNT))
        self.assertEqual(value["storage"], "MACOS_SECURITY_FRAMEWORK_KEYCHAIN")
        self.assertTrue(value["persistent"])
        self.assertFalse(value["delete_after_test"] or value["rotation_authorized"] or
            value["revocation_authorized"] or value["secret_exposed"])
        self.assertTrue(value["provisioning_separate_authorization_required"])
        self.assertTrue(value["provider_contact_separate_authorization_required"])

    def test_exact_https_host_schema_unknown_field_and_provenance(self):
        body = (FIXTURES / "fmp_company_batch.json").read_bytes()
        calls = []
        def transport(host, symbols, capability, timeout):
            calls.append((host, symbols, capability, timeout)); return response(body)
        adapter = FMPAdapter(enabled_policy(), transport=transport, utcnow=lambda: NOW)
        result = adapter.fetch(("MU", "AMD"), Capability.COMPANY_PROFILE, point_in_time_cutoff=CUTOFF)
        self.assertEqual(FMP_BASE_URL, "https://financialmodelingprep.com")
        self.assertEqual(result.state, "CURRENT"); self.assertEqual(len(calls), 1)
        self.assertTrue(all(item.provider == "FMP" and item.datum_kind == "FACT" and
            item.verification_state == "PRIMARY_SOURCE_REQUIRED" for item in result.data))
        self.assertNotIn("ignoredFixtureField", {item.field for item in result.data})
        stale = FMPAdapter(enabled_policy(stale_after_seconds=60), transport=transport, utcnow=lambda: NOW)
        self.assertTrue(all(item.freshness == "STALE" for item in stale.fetch(("MU", "AMD"),
            Capability.COMPANY_PROFILE, point_in_time_cutoff=CUTOFF).data))
        strict = FMPAdapter(enabled_policy(unknown_field_policy="REJECT"), transport=transport, utcnow=lambda: NOW)
        self.assertEqual(strict.fetch(("MU", "AMD"), Capability.COMPANY_PROFILE,
            point_in_time_cutoff=CUTOFF).failure_category, "INVALID_SCHEMA")

    def test_invalid_oversized_timeout_retry_rate_and_redirect(self):
        invalid = FMPAdapter(enabled_policy(), transport=lambda *_: response({}), utcnow=lambda: NOW)
        self.assertEqual(invalid.fetch(("MU",), Capability.COMPANY_PROFILE,
            point_in_time_cutoff=CUTOFF).failure_category, "INVALID_SCHEMA")
        large = FMPAdapter(enabled_policy(max_response_bytes=10), transport=lambda *_: response(b"x" * 11))
        self.assertEqual(large.fetch(("MU",), Capability.COMPANY_PROFILE,
            point_in_time_cutoff=CUTOFF).failure_category, "RESPONSE_TOO_LARGE")
        attempts = []
        def timeout(*_): attempts.append(1); raise TimeoutError
        timed = FMPAdapter(enabled_policy(max_retries=1), transport=timeout)
        result = timed.fetch(("MU",), Capability.COMPANY_PROFILE, point_in_time_cutoff=CUTOFF)
        self.assertEqual((result.failure_category, len(attempts)), ("TIMEOUT", 2))
        failed = FMPAdapter(enabled_policy(max_retries=1), transport=lambda *_: (_ for _ in ()).throw(OSError()))
        self.assertEqual(failed.fetch(("MU",), Capability.COMPANY_PROFILE,
            point_in_time_cutoff=CUTOFF).failure_category, "RETRY_EXHAUSTED")
        limited = FMPAdapter(enabled_policy(requests_per_minute=1, max_retries=0),
            transport=lambda *_: response([], status=500))
        limited.fetch(("MU",), Capability.COMPANY_PROFILE, point_in_time_cutoff=CUTOFF)
        self.assertEqual(limited.fetch(("AMD",), Capability.COMPANY_PROFILE,
            point_in_time_cutoff=CUTOFF).failure_category, "RATE_LIMITED")
        redirected = FMPAdapter(enabled_policy(), transport=lambda *_: response([], redirects=2))
        self.assertEqual(redirected.fetch(("MU",), Capability.COMPANY_PROFILE,
            point_in_time_cutoff=CUTOFF).failure_category, "INVALID_SCHEMA")

    def test_cache_single_flight_batch_and_duplicate_hash(self):
        body = (FIXTURES / "fmp_company_batch.json").read_bytes(); calls = []
        entered = threading.Event(); release = threading.Event()
        def transport(*_):
            calls.append(1); entered.set(); release.wait(2); return response(body)
        adapter = FMPAdapter(enabled_policy(), transport=transport, utcnow=lambda: NOW)
        results = []
        first = threading.Thread(target=lambda: results.append(adapter.fetch(("MU", "AMD"),
            Capability.COMPANY_PROFILE, point_in_time_cutoff=CUTOFF)))
        second = threading.Thread(target=lambda: results.append(adapter.fetch(("MU", "AMD"),
            Capability.COMPANY_PROFILE, point_in_time_cutoff=CUTOFF)))
        first.start(); entered.wait(1); second.start(); release.set(); first.join(); second.join()
        self.assertEqual(len(calls), 1); self.assertEqual(len(results), 2)
        self.assertEqual(sum(item.request_count for item in results), 1)
        cached = adapter.fetch(("MU", "AMD"), Capability.COMPANY_PROFILE, point_in_time_cutoff=CUTOFF)
        self.assertTrue(cached.cache_hit); self.assertEqual(cached.request_count, 0)
        self.assertEqual(len({item.response_hash for item in results[0].data}), 1)

    def test_estimates_are_not_facts_and_point_in_time_is_enforced(self):
        estimate = [{"symbol":"MU", "date":"2026-08-01T00:00:00Z", "estimatedRevenueAvg":1,
            "estimatedEpsAvg":2, "updatedAt":"2026-08-01T12:00:00Z"}]
        adapter = FMPAdapter(enabled_policy(), transport=lambda *_: response(estimate), utcnow=lambda: NOW)
        result = adapter.fetch(("MU",), Capability.ANALYST_ESTIMATES, point_in_time_cutoff=CUTOFF)
        self.assertTrue(result.data); self.assertTrue(all(item.datum_kind == "ESTIMATE" for item in result.data))
        future = FMPAdapter(enabled_policy(), transport=lambda *_: response(estimate), utcnow=lambda: NOW)
        self.assertEqual(future.fetch(("MU",), Capability.ANALYST_ESTIMATES,
            point_in_time_cutoff="2026-07-31T23:59:59Z").failure_category, "POINT_IN_TIME_INVALID")

    def test_accounting_is_per_endpoint_and_never_exposes_credentials(self):
        adapter = FMPAdapter(enabled_policy(max_retries=0), transport=lambda *_: response([], status=500))
        adapter.fetch(("MU",), Capability.COMPANY_PROFILE, point_in_time_cutoff=CUTOFF)
        value = adapter.accounting()
        self.assertEqual(value["requests_by_capability"], {"COMPANY_PROFILE": 1})
        self.assertIsNone(value["billable_cost_usd"]); self.assertFalse(value["credentials_exposed"])

    def test_license_pending_probe_retains_metadata_only(self):
        body = (FIXTURES / "fmp_company_batch.json").read_bytes()
        value = summarize_license_pending_coverage(capability=Capability.COMPANY_PROFILE,
            response_body=body, http_status_category="SUCCESS", latency_ms=120, cache_result="MISS",
            accounting_request_count=1, freshness="CURRENT")
        self.assertEqual(set(value), {"endpoint_capability", "http_status_category", "response_byte_count",
            "latency_ms", "returned_top_level_field_names", "schema_match", "timestamp_availability",
            "freshness", "content_hash", "cache_result", "accounting_request_count", "failure_category",
            "response_body_retained", "normalized_security_evidence_retained", "license_state"})
        encoded = json.dumps(value, sort_keys=True)
        for prohibited in ("Synthetic MU Fixture", "Synthetic AMD Fixture", "fixture-cik", "MU", "AMD"):
            self.assertNotIn(prohibited, encoded)
        self.assertFalse(value["response_body_retained"] or value["normalized_security_evidence_retained"])
        self.assertEqual(value["license_state"], "LICENSE_REVIEW_REQUIRED")


class ManifestBoundaryTests(unittest.TestCase):
    def test_watchlist_is_research_inventory_without_trade_authority(self):
        entries = load_watchlist(FIXTURES / "iios_research_watchlist.json")
        self.assertEqual({item["symbol"] for item in entries}, {"MU", "INTC", "AMD", "NVDA", "MSTR"})
        self.assertTrue(all(item["automatic_execution_authority"] is False and
            item["paper_eligibility_status"] == "NOT_EVALUATED" for item in entries))

    def test_capability_audit_koyfin_and_market_vision_boundaries(self):
        records = load_capability_audit(FIXTURES / "provider_capability_audit.json")
        by_name = {item["source"]: item for item in records}
        self.assertEqual(by_name["KOYFIN_PLUS"]["coverage"], ["HUMAN_RESEARCH_COCKPIT"])
        self.assertEqual(by_name["MARKET_VISION"]["internal_use"], "RIGHTS_REVIEW_REQUIRED")
        self.assertEqual(market_vision_registration()["trust_class"], "SECONDARY_DOMAIN_EXPERT")
        self.assertEqual(sum(item["source"] == "MARKET_VISION" for item in records), 1)
        cockpit = koyfin_manual_import_contract()
        self.assertFalse(any((cockpit["authenticated_automation"], cockpit["scraping"],
            cockpit["polling"], cockpit["cookie_access"], cockpit["autonomous_provider"])))
        self.assertTrue(all(value is False for value in cockpit["authority"].values()))


if __name__ == "__main__": unittest.main()
