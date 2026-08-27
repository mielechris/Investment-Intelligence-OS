import unittest
from unittest.mock import patch

import jesse_paper_fund_bridge as bridge


class JessePaperFundBridgeTests(unittest.TestCase):
    @patch.object(bridge, "record_event")
    @patch.object(bridge, "record_object")
    @patch.object(bridge, "latest_object")
    @patch.object(bridge, "dispatch_candidate")
    @patch.object(bridge, "get_object")
    def test_only_eligible_jesse_candidates_dispatch(
        self,
        get_object,
        dispatch_candidate,
        latest_object,
        record_object,
        record_event,
    ):
        candidates = {
            "opportunity_1": {
                "opportunity_candidate_id": "opportunity_1",
                "ticker": "AAA",
                "created_by": "DISLOCATION_SCANNER_V1",
                "eligible_for_promotion": True,
            },
            "opportunity_2": {
                "opportunity_candidate_id": "opportunity_2",
                "ticker": "BBB",
                "created_by": "DISLOCATION_SCANNER_V1",
                "eligible_for_promotion": False,
                "reason_codes": ["UNRESOLVED"],
            },
            "opportunity_3": {
                "opportunity_candidate_id": "opportunity_3",
                "ticker": "CCC",
                "created_by": "OTHER_SCANNER",
                "eligible_for_promotion": True,
            },
        }
        get_object.side_effect = lambda candidate_id: candidates.get(candidate_id)
        dispatch_candidate.return_value = {
            "case": {"case_id": "case_aaa"},
            "orchestration": {"orchestration_id": "orch_aaa"},
            "committee": {"disposition": "WATCH", "confidence": 0.81},
            "already_dispatched": False,
        }
        latest_object.return_value = {
            "disposition": "WATCH",
            "confidence": 0.81,
        }

        scan = {
            "dislocation_scan_id": "scan_1",
            "opportunity_candidate_ids": [
                "opportunity_1",
                "opportunity_2",
                "opportunity_3",
            ],
        }
        result = bridge.dispatch_jesse_top_three(scan)

        dispatch_candidate.assert_called_once_with("opportunity_1")
        self.assertEqual(result["top_three_count"], 3)
        self.assertEqual(result["dispatched_count"], 1)
        self.assertEqual(result["skipped_count"], 2)
        self.assertEqual(result["error_count"], 0)
        self.assertEqual(result["next_owner"], "BATCH_9B_GOVERNED_PAPER_TRADING")
        self.assertEqual(result["authority_scope"], "RESEARCH_DISPATCH_ONLY")
        self.assertFalse(result["auto_trade_authority"])
        self.assertFalse(result["paper_order_permission"])
        self.assertFalse(result["trade_execution_permission"])
        self.assertFalse(result["live_execution"])

        self.assertEqual(record_object.call_count, 2)
        scan_write = record_object.call_args_list[1]
        self.assertEqual(scan_write.args[0], "scan_1")
        self.assertEqual(scan_write.args[1], "dislocation_scan")
        self.assertEqual(scan_write.args[3]["bridge"]["dispatched_count"], 1)
        self.assertEqual(
            scan_write.args[3]["bridge"]["authority_scope"],
            "RESEARCH_DISPATCH_ONLY",
        )
        self.assertFalse(scan_write.args[3]["bridge"]["paper_order_permission"])
        self.assertFalse(scan_write.args[3]["bridge"]["live_execution"])
        record_event.assert_called_once()

    @patch.object(bridge, "record_event")
    @patch.object(bridge, "record_object")
    @patch.object(bridge, "latest_object")
    @patch.object(bridge, "dispatch_candidate")
    @patch.object(bridge, "get_object")
    def test_dispatch_failure_fails_closed_without_trade_authority(
        self,
        get_object,
        dispatch_candidate,
        latest_object,
        record_object,
        record_event,
    ):
        get_object.return_value = {
            "opportunity_candidate_id": "opportunity_1",
            "ticker": "AAA",
            "created_by": "DISLOCATION_SCANNER_V1",
            "eligible_for_promotion": True,
        }
        dispatch_candidate.side_effect = RuntimeError("provider unavailable")

        result = bridge.dispatch_jesse_top_three(
            {
                "dislocation_scan_id": "scan_2",
                "opportunity_candidate_ids": ["opportunity_1"],
            }
        )

        self.assertEqual(result["dispatched_count"], 0)
        self.assertEqual(result["error_count"], 1)
        self.assertEqual(result["results"][0]["status"], "ERROR")
        self.assertFalse(result["paper_order_permission"])
        self.assertFalse(result["trade_execution_permission"])
        self.assertFalse(result["live_execution"])
        self.assertEqual(record_object.call_count, 2)
        self.assertFalse(record_object.call_args_list[1].args[3]["bridge"]["live_execution"])


if __name__ == "__main__":
    unittest.main()
