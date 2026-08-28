import io
import json
import subprocess
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
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

    @patch.object(bridge, "urlopen")
    def test_heartbeat_sync_posts_completed_checkpoint_and_stays_locked(self, urlopen):
        urlopen.return_value = _Response(
            json.dumps(
                {
                    "status": "accepted",
                    "paper_mode": True,
                    "trade_execution_permission": False,
                    "live_execution": False,
                }
            ).encode()
        )
        state = {
            "last_cycle_completed_at": "2026-08-28T16:00:00+00:00",
            "market_phase": "REGULAR_SESSION",
            "last_scan_status": "complete",
            "last_scan_count": 518,
        }

        result = bridge.sync_observation_checkpoint_via_backend(state)

        request = urlopen.call_args.args[0]
        sent = json.loads(request.data.decode("utf-8"))
        self.assertEqual(
            request.full_url,
            "http://127.0.0.1:8002/observation-heartbeat/checkpoint",
        )
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(sent["market_phase"], "REGULAR_SESSION")
        self.assertFalse(sent["auto_trade_authority"])
        self.assertFalse(sent["paper_order_permission"])
        self.assertFalse(sent["trade_execution_permission"])
        self.assertFalse(sent["live_execution"])
        self.assertEqual(result["status"], "accepted")

    def test_install_replaces_monitoring_radar_scan_and_cycle_hooks(self):
        original_monitoring = base_runner.refresh_due_profiles
        original_radar = base_runner.run_market_event_radar
        original_scan = base_runner.scan_universe
        original_cycle = base_runner.run_cycle
        try:
            installed = bridge.install_backend_monitoring_bridge()
            self.assertIs(installed, base_runner)
            self.assertIs(base_runner.refresh_due_profiles, bridge.refresh_due_profiles_via_backend)
            self.assertIs(base_runner.run_market_event_radar, bridge.run_market_event_radar_bounded)
            self.assertIs(base_runner.scan_universe, bridge.scan_universe_bounded)
            self.assertIs(base_runner.run_cycle, bridge.run_cycle_with_backend_heartbeat)
        finally:
            base_runner.refresh_due_profiles = original_monitoring
            base_runner.run_market_event_radar = original_radar
            base_runner.scan_universe = original_scan
            base_runner.run_cycle = original_cycle

    @patch.object(bridge, "_run_stage_in_subprocess")
    def test_external_stages_use_hard_process_ceilings(self, bounded):
        bounded.side_effect = [{"event_count": 0}, {"scanned_count": 0}]

        radar = bridge.run_market_event_radar_bounded()
        scan = bridge.scan_universe_bounded(news_limit=8, max_candidates=10)

        self.assertEqual(radar["event_count"], 0)
        self.assertEqual(scan["scanned_count"], 0)
        self.assertEqual(bounded.call_args_list[0].args[0], "market_event_radar")
        self.assertEqual(bounded.call_args_list[0].args[1], bridge.RADAR_TIMEOUT_SECONDS)
        self.assertEqual(bounded.call_args_list[1].args[0], "opportunity_scan")
        self.assertEqual(bounded.call_args_list[1].args[1], bridge.OPPORTUNITY_SCAN_TIMEOUT_SECONDS)
        self.assertEqual(bridge.RADAR_TIMEOUT_SECONDS, 120)
        self.assertEqual(bridge.OPPORTUNITY_SCAN_TIMEOUT_SECONDS, 180)

    @patch.object(bridge.subprocess, "run")
    def test_subprocess_timeout_becomes_observation_stage_timeout(self, run):
        run.side_effect = subprocess.TimeoutExpired(["python", "worker"], 180)

        with self.assertRaises(bridge.ObservationStageTimeout) as caught:
            bridge._run_stage_in_subprocess(
                "opportunity_scan",
                180,
                "OPPORTUNITY_SCAN",
                news_limit=8,
                max_candidates=10,
            )

        self.assertIn("OPPORTUNITY_SCAN_TIMEOUT_180s", str(caught.exception))

    @patch.object(bridge.subprocess, "run")
    def test_subprocess_success_returns_machine_readable_result(self, run):
        run.return_value = SimpleNamespace(
            returncode=0,
            stdout=json.dumps({"scanned_count": 16, "queued_count": 10}),
            stderr="",
        )

        result = bridge._run_stage_in_subprocess(
            "opportunity_scan",
            180,
            "OPPORTUNITY_SCAN",
            news_limit=8,
            max_candidates=10,
        )

        self.assertEqual(result["scanned_count"], 16)
        self.assertEqual(result["queued_count"], 10)
        self.assertEqual(run.call_args.kwargs["timeout"], 180)
        self.assertIn("iios_observation_stage_worker.py", run.call_args.args[0][1])

    def test_timeout_exception_is_caught_by_existing_safe_call(self):
        def timeout_stage():
            raise bridge.ObservationStageTimeout("MARKET_EVENT_RADAR_TIMEOUT_120s")

        result = base_runner._safe_call("market_event_radar", timeout_stage)

        self.assertEqual(result["status"], "error")
        self.assertIn("ObservationStageTimeout", result["error"])
        self.assertIn("TIMEOUT_120s", result["error"])

    @patch.object(bridge, "sync_observation_checkpoint_via_backend")
    @patch.object(bridge, "_ORIGINAL_RUN_CYCLE")
    def test_heartbeat_failure_does_not_fail_completed_observation_cycle(
        self,
        original_cycle,
        heartbeat,
    ):
        original_cycle.return_value = {
            "last_cycle_completed_at": "2026-08-28T16:00:00+00:00",
            "market_phase": "REGULAR_SESSION",
        }
        heartbeat.side_effect = RuntimeError("backend unavailable")

        result = bridge.run_cycle_with_backend_heartbeat()

        self.assertEqual(result["market_phase"], "REGULAR_SESSION")
        heartbeat.assert_called_once_with(result)

    def test_bridge_has_no_remote_or_broker_target(self):
        self.assertEqual(bridge.BACKEND_BASE_URL, "http://127.0.0.1:8002")
        for path in (bridge.MONITORING_PATH, bridge.HEARTBEAT_PATH):
            self.assertNotIn("broker", path.lower())
            self.assertNotIn("execute", path.lower())
        self.assertFalse(hasattr(bridge, "broker"))
        self.assertEqual(bridge.STAGE_WORKER.name, "iios_observation_stage_worker.py")


if __name__ == "__main__":
    unittest.main()
