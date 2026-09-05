from __future__ import annotations

import json
import os
import stat
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .multi_asset_projection import AUTHORITY, LANES
from .projection_cadence import OBSERVATION_CADENCE_SECONDS, publication_decision
from .projection_publisher import GovernedProjectionPublisher, publisher_health
from .projection_runtime import MANIFEST_NAME, PROJECTION_NAME, ProjectionStore
from .projection_source_registry import (RegisteredSourceReader, SOURCE_ENVELOPE_SCHEMA, canonical,
                                         content_hash, source_registry, validate_envelope)

NOW = datetime(2026, 9, 8, 18, 0, tzinfo=timezone.utc)


def lane(name: str, *, state: str = "AVAILABLE", freshness: str = "CURRENT") -> dict:
    basis = "REFERENCE_ONLY" if name == "crypto_reference" else (
        "EXPLICIT_PROXY" if name in {"treasury_rates", "bond_proxies", "commodity_proxies", "fx_proxies", "relative_value"}
        else "DIRECT")
    return {"state": state, "freshness": freshness, "candidate_count": 0 if state == "AVAILABLE" else None,
            "research_eligible": state == "AVAILABLE", "paper_eligible": False,
            "missing_evidence": "NONE" if state == "AVAILABLE" else "EVIDENCE_UNAVAILABLE",
            "instrument_basis": basis, "session_evidence": "SYNTHETIC_POINT_IN_TIME",
            "last_trustworthy_timestamp": (NOW - timedelta(minutes=1)).isoformat()}


def payloads() -> dict[str, dict]:
    return {
        "factory_health": {"state": "AVAILABLE"},
        "market_session": {"state": "REGULAR_SESSION", "session_date": "2026-09-08", "calendar_approved": True},
        "radar_cycle": {"state": "AVAILABLE_EMPTY", "cycle_id": "cycle_17_1", "cycle_complete": True,
                        "source_artifact_hash": "a" * 64},
        "candidate_lineage": {"state": "AVAILABLE_EMPTY", "cycle_id": "cycle_17_1",
                              "source_artifact_hash": "a" * 64, "candidates": []},
        "benchmark_9h": {"state": "INCOMPLETE", "session_date": "2026-09-08", "full_session_complete": False},
        "shadow_9i": {"state": "UNAVAILABLE", "source_session": "2026-09-08",
                      "consumed_naturally": False, "observational_only": True},
        "outcomes_9j": {"state": "AVAILABLE_EMPTY", "source_session": "2026-09-08", "advanced": False},
        "professional_research": {"state": "AVAILABLE_EMPTY", "observation_count": 0,
                                  "primary_verification_state": "PRIMARY_SOURCE_REQUIRED", "agreement_state": "UNAVAILABLE"},
        "lane_evidence": {"state": "AVAILABLE", "session_date": "2026-09-08",
                          "lanes": {name: lane(name) for name in LANES}},
        "research_sleeves": {"state": "AVAILABLE_EMPTY", "sleeve_count": 0, "operational_position_count": 0},
        "paper_fund": {"state": "AVAILABLE_EMPTY", "nav": 10_000, "cash": 10_000,
                       "positions": 0, "transactions": 0, "orders": 0, "fills": 0},
        "provider_credit": {"state": "UNAVAILABLE", "confirmed_credits": None,
                            "ambiguous_credits": None, "remaining_ceiling": None},
        "authority_locks": AUTHORITY.copy(),
    }


def envelopes(values: dict[str, dict] | None = None, *, moment: datetime = NOW) -> dict[str, dict]:
    values = values or payloads()
    result = {}
    contracts = source_registry()
    for name, value in values.items():
        contract = contracts[name]
        when = moment - timedelta(minutes=1)
        result[name] = {"schema_version": SOURCE_ENVELOPE_SCHEMA, "source_identifier": name,
            "source_schema": contract.source_schema, "artifact_identity": contract.artifact_identity,
            "generated_at": when.isoformat(), "effective_at": when.isoformat(),
            "immutable_hash": content_hash(value), "payload": value}
    return result


