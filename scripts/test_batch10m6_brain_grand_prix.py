#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "iios_brain_grand_prix.py"
LAUNCHER = ROOT / "scripts" / "run_batch10m6_brain_grand_prix.py"
CONFIG = ROOT / "config" / "iios_batch10m6_brain_grand_prix.json"

spec = importlib.util.spec_from_file_location("grandprix", SCRIPT)
assert spec and spec.loader
grandprix = importlib.util.module_from_spec(spec)
spec.loader.exec_module(grandprix)


class Batch10M6Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = json.loads(CONFIG.read_text(encoding="utf-8"))

    def test_default_five_case_plan_is_bounded(self) -> None:
        plan = grandprix.planned_calls(self.config, 5)
        self.assertEqual(plan["core_per_case"], 8)
        self.assertEqual(plan["core_total"], 40)
        self.assertEqual(plan["fallback_max_per_case"], 2)
        self.assertEqual(plan["maximum_total"], 50)
        self.assertLessEqual(plan["maximum_total"], self.config["max_provider_calls_per_run"])

    def test_ten_case_plan_stays_at_hard_cap(self) -> None:
        plan = grandprix.planned_calls(self.config, 10)
        self.assertEqual(plan["maximum_total"], 100)
        self.assertEqual(plan["maximum_total"], self.config["max_provider_calls_per_run"])

    def test_safety_contract_is_read_only(self) -> None:
        safety = self.config["safety"]
        self.assertEqual(safety["ledger_mode"], "READ_ONLY")
        self.assertFalse(safety["ledger_write"])
        self.assertFalse(safety["production_model_routing_change"])
        self.assertFalse(safety["committee_change_authority"])
        self.assertFalse(safety["risk_change_authority"])
        self.assertFalse(safety["threshold_auto_change"])
        self.assertFalse(safety["capital_authority"])
        self.assertFalse(safety["trade_execution_permission"])
        self.assertFalse(safety["live_execution"])
        self.assertFalse(safety["auto_apply_winner"])
        self.assertTrue(safety["provider_calls_require_explicit_execute"])
        self.assertTrue(safety["provider_spend_requires_second_confirmation"])

    def test_capability_policy_does_not_blindly_enable_tools(self) -> None:
        policy = self.config["capability_policy"]
        self.assertTrue(policy["test_relevant_capabilities_in_assigned_role"])
        self.assertTrue(policy["do_not_enable_every_tool_blindly"])
        self.assertEqual(policy["openai_governed_committee_external_tools"], "INTENTIONALLY_OFF")
        self.assertEqual(policy["vision_file_code_computer_tools"], "SEPARATE_TARGETED_SHADOW_TEST_WHEN_CASE_RELEVANT")

    def test_select_cases_prefers_distinct_topics(self) -> None:
        packets = [
            {"case_id": "1", "topic": "ABC opportunity review"},
            {"case_id": "2", "topic": "ABC opportunity review"},
            {"case_id": "3", "topic": "XYZ opportunity review"},
        ]
        selected = grandprix.select_cases(packets, 2)
        self.assertEqual([x["case_id"] for x in selected], ["1", "3"])

    def test_leaderboard_never_claims_accuracy_or_cost(self) -> None:
        cases = [{
            "openai_committee_variants": [{
                "status": "COMPLETE",
                "model": "gpt-5.6-luna",
                "reasoning_effort": "medium",
                "latency_ms": 1000,
                "response_completeness_pct": 100,
                "agreement_with_production_disposition": True,
                "output": {"required_evidence": ["x"]},
            }],
            "grok_reasoning_variants": [],
            "gemini_thinking_variants": [],
            "multi_model_arbiter": {"status": "SKIPPED"},
        }]
        board = grandprix.build_leaderboard(cases)
        self.assertEqual(len(board), 1)
        self.assertIsNone(board[0]["accuracy_score"])
        self.assertIsNone(board[0]["exact_cost_usd"])
        self.assertIn("WAITING_FOR_EXACT_TASK_TO_OUTCOME_LINKAGE", board[0]["accuracy_state"])

    def test_source_requires_double_confirmation_and_has_no_ledger_writes(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")
        self.assertIn('if not args.execute:', text)
        self.assertIn('if not args.confirm_shadow_provider_spend:', text)
        self.assertIn('--confirm-shadow-provider-spend', text)
        self.assertNotIn('record_object(', text)
        self.assertNotIn('record_event(', text)

    def test_launcher_requires_backend_venv(self) -> None:
        text = LAUNCHER.read_text(encoding="utf-8")
        self.assertIn('backend/.venv/bin/python', text)
        self.assertIn('TCC-safe Grand Prix ledger access', text)


if __name__ == "__main__":
    unittest.main()
