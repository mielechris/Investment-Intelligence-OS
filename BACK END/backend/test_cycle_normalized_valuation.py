import unittest

from cycle_normalized_valuation import (
    build_cycle_normalized_stress,
)


class CycleNormalizedValuationTests(unittest.TestCase):

    def setUp(self):
        self.result = build_cycle_normalized_stress(
            current_price=912.655,
            forward_eps=73.36,
            ttm_eps=44.24,
            diluted_shares_m=1145.0,
        )

    def test_baseline_uses_verified_inputs(self):
        baseline = self.result["baseline"]

        self.assertEqual(
            baseline["current_price"],
            912.655,
        )
        self.assertEqual(
            baseline["forward_eps"],
            73.36,
        )
        self.assertEqual(
            baseline["ttm_eps"],
            44.24,
        )
        self.assertEqual(
            baseline["diluted_shares_m"],
            1145.0,
        )

    def test_normalized_cycle_is_mechanical_not_forecast(self):
        cycle = self.result["normalized_cycle"]

        self.assertEqual(cycle["low_eps"], 44.24)
        self.assertEqual(cycle["high_eps"], 73.36)
        self.assertEqual(cycle["mid_eps"], 58.8)
        self.assertFalse(cycle["forecast_claim"])

    def test_ten_percent_asp_decline_one_point_five_elasticity(self):
        scenario = next(
            row
            for row in self.result["scenarios"]
            if row["asp_decline_pct"] == 10.0
            and row["earnings_elasticity_to_asp"] == 1.5
        )

        self.assertEqual(
            scenario["earnings_haircut_pct"],
            15.0,
        )
        self.assertAlmostEqual(
            scenario["stressed_eps"],
            62.356,
            places=3,
        )
        self.assertTrue(
            scenario["assumption_only"]
        )
        self.assertFalse(
            scenario["observed_fact"]
        )

    def test_twenty_percent_asp_decline_two_x_elasticity(self):
        scenario = next(
            row
            for row in self.result["scenarios"]
            if row["asp_decline_pct"] == 20.0
            and row["earnings_elasticity_to_asp"] == 2.0
        )

        self.assertEqual(
            scenario["earnings_haircut_pct"],
            40.0,
        )

        self.assertAlmostEqual(
            scenario["stressed_eps"],
            44.016,
            places=3,
        )

    def test_engine_cannot_authorize_trade(self):
        governance = self.result["governance"]

        self.assertFalse(
            governance["may_resolve_primary_fact"]
        )
        self.assertFalse(
            governance["may_authorize_trade"]
        )
        self.assertFalse(
            governance["paper_buy_enabled"]
        )


    def test_gap_hunter_quote_override_wins_over_monitor_snapshot(self):
        from cycle_normalized_valuation import _effective_quote

        snapshot = {
            "quote": {
                "current_price": 910.87,
            }
        }

        gap_quote = {
            "current_price": 917.25,
        }

        result = _effective_quote(
            snapshot,
            gap_quote,
        )

        self.assertEqual(
            result["current_price"],
            917.25,
        )

    def test_monitor_quote_used_without_override(self):
        from cycle_normalized_valuation import _effective_quote

        snapshot = {
            "quote": {
                "current_price": 910.87,
            }
        }

        result = _effective_quote(snapshot)

        self.assertEqual(
            result["current_price"],
            910.87,
        )


if __name__ == "__main__":
    unittest.main()
