from __future__ import annotations

import json
import os
import stat
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from expansion_wing.candidate_enrichment_bridge import BridgePolicy, CandidateEnrichmentBridge
from expansion_wing.candidate_flow_acceptance import (
    CandidateFlowAcceptance, CreditCheckpoint, CreditCheckpointStore, genesis_checkpoint,
    parse_sanitized_batch,
)
from expansion_wing.financial_datasets import API_ORIGIN, FDCapability, FDPolicy, FDResponse, FinancialDatasetsAdapter

FIXTURES = Path(__file__).parent / "fixtures"
BATCH = json.loads((FIXTURES / "scanner_candidate_batch_14b.json").read_text())
FACTS = json.loads((FIXTURES / "financial_datasets_mu_amd.json").read_text())["company_facts"]
NOW = datetime(2026, 9, 4, 18, 0, tzinfo=timezone.utc)


class Credentials:
    def retrieve(self) -> bytes: return b"synthetic-opaque-credential"


class Transport:
    def __init__(self, fail: str | None = None) -> None: self.calls = 0; self.fail = fail
    def trust_readiness(self) -> str: return "READY"
    def __call__(self, url, _headers, tickers, _connect, _response):
        self.calls += 1; ticker = tickers[0]; status = 500 if ticker == self.fail else 200
        return FDResponse(status, f"{API_ORIGIN}/company/facts", (),
            json.dumps({} if status != 200 else FACTS[ticker]).encode())


def provider(transport: Transport | None = None, *, confirmed: int = 3, ambiguous: int = 2):
    return FinancialDatasetsAdapter(FDPolicy(enabled=True, provider_balance=1_000), credentials=Credentials(),
        transport=transport or Transport(), utcnow=lambda: NOW, prior_confirmed_credits=confirmed,
        prior_ambiguous_credits=ambiguous)


class CandidateFlowAcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(); self.root = Path(self.temporary.name) / "credits"
        self.root.mkdir(mode=0o700); self.root.chmod(0o700); self.store = CreditCheckpointStore(self.root)
        self.store.initialize(genesis_checkpoint())

    def tearDown(self): self.temporary.cleanup()

    def runner(self, source=None, **kwargs):
        source = source or provider()
        bridge = CandidateEnrichmentBridge(source, BridgePolicy(enabled=True))
        return CandidateFlowAcceptance(bridge, self.store, enabled=True, fixture_only=True, **kwargs), source

    def test_complete_fixture_flow_persists_restart_safe_accounting(self):
        runner, source = self.runner(); result = runner.run(BATCH, explicitly_authorized=True)
        self.assertEqual((result.state, result.candidate_count, result.unique_ticker_count), ("COMPLETE", 3, 2))
        self.assertEqual((source.transport.calls, result.provider_request_count, result.cache_hit_count), (2, 2, 0))
        self.assertEqual((result.starting_credits, result.ending_credits, len(result.review_items)), (5, 7, 3))
        restarted = CreditCheckpointStore(self.root).load()
        self.assertEqual((restarted.confirmed, restarted.ambiguous, restarted.consumed), (5, 2, 7))
        self.assertEqual(restarted.last_batch_id, BATCH["batch_id"])

    def test_replay_is_rejected_before_provider_work(self):
        runner, source = self.runner(); runner.run(BATCH, explicitly_authorized=True)
        first_calls = source.transport.calls
        replay = runner.run(BATCH, explicitly_authorized=True)
        self.assertEqual((replay.state, replay.failure_category, source.transport.calls),
            ("REPLAY_REJECTED", "BATCH_REPLAY", first_calls))

    def test_checkpoint_mismatch_stops_before_provider(self):
        source = provider(confirmed=4, ambiguous=2); runner, _ = self.runner(source)
        result = runner.run(BATCH, explicitly_authorized=True)
        self.assertEqual((result.state, result.failure_category, source.transport.calls),
            ("REJECTED", "CREDIT_CHECKPOINT_MISMATCH", 0))

    def test_provider_failure_still_persists_confirmed_accounting(self):
        source = provider(Transport(fail="AMD")); runner, _ = self.runner(source)
        result = runner.run(BATCH, explicitly_authorized=True)
        self.assertEqual((result.state, result.review_items, source.transport.calls),
            ("STOPPED_FAIL_CLOSED", (), 2))
        checkpoint = self.store.load()
        self.assertEqual((checkpoint.confirmed, checkpoint.ambiguous, checkpoint.consumed), (5, 2, 7))

    def test_existing_cache_prevents_duplicate_paid_transport(self):
        source = provider(); source.fetch(FDCapability.COMPANY_FACTS, ("MU",))
        self.store.path.unlink(); self.store.initialize(genesis_checkpoint(confirmed=4, ambiguous=2))
        runner, _ = self.runner(source); result = runner.run(BATCH, explicitly_authorized=True)
        self.assertEqual((result.state, source.transport.calls, result.provider_request_count,
            result.cache_hit_count, result.starting_credits, result.ending_credits),
            ("COMPLETE", 2, 1, 1, 6, 7))

    def test_disabled_and_nonfixture_modes_do_not_read_store_or_call_provider(self):
        source = provider(); bridge = CandidateEnrichmentBridge(source, BridgePolicy(enabled=True))
        missing = CreditCheckpointStore(self.root / "missing")
        for runner in (CandidateFlowAcceptance(bridge, missing),
                CandidateFlowAcceptance(bridge, missing, enabled=True, fixture_only=False)):
            result = runner.run(BATCH, explicitly_authorized=True)
            self.assertEqual((result.state, source.transport.calls), ("NOT_ACTIVATED", 0))

    def test_strict_scanner_contract_rejects_private_or_unknown_fields(self):
        value = json.loads(json.dumps(BATCH)); value["candidates"][0]["private_reason"] = "secret"
        with self.assertRaises(ValueError): parse_sanitized_batch(value)
        value = json.loads(json.dumps(BATCH)); value["originating_scanner"] = "NEW_SCANNER"
        with self.assertRaises(ValueError): parse_sanitized_batch(value)

    def test_checkpoint_permissions_hash_and_conflict_fail_closed(self):
        checkpoint = self.store.load(); self.assertEqual(stat.S_IMODE(self.store.path.stat().st_mode), 0o600)
        conflict = replace(checkpoint, last_batch_id="batch_0000000000000099")
        with self.assertRaises(ValueError): conflict.validate()
        valid = genesis_checkpoint(confirmed=4, ambiguous=2)
        with self.assertRaisesRegex(RuntimeError, "CREDIT_CHECKPOINT_CONFLICT"):
            self.store.save(valid, expected_previous_hash="f" * 64)
        self.store.path.chmod(0o644)
        with self.assertRaisesRegex(RuntimeError, "CREDIT_CHECKPOINT_UNAVAILABLE"): self.store.load()

    def test_browser_projection_contains_counts_only_and_no_authority(self):
        runner, _ = self.runner(); result = runner.run(BATCH, explicitly_authorized=True)
        projection = result.browser_safe(); encoded = json.dumps(projection, sort_keys=True)
        for prohibited in ("MU", "AMD", "candidate_id", "normalized_hash", "company_facts"):
            self.assertNotIn(prohibited, encoded)
        self.assertFalse(projection["scheduled"] or projection["provider_enabled"])
        self.assertTrue(all(value is False for value in projection["authority"].values()))

    def test_credit_checkpoint_contains_no_provider_data(self):
        runner, _ = self.runner(); runner.run(BATCH, explicitly_authorized=True)
        encoded = self.store.path.read_text()
        for prohibited in ("MU", "AMD", "company", "candidate", "credential", "api"):
            self.assertNotIn(prohibited, encoded.lower())
        self.assertEqual(set(json.loads(encoded)), {"schema_version", "confirmed", "ambiguous", "ceiling",
            "last_batch_id", "previous_event_hash", "event_hash"})


if __name__ == "__main__": unittest.main()
