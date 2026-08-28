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

    def test_install_replaces_only_monitoring_refresh_hook(self):
        original = base_runner.refresh_due_profiles
        try:
            installed = bridge.install_backend_monitoring_bridge()
            self.assertIs(installed, base_runner)
            self.assertIs(base_runner.refresh_due_profiles, bridge.refresh_due_profiles_via_backend)
        finally:
            base_runner.refresh_due_profiles = original

    def test_bridge_has_no_remote_or_broker_target(self):
        self.assertEqual(bridge.BACKEND_BASE_URL, "http://127.0.0.1:8002")
        self.assertNotIn("broker", bridge.MONITORING_PATH.lower())
        self.assertNotIn("execute", bridge.MONITORING_PATH.lower())


if __name__ == "__main__":
    unittest.main()
