import unittest
from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

import jesse_scheduler as scheduler


class DeepCaseHistoricalRecheckSchedulerTests(unittest.TestCase):
    @patch.object(scheduler, "record_event")
    @patch.object(scheduler, "record_object")
    @patch.object(scheduler, "dislocation_calibration")
    @patch.object(scheduler, "save_state")
    @patch.object(scheduler, "sweep_deep_cases")
    @patch.object(scheduler, "state")
    def test_forced_historical_recheck_sweeps_deep_cases_without_trade_authority(
        self,
        state,
        sweep,
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
            "last_historical_recheck_at": now_iso,
        }
        sweep.return_value = {
            "checked_cases": 12,
            "deep_cases": 4,
            "rechecked_cases": 2,
            "reunderwrite_required": 1,
            "historical_signals": {"HISTORICAL_SUPPORT": 1, "MIXED_PRECEDENT": 1},
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
            "observation_count": 0,
            "calibrated": False,
            "trade_execution_permission": False,
            "live_execution": False,
        }

        result = scheduler.run_cycle(["historical_recheck"])

        sweep.assert_called_once_with()
        self.assertEqual(result["results"]["historical_recheck"]["deep_cases"], 4)
        self.assertFalse(result["auto_trade_authority"])
        self.assertFalse(result["trade_execution_permission"])
        self.assertFalse(result["live_execution"])

    def test_historical_recheck_routes_are_registered(self):
        paths = {
            getattr(route, "path", None)
            for route in scheduler.router.routes
        }
        self.assertIn("/intelligence/historical-recheck/status", paths)
        self.assertIn("/intelligence/historical-recheck/run-now", paths)


if __name__ == "__main__":
    unittest.main()
