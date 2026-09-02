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

    @staticmethod
    def truth(*, unavailable: bool = False) -> dict:
        return {
            "schema_version": "living_wall_truth.v1",
            "generated_at": None if unavailable else "2026-09-02T12:00:00+00:00",
            "availability": "UNAVAILABLE" if unavailable else "AVAILABLE",
            "source_conflict": False,
            "factory": {},
            "validation": {"layers": {}},
            "freshness": {
                "state": "UNAVAILABLE" if unavailable else "CURRENT",
                "age_seconds": None if unavailable else 1,
            },
            "safety": {
                "live_execution": False,
                "telemetry_read_only": True,
                "direct_ledger_access": False,
                "backend_write_permission": False,
                "trade_execution_permission": False,
            },
        }

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
        response = (
            b'{"accepted":true}\n__IIOS_HTTP_STATUS__:202'
            b'\n__IIOS_CONTENT_TYPE__:application/json; charset=utf-8'
        )
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

    def test_bypass_preflight_accepts_application_truth_200_and_sanitized_503(self) -> None:
        for status, truth in ((200, self.truth()), (503, self.truth(unavailable=True))):
            with self.subTest(status=status), patch.object(
                runner,
                "_curl_response",
                return_value=(status, "application/json; charset=utf-8", json.dumps(truth).encode()),
            ) as request:
                self.assertEqual(runner.bypass_preflight(self.policy, "bypass-secret"), status)
                request.assert_called_once_with(
                    self.policy,
                    method="GET",
                    path="/living-wall/truth",
                    bypass_secret="bypass-secret",
                )

    def test_bypass_preflight_rejects_edge_html_and_unexpected_responses(self) -> None:
        unsafe = self.truth(unavailable=True)
        unsafe["safety"]["live_execution"] = True
        cases = (
            (401, "application/json", b'{"error":{"code":"forbidden"}}'),
            (302, "text/html; charset=utf-8", b"<html>redirect</html>"),
            (200, "text/html", b"<html>login</html>"),
            (418, "application/json", b'{"error":"unexpected"}'),
            (503, "application/json", json.dumps(unsafe).encode()),
            (200, "application/json", b"not-json"),
        )
        for status, content_type, body in cases:
            with self.subTest(status=status, content_type=content_type), patch.object(
                runner, "_curl_response", return_value=(status, content_type, body)
            ):
                with self.assertRaises(runner.PublisherFailure) as raised:
                    runner.bypass_preflight(self.policy, "bypass-secret")
                self.assertEqual(raised.exception.code, "BYPASS_REJECTED")
                self.assertEqual(raised.exception.http_status, status)

    def test_invalid_bypass_generates_no_payload_and_sends_no_post(self) -> None:
        calls = []

        def denied(policy, **kwargs):
            calls.append((kwargs["method"], kwargs["path"]))
            return 401, "application/json", b'{"error":{"code":"forbidden"}}'

        with patch.object(runner, "keychain_secret", return_value="bypass-secret") as keychain, \
             patch.object(runner, "_curl_response", side_effect=denied), \
             patch.object(runner, "_publisher_module") as publisher_module, \
             patch.object(runner, "curl_json") as request:
            with self.assertRaises(runner.PublisherFailure) as raised:
                runner.publish_cycle(self.policy)
        self.assertEqual(raised.exception.code, "BYPASS_REJECTED")
        self.assertEqual(raised.exception.http_status, 401)
        self.assertEqual(calls, [("GET", "/living-wall/truth")])
        keychain.assert_called_once_with(self.policy["bypass_keychain"])
        publisher_module.assert_not_called()
        request.assert_not_called()

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

    def test_publish_cycle_preflights_then_makes_exactly_one_post_and_one_health_read(self) -> None:
        events = []

        def read_snapshot(source):
            events.append(("PAYLOAD", source))
            return b"{}"

        module = type("Publisher", (), {"_read_snapshot": staticmethod(read_snapshot)})
        calls = []

        def keychain(item):
            if item == self.policy["bypass_keychain"]:
                events.append(("KEYCHAIN", "bypass"))
                return "bypass"
            events.append(("KEYCHAIN", "ingest"))
            return "ingest"

        def preflight(policy, secret):
            events.append(("GET", "/living-wall/truth"))
            self.assertEqual(secret, "bypass")
            return 503

        def request(policy, **kwargs):
            calls.append((kwargs["method"], kwargs["path"]))
            events.append((kwargs["method"], kwargs["path"]))
            if kwargs["method"] == "POST":
                return 202, {"accepted": True}
            return 200, self.truth()
        with patch.object(runner, "_publisher_module", return_value=module), \
             patch.object(runner, "keychain_secret", side_effect=keychain), \
             patch.object(runner, "bypass_preflight", side_effect=preflight), \
             patch.object(runner, "curl_json", side_effect=request):
            runner.publish_cycle(self.policy)
        self.assertEqual(calls, [("POST", "/telemetry/ingest"), ("GET", "/living-wall/truth")])
        self.assertEqual(events, [
            ("KEYCHAIN", "bypass"),
            ("GET", "/living-wall/truth"),
            ("PAYLOAD", "http://127.0.0.1:5176/living/overview"),
            ("KEYCHAIN", "ingest"),
            ("POST", "/telemetry/ingest"),
            ("GET", "/living-wall/truth"),
        ])

    def test_ingest_rejection_retains_only_numeric_http_status(self) -> None:
        module = type("Publisher", (), {"_read_snapshot": staticmethod(lambda source: b"{}")})
        with patch.object(runner, "bypass_preflight", return_value=503), \
             patch.object(runner, "_publisher_module", return_value=module), \
             patch.object(runner, "keychain_secret", side_effect=["bypass", "ingest"]), \
             patch.object(runner, "curl_json", return_value=(401, {"error": "discarded"})):
            with self.assertRaises(runner.PublisherFailure) as raised:
                runner.publish_cycle(self.policy)
        self.assertEqual(raised.exception.code, "INGEST_REJECTED")
        self.assertEqual(raised.exception.http_status, 401)
        self.assertEqual(str(raised.exception), "INGEST_REJECTED")

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
        self.assertNotIn("http_status", persisted)
        runner.append_log(self.policy, "CYCLE_FAILED", failure_code=secret)
        self.assertNotIn(secret, (self.root / "logs" / "publisher.log").read_text())

    def test_bypass_failure_records_only_status_and_allowlisted_category(self) -> None:
        now = datetime(2026, 9, 2, 12, 0, tzinfo=timezone.utc)
        with patch.object(
            runner,
            "publish_cycle",
            side_effect=runner.PublisherFailure("BYPASS_REJECTED", http_status=401),
        ):
            self.assertEqual(runner.run_once(self.policy, now), 1)
        state = runner.read_state(self.policy)
        self.assertEqual(state["failure_code"], "BYPASS_REJECTED")
        self.assertEqual(state["http_status"], 401)
        log = json.loads((self.root / "logs" / "publisher.log").read_text().splitlines()[-1])
        self.assertEqual(log["failure_code"], "BYPASS_REJECTED")
        self.assertEqual(log["http_status"], 401)
        self.assertEqual(
            set(log),
            {"at", "event", "failure_code", "http_status", "consecutive_failures", "next_attempt_at"},
        )

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


