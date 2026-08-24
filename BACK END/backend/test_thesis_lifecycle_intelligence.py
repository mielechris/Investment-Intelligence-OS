import unittest
from unittest.mock import patch

import thesis_lifecycle_intelligence as lifecycle


class ThesisLifecycleIntelligenceTests(unittest.TestCase):
    @patch.object(lifecycle, "latest_object")
    @patch.object(lifecycle, "get_object")
    def test_broken_thesis_requests_reunderwrite_without_execution(self, get_object, latest_object):
        get_object.return_value = {"case_id": "case_test", "topic": "Test"}

        def latest(object_type, case_id=None, **kwargs):
            if object_type == "committee_decision":
                return {"decision_id": "decision_test"}
            if object_type == "thesis_monitor":
                return {
                    "thesis_status": "THESIS_BROKEN",
                    "flags": ["FALSIFIER_TRIGGERED"],
                    "catalyst_status": "MISSED",
                }
            return {}

        latest_object.side_effect = latest
        result = lifecycle.assess_thesis_lifecycle("case_test")
        self.assertEqual(result["action"], "REUNDERWRITE_REQUIRED")
        self.assertIn("skeptic", result["targeted_desks"])
        self.assertFalse(result["automatic_agent_rerun"])
        self.assertFalse(result["paper_order_permission"])
        self.assertFalse(result["trade_execution_permission"])
        self.assertFalse(result["live_execution"])

    @patch.object(lifecycle, "record_event")
    @patch.object(lifecycle, "record_object")
    @patch.object(lifecycle, "assess_thesis_lifecycle")
    def test_request_records_research_request_only(self, assess, record_object, record_event):
        assess.return_value = {
            "case_id": "case_test",
            "topic": "Test",
            "decision_id": "decision_test",
            "action": "REUNDERWRITE_REQUIRED",
            "lifecycle_state": "MATERIAL_CHANGE",
            "thesis_status": "REUNDERWRITE_REQUIRED",
            "thesis_flags": ["CATALYST_MISSED"],
            "targeted_desks": ["skeptic", "portfolio", "fundamentals"],
        }
        result = lifecycle.record_reunderwrite_request("case_test")
        request = result["request"]
        self.assertEqual(request["agents_started"], 0)
        self.assertTrue(request["human_or_scheduler_drain_required"])
        self.assertFalse(request["trade_execution_permission"])
        record_object.assert_called_once()
        record_event.assert_called_once()


if __name__ == "__main__":
    unittest.main()
