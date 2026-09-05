from __future__ import annotations

import json
import os
import socket
import threading
import time
import tempfile
import unittest
from http.client import HTTPConnection
from pathlib import Path
from typing import Any
from unittest import mock

import iios_factory_browser_preview as preview


class LivingOverviewCacheTest(unittest.TestCase):
    def setUp(self) -> None:
        self.now = 100.0
        self.cache = preview.LivingOverviewCache(clock=lambda: self.now)

    def tearDown(self) -> None:
        self.cache.close()

    def wait_for_refresh(self, cache=None) -> None:
        selected = cache or self.cache
        deadline = time.monotonic() + 1
        while selected._refreshing and time.monotonic() < deadline:
            time.sleep(0.005)
        self.assertFalse(selected._refreshing)

    @staticmethod
    def healthy(marker: str = "ok") -> dict[str, Any]:
        return {
            "schema_version": preview.LIVING_SCHEMA_VERSION,
            "generated_at": "2026-09-05T12:00:00+00:00",
            "marker": marker,
            "factory": {"availability": "AVAILABLE", "payload": {}},
            "jesse_dislocation": {"availability": "AVAILABLE", "payload": {}},
            "safety": {
                "backend_access": "READ_ONLY_GET_ONLY",
                "backend_write_permission": False,
                "trade_execution_permission": False,
                "live_execution": False,
            },
        }

    def test_inside_ttl_and_refresh_after_ttl(self) -> None:
        calls = 0

        def load() -> dict[str, Any]:
            nonlocal calls
            calls += 1
            return self.healthy(str(calls))

        self.assertEqual(self.cache.get("a", load)["marker"], "1")
        self.now += 14.9
        self.assertEqual(self.cache.get("a", load)["marker"], "1")
        self.assertEqual(calls, 1)
        self.now += 0.2
        self.assertEqual(self.cache.get("a", load)["marker"], "1")
        self.wait_for_refresh()
        self.assertEqual(self.cache.get("a", load)["marker"], "2")
        self.assertEqual(calls, 2)

    def test_simultaneous_requests_coalesce_and_serve_last_good(self) -> None:
        self.cache.get("a", lambda: self.healthy("first"))
        self.now += 16.0
        entered = threading.Event()
        release = threading.Event()
        calls = 0

        def load() -> dict[str, Any]:
            nonlocal calls
            calls += 1
            entered.set()
            release.wait(1)
            return self.healthy("second")

        result: list[dict[str, Any]] = []
        result.append(self.cache.get("a", load))
        self.assertTrue(entered.wait(1))
        concurrent = self.cache.get("a", load)
        self.assertEqual(concurrent["marker"], "first")
        self.assertEqual(concurrent["cache"]["state"], "STALE_REFRESHING")
        self.assertEqual(calls, 1)
        release.set()
        self.wait_for_refresh()
        self.assertEqual(result[0]["marker"], "first")
        self.assertEqual(self.cache.get("a", load)["marker"], "second")

    def test_timeout_recovery_and_retry_is_bounded_by_ttl(self) -> None:
        timed_out = self.healthy("timed-out") | {
            "factory": {
                "availability": "WAITING",
                "payload": None,
                "error_type": "TimeoutError",
                "error": "raw private backend URL and evidence must not escape",
            },
            "jesse_dislocation": {"availability": "WAITING", "payload": None},
        }
        calls = 0

        def load() -> dict[str, Any]:
            nonlocal calls
            calls += 1
            return timed_out if calls == 1 else self.healthy("recovered")

        first = self.cache.get("a", load)
        self.assertEqual(first["cache"]["state"], "DEGRADED")
        self.assertEqual(first["factory"]["failure_category"], "BACKEND_TIMEOUT")
        self.assertNotIn("error", first["factory"])
        self.assertNotIn("error_type", first["factory"])
        self.now += 14.0
        self.cache.get("a", load)
        self.assertEqual(calls, 1)
        self.now += 2.0
        self.cache.get("a", load)
        self.wait_for_refresh()
        recovered = self.cache.get("a", load)
        self.assertEqual(recovered["marker"], "recovered")
        self.assertEqual(recovered["cache"]["state"], "FRESH")

    def test_stale_transition_no_snapshot_and_identity_isolation(self) -> None:
        self.cache.get("a", lambda: self.healthy("a"))
        self.now += 31.0
        entered = threading.Event()
        release = threading.Event()

        def blocked() -> dict[str, Any]:
            entered.set()
            release.wait(1)
            return self.healthy("new")

        self.cache.get("a", blocked)
        self.assertTrue(entered.wait(1))
        self.assertEqual(self.cache.get("a", blocked)["cache"]["state"], "DEGRADED_STALE")
        release.set()
        self.wait_for_refresh()
        self.assertEqual(self.cache.get("b", lambda: self.healthy("b"))["marker"], "b")

        empty = preview.LivingOverviewCache(ttl_seconds=0.01)
        gate = threading.Event()
        release_empty = threading.Event()

        def first_load() -> dict[str, Any]:
            gate.set()
            release_empty.wait(1)
            return self.healthy("x")

        first = threading.Thread(target=lambda: empty.get("x", first_load))
        first.start()
        self.assertTrue(gate.wait(1))
        self.assertEqual(
            empty.get("x", lambda: self.healthy("unexpected"))["cache"]["state"],
            "DEGRADED_NO_SNAPSHOT",
        )
        release_empty.set()
        first.join(1)
        empty.close()

    def test_authority_remains_read_only_and_cache_is_bounded(self) -> None:
        snapshot = self.cache.get("a", self.healthy)
        self.assertEqual(snapshot["cache"]["bounded_entries"], 1)
        self.assertEqual(snapshot["safety"]["backend_access"], "READ_ONLY_GET_ONLY")
        self.assertFalse(snapshot["safety"]["backend_write_permission"])
        self.assertFalse(snapshot["safety"]["trade_execution_permission"])
        self.assertFalse(snapshot["safety"]["live_execution"])

    def test_incompatible_identity_cannot_reuse_inflight_result(self) -> None:
        cache = preview.LivingOverviewCache(ttl_seconds=0.01)
        entered = threading.Event()
        release = threading.Event()

        def first_load() -> dict[str, Any]:
            entered.set()
            release.wait(1)
            return self.healthy("identity-a")

        first = threading.Thread(target=lambda: cache.get("a", first_load))
        first.start()
        self.assertTrue(entered.wait(1))
        waiting = cache.get("b", lambda: self.healthy("identity-b"))
        self.assertEqual(waiting["cache"]["state"], "DEGRADED_NO_SNAPSHOT")
        release.set()
        first.join(1)
        isolated = cache.get("b", lambda: self.healthy("identity-b"))
        self.assertEqual(isolated["marker"], "identity-b")
        cache.close()

    def test_raw_loader_exception_is_sanitized(self) -> None:
        def fail() -> dict[str, Any]:
            raise RuntimeError("private path and backend evidence")

        snapshot = self.cache.get("a", fail)
        self.assertEqual(snapshot["cache"]["state"], "DEGRADED_NO_SNAPSHOT")
        self.assertNotIn("private path", str(snapshot))
        self.assertNotIn("RuntimeError", str(snapshot))

    def test_failed_refresh_preserves_last_good_snapshot(self) -> None:
        self.cache.get("a", lambda: self.healthy("last-good"))
        self.now += 16.0
        failed = self.cache.get(
            "a",
            lambda: {
                "factory": {"availability": "WAITING", "payload": None},
                "jesse_dislocation": {"availability": "WAITING", "payload": None},
            },
        )
        self.assertEqual(failed["marker"], "last-good")
        self.wait_for_refresh()
        retained = self.cache.get("a", lambda: self.healthy("unused"))
        self.assertEqual(retained["marker"], "last-good")
        self.assertEqual(retained["cache"]["last_failure_category"], "FACTORY_SOURCE_INVALID")

    def test_identity_replacement_keeps_one_bounded_entry(self) -> None:
        first = self.cache.get("a", lambda: self.healthy("identity-a"))
        second = self.cache.get("b", lambda: self.healthy("identity-b"))
        self.assertEqual(first["cache"]["bounded_entries"], 1)
        self.assertEqual(second["cache"]["bounded_entries"], 1)
        self.assertEqual(second["marker"], "identity-b")

    def test_poll_boundary_starts_one_refresh_without_blocking(self) -> None:
        self.cache.get("a", lambda: self.healthy("first"))
        self.now += 15.0
        entered = threading.Event()
        release = threading.Event()
        calls = 0

        def slow() -> dict[str, Any]:
            nonlocal calls
            calls += 1
            entered.set()
            release.wait(1)
            return self.healthy("second")

        start = time.monotonic()
        retained = self.cache.get("a", slow)
        self.assertLess(time.monotonic() - start, 0.1)
        self.assertTrue(entered.wait(1))
        results: list[dict[str, Any]] = []
        readers = [threading.Thread(target=lambda: results.append(self.cache.get("a", slow))) for _ in range(12)]
        for reader in readers:
            reader.start()
        for reader in readers:
            reader.join(1)
        self.assertEqual(calls, 1)
        self.assertTrue(all(value["marker"] == "first" for value in results))
        self.assertEqual(retained["cache"]["state"], "STALE_REFRESHING")
        release.set()
        self.wait_for_refresh()

    def test_retained_snapshot_age_and_stale_truth_are_not_retimestamped(self) -> None:
        initial = self.cache.get("a", lambda: self.healthy("first"))
        generated_at = initial["generated_at"]
        self.now += 30.001
        release = threading.Event()
        retained = self.cache.get("a", lambda: (release.wait(1), self.healthy("second"))[1])
        self.assertEqual(retained["generated_at"], generated_at)
        self.assertEqual(retained["cache"]["freshness_state"], "STALE")
        self.assertFalse(retained["cache"]["evidence_current"])
        self.assertGreater(retained["cache"]["age_seconds"], 30.0)
        release.set()
        self.wait_for_refresh()

    def test_invalid_injected_cache_is_never_served(self) -> None:
        self.cache._identity = "a"
        self.cache._snapshot = {"secret": "must-not-serve"}
        self.cache._snapshot_at = self.now
        result = self.cache.get("a", lambda: self.healthy("replacement"))
        self.assertNotIn("secret", result)
        self.assertEqual(result["marker"], "replacement")

    def test_cold_slow_source_returns_bounded_unavailable_then_recovers(self) -> None:
        cache = preview.LivingOverviewCache(cold_wait_seconds=0.02)
        release = threading.Event()
        start = time.monotonic()
        result = cache.get("cold", lambda: (release.wait(1), self.healthy("ready"))[1])
        self.assertLess(time.monotonic() - start, 0.1)
        self.assertEqual(result["status"], "FACTORY_SOURCE_UNAVAILABLE")
        self.assertEqual(result["cache"]["state"], "DEGRADED_NO_SNAPSHOT")
        release.set()
        self.wait_for_refresh(cache)
        self.assertEqual(cache.get("cold", self.healthy)["marker"], "ready")
        cache.close()

    def test_required_invalid_and_sqlite_busy_fail_with_fixed_categories(self) -> None:
        for loader in (
            lambda: {"schema_version": "wrong"},
            lambda: (_ for _ in ()).throw(RuntimeError("database is locked at private path")),
        ):
            cache = preview.LivingOverviewCache(cold_wait_seconds=0.1)
            result = cache.get("required", loader)
            self.assertEqual(result["status"], "FACTORY_SOURCE_UNAVAILABLE")
            self.assertNotIn("private path", json.dumps(result))
            cache.close()

    def test_optional_missing_and_atomic_replacement_are_bounded(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            missing = root / "optional.json"
            self.assertIsNone(preview._read_json(missing))
            source = root / "source.json"
            replacement = root / "replacement.json"
            source.write_text('{"generation": 1}', encoding="utf-8")
            observed: set[int] = set()
            for generation in range(2, 30):
                replacement.write_text(json.dumps({"generation": generation}), encoding="utf-8")
                os.replace(replacement, source)
                payload = preview._read_json(source)
                self.assertIsNotNone(payload)
                observed.add(payload["generation"])
            self.assertTrue(observed)

    def test_clean_shutdown_finishes_one_worker(self) -> None:
        cache = preview.LivingOverviewCache(cold_wait_seconds=0.01)
        release = threading.Event()
        cache.get("a", lambda: (release.wait(1), self.healthy())[1])
        release.set()
        cache.close()
        self.assertTrue(cache._closed)
        self.assertFalse(cache._refreshing)

    def test_isolated_builder_never_contacts_backend_or_ledger(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with mock.patch.object(preview, "_backend_get_json") as backend:
                snapshot = preview.build_isolated_living_factory_snapshot(
                    telemetry_dir=root,
                    state_dir=root,
                )
            backend.assert_not_called()
            self.assertTrue(snapshot["fixture_only"])
            self.assertEqual(snapshot["safety"]["backend_access"], "NONE")
            self.assertFalse(snapshot["safety"]["backend_write_permission"])
            self.assertFalse(snapshot["safety"]["trade_execution_permission"])

    def test_builder_timing_categories_are_scalar_and_backend_internals_unknown(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with mock.patch.object(preview, "_backend_get_json", return_value={}):
                snapshot = preview.build_living_factory_snapshot(
                    telemetry_dir=root,
                    state_dir=root,
                )
        diagnostics = snapshot["diagnostics"]
        self.assertEqual(diagnostics["schema_version"], "living-overview-timing-v1")
        categories = diagnostics["categories_ms"]
        for name in (
            "source_stat_ms", "source_read_ms", "json_parse_ms",
            "backend_factory_read_ms", "backend_dislocation_read_ms",
            "telemetry_assembly_ms", "total_refresh_ms",
        ):
            self.assertIsInstance(categories[name], float)
        for name in (
            "sqlite_connect_query_ms", "ledger_reconstruction_ms",
            "character_story_assembly_ms",
        ):
            self.assertIsNone(categories[name])


class LivingOverviewHTTPTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / "index.html").write_text("<main>FACTORY</main>", encoding="utf-8")
        self.cache = preview.LivingOverviewCache(cold_wait_seconds=0.1)
        self.original_cache = preview._living_overview_cache
        preview._living_overview_cache = self.cache
        self.server = preview.PreviewServer(
            ("127.0.0.1", 0), self.root, self.root, self.root, self.root / "ledger.db",
            expansion_enabled=True,
            expansion_compositor=mock.Mock(snapshot=lambda: {"mode": "READ_ONLY"}),
            fixture_isolated=False,
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(2)
        self.cache.close()
        preview._living_overview_cache = self.original_cache
        self.temporary.cleanup()

    def request(self, method: str, path: str) -> tuple[int, bytes]:
        connection = HTTPConnection("127.0.0.1", self.server.server_port, timeout=2)
        connection.request(method, path)
        response = connection.getresponse()
        body = response.read()
        connection.close()
        return response.status, body

    def test_head_get_and_mutations_preserve_single_refresh_and_capability(self) -> None:
        with mock.patch.object(preview, "build_living_factory_snapshot", return_value=self.cache_test_value()) as builder:
            self.assertEqual(self.request("HEAD", "/living/overview"), (200, b""))
            status, body = self.request("GET", "/living/overview")
            self.assertEqual(status, 200)
            payload = json.loads(body)
            self.assertTrue(payload["runtime_capabilities"]["expansion_wing_enabled"])
            self.assertEqual(builder.call_count, 1)
            for method in ("POST", "PUT", "PATCH", "DELETE"):
                self.assertEqual(self.request(method, "/living/overview")[0], 405)

    def test_cancelled_client_does_not_poison_cache(self) -> None:
        with mock.patch.object(preview, "build_living_factory_snapshot", return_value=self.cache_test_value()):
            client = socket.create_connection(("127.0.0.1", self.server.server_port), timeout=1)
            client.sendall(b"GET /living/overview HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n")
            client.close()
            time.sleep(0.05)
            status, body = self.request("GET", "/living/overview")
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(body)["marker"], "http")

    @staticmethod
    def cache_test_value() -> dict[str, Any]:
        return LivingOverviewCacheTest.healthy("http")


if __name__ == "__main__":
    unittest.main()
