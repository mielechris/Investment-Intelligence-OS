import unittest
from unittest.mock import patch

import grok_value_cycle as cycle


class GrokValueCycleTests(unittest.TestCase):
    @patch.object(cycle, "record_object")
    @patch.object(cycle, "shadow_paper_status")
    @patch.object(cycle, "build_grok_value_scorecard")
    @patch.object(cycle, "build_paper_value_report")
    @patch.object(cycle, "build_false_positive_report")
    @patch.object(cycle, "build_discovery_lead_time_report")
    @patch.object(cycle, "refresh_shadow_pairs")
    @patch.object(cycle, "enroll_shadow_pairs")
    @patch.object(cycle, "_run_concurrent_sources")
    @patch.object(cycle, "_native_universe")
    def test_cycle_consolidates_measurement_without_execution(
        self,
        native_universe,
        concurrent,
        enroll,
        refresh,
        lead,
        false_positive,
        paper,
        scorecard,
        shadow_status,
        record_object,
    ):
        native_universe.return_value = [{"ticker": "ABC", "label": "ABC", "query": "ABC"}]
        concurrent.return_value = (
            {"opportunity_scan_id": "scan_1", "scanned_count": 1, "queued_count": 1},
            None,
            {
                "discovery": {"nominated_count": 1, "quarantined_count": 0},
                "resolved_this_probe": 1,
                "xai_discovery_batches": 1,
            },
            None,
        )
        enroll.return_value = {"enrolled_count": 4}
        refresh.return_value = {"snapshot_count": 4}
        lead.return_value = {
            "raw_forward_pair_count": 1,
            "same_cycle_pair_count": 1,
            "prospective_pair_count": 0,
            "prospective_grok_earlier_count": 0,
            "prospective_iios_earlier_count": 0,
            "prospective_median_grok_lead_minutes": None,
            "minimum_prospective_separation_minutes": 10.0,
        }
        false_positive.return_value = {
            "nomination_count": 1,
            "resolved_count": 1,
            "validated_count": 1,
            "rejected_count": 0,
            "false_positive_rate": 0.0,
        }
        paper.return_value = {"cases_with_realized_return": 0, "return_comparison_ready": False}
        scorecard.return_value = {
            "scorecard_version": "test",
            "status": "VALUE_PROOF_IN_PROGRESS",
            "milestones": {},
            "promotion_blockers": ["more observations"],
        }
        shadow_status.return_value = {
            "pair_count": 4,
            "snapshot_count": 4,
            "differentiated_action_pair_count": 0,
        }

        out = cycle.run_forward_value_cycle({"query": "test", "max_candidates": 1})
        self.assertEqual(out["status"], "COMPLETE")
        self.assertEqual(out["grok"]["xai_discovery_batches"], 1)
        self.assertEqual(out["lead_time"]["prospective_pair_count"], 0)
        self.assertFalse(out["measurement_integrity"]["same_cycle_pairs_count_as_lead_time"])
        self.assertTrue(out["measurement_integrity"]["native_scan_independent_of_grok_nominations"])
        self.assertFalse(out["automatic_case_promotion"])
        self.assertFalse(out["automatic_agent_run"])
        self.assertFalse(out["auto_trade_authority"])
        self.assertFalse(out["paper_order_permission"])
        self.assertFalse(out["trade_execution_permission"])
        self.assertFalse(out["live_execution"])
        record_object.assert_called_once()

    def test_plan_never_creates_orders_or_promotes(self):
        out = cycle.forward_value_cycle_plan()
        self.assertFalse(out["same_cycle_pairs_count_as_lead_time"])
        self.assertFalse(out["automatic_case_promotion"])
        self.assertFalse(out["automatic_agent_run"])
        self.assertEqual(out["actual_paper_orders_created"], 0)
        self.assertFalse(out["trade_execution_permission"])
        self.assertFalse(out["live_execution"])


if __name__ == "__main__":
    unittest.main()
