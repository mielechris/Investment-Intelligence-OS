import unittest
from unittest.mock import patch

import grok_discovery_lead_time as lead
import grok_false_positive_tracker as fp
import grok_paper_value as paper
import grok_value_scorecard as value


class GrokValueMeasurementTests(unittest.TestCase):
    @patch.object(lead, "_rows")
    def test_lead_time_positive_when_grok_is_earlier(self, rows):
        def fake(kind):
            if kind == "grok_value_discovery_observation":
                return []
            if kind == "grok_opportunity_candidate":
                return [{"ticker": "ABC", "created_at": "2026-01-01T10:00:00+00:00", "eligible_for_iios_revalidation": True}]
            if kind == "opportunity_candidate":
                return [{"ticker": "ABC", "created_at": "2026-01-01T10:30:00+00:00"}]
            return []
        rows.side_effect = fake
        out = lead.build_discovery_lead_time_report()
        self.assertEqual(out["measurable_pair_count"], 1)
        self.assertEqual(out["prospective_pair_count"], 0)
        self.assertEqual(out["grok_earlier_count"], 1)
        self.assertEqual(out["rows"][0]["grok_lead_minutes"], 30.0)
        self.assertFalse(out["trade_execution_permission"])

    @patch.object(fp, "get_object")
    @patch.object(fp, "_rows")
    def test_false_positive_requires_independent_iios_rejection(self, rows, get_object):
        rows.return_value = [{
            "grok_opportunity_candidate_id": "grok_opportunity_1",
            "ticker": "ABC",
            "eligible_for_iios_revalidation": True,
            "standard_candidate_id": "opportunity_1",
            "source_count": 2,
        }]
        get_object.return_value = {
            "score": 20,
            "eligible_for_promotion": False,
            "quote_cross_checked": True,
            "quote_provider_count": 2,
            "news_provider_count": 2,
        }
        out = fp.build_false_positive_report()
        self.assertEqual(out["resolved_count"], 1)
        self.assertEqual(out["rejected_count"], 1)
        self.assertEqual(out["false_positive_rate"], 1.0)
        self.assertEqual(out["standard_gate_definition"], "HARDENED_CROSSCHECKED_QUOTE_PLUS_MULTI_PROVIDER_NEWS_PATH")
        self.assertFalse(out["automatic_promotion"])

    @patch.object(paper, "_rows", return_value=[])
    @patch.object(paper, "latest_object")
    @patch.object(paper, "_valid_repeatability_results")
    def test_paper_value_refuses_to_claim_arm_pnl(self, results, latest, _rows):
        results.return_value = [{
            "case_id": "case_1",
            "comparison": {"baseline_disposition": "NO_TRADE", "grok_disposition": "NO_TRADE", "committee_disposition_changed": False},
        }]
        latest.return_value = {}
        out = paper.build_paper_value_report()
        self.assertFalse(out["return_comparison_ready"])
        self.assertFalse(out["arm_specific_pnl_available"])
        self.assertFalse(out["permanent_promotion_value_proof_ready"])
        self.assertFalse(out["trade_execution_permission"])

    @patch.object(value, "build_paper_value_report")
    @patch.object(value, "build_false_positive_report")
    @patch.object(value, "build_discovery_lead_time_report")
    @patch.object(value, "build_grok_scorecard")
    def test_combined_scorecard_requires_meaningful_samples_and_never_auto_promotes(self, repeatability, lead_time, false_positive, paper_value):
        repeatability.return_value = {"valid_repeatability_cases": 4, "aggregate": {"mean_confidence_delta": 0.14, "median_confidence_delta": 0.13, "disposition_change_cases": 0, "all_guards_clean": True}}
        lead_time.return_value = {
            "measurable_pair_count": 5,
            "prospective_pair_count": 5,
            "grok_earlier_count": 3,
            "iios_earlier_count": 2,
            "prospective_grok_earlier_count": 3,
            "prospective_iios_earlier_count": 2,
            "median_grok_lead_minutes": 12.0,
            "prospective_median_grok_lead_minutes": 12.0,
        }
        false_positive.return_value = {"nomination_count": 5, "resolved_count": 5, "validated_count": 4, "rejected_count": 1, "false_positive_rate": 0.2}
        paper_value.return_value = {
            "valid_ab_case_count": 4,
            "cases_with_position_monitor": 3,
            "cases_with_realized_return": 3,
            "shadow_pair_count": 4,
            "shadow_snapshot_count": 4,
            "differentiated_action_pair_count": 0,
            "shadow_measurement_ledger_ready": True,
            "return_comparison_ready": False,
        }
        out = value.build_grok_value_scorecard()
        self.assertEqual(out["status"], "VALUE_PROOF_IN_PROGRESS")
        self.assertTrue(out["milestones"]["four_case_repeatability_sample"])
        self.assertTrue(out["milestones"]["prospective_lead_time_sample_sufficient"])
        self.assertTrue(out["milestones"]["false_positive_sample_sufficient"])
        self.assertTrue(out["milestones"]["shadow_measurement_ledger_ready"])
        self.assertTrue(out["milestones"]["paper_outcome_sample_sufficient"])
        self.assertFalse(out["milestones"]["dual_arm_pnl_ready"])
        self.assertEqual(out["measurement_thresholds"]["prospective_lead_time_pairs"], 5)
        self.assertEqual(out["measurement_thresholds"]["resolved_grok_nominations"], 5)
        self.assertEqual(out["measurement_thresholds"]["realized_paper_outcomes"], 3)
        self.assertFalse(out["permanent_factory_promotion_ready"])
        self.assertFalse(out["automatic_configuration_change"])
        self.assertFalse(out["live_execution"])

    @patch.object(value, "build_paper_value_report")
    @patch.object(value, "build_false_positive_report")
    @patch.object(value, "build_discovery_lead_time_report")
    @patch.object(value, "build_grok_scorecard")
    def test_one_observation_cannot_clear_value_sample_blockers(self, repeatability, lead_time, false_positive, paper_value):
        repeatability.return_value = {"valid_repeatability_cases": 4, "aggregate": {}}
        lead_time.return_value = {"prospective_pair_count": 1}
        false_positive.return_value = {"resolved_count": 1}
        paper_value.return_value = {
            "cases_with_realized_return": 1,
            "shadow_measurement_ledger_ready": True,
            "return_comparison_ready": False,
        }
        out = value.build_grok_value_scorecard()
        self.assertFalse(out["milestones"]["prospective_lead_time_sample_sufficient"])
        self.assertFalse(out["milestones"]["false_positive_sample_sufficient"])
        self.assertFalse(out["milestones"]["paper_outcome_sample_sufficient"])
        self.assertTrue(any("at least 5 prospective" in blocker for blocker in out["promotion_blockers"]))
        self.assertTrue(any("at least 5 independently resolved" in blocker for blocker in out["promotion_blockers"]))
        self.assertTrue(any("at least 3 realized" in blocker for blocker in out["promotion_blockers"]))


if __name__ == "__main__":
    unittest.main()
