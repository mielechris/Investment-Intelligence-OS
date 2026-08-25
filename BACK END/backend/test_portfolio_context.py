import unittest

import portfolio_context
from portfolio_context import _compute_overlap, _factor_set, _supersede_prior_overlap


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

    def test_new_snapshot_supersedes_prior_current_overlap_evidence(self):
        old_list_objects = portfolio_context.list_objects
        old_record_object = portfolio_context.record_object
        old_record_event = portfolio_context.record_event
        written = []
        try:
            portfolio_context.list_objects = lambda case_id, object_type: [
                {
                    "primary_evidence_id": "primary_old",
                    "lane": "valuation_market",
                    "fact_key": "portfolio_overlap",
                    "first_party_governed_source": True,
                    "gap_resolution_eligible": True,
                },
                {
                    "primary_evidence_id": "primary_other",
                    "lane": "valuation_market",
                    "fact_key": "portfolio_overlap",
                    "first_party_governed_source": True,
                    "gap_resolution_eligible": False,
                },
            ]
            portfolio_context.record_object = lambda object_id, object_type, case_id, payload, topic=None: written.append(payload)
            portfolio_context.record_event = lambda *args, **kwargs: None
            _supersede_prior_overlap("case_test", {"topic": "test"}, "portfolio_snapshot_new")
        finally:
            portfolio_context.list_objects = old_list_objects
            portfolio_context.record_object = old_record_object
            portfolio_context.record_event = old_record_event

        self.assertEqual(len(written), 1)
        self.assertFalse(written[0]["gap_resolution_eligible"])
        self.assertEqual(written[0]["superseded_by_portfolio_snapshot_id"], "portfolio_snapshot_new")


if __name__ == "__main__":
    unittest.main()
