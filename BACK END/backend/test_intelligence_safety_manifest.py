import unittest
from unittest.mock import patch

import intelligence_safety_manifest as manifest


class IntelligenceSafetyManifestTests(unittest.TestCase):
    @patch.object(manifest.agent_calibration_weighting, "build_calibration_policy", return_value={
        "committee_override": False,
    })
    def test_manifest_freezes_all_eight_batches_after_judgment_policy_approval(self, calibration):
        result = manifest.intelligence_safety_manifest()
        self.assertEqual(result["batches_complete"], [1, 2, 3, 4, 5, 6, 7, 8])
        self.assertEqual(result["user_approved_batch"], 4)
        self.assertEqual(result["final_freeze_batch"], 8)
        self.assertTrue(result["all_current_invariants_pass"])
        self.assertTrue(result["final_intelligence_freeze_ready"])
        self.assertTrue(result["intelligence_v1_frozen"])
        self.assertEqual(result["freeze_blockers"], [])

        policy = result["approved_judgment_policy"]
        self.assertTrue(policy["human_approved_low_risk_only"])
        self.assertTrue(policy["advisory_context_only"])
        self.assertFalse(policy["qualification_evidence"])
        self.assertFalse(policy["gap_resolution_eligible"])
        self.assertFalse(policy["fact_resolution_authority"])
        self.assertFalse(policy["committee_override"])
        self.assertFalse(policy["capital_authority"])

        self.assertFalse(result["auto_trade_authority"])
        self.assertFalse(result["paper_order_permission"])
        self.assertFalse(result["trade_execution_permission"])
        self.assertFalse(result["live_execution"])


if __name__ == "__main__":
    unittest.main()
