from __future__ import annotations

import json
import unittest
from datetime import datetime, timezone
from pathlib import Path

from expansion_wing.candidate_enrichment_bridge import (
    AUTHORITY, BridgePolicy, CandidateEnrichmentBridge, ScannerCandidate, downstream_gate,
    validate_browser_projection,
)
from expansion_wing.acceptance_server import Compositor
from expansion_wing.financial_datasets import (
    API_ORIGIN, FDCapability, FDPolicy, FDResponse, FinancialDatasetsAdapter,
)

FIXTURES = Path(__file__).parent / "fixtures"
FACTS = json.loads((FIXTURES / "financial_datasets_mu_amd.json").read_text())["company_facts"]
BATCH = json.loads((FIXTURES / "candidate_enrichment_batch.json").read_text())
NOW = datetime(2026, 9, 4, 17, 0, tzinfo=timezone.utc)


class Credentials:
    def retrieve(self) -> bytes: return b"synthetic-opaque-credential"


class Transport:
    def __init__(self, *, fail_ticker: str | None = None) -> None:
        self.calls = 0; self.fail_ticker = fail_ticker
    def trust_readiness(self) -> str: return "READY"
    def __call__(self, url, _headers, tickers, _connect, _response):
        self.calls += 1; ticker = tickers[0]
        status = 500 if ticker == self.fail_ticker else 200
        body = {} if status != 200 else FACTS[ticker]
        return FDResponse(status, f"{API_ORIGIN}/company/facts", (), json.dumps(body).encode())


def candidates() -> tuple[ScannerCandidate, ...]:
    return tuple(ScannerCandidate(item["candidate_id"], item["ticker"], item["discovered_at"],
        BATCH["originating_scanner"], tuple(item["missing_fields"])) for item in BATCH["candidates"])


def provider(transport: Transport | None = None) -> FinancialDatasetsAdapter:
    return FinancialDatasetsAdapter(FDPolicy(enabled=True, provider_balance=1_000), credentials=Credentials(),
        transport=transport or Transport(), utcnow=lambda: NOW, prior_confirmed_credits=3,
        prior_ambiguous_credits=2)


