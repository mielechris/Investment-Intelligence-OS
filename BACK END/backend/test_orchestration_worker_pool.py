import unittest
from unittest.mock import patch

import orchestration_worker_pool as pool


class OrchestrationWorkerPoolTests(unittest.TestCase):
    def test_case_ids_are_deduplicated_validated_and_capped(self):
        values = ["bad", "case_a", "case_a", "case_b"] + [f"case_{i}" for i in range(20)]
        result = pool.normalize_case_ids(values)
        self.assertEqual(result[0:2], ["case_a", "case_b"])
        self.assertEqual(len(result), pool.MAX_BATCH_CASES)
        self.assertEqual(len(result), len(set(result)))

    def test_batch_is_bounded_and_paper_only(self):
        def fake_run(case_id):
            return {
                "orchestration": {"orchestration_id": f"orch_{case_id}"},
                "committee": {"disposition": "WATCH", "confidence": 0.5},
                "performance": {"total_latency_ms": 10.0},
            }

        with patch.object(pool, "run_eight_agent_orchestration", side_effect=fake_run):
            result = pool.run_case_batch(["case_a", "case_b", "case_c"])

        self.assertEqual(result["requested_case_count"], 3)
        self.assertEqual(result["completed_case_count"], 3)
        self.assertEqual(result["case_workers"], 2)
        self.assertLessEqual(result["case_workers"], pool.MAX_CASE_WORKERS)
        self.assertFalse(result["auto_trade_authority"])
        self.assertFalse(result["paper_order_permission"])
        self.assertFalse(result["trade_execution_permission"])
        self.assertFalse(result["live_execution"])
        for row in result["results"]:
            self.assertFalse(row["paper_order_permission"])
            self.assertFalse(row["trade_execution_permission"])
            self.assertFalse(row["live_execution"])

    def test_one_case_failure_does_not_unlock_or_crash_batch(self):
        def fake_run(case_id):
            if case_id == "case_bad":
                raise ValueError("unknown case")
            return {
                "orchestration": {"orchestration_id": "orch_good"},
                "committee": {"disposition": "WATCH", "confidence": 0.4},
                "performance": {"total_latency_ms": 10.0},
            }

        with patch.object(pool, "run_eight_agent_orchestration", side_effect=fake_run):
            result = pool.run_case_batch(["case_good", "case_bad"])

        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["completed_case_count"], 1)
        self.assertEqual(result["error_case_count"], 1)
        failed = next(row for row in result["results"] if row["case_id"] == "case_bad")
        self.assertEqual(failed["status"], "error")
        self.assertFalse(failed["trade_execution_permission"])
        self.assertFalse(failed["live_execution"])

    def test_empty_batch_is_rejected(self):
        with self.assertRaises(ValueError):
            pool.run_case_batch([])

    def test_routes_are_manual_research_only(self):
        paths = {route.path.lower() for route in pool.router.routes}
        self.assertIn("/orchestration-batch/plan", paths)
        self.assertIn("/orchestration-batch/run", paths)
        self.assertFalse(
            any(
                "broker" in path
                or "authorization" in path
                or "paper-order" in path
                or "live" in path
                for path in paths
            )
        )
        plan = pool.batch_plan()
        self.assertTrue(plan["manual_only"])
        self.assertFalse(plan["auto_trade_authority"])
        self.assertFalse(plan["trade_execution_permission"])
        self.assertFalse(plan["live_execution"])


if __name__ == "__main__":
    unittest.main()
