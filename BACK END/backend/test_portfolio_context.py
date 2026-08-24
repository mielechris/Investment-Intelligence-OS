import unittest

from portfolio_context import _compute_overlap, _factor_set


class PortfolioContextTests(unittest.TestCase):
    def test_factor_parser_normalizes_csv_and_pipe_values(self):
        self.assertEqual(_factor_set("AI, Memory|Semiconductors"), {"ai", "memory", "semiconductors"})

    def test_overlap_does_not_double_count_one_position(self):
        positions = [
            {"ticker": "NVDA", "weight_pct": 40.0, "sector": "Semiconductors", "factors": ["AI", "Growth"]},
            {"ticker": "JPM", "weight_pct": 30.0, "sector": "Financials", "factors": ["Value", "Rates"]},
            {"ticker": "XOM", "weight_pct": 30.0, "sector": "Energy", "factors": ["Energy", "Inflation"]},
        ]
        overlap = _compute_overlap("NVDA", "Semiconductors", {"ai", "memory"}, positions)
        self.assertEqual(overlap["exact_ticker_weight_pct"], 40.0)
        self.assertEqual(overlap["same_sector_weight_pct"], 40.0)
        self.assertEqual(overlap["factor_overlap_weight_pct"], 40.0)
        self.assertEqual(overlap["combined_overlap_weight_pct"], 40.0)
        self.assertEqual(overlap["concentration_level"], "MODERATE")

    def test_overlap_aggregates_distinct_exposures(self):
        positions = [
            {"ticker": "NVDA", "weight_pct": 20.0, "sector": "Semiconductors", "factors": ["AI"]},
            {"ticker": "AMD", "weight_pct": 15.0, "sector": "Semiconductors", "factors": ["AI"]},
            {"ticker": "MSFT", "weight_pct": 25.0, "sector": "Software", "factors": ["AI", "Cloud"]},
            {"ticker": "JPM", "weight_pct": 40.0, "sector": "Financials", "factors": ["Rates"]},
        ]
        overlap = _compute_overlap("MU", "Semiconductors", {"ai", "memory"}, positions)
        self.assertEqual(overlap["exact_ticker_weight_pct"], 0.0)
        self.assertEqual(overlap["same_sector_weight_pct"], 35.0)
        self.assertEqual(overlap["factor_overlap_weight_pct"], 60.0)
        self.assertEqual(overlap["combined_overlap_weight_pct"], 60.0)
        self.assertEqual(overlap["concentration_level"], "HIGH")


if __name__ == "__main__":
    unittest.main()
