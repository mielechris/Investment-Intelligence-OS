#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "iios_brain_shadow_bakeoff.py"
RETRY = ROOT / "scripts" / "retry_batch10m5_failed_shadow_lanes.py"
CONFIG = ROOT / "config" / "iios_batch10m5_brain_shadow_bakeoff.json"

spec = importlib.util.spec_from_file_location("bakeoff", SCRIPT)
assert spec and spec.loader
bakeoff = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bakeoff)


class Batch10M5Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = json.loads(CONFIG.read_text(encoding="utf-8"))

    def test_contract_is_read_only_and_no_authority(self) -> None:
        safety = self.config["safety"]
        self.assertEqual(safety["ledger_mode"], "READ_ONLY")
        self.assertFalse(safety["ledger_write"])
        self.assertFalse(safety["production_routing_change"])
        self.assertFalse(safety["committee_change_authority"])
        self.assertFalse(safety["risk_change_authority"])
        self.assertFalse(safety["capital_authority"])
        self.assertFalse(safety["trade_execution_permission"])
        self.assertFalse(safety["live_execution"])
        self.assertTrue(safety["provider_calls_require_explicit_execute"])
        self.assertTrue(safety["provider_spend_requires_second_confirmation"])

    def test_smoke_plan_is_bounded(self) -> None:
        packets = [{"case_id": "case_1"}]
        plan = bakeoff.build_plan(self.config, packets, "smoke")
        self.assertEqual(plan["planned_provider_calls"], 8)
        self.assertLessEqual(plan["planned_provider_calls"], plan["hard_call_cap"])
        self.assertEqual(len(plan["openai_committee_variants"]), 3)
        self.assertEqual(len(plan["grok_reasoning_levels"]), 2)
        self.assertEqual(len(plan["gemini_thinking_levels"]), 2)

    def test_standard_plan_stays_under_hard_cap_for_two_cases(self) -> None:
        packets = [{"case_id": "case_1"}, {"case_id": "case_2"}]
        plan = bakeoff.build_plan(self.config, packets, "standard")
        self.assertEqual(plan["planned_provider_calls"], 22)
        self.assertLessEqual(plan["planned_provider_calls"], 30)

    def test_read_only_connection_refuses_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ledger.db"
            db = sqlite3.connect(path)
            db.execute("CREATE TABLE ledger_objects (object_id TEXT, object_type TEXT, case_id TEXT, payload_json TEXT, created_at TEXT)")
            db.commit()
            db.close()
            ro = bakeoff.connect_ro(path)
            with self.assertRaises(sqlite3.OperationalError):
                ro.execute("INSERT INTO ledger_objects VALUES ('x','x','x','{}','x')")
            ro.close()

    def test_completed_packet_loader_uses_existing_committee_and_case_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ledger.db"
            db = sqlite3.connect(path)
            db.execute("CREATE TABLE ledger_objects (object_id TEXT, object_type TEXT, case_id TEXT, payload_json TEXT, created_at TEXT)")
            case = {"case_id": "case_abc", "topic": "ABC", "evidence": [{"evidence_id": "e1"}], "evidence_summary": {"evidence_count": 1}}
            agents = {f"agent_{i}": {"status": "complete"} for i in range(8)}
            committee = {"decision_id": "d1", "topic": "ABC", "status": "complete", "agents": agents, "disposition": "NO_TRADE", "confidence": 0.8, "evidence_summary": {"evidence_count": 1}}
            db.execute("INSERT INTO ledger_objects VALUES (?,?,?,?,?)", ("case_abc", "case", "case_abc", json.dumps(case), "2026-08-31T10:00:00+00:00"))
            db.execute("INSERT INTO ledger_objects VALUES (?,?,?,?,?)", ("d1", "committee_decision", "case_abc", json.dumps(committee), "2026-08-31T10:10:00+00:00"))
            db.commit()
            db.close()
            packets = bakeoff.load_completed_case_packets(path, 1)
            self.assertEqual(len(packets), 1)
            self.assertEqual(packets[0]["case_id"], "case_abc")
            self.assertEqual(len(packets[0]["specialists"]), 8)

    def test_result_annotation_never_invents_accuracy(self) -> None:
        result = {"status": "COMPLETE", "output": {"summary": "x", "dissent": "y", "bull_case": "b", "bear_case": "z", "required_evidence": ["e"], "confidence": 0.7, "disposition": "NO_TRADE"}}
        annotated = bakeoff.annotate_result(result, "committee", "NO_TRADE")
        self.assertIsNone(annotated["accuracy_score"])
        self.assertEqual(annotated["accuracy_state"], "WAITING_FOR_EXACT_TASK_TO_OUTCOME_LINKAGE")
        self.assertTrue(annotated["agreement_with_production_disposition"])
        self.assertTrue(annotated["agreement_is_not_accuracy"])

    def test_source_requires_double_execution_confirmation(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")
        self.assertIn('if not args.execute:', text)
        self.assertIn('if not args.confirm_shadow_provider_spend:', text)
        self.assertIn('--confirm-shadow-provider-spend', text)
        self.assertNotIn('record_object(', text)
        self.assertNotIn('record_event(', text)

    def test_retry_is_ca_hardened_and_does_not_repeat_openai_committee(self) -> None:
        text = RETRY.read_text(encoding="utf-8")
        self.assertIn('import certifi', text)
        self.assertIn('SSL_CERT_FILE', text)
        self.assertIn('REQUESTS_CA_BUNDLE', text)
        self.assertIn('openai_committee_calls_repeated": 0', text)
        self.assertIn('FAILED_GROK_GEMINI_LANES_ONLY', text)
        self.assertIn('--confirm-shadow-provider-spend', text)
        self.assertNotIn('for variant in selected_openai_variants', text)
        self.assertNotIn('record_object(', text)
        self.assertNotIn('record_event(', text)


if __name__ == "__main__":
    unittest.main()
