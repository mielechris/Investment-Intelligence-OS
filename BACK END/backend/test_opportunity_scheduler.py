import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import opportunity_scheduler as scheduler


class OpportunitySchedulerTests(unittest.TestCase):

    def base_config(self, **overrides):
        value = {
            "opportunity_automation_config_id": scheduler.CONFIG_ID,
            "enabled": True,
            "auto_dispatch_enabled": False,
            "interval_minutes": 240,
            "news_limit": 8,
            "max_candidates": 10,
            "dispatch_limit": 1,
            "dispatch_mode": "BOUNDED_RESEARCH_QUEUE",
            "last_scan_at": None,
            "last_scan_status": None,
            "last_error": None,
            "paper_mode": True,
            "auto_trade_authority": False,
            "paper_order_permission": False,
            "trade_execution_permission": False,
            "live_execution": False,
        }
        value.update(overrides)
        return value

    def test_defaults_are_disabled_and_never_auto_dispatch(self):
        with patch.object(scheduler, "_bool_env", side_effect=lambda name, default: default):
            config = scheduler.default_config()
        self.assertFalse(config["enabled"])
        self.assertFalse(config["auto_dispatch_enabled"])
        self.assertEqual(config["interval_minutes"], 240)
        self.assertEqual(config["dispatch_mode"], "BOUNDED_RESEARCH_QUEUE")
        self.assertFalse(config["auto_trade_authority"])
        self.assertFalse(config["paper_order_permission"])
        self.assertFalse(config["trade_execution_permission"])
        self.assertFalse(config["live_execution"])

    @patch("opportunity_scheduler.latest_object", return_value=None)
    def test_config_is_hard_bounded(self, latest):
        config = scheduler.normalize_config({
            "interval_minutes": 1,
            "news_limit": 999,
            "max_candidates": 999,
            "dispatch_limit": 999,
            "auto_dispatch_enabled": True,
        })
        self.assertEqual(config["interval_minutes"], scheduler.MIN_INTERVAL_MINUTES)
        self.assertEqual(config["news_limit"], scheduler.MAX_NEWS_LIMIT)
        self.assertEqual(config["max_candidates"], scheduler.DEFAULT_MAX_CANDIDATES)
        self.assertEqual(config["dispatch_limit"], scheduler.MAX_AUTO_DISPATCH)
        self.assertEqual(config["dispatch_mode"], "BOUNDED_RESEARCH_QUEUE")
        self.assertFalse(config["enabled"])

    def test_disabled_config_is_never_due(self):
        now = datetime(2026, 8, 24, 19, 0, tzinfo=timezone.utc)
        self.assertFalse(scheduler._is_due(self.base_config(enabled=False, last_scan_at=None), now))

    def test_due_logic_respects_four_hour_floor(self):
        now = datetime(2026, 8, 24, 19, 0, tzinfo=timezone.utc)
        self.assertTrue(scheduler._is_due(self.base_config(last_scan_at=None), now))
        recent = (now - timedelta(minutes=120)).isoformat()
        self.assertFalse(scheduler._is_due(self.base_config(last_scan_at=recent), now))
        old = (now - timedelta(minutes=241)).isoformat()
        self.assertTrue(scheduler._is_due(self.base_config(last_scan_at=old), now))

    @patch("opportunity_scheduler.record_event")
    @patch("opportunity_scheduler.record_object")
    @patch("opportunity_scheduler.enqueue_ranked_opportunities")
    @patch("opportunity_scheduler.scan_universe")
    @patch("opportunity_scheduler.run_market_event_radar")
    @patch("opportunity_scheduler.normalize_config")
    def test_cycle_scans_radar_without_agent_dispatch_when_explicitly_enabled(
        self, normalize, radar, scan, enqueue, record_object, record_event
    ):
        normalize.return_value = self.base_config(auto_dispatch_enabled=False)
        radar.return_value = {
            "market_event_radar_id": "radar_test",
            "event_count": 12,
            "trade_execution_permission": False,
        }
        scan.return_value = {
            "opportunity_scan_id": "scan_test",
            "scanned_count": 16,
            "queued_count": 3,
        }
        result = scheduler.run_automation_cycle(self.base_config())
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["radar"]["event_count"], 12)
        self.assertEqual(result["dispatch"]["reason"], "AUTO_DISPATCH_DISABLED")
        self.assertEqual(result["dispatch"]["agents_started"], 0)
        radar.assert_called_once_with()
        enqueue.assert_not_called()
        self.assertFalse(result["auto_trade_authority"])
        self.assertFalse(result["paper_order_permission"])
        self.assertFalse(result["trade_execution_permission"])
        self.assertFalse(result["live_execution"])

    @patch("opportunity_scheduler.record_event")
    @patch("opportunity_scheduler.record_object")
    @patch("opportunity_scheduler.enqueue_ranked_opportunities")
    @patch("opportunity_scheduler.scan_universe")
    @patch("opportunity_scheduler.run_market_event_radar")
    @patch("opportunity_scheduler.normalize_config")
    def test_opt_in_dispatch_queues_one_candidate_without_starting_agents(
        self, normalize, radar, scan, enqueue, record_object, record_event
    ):
        normalize.return_value = self.base_config(auto_dispatch_enabled=True, dispatch_limit=1)
        radar.return_value = {
            "market_event_radar_id": "radar_test",
            "event_count": 12,
        }
        scan.return_value = {
            "opportunity_scan_id": "scan_test",
            "scanned_count": 16,
            "queued_count": 3,
        }
        enqueue.return_value = {
            "status": "complete",
            "selected": 1,
            "results": [],
            "paper_mode": True,
            "trade_execution_permission": False,
            "live_execution": False,
        }
        result = scheduler.run_automation_cycle(self.base_config(auto_dispatch_enabled=True))
        enqueue.assert_called_once_with(limit=1)
        self.assertEqual(result["dispatch"]["selected"], 1)
        self.assertEqual(result["dispatch"]["mode"], "BOUNDED_RESEARCH_QUEUE")
        self.assertEqual(result["dispatch"]["agents_started"], 0)
        self.assertFalse(result["trade_execution_permission"])
        self.assertFalse(result["live_execution"])

    def test_scheduler_routes_expose_no_trade_or_execution_controls(self):
        paths = {route.path.lower() for route in scheduler.router.routes if hasattr(route, "path")}
        self.assertIn("/opportunities/automation", paths)
        self.assertIn("/opportunities/automation/run-now", paths)
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
