from __future__ import annotations

import copy
import hashlib
import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from radar_candidate_projection import AUTHORITY, project_candidate_lineage, replay_historical_cycle
from expansion_wing import acceptance_server
from expansion_wing.candidate_flow_acceptance import (
    BASELINE_ATTESTATION_HASH, CandidateFlowAcceptance, CreditCheckpointStore,
    genesis_checkpoint, parse_sanitized_batch,
)
from expansion_wing.post_close_candidate_pipeline import ClosingSessionEvidence, finalize_post_close


NOW = "2026-09-08T20:05:00+00:00"
REVIEWED = "2026-09-01T20:05:00+00:00"


def cycle(rows=1):
    return {"high_speed_market_radar_cycle_id": "high_speed_radar_abc", "last_cycle_completed_at": NOW,
        "promotion_candidates": [{"opportunity_candidate_id": f"opportunity_{i}", "ticker": "MU",
            "created_at": NOW, "created_by": "BATCH_9E_HIGH_SPEED_MARKET_RADAR", "source_scan_id": "scan_1",
            "raw_evidence": "MUST_NOT_ESCAPE", "score": 99} for i in range(rows)]}


def state():
    return {"last_cycle_id": "high_speed_radar_abc", "last_cycle_completed_at": NOW,
        "last_cycle_status": "COMPLETE", "promotion_candidate_count": 99}


class RadarProjectionTests(unittest.TestCase):
    def test_exact_deterministic_projection_is_private_field_free_and_bounded(self):
        value = project_candidate_lineage(state(), cycle(8), now=datetime.fromisoformat(NOW))
        again = project_candidate_lineage(state(), cycle(8), now=datetime.fromisoformat(NOW))
        self.assertEqual(value, again); self.assertEqual(value["state"], "CURRENT")
        self.assertEqual(len(value["candidate_batch"]["candidates"]), 5)
        self.assertEqual(value["promotion_candidate_count"], 8)
        self.assertRegex(value["candidate_batch"]["batch_id"], r"^batch_[0-9a-f]{16}$")
        self.assertNotIn("MUST_NOT_ESCAPE", json.dumps(value))
        self.assertFalse(any(value["authority"].values())); self.assertEqual(value["authority"], AUTHORITY)
        parse_sanitized_batch(value["candidate_batch"])

    def test_failed_mismatch_stale_and_invalid_candidates_are_unavailable(self):
        cases=[]
        failed=state(); failed["last_cycle_id"]="high_speed_radar_failed_closed_x"; cases.append((failed,cycle()))
        mismatch=cycle(); mismatch["high_speed_market_radar_cycle_id"]="other"; cases.append((state(),mismatch))
        bad=cycle(); bad["promotion_candidates"][0]["ticker"]="bad ticker"; cases.append((state(),bad))
        producer=cycle(); producer["promotion_candidates"][0]["created_by"]="OTHER"; cases.append((state(),producer))
        scan=cycle(); scan["promotion_candidates"][0]["source_scan_id"]=""; cases.append((state(),scan))
        for s,c in cases:
            value=project_candidate_lineage(s,c,now=datetime.fromisoformat(NOW)); self.assertEqual(value["state"],"UNAVAILABLE")
            self.assertIsNone(value["candidate_batch"]); self.assertIsNone(value["promotion_candidate_count"])

    def test_empty_and_historical(self):
        empty=project_candidate_lineage(state(),cycle(0),now=datetime.fromisoformat(NOW))
        self.assertEqual((empty["state"],empty["promotion_candidate_count"]),("AVAILABLE_EMPTY",0))
        historical=replay_historical_cycle(cycle())
        self.assertEqual(historical["state"],"HISTORICAL_REPLAY_ONLY")
        self.assertFalse(any(historical["authority"].values()))


