import unittest
from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

import jesse_scheduler as scheduler


class JesseOutcomeSchedulerIntegrationTests(unittest.TestCase):
    @patch.object(scheduler, "record_event")
    @patch.object(scheduler, "record_object")
    @patch.object(scheduler, "dislocation_calibration")
    @patch.object(scheduler, "save_state")
    @patch.object(scheduler, "refresh_all_jesse_outcome_attributions")
    @patch.object(scheduler, "settle_dislocation_outcomes")
    @patch.object(scheduler, "state")
    def test_forced_followup_settles_then_attributes_without_trade_authority(
        self,
        state,
        settle,
        refresh,
        save_state,
        calibration,
        record_object,
        record_event,
    ):
        today = datetime.now(ZoneInfo("America/Los_Angeles")).date().isoformat()
        now_iso = datetime.now(ZoneInfo("UTC")).isoformat()
        state.return_value = {
            **scheduler.default_state(),
            "enabled": True,
            "last_public_research_date": today,
            "last_dislocation_date": today,
            "last_followup_date": today,
            "last_inbox_at": now_iso,
            "last_fed_at": now_iso,
            "last_tariff_at": now_iso,
        }
        settle.return_value = {
            "settled_count": 3,
            "skipped_count": 0,
            "outcomes": [{"ticker": "AAA"}],
            "trade_execution_permission": False,
            "live_execution": False,
        }
        refresh.return_value = {
            "refreshed_count": 3,
            "summary": {"observations": 3},
            "trade_execution_permission": False,
            "live_execution": False,
        }
        save_state.side_effect = lambda value: {
            **value,
            "paper_mode": True,
            "auto_trade_authority": False,
            "trade_execution_permission": False,
            "live_execution": False,
        }
        calibration.return_value = {
            "observation_count": 3,
            "calibrated": False,
            "trade_execution_permission": False,
            "live_execution": False,
        }

        result = scheduler.run_cycle(["followup"])

        settle.assert_called_once()
        refresh.assert_called_once_with()
        followup = result["results"]["followup"]
        self.assertEqual(followup["settled_count"], 3)
        self.assertEqual(followup["attribution"]["refreshed_count"], 3)
        self.assertFalse(result["auto_trade_authority"])
        self.assertFalse(result["trade_execution_permission"])
        self.assertFalse(result["live_execution"])

    def test_outcome_router_is_nested_under_scheduler_router(self):
        paths = {route.path for route in scheduler.router.routes}
        self.assertIn("/intelligence/jesse-outcomes/status", paths)
        self.assertIn("/intelligence/jesse-outcomes/refresh", paths)


if __name__ == "__main__":
    unittest.main()