class FakeClock:
    def __init__(self) -> None:
        self.current = 0.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.current

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.current += seconds


class FakeInstallerRunner:
    def __init__(self, policy: dict, states: list[dict]) -> None:
        self.policy = policy
        self.states = [dict(state) for state in states]
        self.last_state: dict = {}

    def load_policy(self) -> dict:
        return self.policy

    def keychain_secret(self, item: dict) -> str:
        return "opaque-test-value"

    def read_state(self, policy: dict) -> dict:
        if self.states:
            self.last_state = self.states.pop(0)
        return dict(self.last_state)


class PreviewLivingWallInstallerAcceptanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.target = self.root / "Library" / "LaunchAgents" / f"{installer.LABEL}.plist"
        self.policy = json.loads((ROOT / "config" / "preview_living_wall_publisher.json").read_text())
        self.baseline = {
            "event": "CYCLE_OK", "last_attempt_at": "before",
            "last_success_at": "before", "http_status": 200,
            "availability": "AVAILABLE", "freshness": "CURRENT",
            "age_seconds": 1, "consecutive_failures": 0,
            "next_attempt_at": None,
            "live_execution": False, "telemetry_read_only": True,
        }

    def successful_state(self) -> dict:
        return {
            "event": "CYCLE_OK", "last_attempt_at": "after",
            "last_success_at": "after", "http_status": 200,
            "availability": "AVAILABLE", "freshness": "CURRENT",
            "age_seconds": 1, "consecutive_failures": 0,
            "next_attempt_at": None,
            "live_execution": False, "telemetry_read_only": True,
        }

    @staticmethod
    def completed(arguments, returncode: int = 0):
        return subprocess.CompletedProcess(arguments, returncode, "", "")

    def install_with(self, module, launchctl, **constant_overrides):
        clock = FakeClock()
        patches = [
            patch.object(installer.sys, "platform", "darwin"),
            patch.object(installer, "_runner_module", return_value=module),
            patch.object(installer, "launch_agent_path", return_value=self.target),
            patch.object(installer, "_launchctl", side_effect=launchctl),
            patch.object(installer.time, "monotonic", side_effect=clock.monotonic),
            patch.object(installer.time, "sleep", side_effect=clock.sleep),
            patch("builtins.print"),
        ]
        for name, value in constant_overrides.items():
            patches.append(patch.object(installer, name, value))
        entered = [item.start() for item in patches]
        self.addCleanup(lambda: [item.stop() for item in reversed(patches)])
        result = installer.install()
        return result, clock, entered[-1 if not constant_overrides else 6]

    def test_bootstrap_and_run_at_load_succeed_without_kickstart(self) -> None:
        module = FakeInstallerRunner(self.policy, [self.baseline, self.successful_state()])
        calls = []

        def launchctl(*arguments, **kwargs):
            calls.append(arguments)
            if arguments[0] == "kickstart":
                self.fail("RunAtLoad success must not invoke kickstart")
            return self.completed(arguments)

        result, _, printed = self.install_with(module, launchctl)
        self.assertEqual(result, 0)
        self.assertTrue(self.target.exists())
        self.assertIn(("bootstrap", installer.launch_domain(), str(self.target)), calls)
        self.assertNotIn("kickstart", [call[0] for call in calls])
        output = str(printed.call_args)
        self.assertIn('"acceptance": "CYCLE_OK"', output)
        self.assertNotIn("opaque-test-value", output)

    def test_kickstart_timeout_then_proven_cycle_is_accepted(self) -> None:
        module = FakeInstallerRunner(self.policy, [self.baseline, {}, self.successful_state()])
        calls = []

        def launchctl(*arguments, **kwargs):
            calls.append(arguments)
            if arguments[0] == "kickstart":
                raise subprocess.TimeoutExpired(arguments, kwargs["timeout_seconds"])
            return self.completed(arguments)

        result, _, _ = self.install_with(
            module, launchctl, RUN_AT_LOAD_GRACE_SECONDS=0,
            INSTALL_ACCEPTANCE_TIMEOUT_SECONDS=3,
        )
        self.assertEqual(result, 0)
        self.assertIn("kickstart", [call[0] for call in calls])
        self.assertNotIn("bootout", [call[0] for call in calls])

    def test_kickstart_timeout_without_success_rolls_back(self) -> None:
        module = FakeInstallerRunner(self.policy, [self.baseline, {}])
        calls = []

        def launchctl(*arguments, **kwargs):
            calls.append(arguments)
            if arguments[0] == "kickstart":
                raise subprocess.TimeoutExpired(arguments, kwargs["timeout_seconds"])
            return self.completed(arguments)

        result, clock, printed = self.install_with(
            module, launchctl, RUN_AT_LOAD_GRACE_SECONDS=0,
            INSTALL_ACCEPTANCE_TIMEOUT_SECONDS=2,
        )
        self.assertEqual(result, 1)
        self.assertLessEqual(clock.current, 2)
        self.assertFalse(self.target.exists())
        self.assertEqual(calls[-1], ("bootout", installer.launch_service()))
        self.assertIn("INSTALL_ACCEPTANCE_TIMEOUT", str(printed.call_args))

    def test_job_never_loading_fails_closed(self) -> None:
        module = FakeInstallerRunner(self.policy, [self.baseline, {}])
        calls = []

        def launchctl(*arguments, **kwargs):
            calls.append(arguments)
            if arguments[0] == "print":
                return self.completed(arguments, 1)
            return self.completed(arguments)

        result, _, printed = self.install_with(
            module, launchctl, RUN_AT_LOAD_GRACE_SECONDS=10,
            INSTALL_ACCEPTANCE_TIMEOUT_SECONDS=2,
        )
        self.assertEqual(result, 1)
        self.assertFalse(self.target.exists())
        self.assertIn("LAUNCHCTL_JOB_NOT_LOADED", str(printed.call_args))

    def test_new_cycle_failure_fails_closed(self) -> None:
        failed = {
            "event": "CYCLE_FAILED", "last_attempt_at": "after",
            "last_success_at": "before", "failure_code": "SENSITIVE-DIAGNOSTIC",
        }
        module = FakeInstallerRunner(self.policy, [self.baseline, failed])
        calls = []

        def launchctl(*arguments, **kwargs):
            calls.append(arguments)
            return self.completed(arguments)

        result, _, printed = self.install_with(module, launchctl)
        self.assertEqual(result, 1)
        self.assertFalse(self.target.exists())
        self.assertIn("PUBLISHER_CYCLE_FAILED", str(printed.call_args))
        self.assertNotIn("SENSITIVE-DIAGNOSTIC", str(printed.call_args))
        self.assertEqual(calls[-1], ("bootout", installer.launch_service()))

    def test_acceptance_timeout_is_bounded(self) -> None:
        module = FakeInstallerRunner(self.policy, [self.baseline, {}])
        print_calls = 0

        def launchctl(*arguments, **kwargs):
            nonlocal print_calls
            if arguments[0] == "print":
                print_calls += 1
            return self.completed(arguments)

        result, clock, _ = self.install_with(
            module, launchctl, RUN_AT_LOAD_GRACE_SECONDS=10,
            INSTALL_ACCEPTANCE_TIMEOUT_SECONDS=3,
        )
        self.assertEqual(result, 1)
        self.assertEqual(clock.current, 3)
        self.assertEqual(print_calls, 3)

    def test_timeout_output_is_fixed_and_sanitized(self) -> None:
        module = FakeInstallerRunner(self.policy, [self.baseline])

        def launchctl(*arguments, **kwargs):
            if arguments[0] == "bootstrap":
                raise subprocess.TimeoutExpired(
                    ["launchctl", "SENSITIVE-DIAGNOSTIC"], 15,
                    output="SENSITIVE-DIAGNOSTIC",
                )
            return self.completed(arguments)

        result, _, printed = self.install_with(module, launchctl)
        self.assertEqual(result, 1)
        output = str(printed.call_args)
        self.assertIn("LAUNCHCTL_BOOTSTRAP_TIMEOUT", output)
        self.assertNotIn("SENSITIVE-DIAGNOSTIC", output)

    def test_install_rollback_removes_only_target_label(self) -> None:
        self.target.parent.mkdir(parents=True)
        self.target.write_text("target")
        unrelated = self.target.parent / "com.iios.existing-worker.plist"
        unrelated.write_text("preserve")
        calls = []

        def launchctl(*arguments, **kwargs):
            calls.append(arguments)
            return self.completed(arguments)

        with patch.object(installer, "_launchctl", side_effect=launchctl), \
             patch("builtins.print"):
            self.assertEqual(installer._fail_install(self.target, "INSTALL_ACCEPTANCE_TIMEOUT"), 1)
        self.assertFalse(self.target.exists())
        self.assertEqual(unrelated.read_text(), "preserve")
        self.assertEqual(calls, [("bootout", installer.launch_service())])


if __name__ == "__main__":
    unittest.main()