def candidate() -> dict:
    return {"candidate_id": "candidate_1700000000000001", "instrument_id": "MU", "asset_lane": "us_equities",
            "originating_scanner": "EXISTING_IIOS_519_SYMBOL_SCANNER",
            "discovered_at": (NOW - timedelta(minutes=2)).isoformat(), "source_cycle_id": "cycle_17_1",
            "completeness": "INCOMPLETE", "missing_fields": ["PRIMARY_SOURCE_VERIFICATION"],
            "verification_state": "PRIMARY_SOURCE_REQUIRED", "promotion_state": "BLOCKED",
            "blocked_reason": "PRIMARY_SOURCE_REQUIRED"}


class PublisherCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.parent = Path(self.temp.name)
        self.parent.chmod(0o700)
        self.root = self.parent / "projection"
        ProjectionStore(self.root).create_with_rollback(generated_at=NOW.isoformat())

    def tearDown(self) -> None:
        self.temp.cleanup()

    def publish(self, values: dict[str, dict] | None = None, *, moment: datetime = NOW):
        return GovernedProjectionPublisher(self.root).evaluate(envelopes(values, moment=moment), now=moment)

    def read(self, *, moment: datetime = NOW):
        return ProjectionStore(self.root).read(now=moment)

    def test_initial_idempotent_changed_and_restart_sequence(self) -> None:
        first = self.publish()
        self.assertEqual((first.state, first.sequence, first.decision), ("PUBLISHED", 1, "INITIAL_AUTHENTIC_STATE"))
        before = (self.root / PROJECTION_NAME).read_bytes()
        repeated = self.publish()
        self.assertEqual((repeated.state, repeated.sequence, repeated.changed), ("UNCHANGED", 1, False))
        self.assertEqual(before, (self.root / PROJECTION_NAME).read_bytes())
        values = payloads(); values["radar_cycle"]["cycle_id"] = "cycle_17_2"
        values["candidate_lineage"]["cycle_id"] = "cycle_17_2"
        second = GovernedProjectionPublisher(self.root).evaluate(envelopes(values), now=NOW)
        self.assertEqual(second.sequence, 2)
        restarted = GovernedProjectionPublisher(self.root).evaluate(envelopes(values), now=NOW)
        self.assertEqual((restarted.state, restarted.sequence), ("UNCHANGED", 2))

    def test_candidate_lineage_and_five_bound(self) -> None:
        values = payloads(); values["candidate_lineage"]["state"] = "AVAILABLE"
        values["candidate_lineage"]["candidates"] = [candidate()]
        result = self.publish(values)
        projection, _ = self.read()
        self.assertEqual(result.state, "PUBLISHED")
        self.assertEqual([row["instrument_id"] for row in projection["candidate_conveyor"]["candidates"]], ["MU"])
        missing = payloads(); missing.pop("candidate_lineage")
        root2 = self.parent / "projection2"; ProjectionStore(root2).create_with_rollback(generated_at=NOW.isoformat())
        GovernedProjectionPublisher(root2).evaluate(envelopes(missing), now=NOW)
        projection2, _ = ProjectionStore(root2).read(now=NOW)
        self.assertEqual(projection2["candidate_conveyor"], {"state": "UNAVAILABLE", "candidates": []})
        too_many = payloads(); too_many["candidate_lineage"]["state"] = "AVAILABLE"
        too_many["candidate_lineage"]["candidates"] = [{**candidate(), "candidate_id": f"candidate_{n:016x}"} for n in range(6)]
        self.assertEqual(self.publish(too_many).state, "FAILED_CLOSED")

    def test_hash_mismatch_and_failed_cycle_remove_identity(self) -> None:
        values = payloads(); values["candidate_lineage"]["state"] = "AVAILABLE"
        values["candidate_lineage"]["source_artifact_hash"] = "b" * 64
        values["candidate_lineage"]["candidates"] = [candidate()]
        self.publish(values); projection, _ = self.read()
        self.assertEqual(projection["candidate_conveyor"]["candidates"], [])
        failed = payloads(); failed["radar_cycle"]["state"] = "FAILED_CLOSED"
        self.assertEqual(self.publish(failed).state, "PUBLISHED")
        projection, _ = self.read(); self.assertEqual(projection["candidate_conveyor"], {"state": "FAILED_CLOSED", "candidates": []})

    def test_session_and_freshness_policy(self) -> None:
        for state in ("MARKET_CLOSED_WEEKEND", "MARKET_CLOSED_HOLIDAY", "PRE_MARKET"):
            root = self.parent / state.lower(); ProjectionStore(root).create_with_rollback(generated_at=NOW.isoformat())
            values = payloads(); values["market_session"]["state"] = state
            GovernedProjectionPublisher(root).evaluate(envelopes(values), now=NOW)
            projection, _ = ProjectionStore(root).read(now=NOW)
            self.assertEqual(projection["evidence_freshness_state"], "STALE")
            self.assertTrue(all(not row["research_eligible"] for row in projection["lane_states"].values()))
        first = self.publish(); values = payloads(); values["market_session"]["state"] = "POST_MARKET"
        changed = self.publish(values)
        self.assertEqual((first.sequence, changed.sequence, changed.decision), (1, 2, "MARKET_SESSION_TRANSITION"))

    def test_paper_and_authority_fail_closed_without_rewrite(self) -> None:
        good = self.publish(); before = (self.root / PROJECTION_NAME).read_bytes()
        values = payloads(); values["paper_fund"]["cash"] = 9_999
        self.assertEqual(self.publish(values).state, "FAILED_CLOSED")
        values = payloads(); values["authority_locks"]["broker"] = True
        self.assertEqual(self.publish(values).state, "FAILED_CLOSED")
        self.assertEqual((good.sequence, before), (1, (self.root / PROJECTION_NAME).read_bytes()))

    def test_professional_is_nonactionable_and_provider_unavailable(self) -> None:
        values = payloads(); values["professional_research"] = {"state": "AVAILABLE", "observation_count": 2,
            "primary_verification_state": "VERIFIED", "agreement_state": "MIXED"}
        self.publish(values); projection, _ = self.read()
        self.assertFalse(projection["professional_observatory"]["endorsement"])
        self.assertEqual(projection["provider"]["state"], "UNAVAILABLE")
        self.assertTrue(all(not item["paper_eligible"] for item in projection["lane_states"].values()))

    def test_mixed_and_strict_lane_evidence(self) -> None:
        values = payloads()
        values["lane_evidence"]["lanes"]["listed_options"] = lane("listed_options", state="INCOMPLETE")
        values["lane_evidence"]["lanes"]["intraday"] = lane("intraday", state="STALE", freshness="STALE")
        values["lane_evidence"]["lanes"]["bond_proxies"] = lane("bond_proxies", state="INCOMPLETE")
        self.publish(values); projection, _ = self.read()
        for name in ("listed_options", "intraday", "bond_proxies"):
            self.assertFalse(projection["lane_states"][name]["research_eligible"])
            self.assertFalse(projection["lane_states"][name]["paper_eligible"])

    def test_benchmark_shadow_outcomes_are_semantic_only(self) -> None:
        first = self.publish(); values = payloads()
        values["benchmark_9h"] = {"state": "AVAILABLE", "session_date": "2026-09-08", "full_session_complete": True}
        second = self.publish(values); values["shadow_9i"]["state"] = "AVAILABLE"
        values["shadow_9i"]["consumed_naturally"] = True
        third = self.publish(values); values["outcomes_9j"]["advanced"] = True
        fourth = self.publish(values)
        self.assertEqual([first.sequence, second.sequence, third.sequence, fourth.sequence], [1, 2, 3, 4])

    def test_atomic_interruption_and_sanitized_health(self) -> None:
        def interrupt() -> None:
            raise RuntimeError("private value must never escape")
        result = GovernedProjectionPublisher(self.root, before_commit=interrupt).evaluate(envelopes(), now=NOW)
        self.assertEqual(result.state, "FAILED_CLOSED")
        self.assertFalse((self.root / PROJECTION_NAME).exists())
        encoded = json.dumps(publisher_health(result))
        self.assertNotIn("private value", encoded)
        self.assertEqual(publisher_health(result)["authority"], AUTHORITY)

    def test_timestamp_separation_and_unknown_preservation(self) -> None:
        result = self.publish(); projection, _ = self.read()
        self.assertNotEqual(projection["projection_generated_at"], projection["source_generated_at"])
        health = result.browser_safe()
        self.assertEqual(health["market_session_date"], "2026-09-08")
        self.assertEqual(health["evaluated_at"], NOW.isoformat())
        self.assertIsNone(projection["provider"]["confirmed_credits"])


