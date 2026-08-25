import unittest
from datetime import datetime, timezone

import opportunity_acquisition as oa


class OpportunityAcquisitionTests(unittest.TestCase):

    def test_universe_is_deduplicated_and_capped(self):
        values = ["MU", "mu", {"ticker": "NVDA", "label": "NVIDIA"}] + [f"T{i}" for i in range(30)]
        result = oa.normalize_universe(values)
        tickers = [row["ticker"] for row in result]
        self.assertEqual(tickers[0:2], ["MU", "NVDA"])
        self.assertEqual(len(result), oa.MAX_SCAN_SYMBOLS)
        self.assertEqual(len(tickers), len(set(tickers)))

    def test_invalid_symbols_are_removed(self):
        result = oa.normalize_universe(["", "BAD SYMBOL", "A" * 30, "BRK.B"])
        self.assertEqual(result, [{"ticker": "BRK.B", "label": "BRK.B", "query": "BRK.B"}])

    def test_candidate_score_is_research_priority_not_trade_signal(self):
        now = datetime(2026, 8, 24, 19, 0, tzinfo=timezone.utc)
        quote = {
            "status": "ok",
            "current_price": 100.0,
            "items": [],
            "provider": "test",
        }
        news = [
            {
                "source": "source-a",
                "title": "Company raises earnings guidance as demand and orders rise",
                "claim": "earnings guidance demand orders",
                "timestamp": "2026-08-24T18:00:00+00:00",
            },
            {
                "source": "source-b",
                "title": "New capacity investment follows supply shortage",
                "claim": "capacity investment supply shortage",
                "timestamp": "2026-08-24T17:00:00+00:00",
            },
            {
                "source": "source-c",
                "title": "Tariff policy changes sector outlook",
                "claim": "tariff policy regulation",
                "timestamp": "2026-08-24T16:00:00+00:00",
            },
        ]
        result = oa.score_candidate(ticker="TEST", quote=quote, news_items=news, now=now)
        self.assertGreaterEqual(result["score"], oa.MIN_PROMOTION_SCORE)
        self.assertTrue(result["eligible_for_promotion"])
        self.assertFalse(result["trade_signal"])
        self.assertFalse(result["paper_order_permission"])
        self.assertFalse(result["trade_execution_permission"])
        self.assertFalse(result["live_execution"])

    def test_missing_quote_cannot_promote(self):
        result = oa.score_candidate(
            ticker="TEST",
            quote={"status": "error", "current_price": None},
            news_items=[
                {"source": "a", "title": "earnings demand", "claim": "earnings demand"},
                {"source": "b", "title": "supply capacity", "claim": "supply capacity"},
            ],
        )
        self.assertFalse(result["eligible_for_promotion"])
        self.assertFalse(result["quote_ok"])

    def test_routes_have_no_execution_authority(self):
        paths = {route.path.lower() for route in oa.router.routes}
        self.assertIn("/opportunities/scan", paths)
        self.assertIn("/opportunities/queue", paths)
        self.assertTrue(any("promote" in path for path in paths))
        self.assertFalse(any("execute" in path or "broker" in path or "authorize" in path for path in paths))


if __name__ == "__main__":
    unittest.main()