class BaselineAndEmptyTests(unittest.TestCase):
    def test_once_only_authenticated_baseline(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name); os.chmod(root,0o700); store=CreditCheckpointStore(root)
            with self.assertRaisesRegex(RuntimeError,"UNAUTHORIZED"):
                store.initialize_accepted_baseline(explicitly_authorized=False,
                    attestation_hash=BASELINE_ATTESTATION_HASH,reviewed_at=REVIEWED)
            with self.assertRaisesRegex(RuntimeError,"ATTESTATION_INVALID"):
                store.initialize_accepted_baseline(explicitly_authorized=True,
                    attestation_hash="0"*64,reviewed_at=REVIEWED)
            got=store.initialize_accepted_baseline(explicitly_authorized=True,
                attestation_hash=BASELINE_ATTESTATION_HASH,reviewed_at=REVIEWED)
            self.assertEqual((got.confirmed,got.ambiguous,got.ceiling,got.consumed),(3,2,1000,5))
            with self.assertRaisesRegex(RuntimeError,"CONFLICT"):
                store.initialize_accepted_baseline(explicitly_authorized=True,
                    attestation_hash=BASELINE_ATTESTATION_HASH,reviewed_at=REVIEWED)

    def test_parser_accepts_truthful_empty_batch(self):
        payload={"schema_version":"iios-sanitized-scanner-batch-v1","batch_id":"batch_0123456789abcdef",
            "generated_at":NOW,"originating_scanner":"EXISTING_IIOS_519_SYMBOL_SCANNER","candidates":[]}
        batch,rows=parse_sanitized_batch(payload); self.assertEqual(batch,payload["batch_id"]); self.assertEqual(rows,())

    def test_empty_flow_persists_replay_without_provider_work(self):
        payload={"schema_version":"iios-sanitized-scanner-batch-v1","batch_id":"batch_0123456789abcdef",
            "generated_at":NOW,"originating_scanner":"EXISTING_IIOS_519_SYMBOL_SCANNER","candidates":[]}
        with tempfile.TemporaryDirectory() as name:
            root=Path(name); os.chmod(root,0o700); store=CreditCheckpointStore(root); store.initialize(genesis_checkpoint())
            credits=SimpleNamespace(snapshot=lambda:{"confirmed":3,"ambiguous":2,"consumed":5})
            bridge=SimpleNamespace(provider=SimpleNamespace(credits=credits))
            runner=CandidateFlowAcceptance(bridge,store,enabled=True,fixture_only=True)
            result=runner.run(payload,explicitly_authorized=True)
            self.assertEqual((result.state,result.provider_request_count,result.ending_credits),("AVAILABLE_EMPTY",0,5))
            self.assertEqual(store.load().last_batch_id,payload["batch_id"])
            replay=runner.run(payload,explicitly_authorized=True)
            self.assertEqual((replay.state,replay.failure_category),("REPLAY_REJECTED","BATCH_REPLAY"))

    def test_post_close_empty_is_successful_not_a_case(self):
        body={"session_date":"2026-09-08","market_timezone":"America/New_York","final_snapshot_at":NOW,
            "expected_snapshot_count":78,"observed_snapshot_count":78,"provider_error_count":0,
            "universe_count":519,"complete":True}
        digest=hashlib.sha256(json.dumps(body,sort_keys=True,separators=(",", ":")).encode()).hexdigest()
        close=ClosingSessionEvidence(**body,evidence_hash=digest)
        accepted=SimpleNamespace(state="AVAILABLE_EMPTY",candidate_count=0,review_items=())
        result=finalize_post_close(close,accepted,(),explicitly_authorized=True)
        self.assertEqual((result.state,result.governed_case_count),("AVAILABLE_EMPTY",0))

    def test_browser_conveyor_is_bounded_and_authority_free(self):
        projected=project_candidate_lineage(state(),cycle(8),now=datetime.fromisoformat(NOW))
        radar={"last_cycle_completed_at":NOW,"candidate_lineage_state":"CURRENT",
            "candidate_batch":projected["candidate_batch"],"promotion_candidate_count":8}
        telemetry={"schema_version":acceptance_server.TELEMETRY_SCHEMA,"generated_at":NOW,
            "cadence":{"observation":{},"paper_trading":{}},"radar":radar,"paper_fund":{},
            "recent_paper_orders":[],"recent_paper_fills":[],"safety":{"telemetry_read_only":True,
            "broker_connected":False,"trade_execution_permission":False,"live_execution":False}}
        with tempfile.TemporaryDirectory() as name:
            root=Path(name); path=root/"telemetry.json"; path.write_text(json.dumps(telemetry))
            missing=[root/f"missing-{i}" for i in range(3)]
            compositor=acceptance_server.Compositor(path,*missing,"http://127.0.0.1:8002/system/status")
            compositor._reachability=lambda:"CURRENT"
            conveyor=compositor.snapshot()["sections"]["candidate_conveyor"]
        self.assertEqual((conveyor["state"],len(conveyor["data"]["candidates"])),("CURRENT",5))
        self.assertFalse(conveyor["data"]["automatic_promotion"] or conveyor["data"]["paper_order"] or
            conveyor["data"]["broker"] or conveyor["data"]["live_execution"])
