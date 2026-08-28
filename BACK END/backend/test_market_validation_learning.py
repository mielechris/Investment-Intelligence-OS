from __future__ import annotations

import unittest

from market_validation_learning import build_learning_report


class MarketValidationLearningTest(unittest.TestCase):
    def test_high_miss_rate_is_advisory_only(self) -> None:
        scorecard = {
            "input": {"benchmark_complete": True},
            "metrics": {
                "detection_rate_pct": 50.0,
                "opportunity_miss_rate_pct": 50.0,
                "false_positive_rate_pct": 75.0,
                "median_detection_latency_minutes": 25.0,
                "promotion_rate_of_detected_pct": 8.0,
                "cadence_reliability_pct": 100.0,
                "provider_error_count": 0,
            },
            "opportunities": [
                {
                    "ticker": "MISS",
                    "event_at": "2026-08-28T15:00:00+00:00",
                    "move_pct": -8.0,
                    "importance": "HIGH",
                    "missed": True,
                    "detected": False,
                    "promoted": False,
                }
            ],
        }
        report = build_learning_report(scorecard)
        codes = {row["code"] for row in report["recommendations"]}
        self.assertIn("MISS_RATE_HIGH", codes)
        self.assertIn("FALSE_POSITIVE_RATE_HIGH", codes)
        self.assertIn("DETECTION_LATENCY_HIGH", codes)
        self.assertTrue(report["learning_contract"]["recommendations_are_advisory_only"])
        self.assertFalse(report["learning_contract"]["auto_apply_threshold_changes"])
        self.assertFalse(report["learning_contract"]["trade_execution_permission"])
        self.assertFalse(report["learning_contract"]["live_execution"])

    def test_incomplete_benchmark_blocks_tuning_conclusions(self) -> None:
        scorecard = {
            "input": {"benchmark_complete": False},
            "metrics": {
                "detection_rate_pct": 0.0,
                "opportunity_miss_rate_pct": 100.0,
                "false_positive_rate_pct": None,
                "cadence_reliability_pct": 100.0,
                "provider_error_count": 0,
            },
            "opportunities": [],
        }
        report = build_learning_report(scorecard)
        codes = {row["code"] for row in report["recommendations"]}
        self.assertEqual(report["status"], "VALIDATION_INCOMPLETE")
        self.assertIn("BENCHMARK_INCOMPLETE", codes)
        self.assertNotIn("MISS_RATE_HIGH", codes)


if __name__ == "__main__":
    unittest.main()
