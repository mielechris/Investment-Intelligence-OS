import unittest
from unittest.mock import patch

import grok_experiment_scorecard as scorecard


def result(case_id, created_at, delta, *, valid=True, runs=2, evidence_delta=0.0):
    return {
        "case_id": case_id,
        "created_at": created_at,
        "runs_per_arm": runs,
        "new_xai_search_calls": 0,
        "auto_trade_authority": False,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
        "grok_context_summary": {"citation_count": 50, "admitted_count": 5},
        "comparison": {
            "experiment_valid": valid,
            "committee_disposition_changed": False,
            "confidence_delta": delta,
            "required_evidence_count_delta": evidence_delta,
            "baseline": {
                "dispositions": ["NO_TRADE", "NO_TRADE"],
                "median_confidence": 0.5,
                "median_latency_ms": 30000,
                "all_guards_clean": True,
            },
            "iios_plus_grok": {
                "dispositions": ["NO_TRADE", "NO_TRADE"],
                "median_confidence": 0.5 + delta,
                "median_latency_ms": 32000,
                "all_guards_clean": True,
            },
        },
    }


class GrokExperimentScorecardTests(unittest.TestCase):
    def test_selects_latest_valid_repeatability_result_per_case(self):
        rows = [
            result("case_a", "2026-01-01T00:00:00+00:00", -0.4, valid=False),
            result("case_a", "2026-01-02T00:00:00+00:00", -0.05),
            result("case_b", "2026-01-02T00:00:00+00:00", 0.3),
            result("case_b", "2026-01-03T00:00:00+00:00", 0.9, runs=1),
        ]
        selected = scorecard._selected_results(rows)
        self.assertEqual(len(selected), 2)
        by_case = {row["case_id"]: row for row in selected}
        self.assertEqual(by_case["case_a"]["comparison"]["confidence_delta"], -0.05)
        self.assertEqual(by_case["case_b"]["comparison"]["confidence_delta"], 0.3)

    @patch.object(scorecard, "get_object", return_value={"topic": "test"})
    @patch.object(scorecard, "_all_results")
    def test_scorecard_is_interim_and_never_auto_promotes(self, all_results, _case):
        all_results.return_value = [
            result("case_a", "2026-01-01T00:00:00+00:00", 0.30),
            result("case_b", "2026-01-01T00:00:01+00:00", 0.295, evidence_delta=0.5),
            result("case_c", "2026-01-01T00:00:02+00:00", -0.05),
        ]
        out = scorecard.build_grok_scorecard()
        self.assertEqual(out["valid_repeatability_cases"], 3)
        self.assertEqual(out["status"], "INTERIM_SIGNAL_AVAILABLE")
        self.assertAlmostEqual(out["aggregate"]["mean_confidence_delta"], 0.1817, places=4)
        self.assertEqual(out["aggregate"]["confidence_increase_cases"], 2)
        self.assertEqual(out["aggregate"]["confidence_decrease_cases"], 1)
        self.assertTrue(out["aggregate"]["all_safety_locked"])
        self.assertFalse(out["permanent_factory_promotion_ready"])
        self.assertFalse(out["automatic_configuration_change"])
        self.assertFalse(out["trade_execution_permission"])
        self.assertFalse(out["live_execution"])


if __name__ == "__main__":
    unittest.main()