class CandidateEnrichmentBridgeTests(unittest.TestCase):
    def test_disabled_default_touches_neither_provider_nor_credits(self):
        source = provider(); result = CandidateEnrichmentBridge(source).run(candidates())
        self.assertEqual((result.state, source.transport.calls, result.ending_conservative_credits),
            ("NOT_ACTIVATED", 0, 5))

    def test_fixture_batch_deduplicates_tickers_and_routes_to_primary_review(self):
        source = provider(); bridge = CandidateEnrichmentBridge(source, BridgePolicy(enabled=True))
        result = bridge.run(candidates(), explicitly_authorized=True)
        self.assertEqual((result.state, result.candidate_count, result.unique_ticker_count),
            ("READY_FOR_PRIMARY_REVIEW", 3, 2))
        self.assertEqual((source.transport.calls, result.provider_request_count, result.new_conservative_credits),
            (2, 2, 2))
        self.assertEqual((result.starting_conservative_credits, result.ending_conservative_credits), (5, 7))
        self.assertEqual(result.primary_review_queue_count, 3)
        self.assertEqual(len({item.normalized_hash for item in result.evidence}), 2)

    def test_existing_cache_is_checked_before_paid_request(self):
        source = provider(); source.fetch(FDCapability.COMPANY_FACTS, ("MU",))
        result = CandidateEnrichmentBridge(source, BridgePolicy(enabled=True)).run(
            candidates(), explicitly_authorized=True)
        self.assertEqual((source.transport.calls, result.provider_request_count, result.cache_hit_count), (2, 1, 1))
        self.assertEqual((result.starting_conservative_credits, result.new_conservative_credits), (6, 1))

    def test_invalid_origin_batch_and_unknown_missing_field_stop_before_provider(self):
        original = candidates()[0]
        invalid = (ScannerCandidate(original.candidate_id, original.ticker, original.discovered_at,
            "NEW_SCANNER", original.missing_fields),)
        source = provider(); bridge = CandidateEnrichmentBridge(source, BridgePolicy(enabled=True))
        self.assertEqual(bridge.run(invalid, explicitly_authorized=True).failure_category,
            "CANDIDATE_CONTRACT_INVALID")
        unknown = (ScannerCandidate(original.candidate_id, original.ticker, original.discovered_at,
            original.originating_scanner, ("analyst_estimates",)),)
        self.assertEqual(bridge.run(unknown, explicitly_authorized=True).failure_category,
            "CANDIDATE_CONTRACT_INVALID")
        self.assertEqual(source.transport.calls, 0)

    def test_provider_failure_stops_remaining_work_and_exposes_no_partial_evidence(self):
        transport = Transport(fail_ticker="AMD"); source = provider(transport)
        result = CandidateEnrichmentBridge(source, BridgePolicy(enabled=True)).run(
            candidates(), explicitly_authorized=True)
        self.assertEqual((result.state, transport.calls, result.failure_category),
            ("STOPPED_FAIL_CLOSED", 2, "PROVIDER_UNAVAILABLE"))
        self.assertEqual(result.evidence, ())

    def test_browser_projection_is_scalar_counts_only_and_authority_false(self):
        source = provider(); result = CandidateEnrichmentBridge(source, BridgePolicy(enabled=True)).run(
            candidates(), explicitly_authorized=True)
        projection = result.browser_safe(); encoded = json.dumps(projection, sort_keys=True)
        for prohibited in ("MU", "AMD", "candidate_id", "normalized_hash", "company_facts"):
            self.assertNotIn(prohibited, encoded)
        self.assertEqual(projection["primary_review_queue_count"], 3)
        self.assertTrue(all(value is False for value in projection["authority"].values()))
        validate_browser_projection(projection)

    def test_compositor_projects_counts_without_enabling_provider(self):
        source = provider(); projection = CandidateEnrichmentBridge(source, BridgePolicy(enabled=True)).run(
            candidates(), explicitly_authorized=True).browser_safe()
        missing = Path("/definitely/missing")
        compositor = Compositor(missing, missing, missing, missing, "http://127.0.0.1:1",
            enrichment_reader=lambda: projection)
        compositor._reachability = lambda: "UNAVAILABLE"
        snapshot = compositor.snapshot()
        self.assertEqual(snapshot["sections"]["candidate_enrichment"]["state"], "CURRENT")
        governor = snapshot["room_states"]["Resource Governor"]
        self.assertEqual(governor["data"]["primary_review_queue_count"], 3)
        self.assertFalse(governor["data"]["network_enabled"] or governor["data"]["provider_enabled"] or
            governor["data"]["authority_granted"])

    def test_downstream_gate_never_creates_operational_authority(self):
        source = provider(); evidence = CandidateEnrichmentBridge(source, BridgePolicy(enabled=True)).run(
            candidates()[:1], explicitly_authorized=True).evidence[0]
        blocked = downstream_gate(evidence, primary_source_verified=False, human_approved=True)
        reviewed = downstream_gate(evidence, primary_source_verified=True, human_approved=True)
        self.assertEqual(blocked["state"], "BLOCKED_PRIMARY_SOURCE_REVIEW")
        self.assertEqual(reviewed["state"], "RESEARCH_REVIEWED")
        for result in (blocked, reviewed):
            self.assertFalse(result["committee_reliance"] or result["judgment_foundry"] or
                result["pattern_laboratory"] or result["paper_order"] or result["automatic_action"])
            self.assertEqual(result["authority"], AUTHORITY)

    def test_credit_baseline_and_policy_bounds(self):
        source = provider(); self.assertEqual(source.credits.snapshot(),
            {"consumed": 5, "confirmed": 3, "ambiguous": 2, "remaining": 995})
        limited = CandidateEnrichmentBridge(source, BridgePolicy(enabled=True, max_new_credits=1)).run(
            candidates(), explicitly_authorized=True)
        self.assertEqual((limited.failure_category, source.transport.calls,
            limited.new_conservative_credits), ("CREDIT_LIMIT_REACHED", 1, 1))
        with self.assertRaises(ValueError): BridgePolicy(max_candidates=6).validate()
        with self.assertRaises(ValueError): BridgePolicy(max_new_credits=0).validate()


if __name__ == "__main__": unittest.main()
