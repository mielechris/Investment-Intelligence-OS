import unittest

import orchestration_ab_benchmark as ab


class OrchestrationABBenchmarkTests(unittest.TestCase):
    def _signature(
        self,
        *,
        latency=35000.0,
        disposition="WATCH",
        confidence=0.6,
        evidence_count=6,
        guards=None,
        errors=0,
        safety=True,
    ):
        return {
            "runtime_profile": "test",
            "latency_ms": latency,
            "disposition": disposition,
            "confidence": confidence,
            "required_evidence_count": evidence_count,
            "required_evidence": ["item"] * evidence_count,
            "failed_guard_checks": list(guards or []),
            "agent_count": 8,
            "agent_error_count": errors,
            "bull_case_present": True,
            "bear_case_present": True,
            "dissent_present": True,
            "safety_ok": safety,
            "paper_mode": True,
        }

    def test_run_count_is_bounded(self):
        self.assertEqual(ab.normalize_runs(0), 1)
        self.assertEqual(ab.normalize_runs(2), 2)
        self.assertEqual(ab.normalize_runs(99), ab.MAX_RUNS_PER_PROFILE)

    def test_quality_signature_preserves_governance_and_safety(self):
        result = {
            "orchestration": {
                "agents": {
                    f"a{i}": {"status": "complete"}
                    for i in range(8)
                },
                "paper_order_permission": False,
                "trade_execution_permission": False,
                "live_execution": False,
            },
            "committee": {
                "runtime_profile": "baseline",
                "disposition": "WATCH",
                "confidence": 0.7,
                "required_evidence": ["fresh filing", "valuation"],
                "bull_case": "bull",
                "bear_case": "bear",
                "dissent": "dissent",
                "orchestration_guard": {"failed_checks": []},
                "paper_mode": True,
                "paper_order_permission": False,
                "trade_execution_permission": False,
                "live_execution": False,
            },
            "performance": {
                "total_latency_ms": 30000.0,
                "paper_order_permission": False,
                "trade_execution_permission": False,
                "live_execution": False,
            },
        }
        signature = ab.quality_signature(result)
        self.assertEqual(signature["agent_count"], 8)
        self.assertEqual(signature["required_evidence_count"], 2)
        self.assertTrue(signature["safety_ok"])
        self.assertEqual(signature["failed_guard_checks"], [])

    def test_stable_faster_profile_can_be_eligible_for_manual_review(self):
        baseline = [
            self._signature(latency=35000, confidence=0.62, evidence_count=6),
            self._signature(latency=34000, confidence=0.58, evidence_count=6),
        ]
        speed = [
            self._signature(latency=28000, confidence=0.60, evidence_count=6),
            self._signature(latency=27500, confidence=0.57, evidence_count=5),
        ]
        result = ab.compare_profiles(baseline, speed)
        self.assertTrue(result["speed_profile_eligible_for_manual_default_review"])
        self.assertEqual(result["recommendation"], "ELIGIBLE_FOR_MANUAL_DEFAULT_REVIEW")
        self.assertFalse(result["automatic_default_change"])
        self.assertFalse(result["trade_execution_permission"])
        self.assertFalse(result["live_execution"])

    def test_confidence_instability_keeps_baseline(self):
        baseline = [
            self._signature(latency=35000, confidence=0.82),
            self._signature(latency=34000, confidence=0.80),
        ]
        speed = [
            self._signature(latency=28000, confidence=0.25),
            self._signature(latency=27500, confidence=0.28),
        ]
        result = ab.compare_profiles(baseline, speed)
        self.assertFalse(result["checks"]["confidence_delta_within_025"])
        self.assertEqual(result["recommendation"], "KEEP_BASELINE_AND_CONTINUE_TRIAL")
        self.assertFalse(result["speed_profile_eligible_for_manual_default_review"])

    def test_disposition_change_keeps_baseline(self):
        baseline = [self._signature(disposition="WATCH") for _ in range(2)]
        speed = [self._signature(disposition="NO_TRADE", latency=28000) for _ in range(2)]
        result = ab.compare_profiles(baseline, speed)
        self.assertFalse(result["checks"]["cross_profile_disposition_match"])
        self.assertEqual(result["recommendation"], "KEEP_BASELINE_AND_CONTINUE_TRIAL")

    def test_guard_or_safety_failure_can_never_be_eligible(self):
        baseline = [self._signature() for _ in range(2)]
        speed = [
            self._signature(latency=28000, guards=["all_eight_agents_complete"]),
            self._signature(latency=27500, safety=False),
        ]
        result = ab.compare_profiles(baseline, speed)
        self.assertFalse(result["speed_profile_eligible_for_manual_default_review"])
        self.assertFalse(result["checks"]["speed_guards_clean"])
        self.assertFalse(result["checks"]["speed_safety_locked"])

    def test_child_result_parser_uses_explicit_marker(self):
        payload = {"committee": {"disposition": "WATCH"}}
        stdout = "noise\n" + ab.CHILD_MARKER + __import__("json").dumps(payload) + "\n"
        self.assertEqual(ab._parse_child_result(stdout), payload)


if __name__ == "__main__":
    unittest.main()
