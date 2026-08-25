import unittest
from unittest.mock import patch

import grok_experiment_manifest as manifest


class GrokExperimentManifestTests(unittest.TestCase):
    @patch.object(manifest, "grok_plan", return_value={
        "enabled": False,
        "api_key_configured": False,
        "model": "grok-4.6",
        "automatic_injection": False,
        "qualification_evidence": False,
        "gap_resolution_eligible": False,
        "fact_resolution_authority": False,
        "committee_override": False,
        "capital_authority": False,
        "trade_signal": False,
    })
    @patch.object(manifest, "grok_ab_plan", return_value={
        "same_case": True,
        "same_ledger_snapshot": True,
        "live_decision_history_pollution": False,
        "architecture_promotion_automatic": False,
    })
    @patch.object(manifest, "grok_opportunity_plan", return_value={
        "grok_can_create_governed_case_directly": False,
        "standard_opportunity_score_required": True,
        "automatic_promotion": False,
        "automatic_agent_run": False,
    })
    @patch.object(manifest, "v1_consolidation_manifest", return_value={"grok_included": False})
    def test_manifest_keeps_v1_frozen_and_grok_experimental(self, v1, opportunities, ab, context):
        result = manifest.grok_experiment_manifest()
        self.assertTrue(result["all_invariants_pass"])
        self.assertEqual(result["baseline_tag"], "IIOS-V1.0")
        self.assertEqual(result["experiment_branch"], "experiment/grok-intelligence-v1")
        self.assertFalse(result["permanent_factory_promotion_ready"])
        self.assertTrue(result["main_baseline_should_remain_unchanged"])
        self.assertFalse(result["auto_trade_authority"])
        self.assertFalse(result["paper_order_permission"])
        self.assertFalse(result["trade_execution_permission"])
        self.assertFalse(result["live_execution"])


if __name__ == "__main__":
    unittest.main()
