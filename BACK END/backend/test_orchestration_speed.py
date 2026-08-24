import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import orchestration_speed as speed


class OrchestrationSpeedTests(unittest.TestCase):
    def test_parallelism_defaults_to_six_and_is_hard_capped(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("IIOS_AGENT_PARALLELISM", None)
            self.assertEqual(speed.configured_parallelism(), 6)
        with patch.dict(os.environ, {"IIOS_AGENT_PARALLELISM": "99"}):
            self.assertEqual(speed.configured_parallelism(), 6)
        with patch.dict(os.environ, {"IIOS_AGENT_PARALLELISM": "2"}):
            self.assertEqual(speed.configured_parallelism(), 2)

    def test_speed_layer_times_agents_and_records_paper_only_performance(self):
        objects = []
        events = []

        def run_one(agent_key, topic, evidence):
            return {
                "agent_key": agent_key,
                "agent": agent_key,
                "status": "complete",
                "disposition": "WATCH",
                "confidence": 0.5,
            }

        def synthesize(*args, **kwargs):
            return {
                "decision_id": "decision_test",
                "paper_mode": True,
                "paper_order_permission": False,
                "trade_execution_permission": False,
                "live_execution": False,
            }

        agents = {
            key: {"agent_key": key, "latency_ms": 10.0}
            for key in ("policy", "macro", "fundamentals", "market_structure", "commodities", "geo_weather", "skeptic", "portfolio")
        }

        def orchestration(case_id):
            return {
                "orchestration": {
                    "orchestration_id": "orchestration_test",
                    "case_id": case_id,
                    "topic": "test topic",
                    "agents": agents,
                    "paper_mode": True,
                    "paper_order_permission": False,
                    "trade_execution_permission": False,
                    "live_execution": False,
                },
                "committee": {
                    "committee_latency_ms": 12.0,
                    "paper_mode": True,
                    "paper_order_permission": False,
                    "trade_execution_permission": False,
                    "live_execution": False,
                },
            }

        module = SimpleNamespace(
            _speed_layer_installed=False,
            MAX_PARALLEL_SPECIALISTS=3,
            FIRST_WAVE=("policy", "macro", "fundamentals", "market_structure", "commodities", "geo_weather"),
            SECOND_WAVE=("skeptic", "portfolio"),
            _run_one=run_one,
            _synthesize_committee=synthesize,
            run_eight_agent_orchestration=orchestration,
            utc_now=lambda: "2026-08-24T20:30:00+00:00",
            record_object=lambda *args, **kwargs: objects.append((args, kwargs)),
            record_event=lambda *args, **kwargs: events.append((args, kwargs)),
        )

        with patch.dict(os.environ, {"IIOS_AGENT_PARALLELISM": "6"}):
            speed.install_orchestration_speed(module)

        self.assertEqual(module.MAX_PARALLEL_SPECIALISTS, 6)

        timed_agent = module._run_one("policy", "topic", [])
        self.assertTrue(timed_agent["timing_measured"])
        self.assertGreaterEqual(timed_agent["latency_ms"], 0.0)

        timed_committee = module._synthesize_committee()
        self.assertTrue(timed_committee["timing_measured"])
        self.assertGreaterEqual(timed_committee["committee_latency_ms"], 0.0)

        result = module.run_eight_agent_orchestration("case_speed_test")
        perf = result["performance"]
        self.assertEqual(perf["first_wave_parallelism"], 6)
        self.assertEqual(perf["serial_agent_latency_ms"], 80.0)
        self.assertFalse(perf["paper_order_permission"])
        self.assertFalse(perf["trade_execution_permission"])
        self.assertFalse(perf["live_execution"])
        self.assertTrue(objects)
        self.assertTrue(events)

    def test_install_is_idempotent(self):
        module = SimpleNamespace(_speed_layer_installed=True, MAX_PARALLEL_SPECIALISTS=3)
        speed.install_orchestration_speed(module)
        self.assertEqual(module.MAX_PARALLEL_SPECIALISTS, 3)


if __name__ == "__main__":
    unittest.main()
