import unittest
from unittest.mock import patch

import evidence_depth_engine as depth


class EvidenceDepthEngineTests(unittest.TestCase):
    def test_atomic_facts_split_compound_requirement(self):
        facts = depth.atomic_facts("Latest 10-Q, segment margins, capex and free cash flow")
        self.assertGreaterEqual(len(facts), 3)
        self.assertLessEqual(len(facts), depth.MAX_FACTS_PER_REQUIREMENT)

    @patch.object(depth, "record_event")
    @patch.object(depth, "record_object")
    @patch.object(depth, "list_objects")
    @patch.object(depth, "latest_object")
    @patch.object(depth, "get_object")
    def test_plan_is_research_only_and_fail_closed(self, get_object, latest_object, list_objects, record_object, record_event):
        get_object.return_value = {"case_id": "case_test", "topic": "Test opportunity"}
        latest_object.return_value = {
            "decision_id": "decision_test",
            "required_evidence": ["Current valuation and portfolio overlap"],
        }
        list_objects.return_value = []
        plan = depth.build_evidence_depth_plan("case_test")
        self.assertGreaterEqual(plan["atomic_fact_count"], 1)
        self.assertTrue(plan["research_only"])
        self.assertFalse(plan["auto_trade_authority"])
        self.assertFalse(plan["paper_order_permission"])
        self.assertFalse(plan["trade_execution_permission"])
        self.assertFalse(plan["live_execution"])
        record_object.assert_called_once()
        record_event.assert_called_once()


if __name__ == "__main__":
    unittest.main()
