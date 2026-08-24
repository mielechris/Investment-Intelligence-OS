import os
import unittest
from unittest.mock import patch

import orchestration_runtime as runtime


class FakeResponses:
    def __init__(self):
        self.calls = []

    def create(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return {"ok": True}


class OrchestrationRuntimeTests(unittest.TestCase):
    def test_baseline_preserves_current_reasoning(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("IIOS_ORCHESTRATION_PROFILE", None)
            os.environ.pop("IIOS_FIRST_WAVE_REASONING_EFFORT", None)
            policy = runtime.runtime_policy()
        self.assertEqual(policy["profile"], "baseline")
        self.assertEqual(policy["first_wave_model"], "gpt-5.6-luna")
        self.assertEqual(policy["first_wave_reasoning_effort"], "medium")
        self.assertEqual(policy["critical_reasoning_effort"], "medium")
        self.assertEqual(policy["committee_reasoning_effort"], "medium")
        self.assertFalse(policy["judgment_output_cache"])

    def test_speed_trial_only_lowers_first_wave_by_default(self):
        with patch.dict(
            os.environ,
            {"IIOS_ORCHESTRATION_PROFILE": "speed_trial"},
            clear=False,
        ):
            for key in (
                "IIOS_FIRST_WAVE_REASONING_EFFORT",
                "IIOS_CRITICAL_REASONING_EFFORT",
                "IIOS_COMMITTEE_REASONING_EFFORT",
            ):
                os.environ.pop(key, None)
            policy = runtime.runtime_policy()
        self.assertEqual(policy["profile"], "speed_trial")
        self.assertEqual(policy["first_wave_reasoning_effort"], "low")
        self.assertEqual(policy["critical_reasoning_effort"], "medium")
        self.assertEqual(policy["committee_reasoning_effort"], "medium")

    def test_invalid_effort_fails_back_to_profile_default(self):
        with patch.dict(
            os.environ,
            {
                "IIOS_ORCHESTRATION_PROFILE": "speed_trial",
                "IIOS_FIRST_WAVE_REASONING_EFFORT": "turbo",
            },
            clear=False,
        ):
            policy = runtime.runtime_policy()
        self.assertEqual(policy["first_wave_reasoning_effort"], "low")

    def test_exact_prompt_cache_key_is_stable_and_input_bound(self):
        first = runtime._exact_prompt_cache_key("policy", "gpt-5.6-luna", "same")
        second = runtime._exact_prompt_cache_key("policy", "gpt-5.6-luna", "same")
        changed = runtime._exact_prompt_cache_key("policy", "gpt-5.6-luna", "changed")
        self.assertEqual(first, second)
        self.assertNotEqual(first, changed)
        self.assertLessEqual(len(first), 64)

    def test_routed_response_applies_model_effort_and_prompt_cache(self):
        inner = FakeResponses()
        routed = runtime._RoutedResponses(inner)

        with runtime._request_context(
            role="policy",
            model="gpt-5.6-luna",
            effort="low",
            cache_enabled=True,
        ):
            routed.create(model="ignored", input="deterministic test prompt")

        kwargs = inner.calls[0][1]
        self.assertEqual(kwargs["model"], "gpt-5.6-luna")
        self.assertEqual(kwargs["reasoning"]["effort"], "low")
        self.assertTrue(kwargs["prompt_cache_key"].startswith("iios-"))
        self.assertEqual(kwargs["prompt_cache_options"], {"ttl": "30m"})

    def test_no_runtime_context_preserves_original_request(self):
        inner = FakeResponses()
        routed = runtime._RoutedResponses(inner)
        routed.create(model="gpt-5.6-luna", input="prompt")
        kwargs = inner.calls[0][1]
        self.assertNotIn("reasoning", kwargs)
        self.assertNotIn("prompt_cache_key", kwargs)

    def test_runtime_route_exposes_no_execution_control(self):
        paths = {route.path.lower() for route in runtime.router.routes}
        self.assertIn("/orchestration-runtime/plan", paths)
        self.assertFalse(
            any(
                "broker" in path
                or "authorization" in path
                or "paper-order" in path
                or "live" in path
                for path in paths
            )
        )
        policy = runtime.orchestration_runtime_plan()
        self.assertFalse(policy["auto_trade_authority"])
        self.assertFalse(policy["paper_order_permission"])
        self.assertFalse(policy["trade_execution_permission"])
        self.assertFalse(policy["live_execution"])


if __name__ == "__main__":
    unittest.main()
