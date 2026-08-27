import unittest
from unittest.mock import patch

import opportunity_dispatch as dispatch


class OpportunityDispatchTests(unittest.TestCase):

    @patch("opportunity_dispatch.record_event")
    @patch("opportunity_dispatch.opportunity_queue")
    def test_batch_dispatch_is_hard_capped(self, queue, record_event):
        queue.return_value = []
        self.assertEqual(dispatch.MAX_BATCH_DISPATCH, 3)
        result = dispatch.dispatch_ranked_queue(limit=99)
        self.assertLessEqual(result["requested"], 3)
        self.assertFalse(result["paper_order_permission"])
        self.assertFalse(result["trade_execution_permission"])
        self.assertFalse(result["live_execution"])

    def test_current_orchestration_with_history_is_not_rerun(self):
        candidate = {
            "opportunity_candidate_id": "opportunity_current",
            "eligible_for_promotion": True,
        }
        case = {"case_id": "case_current"}
        existing = {
            "orchestration_id": "orchestration_current",
            "agents": {
                "historical_pattern": {
                    "status": "complete",
                    "trade_execution_permission": False,
                    "live_execution": False,
                }
            },
        }
        with patch.object(dispatch, "get_object", return_value=candidate), patch.object(
            dispatch, "promote_candidate", return_value={"case": case}
        ), patch.object(dispatch, "latest_object", return_value=existing), patch.object(
            dispatch, "run_eight_agent_orchestration"
        ) as run:
            result = dispatch.dispatch_candidate("opportunity_current")

        run.assert_not_called()
        self.assertTrue(result["already_dispatched"])
        self.assertTrue(result["historical_review_complete"])
        self.assertFalse(result["upgraded_legacy_orchestration"])

    def test_legacy_eight_desk_orchestration_is_upgraded_before_reuse(self):
        candidate = {
            "opportunity_candidate_id": "opportunity_legacy",
            "eligible_for_promotion": True,
        }
        case = {"case_id": "case_legacy"}
        legacy = {
            "orchestration_id": "orchestration_legacy",
            "agents": {"portfolio": {"status": "complete"}},
        }
        upgraded = {
            "orchestration": {
                "orchestration_id": "orchestration_upgraded",
                "agents": {
                    "historical_pattern": {
                        "status": "complete",
                        "trade_execution_permission": False,
                        "live_execution": False,
                    }
                },
            },
            "historical_pattern": {"status": "complete"},
            "committee": {"disposition": "WATCH", "confidence": 0.71},
        }
        with patch.object(dispatch, "get_object", return_value=candidate), patch.object(
            dispatch, "promote_candidate", return_value={"case": case}
        ), patch.object(dispatch, "latest_object", return_value=legacy), patch.object(
            dispatch, "run_eight_agent_orchestration", return_value=upgraded
        ) as run, patch.object(dispatch, "record_event"):
            result = dispatch.dispatch_candidate("opportunity_legacy")

        run.assert_called_once_with("case_legacy")
        self.assertFalse(result["already_dispatched"])
        self.assertTrue(result["historical_review_complete"])
        self.assertTrue(result["upgraded_legacy_orchestration"])
        self.assertFalse(result["paper_order_permission"])
        self.assertFalse(result["trade_execution_permission"])
        self.assertFalse(result["live_execution"])

    def test_dispatch_routes_have_no_execution_or_authorization(self):
        paths = {route.path.lower() for route in dispatch.router.routes}
        self.assertIn("/opportunities/{candidate_id}/dispatch", paths)
        self.assertIn("/opportunities/dispatch-queue", paths)
        self.assertFalse(
            any(
                "paper-authorization" in path
                or "governed-paper-execution" in path
                or "broker" in path
                or "live" in path
                for path in paths
            )
        )


if __name__ == "__main__":
    unittest.main()
