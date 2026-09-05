from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .multi_asset_projection import AUTHORITY, LANES
from .projection_bindings import OPERATIONAL_ROOTS, load_binding_manifest, read_bound_artifacts
from .projection_input_snapshot import INPUT_MANIFEST, EnvelopeSnapshotBuilder
from .projection_publisher import GovernedProjectionPublisher
from .projection_publisher_service import (BoundedStatusLog, PublisherService, SingleFlightLock,
                                           parse_args)
from .projection_runtime import PROJECTION_NAME, ProjectionStore
from .projection_source_adapters import ABSENT_HASH, adapt_source
from .projection_source_registry import source_registry, validate_envelope

NOW = datetime(2026, 9, 5, 18, 30, tzinfo=timezone.utc)


def telemetry() -> dict:
    generated = (NOW - timedelta(seconds=30)).isoformat()
    cadence = {name: {"availability":"AVAILABLE", "last_completed_at":generated}
               for name in ("observation", "paper_trading", "radar")}
    return {"schema_version":"batch9g-factory-telemetry-v2", "generated_at":generated,
        "health":{"state":"HEALTHY","flags":[]}, "cadence":cadence,
        "radar":{"last_cycle_id":"high_speed_radar_failed_closed_test", "last_cycle_completed_at":generated,
                 "promotion_candidate_count":8, "promoted_case_count":0},
        "paper_fund":{"snapshot_as_of":generated,"nav":10000.0,"cash":10000.0,
                      "position_count":0,"transaction_count":0},
        "recent_paper_orders":[],"recent_paper_fills":[],
        "safety":{"broker_connected":False,"live_execution":False,"trade_execution_permission":False,
                  "telemetry_read_only":True}}


def benchmark() -> dict:
    return {"schema_version":"batch9h-remote-market-validation-v1","generated_at":(NOW-timedelta(minutes=1)).isoformat(),
        "session_id":"2026-09-04","benchmark_complete":True,
        "benchmark_meta":{"expected_sample_count":78,"sample_count":78,"coverage_pct":100.0,"provider_error_count":0}}


def shadow() -> dict:
    return {"schema_version":"batch9i-browser-shadow-strategy-v1","generated_at":(NOW-timedelta(minutes=1)).isoformat(),
        "truth_state":"INCOMPLETE","source_session":"2026-09-04","complete_sessions":1,"required_sessions":5,
        "observational_only":True,"automatic_threshold_changes":False,"automatic_weight_changes":False,
        "judgment_bank_auto_write":False,"ledger_write":False,"trade_execution_permission":False,
        "broker_connected":False,"live_execution":False}


def outcomes() -> dict:
    return {"schema_version":"batch9j-browser-outcome-summary-v1","generated_at":(NOW-timedelta(minutes=1)).isoformat(),
        "status":"AVAILABLE","complete_session_count":1,
        "safety":{"auto_write_judgment_bank":False,"trade_execution_permission":False,"live_execution":False}}


class FixtureRoots:
    def __init__(self, base: Path) -> None:
        self.roots = {name: base/name.lower() for name in OPERATIONAL_ROOTS}
        for root in self.roots.values(): root.mkdir(mode=0o700)
        self.write("TELEMETRY", "latest.json", telemetry(), 0o644)
        self.write("MARKET_VALIDATION", "latest_market_validation.json", benchmark(), 0o644)
        self.write("MARKET_VALIDATION_BROWSER", "shadow_strategy.json", shadow(), 0o600)
        self.write("MARKET_VALIDATION_BROWSER", "outcome_learning.json", outcomes(), 0o644)

    def write(self, root: str, name: str, value: dict, mode: int) -> Path:
        path=self.roots[root]/name; path.write_text(json.dumps(value,sort_keys=True,separators=(",",":"))); path.chmod(mode); return path


class BindingAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp=tempfile.TemporaryDirectory(); self.base=Path(self.temp.name); self.base.chmod(0o700)
        self.fixture=FixtureRoots(self.base); self.bindings=load_binding_manifest()
    def tearDown(self) -> None: self.temp.cleanup()

    def artifacts(self): return read_bound_artifacts(self.bindings,roots=self.fixture.roots,test_mode=True)

    def test_manifest_has_exact_fixed_contracts(self):
        self.assertEqual(set(self.bindings),set(source_registry())); self.assertEqual(len(self.bindings),13)
        for name,binding in self.bindings.items():
            self.assertEqual(set(binding.allowed_projected_fields),source_registry()[name].allowed_projected_fields)
            self.assertEqual(binding.symlink_policy,"REJECT"); self.assertEqual(binding.expected_owner,"CURRENT_USER")
        with self.assertRaises(RuntimeError): load_binding_manifest(manifest=Path("elsewhere.json"))
        with self.assertRaises(RuntimeError): read_bound_artifacts(self.bindings,roots=self.fixture.roots)

    def test_every_adapter_and_complete_inventory(self):
        artifacts=self.artifacts(); envelopes={n:adapt_source(n,self.bindings[n],artifacts[n]) for n in self.bindings}
        self.assertEqual(set(envelopes),set(self.bindings))
        for name,envelope in envelopes.items():
            receipt=validate_envelope(envelope,source_registry()[name],now=NOW)
            self.assertEqual(receipt["source_content_hash"],envelope["source_content_hash"])
            self.assertEqual(receipt["adapter_version"],"v1")

    def test_optional_absence_and_required_availability_envelope(self):
        artifacts=self.artifacts()
        for name in ("candidate_lineage","professional_research","research_sleeves","provider_credit"):
            envelope=adapt_source(name,self.bindings[name],artifacts[name])
            self.assertEqual(envelope["payload"]["state"],"UNAVAILABLE"); self.assertEqual(envelope["source_content_hash"],ABSENT_HASH)
        lanes=adapt_source("lane_evidence",self.bindings["lane_evidence"],None)["payload"]
        self.assertEqual(set(lanes["lanes"]),LANES)
        self.assertTrue(all(x["candidate_count"] is None and not x["research_eligible"] for x in lanes["lanes"].values()))
        binding=self.bindings["factory_health"]
        with self.assertRaises(ValueError): adapt_source("factory_health",binding,None)

    def test_hash_and_timestamps_preserved(self):
        artifact=self.artifacts()["paper_fund"]; envelope=adapt_source("paper_fund",self.bindings["paper_fund"],artifact)
        self.assertEqual(envelope["source_content_hash"],hashlib.sha256(artifact.encoded).hexdigest())
        self.assertEqual(envelope["effective_at"],telemetry()["paper_fund"]["snapshot_as_of"])

    def test_schema_mode_symlink_oversize_and_future_rejected(self):
        path=self.fixture.roots["TELEMETRY"]/"latest.json"
        bad=telemetry();bad["schema_version"]="unknown";self.fixture.write("TELEMETRY","latest.json",bad,0o644)
        artifact=self.artifacts()["factory_health"]
        with self.assertRaises(ValueError): adapt_source("factory_health",self.bindings["factory_health"],artifact)
        self.fixture.write("TELEMETRY","latest.json",telemetry(),0o600)
        with self.assertRaises(RuntimeError): self.artifacts()
        path.unlink(); path.symlink_to(self.fixture.roots["MARKET_VALIDATION"]/"latest_market_validation.json")
        with self.assertRaises(RuntimeError): self.artifacts()
        path.unlink(); path.write_bytes(b"{"+b"x"*262144); path.chmod(0o644)
        with self.assertRaises(RuntimeError): self.artifacts()
        future=telemetry(); future["generated_at"]=(NOW+timedelta(seconds=1)).isoformat()
        future["paper_fund"]["snapshot_as_of"]=future["generated_at"]
        self.fixture.write("TELEMETRY","latest.json",future,0o644)
        envelope=adapt_source("paper_fund",self.bindings["paper_fund"],self.artifacts()["paper_fund"])
        with self.assertRaises(ValueError): validate_envelope(envelope,source_registry()["paper_fund"],now=NOW)

    def test_radar_aggregate_never_becomes_identity(self):
        artifacts=self.artifacts(); radar=adapt_source("radar_cycle",self.bindings["radar_cycle"],artifacts["radar_cycle"])
        lineage=adapt_source("candidate_lineage",self.bindings["candidate_lineage"],None)
        self.assertEqual(radar["payload"]["state"],"FAILED_CLOSED")
        self.assertEqual(lineage["payload"]["candidates"],[])

    def test_valid_lineage_and_empty_sleeves(self):
        candidate={"candidate_id":"candidate_1700000000000001","instrument_id":"MU","asset_lane":"us_equities",
            "originating_scanner":"EXISTING_IIOS_519_SYMBOL_SCANNER","discovered_at":(NOW-timedelta(minutes=2)).isoformat(),
            "source_cycle_id":"cycle_a","completeness":"INCOMPLETE","missing_fields":["PRIMARY_SOURCE_VERIFICATION"],
            "verification_state":"PRIMARY_SOURCE_REQUIRED","promotion_state":"BLOCKED","blocked_reason":"PRIMARY_SOURCE_REQUIRED"}
        value={"state":"CURRENT","reason":None,"source_cycle_id":"cycle_a","source_artifact_hash":"a"*64,
            "candidate_batch":{"schema_version":"iios-sanitized-scanner-batch-v1","batch_id":"batch_0123456789abcdef",
                "generated_at":(NOW-timedelta(minutes=1)).isoformat(),"originating_scanner":"EXISTING_IIOS_519_SYMBOL_SCANNER",
                "candidates":[{"candidate_id":candidate["candidate_id"],"ticker":"MU","discovered_at":candidate["discovered_at"],
                               "missing_fields":candidate["missing_fields"]}]},
            "promotion_candidate_count":1,
            "authority":{"automatic_promotion":False,"paper_order":False,"ledger_write":False,"broker":False,"live_execution":False}}
        self.fixture.write("PUBLISHER_SOURCES","candidate_lineage.json",value,0o600)
        sleeve={"schema_version":"iios-research-sleeves-source-v1","generated_at":(NOW-timedelta(minutes=1)).isoformat(),
                "effective_at":(NOW-timedelta(minutes=1)).isoformat(),"sleeve_count":0,"operational_position_count":0}
        self.fixture.write("PUBLISHER_SOURCES","research_sleeves.json",sleeve,0o600)
        artifacts=self.artifacts()
        self.assertEqual(len(adapt_source("candidate_lineage",self.bindings["candidate_lineage"],artifacts["candidate_lineage"])["payload"]["candidates"]),1)
        self.assertEqual(adapt_source("research_sleeves",self.bindings["research_sleeves"],artifacts["research_sleeves"])["payload"]["state"],"AVAILABLE_EMPTY")

    def test_paper_mismatch_and_authority_true_fail(self):
        bad=telemetry();bad["paper_fund"]["cash"]=9999
        self.fixture.write("TELEMETRY","latest.json",bad,0o644); artifacts=self.artifacts()
        with self.assertRaises(ValueError): adapt_source("paper_fund",self.bindings["paper_fund"],artifacts["paper_fund"])
        bad=telemetry();bad["safety"]["broker_connected"]=True
        self.fixture.write("TELEMETRY","latest.json",bad,0o644); artifacts=self.artifacts()
        with self.assertRaises(ValueError): adapt_source("authority_locks",self.bindings["authority_locks"],artifacts["authority_locks"])


class SnapshotServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.base=Path(self.temp.name);self.base.chmod(0o700)
        self.fixture=FixtureRoots(self.base);self.bindings=load_binding_manifest();self.inputs=self.base/"inputs"
    def tearDown(self): self.temp.cleanup()
    def builder(self,**kw): return EnvelopeSnapshotBuilder(self.inputs,self.bindings,roots=self.fixture.roots,test_mode=True,**kw)

    def test_snapshot_inventory_idempotence_and_one_update(self):
        envelopes,first=self.builder().build(now=NOW);self.assertTrue(first.changed);self.assertEqual(first.changed_envelopes,13)
        mtimes={p.name:p.stat().st_mtime_ns for p in self.inputs.iterdir()}
        _,again=self.builder().build(now=NOW);self.assertEqual((again.changed,again.changed_envelopes),(False,0))
        self.assertEqual(mtimes,{p.name:p.stat().st_mtime_ns for p in self.inputs.iterdir()})
        changed={"schema_version":"iios-provider-credit-source-v1",
            "generated_at":(NOW-timedelta(minutes=1)).isoformat(),"effective_at":(NOW-timedelta(minutes=1)).isoformat(),
            "confirmed_credits":0,"ambiguous_credits":None,"remaining_ceiling":None}
        self.fixture.write("PUBLISHER_SOURCES","provider_credit.json",changed,0o600)
        _,third=self.builder().build(now=NOW);self.assertTrue(third.changed)
        self.assertEqual(third.changed_envelopes,1)
        self.assertEqual({p.name for p in self.inputs.iterdir()}, {f"{n}.json" for n in self.bindings}|{INPUT_MANIFEST})

    def test_atomic_interruption_has_no_committed_manifest(self):
        def fail(): raise RuntimeError("PRIVATE")
        with self.assertRaises(RuntimeError): self.builder(before_manifest=fail).build(now=NOW)
        self.assertFalse((self.inputs/INPUT_MANIFEST).exists())
        _,recovered=self.builder().build(now=NOW);self.assertTrue(recovered.changed)

    def test_end_to_end_publication_and_restart(self):
        envelopes,_=self.builder().build(now=NOW)
        projection=self.base/"projection";ProjectionStore(projection).create_with_rollback(generated_at=NOW.isoformat())
        first=GovernedProjectionPublisher(projection).evaluate(envelopes,now=NOW)
        self.assertEqual((first.state,first.sequence),("PUBLISHED",1))
        again=GovernedProjectionPublisher(projection).evaluate(envelopes,now=NOW)
        self.assertEqual((again.state,again.sequence),("UNCHANGED",1))
        value,_=ProjectionStore(projection).read(now=NOW);self.assertEqual(value["evidence_freshness_state"],"STALE")
        self.assertEqual(value["candidate_conveyor"]["candidates"],[]);self.assertEqual(value["authority"],AUTHORITY)

    def service(self,sleeper=lambda _:None):
        projection=self.base/"projection";ProjectionStore(projection).create_with_rollback(generated_at=NOW.isoformat())
        state=self.base/"state";state.mkdir(mode=0o700)
        return PublisherService(self.builder(),GovernedProjectionPublisher(projection),SingleFlightLock(state/"publisher.lock"),
            BoundedStatusLog(state/"status.jsonl",1024),clock=lambda:NOW,sleeper=sleeper),state

    def test_once_two_observations_bounded_logs_and_no_overlap(self):
        service,state=self.service();self.assertEqual(service.observe(),"OBSERVATION_PUBLISHED")
        self.assertEqual(service.run(maximum_observations=2),2)
        log=(state/"status.jsonl").read_text();self.assertLessEqual(len(log.encode()),1024);self.assertNotIn(str(self.base),log)
        self.assertNotIn("PRIVATE",log)

    def test_lock_contention_and_graceful_stop(self):
        service,state=self.service();other=SingleFlightLock(state/"publisher.lock");self.assertTrue(other.acquire())
        self.assertEqual(service.observe(),"LOCK_CONTENDED");other.release()
        def stop(_): service.stop()
        service.sleeper=stop;self.assertEqual(service.run(maximum_observations=None),1)

    def test_cli_contract_and_browser_isolation(self):
        self.assertTrue(parse_args(["--operational","--validate-bindings"]).validate_bindings)
        self.assertTrue(parse_args(["--operational","--once"]).once)
        with self.assertRaises(SystemExit): parse_args(["--once"])
        with self.assertRaises(SystemExit): parse_args(["--operational","--interval","59"])
        with self.assertRaises(SystemExit): parse_args(["--operational","--root","/tmp/x"])
        publisher=(Path(__file__).parent/"projection_publisher_service.py").read_text()
        browser=(Path(__file__).parents[3]/"FRONT END"/"src"/"ExpansionWingSnapshotProvider.tsx").read_text()
        self.assertIn("15_000",browser)
        for forbidden in ("urlopen", "Keychain", "submit_order", "ledger.write", "/publish"):
            self.assertNotIn(forbidden,publisher)

    def test_fixture_lists_exact_thirty_scenarios(self):
        value=json.loads((Path(__file__).parent/"fixtures"/"publisher_binding_rehearsal_scenarios.json").read_text())
        self.assertEqual((len(value["scenarios"]),len(set(value["scenarios"]))),(30,30))
        self.assertEqual((value["provider_requests"],value["provider_credits"],value["ledger_writes"]),(0,0,0))


if __name__ == "__main__": unittest.main()
