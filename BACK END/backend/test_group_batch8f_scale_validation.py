import unittest
from unittest.mock import patch

import model_scale_validation as calibration


def evaluation(
    model: str,
    task_type: str,
    benchmark_id: str,
    score: float,
    *,
    latency_ms: float = 1000.0,
    cost_usd: float = 0.05,
):
    return {
        "model": model,
        "task_type": task_type,
        "benchmark_id": benchmark_id,
        "human_or_governed_benchmark_attested": True,
        "metrics": {
            "factual_accuracy": score,
            "citation_quality": score,
            "completeness": score,
            "dissent_detection": score,
            "committee_usefulness": score,
        },
        "latency_ms": latency_ms,
        "cost_usd": cost_usd,
    }


class GroupBatch8FScaleValidationTests(
    unittest.TestCase
):
    def test_unattested_benchmark_is_rejected(self):
        row = evaluation(
            "IIOS_OPENAI_CORE",
            "POLICY_MACRO",
            "benchmark_1",
            0.8,
        )
        row[
            "human_or_governed_benchmark_attested"
        ] = False
        with self.assertRaises(ValueError):
            calibration.normalize_evaluation(row)

    def test_unknown_model_and_task_fail_closed(self):
        with self.assertRaises(ValueError):
            calibration.normalize_evaluation(
                evaluation(
                    "UNKNOWN_MODEL",
                    "POLICY_MACRO",
                    "benchmark_1",
                    0.8,
                )
            )
        with self.assertRaises(ValueError):
            calibration.normalize_evaluation(
                evaluation(
                    "IIOS_OPENAI_CORE",
                    "TRADE_EXECUTION",
                    "benchmark_1",
                    0.8,
                )
            )

    def test_immature_samples_keep_neutral_weights(self):
        rows = [
            evaluation(
                "IIOS_OPENAI_CORE",
                "POLICY_MACRO",
                f"benchmark_{index}",
                0.9,
            )
            for index in range(4)
        ]
        rows.extend(
            evaluation(
                "KIMI_RESEARCH",
                "POLICY_MACRO",
                f"benchmark_{index}",
                0.8,
            )
            for index in range(4)
        )
        result = calibration.build_calibration(rows)
        task = result["tasks"]["POLICY_MACRO"]
        self.assertEqual(
            task["status"],
            "INSUFFICIENT_MATURE_MODELS",
        )
        for model in task[
            "model_recommendations"
        ].values():
            self.assertEqual(
                model["recommended_task_weight"],
                1.0,
            )
            self.assertFalse(
                model["recommendation_active"]
            )
            self.assertFalse(
                model[
                    "automatically_applied_to_council"
                ]
            )

    def test_task_specific_strengths_produce_different_bounded_recommendations(
        self,
    ):
        rows = []
        for index in range(5):
            benchmark = f"benchmark_{index}"
            rows.extend(
                [
                    evaluation(
                        "IIOS_OPENAI_CORE",
                        "POLICY_MACRO",
                        benchmark,
                        0.95,
                    ),
                    evaluation(
                        "KIMI_RESEARCH",
                        "POLICY_MACRO",
                        benchmark,
                        0.70,
                    ),
                    evaluation(
                        "IIOS_OPENAI_CORE",
                        "DEEP_RESEARCH",
                        benchmark,
                        0.72,
                    ),
                    evaluation(
                        "KIMI_RESEARCH",
                        "DEEP_RESEARCH",
                        benchmark,
                        0.96,
                    ),
                ]
            )

        result = calibration.build_calibration(rows)
        policy = result["tasks"]["POLICY_MACRO"]
        deep = result["tasks"]["DEEP_RESEARCH"]

        self.assertEqual(
            policy["status"],
            "READY_FOR_MANUAL_REVIEW",
        )
        self.assertEqual(
            deep["status"],
            "READY_FOR_MANUAL_REVIEW",
        )

        policy_weights = {
            model: row[
                "recommended_task_weight"
            ]
            for model, row
            in policy[
                "model_recommendations"
            ].items()
        }
        deep_weights = {
            model: row[
                "recommended_task_weight"
            ]
            for model, row
            in deep[
                "model_recommendations"
            ].items()
        }

        self.assertGreater(
            policy_weights["IIOS_OPENAI_CORE"],
            policy_weights["KIMI_RESEARCH"],
        )
        self.assertGreater(
            deep_weights["KIMI_RESEARCH"],
            deep_weights["IIOS_OPENAI_CORE"],
        )
        for weight in [
            *policy_weights.values(),
            *deep_weights.values(),
        ]:
            self.assertGreaterEqual(
                weight,
                calibration.MIN_RECOMMENDED_WEIGHT,
            )
            self.assertLessEqual(
                weight,
                calibration.MAX_RECOMMENDED_WEIGHT,
            )

    def test_duplicate_benchmark_cannot_inflate_maturity(self):
        duplicate = evaluation(
            "IIOS_OPENAI_CORE",
            "DISSENT_DETECTION",
            "same_benchmark",
            0.95,
        )
        rows = [duplicate for _ in range(10)]
        result = calibration.build_calibration(rows)
        self.assertEqual(
            result["deduplicated_evaluation_count"],
            1,
        )
        self.assertEqual(
            result["duplicate_evaluation_count"],
            9,
        )
        summary = result["tasks"][
            "DISSENT_DETECTION"
        ]["model_recommendations"][
            "IIOS_OPENAI_CORE"
        ]
        self.assertFalse(summary["mature"])

    def test_scale_run_is_hard_capped(self):
        rows = [
            evaluation(
                "IIOS_OPENAI_CORE",
                "GENERAL_RESEARCH",
                f"benchmark_{index}",
                0.8,
            )
            for index in range(
                calibration.MAX_SCALE_EVALUATIONS + 1
            )
        ]
        with self.assertRaises(ValueError):
            calibration.build_calibration(rows)

    def test_calibration_has_zero_decision_or_execution_authority(
        self,
    ):
        rows = []
        for index in range(5):
            rows.extend(
                [
                    evaluation(
                        "IIOS_OPENAI_CORE",
                        "GENERAL_RESEARCH",
                        f"benchmark_{index}",
                        0.9,
                    ),
                    evaluation(
                        "KIMI_RESEARCH",
                        "GENERAL_RESEARCH",
                        f"benchmark_{index}",
                        0.85,
                    ),
                ]
            )
        result = calibration.build_calibration(rows)
        self.assertFalse(
            result["universal_model_weighting"]
        )
        self.assertTrue(
            result["manual_promotion_required"]
        )
        self.assertFalse(
            result[
                "automatically_applied_to_council"
            ]
        )
        self.assertTrue(
            result[
                "governed_iios_committee_remains_authoritative"
            ]
        )
        self.assertFalse(result["committee_override"])
        self.assertFalse(result["risk_override"])
        self.assertFalse(
            result["qualification_evidence"]
        )
        self.assertFalse(
            result["gap_resolution_eligible"]
        )
        self.assertFalse(
            result["fact_resolution_authority"]
        )
        self.assertFalse(result["capital_authority"])
        self.assertFalse(result["trade_signal"])
        self.assertFalse(result["auto_trade_authority"])
        self.assertFalse(
            result["paper_order_permission"]
        )
        self.assertFalse(
            result["trade_execution_permission"]
        )
        self.assertFalse(result["live_execution"])

    def test_nonpersisted_scale_run_writes_nothing(self):
        rows = [
            evaluation(
                "IIOS_OPENAI_CORE",
                "GENERAL_RESEARCH",
                f"benchmark_{index}",
                0.9,
            )
            for index in range(5)
        ]
        rows.extend(
            evaluation(
                "KIMI_RESEARCH",
                "GENERAL_RESEARCH",
                f"benchmark_{index}",
                0.8,
            )
            for index in range(5)
        )
        with patch.object(
            calibration,
            "record_object",
        ) as record_object, patch.object(
            calibration,
            "record_event",
        ) as record_event:
            result = calibration.run_scale_validation(
                {
                    "evaluations": rows,
                    "persist": False,
                }
            )
        self.assertFalse(result["persisted"])
        record_object.assert_not_called()
        record_event.assert_not_called()

    def test_recorded_evaluation_never_gains_authority(self):
        row = evaluation(
            "GROK_NARRATIVE",
            "NARRATIVE_SENTIMENT",
            "benchmark_1",
            0.8,
        )
        with patch.object(
            calibration,
            "record_object",
        ) as record_object, patch.object(
            calibration,
            "record_event",
        ):
            result = calibration.record_evaluation(row)
        self.assertTrue(record_object.called)
        self.assertTrue(
            result["operational_evaluation_only"]
        )
        self.assertFalse(
            result["qualification_evidence"]
        )
        self.assertFalse(
            result["fact_resolution_authority"]
        )
        self.assertFalse(result["trade_signal"])
        self.assertFalse(
            result["trade_execution_permission"]
        )
        self.assertFalse(result["live_execution"])

    def test_status_and_routes_expose_no_execution_controls(
        self,
    ):
        with patch.object(
            calibration,
            "_rows",
            return_value=[],
        ):
            status = calibration.status()
        self.assertFalse(
            status["universal_model_weighting"]
        )
        self.assertTrue(
            status["manual_promotion_required"]
        )
        self.assertFalse(
            status[
                "automatically_applied_to_council"
            ]
        )
        self.assertFalse(
            status["trade_execution_permission"]
        )
        self.assertFalse(status["live_execution"])

        paths = {
            route.path
            for route in calibration.router.routes
        }
        self.assertIn(
            "/intelligence/model-calibration/status",
            paths,
        )
        self.assertIn(
            "/intelligence/model-calibration/evaluations",
            paths,
        )
        self.assertIn(
            "/intelligence/model-calibration/run",
            paths,
        )
        self.assertFalse(
            any(
                "execute" in path.lower()
                or "broker" in path.lower()
                or "live-trade" in path.lower()
                for path in paths
            )
        )


if __name__ == "__main__":
    unittest.main()
