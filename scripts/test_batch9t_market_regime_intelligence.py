from __future__ import annotations

import unittest
from datetime import datetime, timezone

import iios_market_regime_intelligence as regime


class Batch9TMarketRegimeIntelligenceTest(unittest.TestCase):
    def test_downside_significant_mover_regime_is_classified_without_macro_inference(self) -> None:
        opportunities = [
            {"ticker": f"D{i}", "move_pct": -4.0 - (i % 5), "importance": "HIGH" if i < 4 else "MEDIUM"}
            for i in range(24)
        ] + [
            {"ticker": f"U{i}", "move_pct": 3.2 + (i % 2), "importance": "LOW"}
            for i in range(6)
        ]
        payload = regime.build_regime(
            scorecard={
                "input": {"benchmark_complete": True, "opportunities": opportunities},
                "metrics": {"opportunity_count": 30, "detection_rate_pct": 47.2, "opportunity_miss_rate_pct": 52.8},
            },
            learning={"outcome_count": 0},
            league={"agent_standings": []},
            telemetry={"generated_at": "2026-08-28T22:00:00+00:00"},
            generated_at=datetime(2026, 8, 28, 23, 0, tzinfo=timezone.utc),
        )
        current = payload["current_regime"]
        self.assertEqual(current["regime_label"], "DOWNSIDE_SIGNIFICANT_MOVER_DOMINANCE")
        self.assertEqual(current["evidence_level"], "HIGH")
        self.assertEqual(current["row_availability"], "DETAILED_ROWS_EXPOSED")
        gaps = {row["dimension"]: row for row in payload["dimensions"]}
        self.assertEqual(gaps["CROSS_SECTIONAL_DIRECTION"]["state"], "MEASURED")
        self.assertEqual(gaps["RATES_LIQUIDITY"]["state"], "MEASUREMENT_GAP")
        self.assertEqual(gaps["VOLATILITY_INDEX_TERM_STRUCTURE"]["state"], "MEASUREMENT_GAP")
        self.assertFalse(payload["safety"]["auto_change_portfolio_exposure"])
        self.assertFalse(payload["safety"]["trade_execution_permission"])

    def test_small_sample_stays_low_evidence_and_does_not_fake_macro_regime(self) -> None:
        payload = regime.build_regime(
            scorecard={
                "input": {
                    "benchmark_complete": False,
                    "opportunities": [
                        {"ticker": "A", "move_pct": 5.0},
                        {"ticker": "B", "move_pct": -6.0},
                    ],
                },
                "metrics": {"opportunity_count": 2},
            },
            learning={}, league={}, telemetry={},
        )
        self.assertEqual(payload["current_regime"]["regime_label"], "INSUFFICIENT_SIGNIFICANT_MOVER_SAMPLE")
        self.assertEqual(payload["current_regime"]["evidence_level"], "LOW")
        self.assertFalse(payload["regime_tag_contract"]["historical_backfill_available"])
        self.assertFalse(payload["safety"]["auto_change_thresholds"])
        self.assertTrue(payload["safety"]["human_approval_required"])

    def test_aggregate_metrics_without_rows_are_not_rendered_as_zero_movers(self) -> None:
        payload = regime.build_regime(
            scorecard={
                "input": {"benchmark_complete": True},
                "metrics": {
                    "opportunity_count": 36,
                    "detected_count": 17,
                    "detection_rate_pct": 47.2,
                    "opportunity_miss_rate_pct": 52.8,
                },
            },
            learning={}, league={}, telemetry={},
        )
        current = payload["current_regime"]
        self.assertEqual(current["regime_label"], "SIGNIFICANT_MOVER_ROWS_NOT_EXPOSED")
        self.assertEqual(current["row_availability"], "ROWS_NOT_EXPOSED")
        self.assertEqual(current["reported_opportunity_count"], 36)
        self.assertEqual(current["detailed_row_count"], 0)
        self.assertIsNone(current["sample_count"])
        self.assertIsNone(current["upside_count"])
        dims = {row["dimension"]: row for row in payload["dimensions"]}
        self.assertEqual(dims["CROSS_SECTIONAL_DIRECTION"]["state"], "SOURCE_ROWS_UNAVAILABLE")
        self.assertEqual(dims["MOVE_INTENSITY_DISPERSION"]["state"], "SOURCE_ROWS_UNAVAILABLE")
        self.assertFalse(payload["regime_tag_contract"]["tag_new_sessions"])
        self.assertEqual(payload["factory_context"]["9h_reported_opportunity_count"], 36)
        self.assertEqual(payload["factory_context"]["9h_detailed_mover_rows_exposed"], 0)


if __name__ == "__main__":
    unittest.main()
