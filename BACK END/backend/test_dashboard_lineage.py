import unittest

from dashboard_lineage import apply_latest_decision_lineage


class DashboardLineageTests(unittest.TestCase):
    def test_latest_committee_decision_overrides_stale_monitor_snapshot(self):
        row = {
            "committee_disposition": "WATCH",
            "committee_confidence": 0.86,
            "evidence_quality": 0.51,
            "latest_evidence_count": 25,
            "latest_action": "WATCH",
        }
        decision = {
            "decision_id": "decision_latest",
            "disposition": "NO_TRADE",
            "confidence": 0.91,
            "evidence_summary": {"average_quality_score": 0.72, "evidence_count": 17},
        }
        snapshot = {"evidence_packet": {"summary": {"average_quality_score": 0.51, "evidence_count": 25}}}
        result = apply_latest_decision_lineage(row, decision=decision, snapshot=snapshot)
        self.assertEqual(result["committee_disposition"], "NO_TRADE")
        self.assertEqual(result["committee_confidence"], 0.91)
        self.assertEqual(result["evidence_quality"], 0.72)
        self.assertEqual(result["latest_evidence_count"], 17)
        self.assertEqual(result["latest_action"], "NO_TRADE")
        self.assertEqual(result["latest_research_source"], "COMMITTEE_DECISION")

    def test_matching_qualification_can_refine_latest_action(self):
        decision = {
            "decision_id": "decision_latest",
            "disposition": "WATCH",
            "confidence": 0.84,
            "evidence_summary": {"average_quality_score": 0.70, "evidence_count": 18},
        }
        qualification = {
            "decision_id": "decision_latest",
            "stage": "QUALIFIED_BUY_CANDIDATE",
            "qualified_buy_candidate": True,
        }
        result = apply_latest_decision_lineage({}, decision=decision, qualification=qualification)
        self.assertEqual(result["latest_action"], "QUALIFIED_BUY_CANDIDATE")
        self.assertTrue(result["qualified_buy_candidate"])

    def test_stale_qualification_cannot_override_newer_decision(self):
        decision = {
            "decision_id": "decision_new",
            "disposition": "NO_TRADE",
            "confidence": 0.91,
            "evidence_summary": {"average_quality_score": 0.72, "evidence_count": 17},
        }
        qualification = {
            "decision_id": "decision_old",
            "stage": "WATCH",
            "qualified_buy_candidate": False,
        }
        result = apply_latest_decision_lineage({}, decision=decision, qualification=qualification)
        self.assertEqual(result["latest_action"], "NO_TRADE")
        self.assertNotIn("qualification_stage", result)


if __name__ == "__main__":
    unittest.main()
