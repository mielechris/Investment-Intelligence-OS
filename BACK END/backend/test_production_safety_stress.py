import os
import unittest
from unittest.mock import patch

import adaptive_research_queue as research_queue
import opportunity_scheduler
import orchestration_resilience
import orchestration_worker_pool
import production_safety_freeze
import production_safety_stress


class ProductionSafetyStressTests(unittest.TestCase):
    def setUp(self):
        orchestration_resilience.reset_circuit_breaker()

    def tearDown(self):
        orchestration_resilience.reset_circuit_breaker()

    def test_hundred_case_burst_is_bounded_and_backpressured(self):
        with patch.dict(os.environ, {"IIOS_CASE_WORKERS": "2"}):
            plan = production_safety_stress.synthetic_load_plan(100)
        self.assertEqual(plan["requested_cases"], 100)
        self.assertEqual(plan["accepted_into_bounded_queue"], research_queue.MAX_QUEUE_DEPTH)
        self.assertEqual(plan["deferred_by_capacity"], 50)
        self.assertTrue(plan["backpressure_expected"])
        self.assertTrue(plan["backpressure_state"]["backpressure_active"])
        self.assertLessEqual(plan["workers"], orchestration_worker_pool.MAX_CASE_WORKERS)
        self.assertFalse(plan["trade_execution_permission"])
        self.assertFalse(plan["live_execution"])

    def test_extreme_worker_override_is_hard_capped(self):
        with patch.dict(os.environ, {"IIOS_CASE_WORKERS": "999"}):
            self.assertEqual(
                orchestration_worker_pool.configured_case_workers(),
                orchestration_worker_pool.MAX_CASE_WORKERS,
            )
            plan = production_safety_stress.synthetic_load_plan(20)
        self.assertEqual(plan["workers"], orchestration_worker_pool.MAX_CASE_WORKERS)

    def test_scheduler_default_remains_disabled(self):
        with patch.object(opportunity_scheduler, "_bool_env", side_effect=lambda name, default: default):
            config = opportunity_scheduler.default_config()
        self.assertFalse(config["enabled"])
        self.assertFalse(config["auto_dispatch_enabled"])
        self.assertFalse(config["auto_trade_authority"])
        self.assertFalse(config["trade_execution_permission"])
        self.assertFalse(config["live_execution"])

    def test_model_outage_opens_breaker_and_never_grants_execution(self):
        with patch.object(orchestration_resilience.time, "sleep", return_value=None):
            for _ in range(2):
                with self.assertRaises(TimeoutError):
                    orchestration_resilience.call_with_resilience(
                        lambda: (_ for _ in ()).throw(TimeoutError("503 service unavailable")),
                        role="stress",
                    )
        status = orchestration_resilience.resilience_status()
        self.assertTrue(status["circuit_breaker"]["open"])
        self.assertFalse(status["paper_order_permission"])
        self.assertFalse(status["trade_execution_permission"])
        self.assertFalse(status["live_execution"])

    def test_freeze_manifest_locks_proven_defaults(self):
        with patch.dict(
            os.environ,
            {
                "IIOS_ORCHESTRATION_PROFILE": "baseline",
                "IIOS_CASE_WORKERS": "2",
                "IIOS_OPPORTUNITY_AUTO_SCAN": "0",
                "IIOS_OPPORTUNITY_AUTO_DISPATCH": "0",
            },
        ):
            with patch.object(opportunity_scheduler, "current_config", return_value=opportunity_scheduler.default_config()):
                manifest = production_safety_freeze.production_freeze_manifest()
        self.assertTrue(manifest["all_invariants_pass"])
        self.assertTrue(manifest["current_matches_proven_envelope"])
        self.assertEqual(manifest["proven_production_envelope"]["default_case_workers"], 2)
        self.assertEqual(manifest["proven_production_envelope"]["specialist_parallelism"], 6)
        self.assertEqual(manifest["proven_production_envelope"]["judgment_output_cache"], "OFF")
        self.assertFalse(manifest["automatic_configuration_change"])
        self.assertFalse(manifest["paper_order_permission"])
        self.assertFalse(manifest["trade_execution_permission"])
        self.assertFalse(manifest["live_execution"])

    def test_stress_report_passes_under_proven_envelope(self):
        with patch.dict(
            os.environ,
            {
                "IIOS_ORCHESTRATION_PROFILE": "baseline",
                "IIOS_CASE_WORKERS": "2",
                "IIOS_OPPORTUNITY_AUTO_SCAN": "0",
                "IIOS_OPPORTUNITY_AUTO_DISPATCH": "0",
            },
        ):
            with patch.object(opportunity_scheduler, "current_config", return_value=opportunity_scheduler.default_config()):
                report = production_safety_stress.production_stress_report(100)
        self.assertTrue(report["stress_pass"])
        self.assertTrue(all(report["checks"].values()))
        self.assertFalse(report["auto_trade_authority"])
        self.assertFalse(report["paper_order_permission"])
        self.assertFalse(report["trade_execution_permission"])
        self.assertFalse(report["live_execution"])

    def test_new_safety_routes_are_read_only_surfaces(self):
        paths = {route.path.lower() for route in production_safety_freeze.router.routes}
        self.assertEqual(paths, {"/production-safety/freeze"})
        self.assertFalse(any("broker" in path or "authorization" in path or "paper-order" in path or "live" in path for path in paths))


if __name__ == "__main__":
    unittest.main()
