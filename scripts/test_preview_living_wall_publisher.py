from __future__ import annotations

from datetime import datetime, timedelta, timezone
import importlib.util
import json
import os
from pathlib import Path
import plistlib
import subprocess
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


runner = load("preview_runner", ROOT / "scripts" / "run_preview_living_wall_publisher.py")
installer = load("preview_installer", ROOT / "scripts" / "install_preview_living_wall_publisher.py")


class PreviewLivingWallPublisherTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.policy = json.loads((ROOT / "config" / "preview_living_wall_publisher.json").read_text())
        self.policy["state_directory"] = str(self.root / "state")
        self.policy["log_path"] = str(self.root / "logs" / "publisher.log")

    def test_policy_uses_only_canonical_local_source_and_stable_branch_alias(self) -> None:
        policy = runner.load_policy()
        self.assertEqual(policy["local_source"], "http://127.0.0.1:5176/living/overview")
        self.assertEqual(policy["preview_host"], runner.EXPECTED_PREVIEW_HOST)
        self.assertEqual(
            runner.validate_destination(policy, "/telemetry/ingest"),
            f"https://{runner.EXPECTED_PREVIEW_HOST}/telemetry/ingest",
        )

    def test_policy_rejects_keychain_and_local_path_redirection(self) -> None:
        original = json.loads((ROOT / "config" / "preview_living_wall_publisher.json").read_text())
        for key, value in (
            ("state_directory", str(self.root / "redirected")),
            ("log_path", str(self.root / "redirected.log")),
            ("ingest_keychain", {"service": "other", "account": "other"}),
            ("bypass_keychain", {"service": "other", "account": "other"}),
        ):
            changed = dict(original); changed[key] = value
            path = self.root / f"{key}.json"; path.write_text(json.dumps(changed))
            with self.assertRaisesRegex(runner.PublisherFailure, "POLICY_BOUNDARY_INVALID"):
                runner.load_policy(path)

    def test_production_deployment_specific_and_unknown_paths_are_rejected(self) -> None:
        for host in (
            "investment-intelligence-os-gules.vercel.app",
            "investment-intelligence-1xex08iyd-chris-2274.vercel.app",
        ):
            policy = dict(self.policy, preview_host=host)
            with self.assertRaisesRegex(runner.PublisherFailure, "DESTINATION_HOST_REJECTED"):
                runner.validate_destination(policy, "/telemetry/ingest")
        with self.assertRaisesRegex(runner.PublisherFailure, "DESTINATION_PATH_REJECTED"):
            runner.validate_destination(self.policy, "/")

    def test_keychain_lookup_has_no_secret_in_argv_or_environment(self) -> None:
        captured = {}
        def fake(command, **kwargs):
            captured.update({"command": command, "env": kwargs["env"]})
            return subprocess.CompletedProcess(command, 0, "top-secret\n", "")
        with patch.object(runner.subprocess, "run", fake):
            value = runner.keychain_secret(self.policy["ingest_keychain"])
        self.assertEqual(value, "top-secret")
        self.assertNotIn("top-secret", " ".join(captured["command"]))
        self.assertNotIn("top-secret", json.dumps(captured["env"]))

    def test_remote_secrets_travel_through_anonymous_config_pipe(self) -> None:
        captured = {}
        response = b'{"accepted":true}\n__IIOS_HTTP_STATUS__:202'
        def fake(command, **kwargs):
            captured.update({"command": command, "env": kwargs["env"], "input": kwargs["input"]})
            return subprocess.CompletedProcess(command, 0, response, b"")
        with patch.object(runner.subprocess, "run", fake):
            status, body = runner.curl_json(
                self.policy, method="POST", path="/telemetry/ingest",
                bypass_secret="bypass-secret", ingest_token="ingest-secret", payload=b"{}",
            )
        serialized = json.dumps({"command": captured["command"], "env": captured["env"]})
        self.assertNotIn("bypass-secret", serialized)
        self.assertNotIn("ingest-secret", serialized)
        self.assertEqual(captured["input"], b"{}")
        self.assertIn("--disable", captured["command"])
        self.assertNotIn("--location", captured["command"])
        self.assertNotIn("--retry", captured["command"])
        self.assertEqual(captured["command"][captured["command"].index("--connect-timeout") + 1], "5")
        self.assertEqual(captured["command"][captured["command"].index("--max-time") + 1], "15")
        self.assertEqual((status, body["accepted"]), (202, True))

    def test_truth_requires_current_available_and_all_authority_disabled(self) -> None:
        truth = {
            "schema_version": "living_wall_truth.v1", "availability": "AVAILABLE",
            "freshness": {"state": "CURRENT", "age_seconds": 3},
            "safety": {"live_execution": False, "telemetry_read_only": True,
                       "direct_ledger_access": False, "backend_write_permission": False,
                       "trade_execution_permission": False},
        }
        self.assertEqual(runner.validate_remote_truth(200, truth)["freshness"], "CURRENT")
        unsafe = json.loads(json.dumps(truth)); unsafe["safety"]["live_execution"] = True
        with self.assertRaisesRegex(runner.PublisherFailure, "REMOTE_TRUTH_UNSAFE"):
            runner.validate_remote_truth(200, unsafe)

    def test_nonblocking_single_instance_lock(self) -> None:
        with runner.publisher_lock(self.policy) as first:
            with runner.publisher_lock(self.policy) as second:
                self.assertTrue(first)
                self.assertFalse(second)

    def test_one_cycle_publishes_once_and_resets_backoff(self) -> None:
        now = datetime(2026, 9, 2, 12, 0, tzinfo=timezone.utc)
        health = {"http_status": 200, "availability": "AVAILABLE", "freshness": "CURRENT",
                  "age_seconds": 1, "live_execution": False, "telemetry_read_only": True}
        with patch.object(runner, "publish_cycle", return_value=health) as publish:
            self.assertEqual(runner.run_once(self.policy, now), 0)
        publish.assert_called_once_with(self.policy)
        state = runner.read_state(self.policy)
        self.assertEqual(state["consecutive_failures"], 0)
        self.assertIsNone(state["next_attempt_at"])

    def test_publish_cycle_makes_exactly_one_post_and_one_health_read(self) -> None:
        module = type("Publisher", (), {"_read_snapshot": staticmethod(lambda source: b"{}")})
        calls = []
        def request(policy, **kwargs):
            calls.append((kwargs["method"], kwargs["path"]))
            if kwargs["method"] == "POST":
                return 202, {"accepted": True}
            return 200, {
                "schema_version": "living_wall_truth.v1", "availability": "AVAILABLE",
                "freshness": {"state": "CURRENT", "age_seconds": 1},
                "safety": {"live_execution": False, "telemetry_read_only": True,
                           "direct_ledger_access": False, "backend_write_permission": False,
                           "trade_execution_permission": False},
            }
        with patch.object(runner, "_publisher_module", return_value=module), \
             patch.object(runner, "keychain_secret", side_effect=["ingest", "bypass"]), \
             patch.object(runner, "curl_json", side_effect=request):
            runner.publish_cycle(self.policy)
        self.assertEqual(calls, [("POST", "/telemetry/ingest"), ("GET", "/living-wall/truth")])

    def test_persistent_backoff_is_30_60_120_then_300(self) -> None:
        start = datetime(2026, 9, 2, 12, 0, tzinfo=timezone.utc)
        expected = [30, 60, 120, 300, 300]
        current = start
        with patch.object(runner, "publish_cycle", side_effect=runner.PublisherFailure("REMOTE_TIMEOUT")):
            for index, delay in enumerate(expected, 1):
                self.assertEqual(runner.run_once(self.policy, current), 1)
                state = runner.read_state(self.policy)
                next_at = datetime.fromisoformat(state["next_attempt_at"])
                self.assertEqual(int((next_at - current).total_seconds()), delay)
                self.assertEqual(state["consecutive_failures"], index)
                current = next_at

    def test_logs_and_status_contain_only_sanitized_failure_codes(self) -> None:
        secret = "DO-NOT-PERSIST"
        with patch.object(runner, "publish_cycle", side_effect=runner.PublisherFailure("KEYCHAIN_READ_FAILED")):
            runner.run_once(self.policy, datetime(2026, 9, 2, 12, 0, tzinfo=timezone.utc))
        persisted = (self.root / "state" / "status.json").read_text() + (self.root / "logs" / "publisher.log").read_text()
        self.assertNotIn(secret, persisted)
        self.assertIn("KEYCHAIN_READ_FAILED", persisted)
        runner.append_log(self.policy, "CYCLE_FAILED", failure_code=secret)
        self.assertNotIn(secret, (self.root / "logs" / "publisher.log").read_text())

    def test_launchagent_contract_contains_no_secrets_and_exact_cadence(self) -> None:
        plist = installer.build_plist(self.policy, python="/usr/bin/python3")
        self.assertEqual(plist["Label"], "com.iios.living-wall-preview-publisher")
        self.assertEqual(plist["StartInterval"], 30)
        self.assertTrue(plist["RunAtLoad"])
        self.assertFalse(plist["KeepAlive"])
        serialized = json.dumps(plist)
        self.assertNotIn("IIOS_TELEMETRY_INGEST_TOKEN", serialized)
        self.assertNotIn("VERCEL_AUTOMATION_BYPASS_SECRET", serialized)
        self.assertEqual(plist["StandardOutPath"], "/dev/null")
        self.assertEqual(plist["StandardErrorPath"], "/dev/null")
        path = self.root / "Library" / "LaunchAgents" / f"{installer.LABEL}.plist"
        installer._write_plist(path, plist)
        with path.open("rb") as handle:
            serialized_plist = plistlib.load(handle)
        self.assertEqual(serialized_plist, plist)
        self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)

    def test_uninstall_targets_only_its_own_launchagent(self) -> None:
        target = self.root / "Library" / "LaunchAgents" / f"{installer.LABEL}.plist"
        target.parent.mkdir(parents=True)
        target.write_text("test")
        calls = []
        with patch.object(installer, "launch_agent_path", return_value=target), \
             patch.object(installer, "_launchctl", side_effect=lambda *args: calls.append(args) or subprocess.CompletedProcess(args, 0, "", "")), \
             patch("builtins.print"):
            self.assertEqual(installer.uninstall(), 0)
        self.assertFalse(target.exists())
        self.assertEqual(calls, [("bootout", installer.launch_service())])


if __name__ == "__main__":
    unittest.main()
