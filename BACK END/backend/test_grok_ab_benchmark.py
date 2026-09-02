import unittest

import grok_ab_benchmark as ab


def signature(disposition="WATCH", confidence=0.6, evidence=4):
    return {
        "latency_ms": 100.0,
        "disposition": disposition,
        "confidence": confidence,
        "required_evidence_count": evidence,
        "required_evidence": ["x"] * evidence,
        "agent_count": 8,
        "agent_error_count": 0,
        "failed_guard_checks": [],
        "bull_case_present": True,
        "bear_case_present": True,
        "dissent_present": True,
        "safety_locked": True,
        "paper_mode": True,
    }


class GrokABBenchmarkTests(unittest.TestCase):
    def test_run_count_is_hard_bounded(self):
        self.assertEqual(ab.normalize_runs(0), 1)
        self.assertEqual(ab.normalize_runs(99), ab.MAX_RUNS)

    def test_comparison_can_never_auto_promote_grok(self):
        result = ab.compare_ab(
            [signature(confidence=0.55)],
            [signature(confidence=0.65)],
            {
                "admitted_count": 2,
                "quarantined_count": 1,
                "citation_count": 5,
                "qualification_evidence": False,
                "capital_authority": False,
                "usage": {"estimated_cost_usd": 0.01},
            },
        )
        self.assertTrue(result["experiment_valid"])
        self.assertEqual(result["confidence_delta"], 0.1)
        self.assertFalse(result["architecture_promotion_eligible"])
        self.assertTrue(result["promotion_blockers"])
        self.assertFalse(result["automatic_configuration_change"])
        self.assertFalse(result["trade_execution_permission"])
        self.assertFalse(result["live_execution"])

    def test_safety_failure_invalidates_experiment(self):
        bad = signature()
        bad["safety_locked"] = False
        result = ab.compare_ab(
            [signature()],
            [bad],
            {
                "admitted_count": 1,
                "qualification_evidence": False,
                "capital_authority": False,
            },
        )
        self.assertFalse(result["experiment_valid"])
        self.assertFalse(result["architecture_promotion_eligible"])

    def test_plan_preserves_v1_baseline_and_ledger_isolation(self):
        plan = ab.grok_ab_plan()
        self.assertEqual(plan["baseline"], "IIOS_V1_0")
        self.assertTrue(plan["same_case"])
        self.assertTrue(plan["same_ledger_snapshot"])
        self.assertFalse(plan["live_decision_history_pollution"])
        self.assertFalse(plan["architecture_promotion_automatic"])
        self.assertFalse(plan["paper_order_permission"])
        self.assertFalse(plan["trade_execution_permission"])


if __name__ == "__main__":
    unittest.main()