class SourceContractCase(unittest.TestCase):
    def test_registry_is_complete_and_deterministic(self) -> None:
        registry = source_registry()
        self.assertEqual(len(registry), 13)
        self.assertEqual(list(registry), list(source_registry()))
        self.assertTrue(all(item.failure_behavior in {"FAIL_CLOSED", "PROJECT_UNAVAILABLE"} for item in registry.values()))

    def test_envelope_rejections(self) -> None:
        contract = source_registry()["factory_health"]
        value = envelopes({"factory_health": {"state": "AVAILABLE"}})["factory_health"]
        self.assertTrue(validate_envelope(value, contract, now=NOW)["fresh"])
        for mutation in ("unknown", "future", "hash", "private"):
            bad = json.loads(json.dumps(value))
            if mutation == "unknown": bad["extra"] = True
            if mutation == "future": bad["generated_at"] = (NOW + timedelta(seconds=1)).isoformat()
            if mutation == "hash": bad["immutable_hash"] = "0" * 64
            if mutation == "private": bad["payload"] = {"credential": "secret"}; bad["immutable_hash"] = content_hash(bad["payload"])
            with self.assertRaises(ValueError): validate_envelope(bad, contract, now=NOW)

    def test_reader_exact_path_modes_and_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); root.chmod(0o700)
            value = envelopes({"factory_health": {"state": "AVAILABLE"}})["factory_health"]
            path = root / "factory.json"; path.write_bytes(canonical(value)); path.chmod(0o600)
            reader = RegisteredSourceReader(root, {"factory_health": "factory.json"})
            self.assertEqual(reader.read("factory_health"), value)
            path.chmod(0o644)
            with self.assertRaises(RuntimeError): reader.read("factory_health")
            path.chmod(0o600); link = root / "link.json"; link.symlink_to(path)
            with self.assertRaises(RuntimeError): RegisteredSourceReader(root, {"factory_health": "link.json"}).read("factory_health")

    def test_cadence_contract(self) -> None:
        self.assertEqual(OBSERVATION_CADENCE_SECONDS, 60)
        unchanged = publication_decision(previous_semantic_hash="a", semantic_hash="a",
            previous_session="REGULAR_SESSION", session="REGULAR_SESSION",
            previous_freshness="CURRENT", freshness="CURRENT")
        changed = publication_decision(previous_semantic_hash="a", semantic_hash="b",
            previous_session="REGULAR_SESSION", session="REGULAR_SESSION",
            previous_freshness="CURRENT", freshness="CURRENT")
        self.assertFalse(unchanged.publish); self.assertTrue(changed.publish)
        self.assertFalse(any((changed.scanner_allowed, changed.provider_allowed, changed.repair_allowed)))

    def test_rehearsal_manifest_exact_24_and_nonlive(self) -> None:
        path = Path(__file__).parent / "fixtures" / "publisher_rehearsal_scenarios.json"
        value = json.loads(path.read_text())
        self.assertEqual(len(value["scenarios"]), 24)
        self.assertEqual(len(set(value["scenarios"])), 24)
        self.assertEqual(value["fixture_label"], "SYNTHETIC_FIXTURE_NON_LIVE")
        self.assertEqual((value["provider_requests"], value["provider_credits"], value["ledger_writes"]), (0, 0, 0))

    def test_browser_cannot_trigger_publisher(self) -> None:
        frontend = (Path(__file__).parents[3] / "FRONT END" / "src" / "ExpansionWingSnapshotProvider.tsx").read_text()
        publisher = (Path(__file__).parent / "projection_publisher.py").read_text()
        self.assertIn("15_000", frontend)
        for forbidden in ("/publish", "KeychainAdapter", "urlopen", "submit_order", "ledger.write"):
            self.assertNotIn(forbidden, publisher)


if __name__ == "__main__":
    unittest.main()
