import unittest
from unittest.mock import patch

import intelligence_safety_manifest as manifest


class IntelligenceSafetyManifestTests(unittest.TestCase):
    @patch.object(manifest.agent_calibration_weighting, "build_calibration_policy", return_value={
        "committee_override": False,
    })
    def test_manifest_blocks_final_freeze_until_user_gated_batch(self, calibration):
        result = manifest.intelligence_safety_manifest()
        self.assertEqual(result["autonomous_batches_complete"], [1, 2, 3, 5, 6, 7])
        self.assertEqual(result["user_gated_batch"], 4)
        self.assertFalse(result["final_intelligence_freeze_ready"])
        self.assertTrue(result["freeze_blockers"])
        self.assertFalse(result["auto_trade_authority"])
        self.assertFalse(result["paper_order_permission"])
        self.assertFalse(result["trade_execution_permission"])
        self.assertFalse(result["live_execution"])


if __name__ == "__main__":
    unittest.main()
