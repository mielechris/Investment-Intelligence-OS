from __future__ import annotations

import threading
import unittest
from typing import Any

import iios_factory_browser_preview as preview


class LivingOverviewCacheTest(unittest.TestCase):
    def setUp(self) -> None:
        self.now = 100.0
        self.cache = preview.LivingOverviewCache(clock=lambda: self.now)

    @staticmethod
    def healthy(marker: str = "ok") -> dict[str, Any]:
        return {
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
        self.now += 4.9
        self.assertEqual(self.cache.get("a", load)["marker"], "1")
        self.assertEqual(calls, 1)
        self.now += 0.2
        self.assertEqual(self.cache.get("a", load)["marker"], "2")
        self.assertEqual(calls, 2)

    def test_simultaneous_requests_coalesce_and_serve_last_good(self) -> None:
        self.cache.get("a", lambda: self.healthy("first"))
        self.now += 6.0
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
        worker = threading.Thread(target=lambda: result.append(self.cache.get("a", load)))
        worker.start()
        self.assertTrue(entered.wait(1))
        concurrent = self.cache.get("a", load)
        self.assertEqual(concurrent["marker"], "first")
        self.assertEqual(concurrent["cache"]["state"], "STALE_REFRESHING")
        self.assertEqual(calls, 1)
        release.set()
        worker.join(1)
        self.assertEqual(result[0]["marker"], "second")

    def test_timeout_recovery_and_retry_is_bounded_by_ttl(self) -> None:
        timed_out = {
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
        self.now += 1.0
        self.cache.get("a", load)
        self.assertEqual(calls, 1)
        self.now += 5.0
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

        worker = threading.Thread(target=lambda: self.cache.get("a", blocked))
        worker.start()
        self.assertTrue(entered.wait(1))
        self.assertEqual(self.cache.get("a", blocked)["cache"]["state"], "DEGRADED_STALE")
        release.set()
        worker.join(1)
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

    def test_raw_loader_exception_is_sanitized(self) -> None:
        def fail() -> dict[str, Any]:
            raise RuntimeError("private path and backend evidence")

        snapshot = self.cache.get("a", fail)
        self.assertEqual(snapshot["cache"]["state"], "DEGRADED")
        self.assertNotIn("private path", str(snapshot))
        self.assertNotIn("RuntimeError", str(snapshot))

    def test_failed_refresh_preserves_last_good_snapshot(self) -> None:
        self.cache.get("a", lambda: self.healthy("last-good"))
        self.now += 6.0
        failed = self.cache.get(
            "a",
            lambda: {
                "factory": {"availability": "WAITING", "payload": None},
                "jesse_dislocation": {"availability": "WAITING", "payload": None},
            },
        )
        self.assertEqual(failed["marker"], "last-good")
        self.assertEqual(failed["status"], "BACKEND_DEGRADED")

    def test_identity_replacement_keeps_one_bounded_entry(self) -> None:
        first = self.cache.get("a", lambda: self.healthy("identity-a"))
        second = self.cache.get("b", lambda: self.healthy("identity-b"))
        self.assertEqual(first["cache"]["bounded_entries"], 1)
        self.assertEqual(second["cache"]["bounded_entries"], 1)
        self.assertEqual(second["marker"], "identity-b")


if __name__ == "__main__":
    unittest.main()
