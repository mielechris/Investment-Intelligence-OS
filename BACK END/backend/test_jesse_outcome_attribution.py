import unittest
from unittest.mock import patch

import jesse_outcome_attribution as attribution


class JesseOutcomeAttributionTests(unittest.TestCase):
    def test_target_assessment_does_not_overclaim_full_thesis(self):
        self.assertEqual(
            attribution._target_assessment("NO_TRADE", False),
            "NO_TRADE_TARGET_NOT_HIT",
        )
        self.assertEqual(
            attribution._target_assessment("NO_TRADE", True),
            "NO_TRADE_MISSED_TARGET_UPSIDE",
        )
        self.assertEqual(attribution._target_assessment("WATCH", True), "TARGET_HIT")
        self.assertEqual(attribution._target_assessment("BUY", False), "TARGET_MISSED")

    def test_wrong_vs_early_requires_governed_thesis(self):
        self.assertEqual(
            attribution._wrong_vs_early_label(None, None),
            "NOT_APPLICABLE_NO_GOVERNED_THESIS",
        )
        self.assertEqual(
            attribution._wrong_vs_early_label(
                {"thesis_integrity_state": "EARLY_BUT_INTACT"}, "case_1"
            ),
            "EARLY",
        )
        self.assertEqual(
            attribution._wrong_vs_early_label(
                {"thesis_integrity_state": "THESIS_BROKEN"}, "case_1"
            ),
            "WRONG",
        )

    @patch.object(attribution, "latest_object")
    @patch.object(attribution, "get_object")
    def test_rejected_jesse_candidate_attribution_is_shadow_only(self, get_object, latest_object):
        scan = {
            "dislocation_scan_id": "scan_1",
            "opportunity_candidate_ids": ["opportunity_1"],
            "top_three": [
                {
                    "ticker": "AAA",
                    "company": "Alpha",
                    "recommendation": "NO_TRADE",
                    "financial_strength_score": 50,
                    "estimated_probability_next_day_plus_5": 0.18,
                }
            ],
            "bridge": {
                "results": [
                    {
                        "candidate_id": "opportunity_1",
                        "ticker": "AAA",
                        "status": "SKIPPED_RESEARCH_GATE",
                        "case_id": None,
                    }
                ]
            },
        }
        candidate = {
            "opportunity_candidate_id": "opportunity_1",
            "ticker": "AAA",
            "label": "Alpha",
            "promoted_case_id": None,
        }
        get_object.side_effect = lambda object_id: {
            "scan_1": scan,
            "opportunity_1": candidate,
        }.get(object_id)
        latest_object.return_value = None

        result = attribution.build_outcome_attribution(
            {
                "dislocation_outcome_id": "outcome_1",
                "dislocation_scan_id": "scan_1",
                "ticker": "AAA",
                "baseline_price": 100.0,
                "followup_price": 99.0,
                "return_pct": -1.0,
                "target_upside_pct": 5.0,
                "target_hit": False,
                "original_recommendation": "NO_TRADE",
            }
        )

        self.assertEqual(result["bridge_status"], "SKIPPED_RESEARCH_GATE")
        self.assertEqual(result["target_assessment"], "NO_TRADE_TARGET_NOT_HIT")
        self.assertEqual(result["wrong_vs_early"], "NOT_APPLICABLE_NO_GOVERNED_THESIS")
        self.assertFalse(result["paper_position_created"])
        self.assertTrue(result["learning_scope"]["next_day_target_is_not_full_thesis_proof"])
        self.assertFalse(result["auto_trade_authority"])
        self.assertFalse(result["paper_order_permission"])
        self.assertFalse(result["trade_execution_permission"])
        self.assertFalse(result["live_execution"])

    @patch.object(attribution, "assess_thesis_integrity_v2")
    @patch.object(attribution, "latest_object")
    @patch.object(attribution, "get_object")
    def test_promoted_case_uses_thesis_integrity_for_wrong_vs_early(
        self, get_object, latest_object, assess_integrity
    ):
        scan = {
            "dislocation_scan_id": "scan_2",
            "opportunity_candidate_ids": ["opportunity_2"],
            "top_three": [
                {
                    "ticker": "BBB",
                    "company": "Beta",
                    "recommendation": "WATCH",
                    "financial_strength_score": 78,
                    "estimated_probability_next_day_plus_5": 0.34,
                }
            ],
            "bridge": {
                "results": [
                    {
                        "candidate_id": "opportunity_2",
                        "ticker": "BBB",
                        "status": "DISPATCHED",
                        "case_id": "case_beta",
                    }
                ]
            },
        }
        candidate = {
            "opportunity_candidate_id": "opportunity_2",
            "ticker": "BBB",
            "promoted_case_id": "case_beta",
        }
        get_object.side_effect = lambda object_id: {
            "scan_2": scan,
            "opportunity_2": candidate,
        }.get(object_id)

        def latest(object_type, *, case_id=None, topic=None):
            if object_type == "committee_decision":
                return {"decision_id": "decision_1", "disposition": "WATCH", "confidence": 0.75}
            if object_type == "governed_paper_execution":
                return {}
            return {}

        latest_object.side_effect = latest
        assess_integrity.return_value = {
            "case_id": "case_beta",
            "thesis_integrity_state": "EARLY_BUT_INTACT",
            "price_alone_can_break_thesis": False,
            "evidence_required_to_break_thesis": True,
        }

        result = attribution.build_outcome_attribution(
            {
                "dislocation_outcome_id": "outcome_2",
                "dislocation_scan_id": "scan_2",
                "ticker": "BBB",
                "baseline_price": 100.0,
                "followup_price": 92.0,
                "return_pct": -8.0,
                "target_hit": False,
                "original_recommendation": "WATCH",
            }
        )

        self.assertEqual(result["case_id"], "case_beta")
        self.assertEqual(result["wrong_vs_early"], "EARLY")
        self.assertEqual(result["target_assessment"], "TARGET_MISSED")
        self.assertFalse(result["live_execution"])


if __name__ == "__main__":
    unittest.main()
