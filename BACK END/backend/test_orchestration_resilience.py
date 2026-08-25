import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import orchestration_resilience as resilience
import orchestration_runtime as runtime


class OrchestrationResilienceTests(unittest.TestCase):
    def setUp(self):
        resilience.reset_circuit_breaker()

    def tearDown(self):
        resilience.reset_circuit_breaker()

    def test_transient_failure_retries_once_then_succeeds(self):
        calls = []

        def flaky():
            calls.append(1)
            if len(calls) == 1:
                raise TimeoutError("temporary timeout")
            return "ok"

        with patch.object(time, "sleep", return_value=None):
            result, attempts = resilience.call_with_resilience(flaky, role="policy")
        self.assertEqual(result, "ok")
        self.assertEqual(attempts, 2)
        self.assertEqual(len(calls), 2)
        self.assertFalse(resilience._breaker_snapshot()["open"])

    def test_nontransient_failure_is_not_retried(self):
        calls = []

        def bad_input():
            calls.append(1)
            raise ValueError("invalid structured input")

        with self.assertRaises(ValueError):
            resilience.call_with_resilience(bad_input, role="macro")
        self.assertEqual(len(calls), 1)

    def test_repeated_transient_failures_open_circuit(self):
        def always_down():
            raise TimeoutError("service unavailable")

        with patch.object(time, "sleep", return_value=None):
            for _ in range(2):
                with self.assertRaises(TimeoutError):
                    resilience.call_with_resilience(always_down, role="policy")

        snapshot = resilience._breaker_snapshot()
        self.assertTrue(snapshot["open"])
        self.assertGreaterEqual(snapshot["failure_count"], resilience.BREAKER_FAILURE_THRESHOLD)
        with self.assertRaises(RuntimeError):
            resilience.call_with_resilience(lambda: "should not run", role="committee")

    def test_runtime_applies_bounded_request_timeout(self):
        class Inner:
            def __init__(self):
                self.calls = []

            def create(self, *args, **kwargs):
                self.calls.append(kwargs)
                return {"ok": True}

        inner = Inner()
        routed = runtime._RoutedResponses(inner)
        with runtime._request_context(
            role="policy",
            model="gpt-5.6-luna",
            effort="medium",
            cache_enabled=False,
            timeout_seconds=45,
        ):
            routed.create(model="ignored", input="test")
        self.assertEqual(inner.calls[0]["timeout"], 45.0)

    def test_timeout_configuration_is_hard_bounded(self):
        with patch.dict(
            "os.environ",
            {
                "IIOS_FIRST_WAVE_TIMEOUT_SECONDS": "9999",
                "IIOS_CRITICAL_TIMEOUT_SECONDS": "1",
                "IIOS_COMMITTEE_TIMEOUT_SECONDS": "bad",
            },
        ):
            policy = runtime.runtime_policy()
        self.assertEqual(policy["first_wave_timeout_seconds"], runtime.MAX_TIMEOUT_SECONDS)
        self.assertEqual(policy["critical_timeout_seconds"], runtime.MIN_TIMEOUT_SECONDS)
        self.assertEqual(policy["committee_timeout_seconds"], runtime.DEFAULT_COMMITTEE_TIMEOUT_SECONDS)

    def test_install_wraps_specialist_and_preserves_safety_contract(self):
        calls = []

        class Responses:
            def create(self, **kwargs):
                return {"ok": True}

        class OpenAI:
            def __init__(self, *args, **kwargs):
                self.responses = Responses()

        def specialist(agent_key, topic, evidence=None):
            calls.append(agent_key)
            return {
                "agent_key": agent_key,
                "status": "complete",
                "paper_order_permission": False,
                "trade_execution_permission": False,
                "live_execution": False,
            }

        module = SimpleNamespace(
            _resilience_layer_installed=False,
            run_specialist=specialist,
            OpenAI=OpenAI,
        )
        resilience.install_orchestration_resilience(module)
        result = module.run_specialist("policy", "topic", [])
        self.assertEqual(result["resilience_attempts"], 1)
        self.assertEqual(calls, ["policy"])
        self.assertFalse(result["trade_execution_permission"])
        self.assertFalse(result["live_execution"])

    def test_resilience_routes_expose_no_execution_control(self):
        paths = {route.path.lower() for route in resilience.router.routes}
        self.assertIn("/orchestration-resilience/plan", paths)
        self.assertFalse(any("broker" in path or "authorization" in path or "paper-order" in path or "live" in path for path in paths))
        plan = resilience.resilience_plan()
        self.assertTrue(plan["fail_closed"])
        self.assertFalse(plan["auto_trade_authority"])
        self.assertFalse(plan["trade_execution_permission"])
        self.assertFalse(plan["live_execution"])


if __name__ == "__main__":
    unittest.main()
