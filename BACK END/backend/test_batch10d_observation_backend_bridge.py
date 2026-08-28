import io
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import iios_observation_runner as base_runner  # noqa: E402
import iios_observation_runner_10d as bridge  # noqa: E402


class _Response(io.BytesIO):
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()
        return False


class Batch10DObservationBackendBridgeTests(unittest.TestCase):
    @patch.object(bridge, "urlopen")
    def test_monitoring_refresh_uses_local_backend_and_stays_locked(self, urlopen):
        urlopen.return_value = _Response(
            json.dumps({"checked_profiles": 3, "due_profiles": 1, "results": []}).encode()
        )

        result = bridge.refresh_due_profiles_via_backend()

        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "http://127.0.0.1:8002/monitoring/refresh-due")
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(result["monitoring_authority"], "BACKEND_8002")
        self.assertTrue(result["paper_mode"])
        self.assertFalse(result["paper_order_permission"])
        self.assertFalse(result["trade_execution_permission"])
        self.assertFalse(result["live_execution"])

    def test_install_replaces_monitoring_radar_and_scan_hooks(self):
        original_monitoring = base_runner.refresh_due_profiles
        original_radar = base_runner.run_market_event_radar
        original_scan = base_runner.scan_universe
        try:
            installed = bridge.install_backend_monitoring_bridge()
            self.assertIs(installed, base_runner)
            self.assertIs(base_runner.refresh_due_profiles, bridge.refresh_due_profiles_via_backend)
            self.assertIs(base_runner.run_market_event_radar, bridge.run_market_event_radar_bounded)
            self.assertIs(base_runner.scan_universe, bridge.scan_universe_bounded)
        finally:
            base_runner.refresh_due_profiles = original_monitoring
            base_runner.run_market_event_radar = original_radar
            base_runner.scan_universe = original_scan

    @patch.object(bridge, "_run_with_timeout")
    def test_external_stages_use_governed_wall_clock_ceilings(self, bounded):
        bounded.side_effect = [{"event_count": 0}, {"scanned_count": 0}]

        radar = bridge.run_market_event_radar_bounded()
        scan = bridge.scan_universe_bounded(news_limit=8, max_candidates=10)

        self.assertEqual(radar["event_count"], 0)
        self.assertEqual(scan["scanned_count"], 0)
        self.assertEqual(bounded.call_args_list[0].args[1], bridge.RADAR_TIMEOUT_SECONDS)
        self.assertEqual(bounded.call_args_list[0].args[2], "MARKET_EVENT_RADAR")
        self.assertEqual(bounded.call_args_list[1].args[1], bridge.OPPORTUNITY_SCAN_TIMEOUT_SECONDS)
        self.assertEqual(bounded.call_args_list[1].args[2], "OPPORTUNITY_SCAN")
        self.assertEqual(bridge.RADAR_TIMEOUT_SECONDS, 120)
        self.assertEqual(bridge.OPPORTUNITY_SCAN_TIMEOUT_SECONDS, 180)

    def test_timeout_exception_is_caught_by_existing_safe_call(self):
        def timeout_stage():
            raise bridge.ObservationStageTimeout("MARKET_EVENT_RADAR_TIMEOUT_120s")

        result = base_runner._safe_call("market_event_radar", timeout_stage)

        self.assertEqual(result["status"], "error")
        self.assertIn("ObservationStageTimeout", result["error"])
        self.assertIn("TIMEOUT_120s", result["error"])

    def test_bridge_has_no_remote_or_broker_target(self):
        self.assertEqual(bridge.BACKEND_BASE_URL, "http://127.0.0.1:8002")
        self.assertNotIn("broker", bridge.MONITORING_PATH.lower())
        self.assertNotIn("execute", bridge.MONITORING_PATH.lower())
        self.assertFalse(hasattr(bridge, "broker"))


if __name__ == "__main__":
    unittest.main()
