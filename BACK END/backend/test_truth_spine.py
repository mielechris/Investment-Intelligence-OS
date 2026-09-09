from __future__ import annotations

import hashlib
import json
import sqlite3
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from contextlib import contextmanager

from truth_spine_contract import Topology, bind, canonical, digest, normalize, seal, universe
from truth_spine_replay import AcceptanceModel, analyze, initialize, registered_agents, replay, routing, transition, validate_ledger


@contextmanager
def test_db(path):
    db = sqlite3.connect(path)
    try:
        with db:
            yield db
    finally:
        db.close()


class TruthSpineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.now = datetime(2026, 9, 9, 16, tzinfo=timezone.utc)
        self.db = self.root / "shadow-ledger.db"
        with test_db(self.db) as db:
            db.execute("CREATE TABLE ledger_objects(object_type TEXT,payload_json TEXT,created_at TEXT)")
        self.topology = Topology("iios-truth-topology-v1", "ISOLATED_SHADOW", "a" * 40, "release-1", str(self.root / "release"),
            "b" * 64, "python-test", str(self.root / "python"), "c" * 64, str(self.root / "runtime-manifest.json"),
            "d" * 64, str(self.db), "e" * 64, "ledger+truth-v1", "2026-09-09", "replay-sep9", "plan-1", "generation-1",
            "publisher-1", "f" * 64, ("FINANCIAL_DATASETS:PERSISTED_ONLY",), ("DETERMINISTIC_ACCEPTANCE_ONLY",),
            tuple((k, False) for k in ("broker", "paper_order", "promotion", "ledger_write", "live_execution")), self.now.isoformat(), "rollback-1", "SESSION_CLOSED")
        self.capture = {"schema_version": "batch9h-benchmark-universe-v1", "source": "OFFICIAL_SP500_PLUS_NASDAQ100_BENCHMARK_SIDECAR",
            "verified_complete": True, "strict_membership": True, "symbols": ["MU"], "symbol_count": 1,
            "official_capture_created_at": self.now.isoformat(), "source_lineage": [
                {"index": index, "source_id": source, "verified_complete": True, "source_mode": "GOVERNED_INDEX_TRACKER_MIRROR", "trust_source": "CERTIFI_CA"}
                for index, source in [("SP500", "SP500_GOVERNED_IVV"), ("NASDAQ100", "NASDAQ100_GOVERNED_IQQ")]]}
        self.raw = canonical({"snapshot": {"ticker": "MU", "price": 1.0, "time": self.now.isoformat()}})
        self.receipt = seal({"schema_version": "iios-operational-market-evidence-receipt-v1", "status": "CONFIRMED", "credit_cost": 1,
            "endpoint": "MARKET_SNAPSHOT", "evidence_hash": hashlib.sha256(self.raw).hexdigest(), "ticker": "MU",
            "request_identity": "market-evidence-" + "1" * 64, "observed_at": self.now.isoformat(), "provider_timestamp": self.now.isoformat(),
            "response_bytes": len(self.raw), "freshness": "CURRENT", "normalized_hash": digest({"ticker": "MU", "provider_timestamp": self.now.isoformat(), "freshness": "CURRENT", "field_count": 3})})
        initialize(self.db, self.topology)

    def captured(self, *, at=None):
        raw = canonical(self.capture)
        return universe(raw, hashlib.sha256(raw).hexdigest(), self.topology, at=at or self.now)

    def evidence(self, **kwargs):
        return normalize(self.receipt, self.raw, topology=self.topology, universe_record=self.captured(), storage_policy="FD_REVIEWED_INTERNAL_EVIDENCE_REPLAY_V1", **kwargs)

    def test_topology_roundtrip(self):
        self.assertEqual(Topology.parse(self.topology.record()), self.topology)

    def test_topology_deterministic(self):
        self.assertEqual(self.topology.record(), self.topology.record())

    def test_ledger_mismatch(self):
        with test_db(self.db) as db: db.execute("UPDATE spine_identity SET identity='wrong'")
        with self.assertRaisesRegex(ValueError, "LEDGER_IDENTITY"): validate_ledger(self.db, self.topology)

    def test_topology_authority_rejected(self):
        x = self.topology.record(); x["authorities"][0][1] = True
        with self.assertRaisesRegex(ValueError, "AUTHORITY"): Topology.parse(seal(x))

    def test_unknown_topology_field(self):
        with self.assertRaises(ValueError): Topology.parse(seal({**self.topology.record(), "unexpected": 1}))

    def test_relative_runtime_path_rejected(self):
        with self.assertRaises(ValueError): Topology.parse(seal({**self.topology.record(), "interpreter": "python"}))

    def test_closed_is_not_disabled(self):
        self.assertEqual(Topology.parse(self.topology.record()).phase, "SESSION_CLOSED")

    def test_valid_governed_capture(self):
        self.assertEqual(self.captured()["symbols"], ["MU"])
        self.assertFalse(self.captured()["direct_membership"])

    def test_stale_universe(self):
        self.assertEqual(self.captured(at=self.now + timedelta(days=2))["status"], "STALE")

    def test_future_universe(self):
        self.assertEqual(self.captured(at=self.now - timedelta(seconds=1))["status"], "STALE")

    def test_missing_provenance(self):
        self.capture["source_lineage"] = []
        with self.assertRaises(ValueError): self.captured()

    def test_fixture_universe(self):
        self.capture["source"] = "FIXTURE"
        with self.assertRaises(ValueError): self.captured()

    def test_unreviewed_proxy(self):
        self.capture["source_lineage"][0]["source_mode"] = "PROXY"
        with self.assertRaises(ValueError): self.captured()

    def test_universe_hash(self):
        with self.assertRaises(ValueError): universe(canonical(self.capture), "0" * 64, self.topology, at=self.now)

    def test_duplicate_constituent(self):
        self.capture["symbols"] = ["MU", "MU"]
        with self.assertRaises(ValueError): self.captured()

    def test_evidence_identity_preserved(self):
        x = self.evidence(); self.assertEqual(x["evidence_id"], self.receipt["request_identity"]); self.assertEqual(x["status"], "REPLAY")
        self.assertEqual(x["cost"]["replay_credits"], 0)

    def test_no_raw_prompt(self):
        self.assertNotIn("snapshot", self.evidence()); self.assertEqual(self.evidence()["freshness_class"], "HISTORICAL")

    def test_missing_receipt(self):
        self.receipt = {}
        with self.assertRaises(ValueError): self.evidence()

    def test_evidence_hash_tamper(self):
        self.raw += b" "
        with self.assertRaises(ValueError): self.evidence()

    def test_entitlement_required(self):
        with self.assertRaises(ValueError): normalize(self.receipt, self.raw, topology=self.topology, universe_record=self.captured(), storage_policy="")

    def test_generation_cannot_mix(self):
        x = self.evidence(); x["generation_id"] = "wrong"
        with self.assertRaises(ValueError): bind(seal(x), self.topology)

    def test_wrong_universe_generation(self):
        u = self.captured(); u["generation_id"] = "wrong"
        with self.assertRaises(ValueError): normalize(self.receipt, self.raw, topology=self.topology, universe_record=seal(u), storage_policy="FD_REVIEWED_INTERNAL_EVIDENCE_REPLAY_V1")

    def test_agents_are_real_registry(self):
        self.assertEqual(len(registered_agents()), 8)

    def test_relevant_routing(self):
        self.assertEqual([k for k,v in routing(()).items() if v["invoked"]], ["market_structure", "skeptic"])

    def test_optional_tag(self):
        self.assertTrue(routing(("macro",))["macro"]["invoked"])

    def test_context_independence_and_memory(self):
        seen = {}; memory = ({"content_hash": "memory-1"},)
        class Capture(AcceptanceModel):
            def assess(self, role, context):
                seen[role] = context
                return super().assess(role, context)
        result = analyze(self.evidence(), memory=memory, boundary=Capture())
        self.assertIsNone(result["failure"])
        self.assertEqual(seen["market_structure"], seen["skeptic"])
        self.assertEqual(seen["skeptic"]["memory"], list(memory))
        self.assertNotIn("independent_assessments", seen["skeptic"])
        self.assertIn("independent_assessments", seen["committee"])

    def test_citation_rejection(self):
        class Bad(AcceptanceModel):
            def assess(self, role, context): return {**super().assess(role, context), "citations": []}
        self.assertIsNotNone(analyze(self.evidence(), boundary=Bad())["failure"])

    def test_unsupported_buy(self):
        class Bad(AcceptanceModel):
            def assess(self, role, context): return {**super().assess(role, context), "conclusion": "BUY"}
        self.assertIsNotNone(analyze(self.evidence(), boundary=Bad())["failure"])

    def test_budget(self):
        self.assertEqual(analyze(self.evidence(), budget=1)["failure"], "MODEL_BUDGET_EXCEEDED")

    def test_timeout(self):
        class Slow(AcceptanceModel):
            def assess(self, role, context): time.sleep(.03); return super().assess(role, context)
        self.assertIsNotNone(analyze(self.evidence(), boundary=Slow(), timeout=.001)["failure"])
        time.sleep(.04)

    def test_idempotent_replay_restart(self):
        a = replay(self.db, self.topology, self.evidence()); b = replay(self.db, self.topology, self.evidence())
        self.assertEqual(a, b); self.assertEqual(a, validate_ledger(self.db, self.topology))
        with test_db(self.db) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM spine_events").fetchone()[0], 10)

    def test_failure_forces_watch(self):
        class Failed(AcceptanceModel):
            def assess(self, role, context): raise RuntimeError("offline test")
        result = replay(self.db, self.topology, self.evidence(), boundary=Failed())
        self.assertEqual(result["decision"], "WATCH"); self.assertEqual(result["committee_state"], "FAILED_CLOSED")

    def test_no_paper_transition(self):
        with self.assertRaises(ValueError): transition("WATCH", "PAPER_AUTHORIZED")

    def test_cannot_skip_risk(self):
        with self.assertRaises(ValueError): transition("CASE_OPEN", "WATCH")

    def test_append_only(self):
        replay(self.db, self.topology, self.evidence())
        with test_db(self.db) as db:
            with self.assertRaises(sqlite3.IntegrityError): db.execute("DELETE FROM spine_events")

    def test_outcome_not_fabricated(self):
        x = replay(self.db, self.topology, self.evidence())
        self.assertIsNone(x["outcome"]["measurement"]); self.assertEqual(x["memory"]["admissions"], 0)
        self.assertTrue(all(v is False for v in x["authority"].values()))

    def test_conflicting_instrument_rejected(self):
        self.raw = canonical({"snapshot": {"ticker": "OTHER", "price": 1, "time": self.now.isoformat()}})
        self.receipt = seal({**self.receipt, "evidence_hash": hashlib.sha256(self.raw).hexdigest()})
        with self.assertRaisesRegex(ValueError, "INSTRUMENT"): self.evidence()

    def test_proxy_cannot_replace_constituent(self):
        self.receipt = seal({**self.receipt, "ticker": "SPY"})
        with self.assertRaisesRegex(ValueError, "UNIVERSE"): self.evidence()

    def test_normalized_receipt_hash_rejected(self):
        self.receipt = seal({**self.receipt, "normalized_hash": "0" * 64})
        with self.assertRaisesRegex(ValueError, "NORMALIZED"): self.evidence()

    def test_evidence_timestamp_conflict(self):
        self.receipt = seal({**self.receipt, "provider_timestamp": (self.now - timedelta(hours=1)).isoformat()})
        with self.assertRaisesRegex(ValueError, "TIME_BINDING"): self.evidence()

    def test_committee_timeout(self):
        class SlowCommittee(AcceptanceModel):
            def assess(self, role, context):
                if role == "committee": time.sleep(.03)
                return super().assess(role, context)
        self.assertIsNotNone(analyze(self.evidence(), boundary=SlowCommittee(), timeout=.001)["failure"])
        time.sleep(.04)

    def test_projection_money_is_cross_language_safe(self):
        from truth_spine_service import money
        self.assertEqual(money(10000.0), "10000.0")
        self.assertIsNone(money(None))
        for x in (float("nan"), float("inf"), True):
            with self.assertRaises(ValueError): money(x)

    def test_missing_active_record_health_closed(self):
        from truth_spine_service import health
        self.assertEqual(health(self.root / "missing.json", "ready")[0], 503)
        self.assertEqual(health(self.root / "missing.json", "live")[0], 200)

    def test_release_manifest_mismatch(self):
        from truth_spine_service import release_check
        Path(self.topology.release_root).mkdir()
        Path(self.topology.release_root, "truth-release.json").write_bytes(b"{}")
        with self.assertRaisesRegex(ValueError, "RELEASE_MANIFEST"): release_check(self.topology)

    def test_dead_process_is_not_ready(self):
        from truth_spine_service import atomic, bindings, process_probe
        atomic(self.root / "scheduler-heartbeat.json", seal({**bindings(self.topology), "role": "scheduler", "pid": 99999999,
            "runtime_id": self.topology.runtime_id, "ledger_identity": self.topology.ledger_identity,
            "observed_at": self.now.isoformat(), "network_dispatch_enabled": False, "allowance": 0}))
        with self.assertRaisesRegex(ValueError, "REQUIRED_PROCESS"): process_probe(self.root / "service.json", "scheduler", self.topology, self.now)

    def test_stale_heartbeat_rejected_before_discovery(self):
        from truth_spine_service import atomic, bindings, process_probe
        atomic(self.root / "publisher-heartbeat.json", seal({**bindings(self.topology), "role": "publisher", "pid": 99999999,
            "runtime_id": self.topology.runtime_id, "ledger_identity": self.topology.ledger_identity,
            "observed_at": (self.now - timedelta(seconds=16)).isoformat(), "network_dispatch_enabled": False, "allowance": 0}))
        with self.assertRaisesRegex(ValueError, "HEARTBEAT_STALE"): process_probe(self.root / "service.json", "publisher", self.topology, self.now)

    def test_wrong_runtime_heartbeat(self):
        from truth_spine_service import atomic, bindings, process_probe
        atomic(self.root / "publisher-heartbeat.json", seal({**bindings(self.topology), "role": "publisher", "pid": 99999999,
            "runtime_id": "wrong", "ledger_identity": self.topology.ledger_identity,
            "observed_at": self.now.isoformat(), "network_dispatch_enabled": False, "allowance": 0}))
        with self.assertRaises(ValueError): process_probe(self.root / "service.json", "publisher", self.topology, self.now)

    def test_publisher_output_and_mismatched_stale_states(self):
        from truth_spine_service import publish, projection_check
        result = replay(self.db, self.topology, self.evidence())
        projection = publish(self.root, self.topology)
        current = datetime.now(timezone.utc)
        projection_check(projection, self.topology, result, current)
        for changes in ({"generation_id": "wrong"}, {"runtime_id": "wrong"}, {"release_id": "wrong"}, {"ledger_identity": "wrong"},
                        {"observed_at": (current - timedelta(seconds=20)).isoformat()}, {"phase": "INSTALLED_DISABLED"},
                        {"classification": "LIVE_VERIFIED"}, {"event_ids": []}, {"case_state": "BUY"}, {"authority": {"broker": True}}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                projection_check(seal({**projection, **changes}), self.topology, result, current)

    def test_memory_requires_actual_validated_outcome(self):
        from truth_spine_replay import memory_context
        outcome = seal({"case_id": "past", "status": "MEASURED"})
        memory = seal({"human_validated": True, "outcome_receipt_hash": outcome["content_hash"], "case_id": "past"})
        with test_db(self.db) as db:
            db.execute("INSERT INTO ledger_objects VALUES (?,?,?)", ("judgment_entry", canonical(memory).decode(), self.now.isoformat()))
        self.assertEqual(memory_context(self.db), ())
        with test_db(self.db) as db:
            db.execute("INSERT INTO ledger_objects VALUES (?,?,?)", ("outcome_measurement_receipt", canonical(outcome).decode(), self.now.isoformat()))
        self.assertEqual(len(memory_context(self.db)), 1)


if __name__ == "__main__":
    unittest.main()
