import unittest

import grok_batch7_checkpoint as checkpoint


class GrokBatch7CheckpointTests(unittest.TestCase):
    def test_checkpoint_marks_infrastructure_complete_but_value_proof_pending(self):
        out = checkpoint.build_batch7_checkpoint()
        self.assertEqual(out["checkpoint"], "VALUE_PROOF_INFRASTRUCTURE_COMPLETE_AWAITING_FORWARD_OBSERVATIONS")
        self.assertTrue(out["completed"]["four_case_repeatability_sample"])
        self.assertTrue(out["completed"]["prospective_discovery_lead_time_instrumentation"])
        self.assertTrue(out["completed"]["automatic_standard_iios_revalidation_probe"])
        self.assertTrue(out["completed"]["dual_arm_decision_shadow_ledger"])
        self.assertFalse(out["value_proof_complete"])
        self.assertFalse(out["permanent_factory_promotion_ready"])
        self.assertFalse(out["automatic_configuration_change"])
        self.assertFalse(out["auto_trade_authority"])
        self.assertFalse(out["paper_order_permission"])
        self.assertFalse(out["trade_execution_permission"])
        self.assertFalse(out["live_execution"])


if __name__ == "__main__":
    unittest.main()
