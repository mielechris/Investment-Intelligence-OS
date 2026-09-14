import unittest

import grok_batch7_checkpoint as checkpoint


class GrokBatch7CheckpointTests(unittest.TestCase):
    def test_checkpoint_marks_nonblocking_forward_cycle_ready_but_value_proof_pending(self):
        out = checkpoint.build_batch7_checkpoint()
        self.assertEqual(out["stage"], "7C_FORWARD_VALUE_PROOF")
        self.assertEqual(out["checkpoint"], "FORWARD_VALUE_CYCLE_NONBLOCKING_READY_AWAITING_TIME_SEPARATED_OBSERVATIONS")
        self.assertEqual(out["resume_phrase"], "pick up Batch 7")
        self.assertEqual(out["resume_from"], "RUN_NONBLOCKING_FORWARD_VALUE_CYCLE")
        self.assertTrue(out["completed"]["four_case_repeatability_sample"])
        self.assertTrue(out["completed"]["prospective_discovery_lead_time_instrumentation"])
        self.assertTrue(out["completed"]["first_seen_observation_deduplication"])
        self.assertTrue(out["completed"]["prospective_metrics_isolated_from_legacy_history"])
        self.assertTrue(out["completed"]["same_cycle_latency_excluded_from_lead_time"])
        self.assertTrue(out["completed"]["minimum_cross_cycle_separation_enforced"])
        self.assertTrue(out["completed"]["automatic_standard_iios_revalidation_probe"])
        self.assertTrue(out["completed"]["hardened_crosschecked_revalidation_gate"])
        self.assertTrue(out["completed"]["dual_arm_decision_shadow_ledger"])
        self.assertTrue(out["completed"]["crosschecked_shadow_quote_policy"])
        self.assertTrue(out["completed"]["meaningful_value_sample_thresholds"])
        self.assertTrue(out["completed"]["single_command_forward_value_cycle"])
        self.assertTrue(out["completed"]["nonblocking_cycle_job_runner"])
        self.assertTrue(out["completed"]["single_active_cycle_backpressure"])
        self.assertFalse(out["measurement_integrity"]["same_cycle_api_latency_counts_as_information_lead"])
        self.assertFalse(out["measurement_integrity"]["blocking_http_request_required"])
        self.assertFalse(out["measurement_integrity"]["concurrent_cycle_jobs_allowed"])
        self.assertFalse(out["value_proof_complete"])
        self.assertFalse(out["permanent_factory_promotion_ready"])
        self.assertFalse(out["automatic_configuration_change"])
        self.assertFalse(out["auto_trade_authority"])
        self.assertFalse(out["paper_order_permission"])
        self.assertFalse(out["trade_execution_permission"])
        self.assertFalse(out["live_execution"])


if __name__ == "__main__":
    unittest.main()
