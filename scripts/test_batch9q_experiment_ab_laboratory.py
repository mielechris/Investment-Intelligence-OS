from __future__ import annotations

import unittest
from datetime import datetime, timezone

import iios_experiment_ab_laboratory as lab


class Batch9QExperimentABLaboratoryTest(unittest.TestCase):
    def _office(self, upgrade_id: str) -> dict:
        return {
            "status": "CHIEF_INTELLIGENCE_OFFICE_ADVISORY_READY",
            "improvement_memo": {
                "top_five_upgrades": [
                    {
                        "upgrade_id": upgrade_id,
                        "title": upgrade_id,
                        "suggested_implementation_batch": "9Q",
                    }
                ]
            },
        }

    def test_radar_variant_can_be_kept_for_human_review_only(self) -> None:
        baseline = {
            "scenario_id": "score_45_capacity_5",
            "min_promotion_score": 45.0,
            "max_cases_per_cycle": 5,
            "captured_count": 17,
            "extra_nonbenchmark_ticker_count": 10,
            "selection_events": 100,
        }
        variant = {
            "scenario_id": "score_40_capacity_5",
            "min_promotion_score": 40.0,
            "max_cases_per_cycle": 5,
            "captured_count": 20,
            "extra_nonbenchmark_ticker_count": 18,
            "selection_events": 125,
            "vs_baseline": {
                "marginal_captured_count": 3,
                "marginal_extra_nonbenchmark_ticker_count": 8,
                "selection_load_delta_pct": 25.0,
            },
        }
        payload = lab.build_lab(
            office=self._office("RADAR_RECALL_REVIEW"),
            shadow={
                "status": "ADVISORY_READY",
                "complete_session_count": 6,
                "minimum_complete_sessions_for_advice": 5,
                "baseline": baseline,
                "scenario_rollup": [baseline, variant],
                "advisory_frontier": [variant],
            },
            learning={},
            telemetry={},
            generated_at=datetime(2026, 8, 28, tzinfo=timezone.utc),
        )
        experiment = payload["experiments"][0]
        self.assertEqual(experiment["verdict"], "KEEP")
        self.assertEqual(experiment["next_action"], "HUMAN_REVIEW_ONLY")
        self.assertEqual(experiment["comparison"]["marginal_captured_count"], 3)
        self.assertEqual(payload["summary"]["production_changes_applied"], 0)
        self.assertFalse(payload["safety"]["auto_apply_variants"])
        self.assertFalse(payload["safety"]["trade_execution_permission"])
        self.assertFalse(payload["safety"]["live_execution"])

    def test_radar_waits_when_shadow_sample_is_immature(self) -> None:
        payload = lab.build_lab(
            office=self._office("RADAR_RECALL_REVIEW"),
            shadow={
                "status": "WARMUP_COLLECTING_COMPLETE_SESSIONS",
                "complete_session_count": 0,
                "minimum_complete_sessions_for_advice": 5,
                "baseline": None,
                "scenario_rollup": [],
            },
            learning={},
            telemetry={},
        )
        experiment = payload["experiments"][0]
        self.assertEqual(experiment["verdict"], "NEED_MORE_DATA")
        self.assertEqual(experiment["status"], "WAITING_FOR_SAMPLE")
        self.assertEqual(experiment["next_action"], "COLLECT_MORE_SHADOW_SESSIONS")

    def test_no_frontier_rejects_variant_and_keeps_governed_baseline(self) -> None:
        baseline = {
            "scenario_id": "score_45_capacity_5",
            "min_promotion_score": 45.0,
            "max_cases_per_cycle": 5,
            "captured_count": 20,
            "selection_events": 90,
        }
        payload = lab.build_lab(
            office=self._office("RADAR_RECALL_REVIEW"),
            shadow={
                "status": "ADVISORY_READY",
                "complete_session_count": 7,
                "minimum_complete_sessions_for_advice": 5,
                "baseline": baseline,
                "scenario_rollup": [baseline],
                "advisory_frontier": [],
            },
            learning={},
            telemetry={},
        )
        experiment = payload["experiments"][0]
        self.assertEqual(experiment["verdict"], "REJECT")
        self.assertEqual(experiment["next_action"], "KEEP_GOVERNED_BASELINE")

    def test_model_routing_is_measurement_gap_not_fake_ab_result(self) -> None:
        payload = lab.build_lab(
            office=self._office("MODEL_TASK_LEAGUE"),
            shadow={},
            learning={},
            telemetry={},
        )
        experiment = payload["experiments"][0]
        self.assertEqual(experiment["verdict"], "NEED_MORE_DATA")
        self.assertEqual(experiment["status"], "BLOCKED_BY_MEASUREMENT_GAP")
        self.assertIsNone(experiment["baseline_arm"])
        self.assertIsNone(experiment["variant_arm"])

    def test_outcome_maturity_gate_is_measurement_only(self) -> None:
        payload = lab.build_lab(
            office=self._office("OUTCOME_MEMORY_MATURITY"),
            shadow={},
            learning={"mature_5d_count": 4},
            telemetry={},
        )
        experiment = payload["experiments"][0]
        self.assertEqual(experiment["verdict"], "NEED_MORE_DATA")
        self.assertEqual(experiment["sample"], {"current": 4, "required": 20})
        self.assertTrue(payload["safety"]["human_approval_required"])
        self.assertFalse(payload["safety"]["capital_authority"])


if __name__ == "__main__":
    unittest.main()
