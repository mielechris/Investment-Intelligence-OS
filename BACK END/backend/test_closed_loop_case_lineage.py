import unittest
from unittest.mock import patch

import closed_loop_case_lineage as lineage


class ClosedLoopCaseLineageTests(unittest.TestCase):
    def _latest_side_effect(self, values):
        def side_effect(object_type, case_id=None):
            return values.get(object_type, {})
        return side_effect

    @patch.object(lineage, "_capital_status", return_value={"stage": "RESEARCH_NOT_QUALIFIED"})
    @patch.object(lineage, "latest_object")
    @patch.object(lineage, "get_object")
    def test_no_trade_with_deep_watch_is_valid_closed_loop(
        self,
        get_object,
        latest_object,
        _capital_status,
    ):
        get_object.return_value = {"case_id": "case_mu", "topic": "Micron"}
        latest_object.side_effect = self._latest_side_effect(
            {
                "committee_decision": {"decision_id": "d1", "disposition": "NO_TRADE", "confidence": 0.9},
                "risk_authorization": {"risk_authorization_id": "r1", "decision": "VETOED"},
                "qualification_assessment": {"qualification_assessment_id": "q1", "qualified_buy_candidate": False, "stage": "NO_TRADE"},
                "monitor_profile": {"monitor_profile_id": "m1", "enabled": True},
                "deep_watch_obligation_set": {"deep_watch_obligation_set_id": "dw1", "obligation_count": 6},
            }
        )

        result = lineage.build_case_lineage("case_mu")

        self.assertEqual(result["continuity_state"], "CLOSED_LOOP_NO_CAPITAL_PATH")
        self.assertTrue(result["valid_no_capital_outcome"])
        self.assertFalse(result["dead_end"])
        self.assertTrue(result["monitoring_active"])
        self.assertTrue(result["deep_watch_active"])
        self.assertFalse(result["trade_execution_permission"])
        self.assertFalse(result["live_execution"])

    @patch.object(lineage, "_capital_status", return_value={"stage": "RESEARCH_NOT_QUALIFIED"})
    @patch.object(lineage, "latest_object")
    @patch.object(lineage, "get_object")
    def test_rejected_case_without_monitoring_is_flagged_dead_end(
        self,
        get_object,
        latest_object,
        _capital_status,
    ):
        get_object.return_value = {"case_id": "case_x", "topic": "Example"}
        latest_object.side_effect = self._latest_side_effect(
            {
                "committee_decision": {"decision_id": "d1", "disposition": "NO_TRADE", "confidence": 0.8},
                "qualification_assessment": {"qualification_assessment_id": "q1", "qualified_buy_candidate": False},
            }
        )

        result = lineage.build_case_lineage("case_x")

        self.assertEqual(result["continuity_state"], "RESEARCH_DECISION_WITHOUT_MONITORING")
        self.assertTrue(result["dead_end"])
        self.assertIn("MONITOR_OR_DEEP_WATCH", result["missing_continuation"])

    @patch.object(lineage, "_capital_status", return_value={"stage": "READY_FOR_POSITION_SIZING"})
    @patch.object(lineage, "latest_object")
    @patch.object(lineage, "get_object")
    def test_completed_paper_execution_is_capital_closed_loop(
        self,
        get_object,
        latest_object,
        _capital_status,
    ):
        get_object.return_value = {"case_id": "case_y", "topic": "Example"}
        latest_object.side_effect = self._latest_side_effect(
            {
                "committee_decision": {"decision_id": "d1", "disposition": "WATCH", "confidence": 0.9},
                "qualification_assessment": {"qualification_assessment_id": "q1", "qualified_buy_candidate": True, "stage": "QUALIFIED_BUY_CANDIDATE"},
                "paper_authorization": {"paper_authorization_id": "a1", "decision": "AUTHORIZED_FOR_PAPER_HANDOFF"},
                "governed_paper_execution": {"execution_id": "e1", "status": "COMPLETE", "execution": "PAPER_ORDER_CREATED"},
                "monitor_profile": {"monitor_profile_id": "m1", "enabled": True},
            }
        )

        result = lineage.build_case_lineage("case_y")

        self.assertEqual(result["continuity_state"], "CLOSED_LOOP_CAPITAL_PATH")
        self.assertEqual(result["current_stage"], "PAPER_POSITION_OPENED")
        self.assertTrue(result["paper_execution_complete"])
        self.assertFalse(result["dead_end"])

    def test_lineage_routes_are_read_only(self):
        paths = {route.path.lower(): {method.upper() for method in (route.methods or set())} for route in lineage.router.routes}
        self.assertIn("/closed-loop/{case_id}/status", paths)
        self.assertIn("/closed-loop/overview", paths)
        self.assertEqual(paths["/closed-loop/{case_id}/status"], {"GET"})
        self.assertEqual(paths["/closed-loop/overview"], {"GET"})


if __name__ == "__main__":
    unittest.main()
