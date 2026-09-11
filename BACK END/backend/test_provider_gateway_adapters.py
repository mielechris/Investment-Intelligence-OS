import unittest

from provider_gateway_adapters import ENDPOINTS, normalize
from provider_gateway_contract import PILOT

NOW = "2026-09-14T13:30:30+00:00"


class AdapterTests(unittest.TestCase):
    def test_massive_raw_nanoseconds_and_fields_preserved(self):
        stamp = 1789392630000000001
        value = normalize("MASSIVE", "BULK_SNAPSHOT", {"status": "OK", "tickers": [
            {"ticker": "MU", "lastQuote": {"p": 99, "P": 101, "t": stamp}, "lastTrade": {"p": 100, "t": stamp}}]})
        row = value["observations"][0]
        self.assertEqual(row["provider_event_timestamps"]["quote"], stamp)
        self.assertEqual(row["fields"], {"bid": 99, "ask": 101, "trade_price": 100})

    def test_missing_provider_time_not_fabricated(self):
        value = normalize("MASSIVE", "BULK_SNAPSHOT", {"tickers": [{"ticker": "MU"}]})
        self.assertIsNone(value["observations"][0]["event_time"])
        self.assertEqual(len(value["observations"][0]["absent_fields"]), 3)

    def test_alpaca_snapshot_shape(self):
        value = normalize("ALPACA", "MULTI_SYMBOL_SNAPSHOT", {"MU": {"latestQuote": {"bp": 1, "ap": 2, "t": NOW}, "latestTrade": {"p": 1.5, "t": NOW}}})
        self.assertEqual(value["observations"][0]["event_time"], NOW)

    def test_company_facts_etf_fields_unavailable(self):
        rows = [{"ticker": s, "name": "Synthetic instrument", "sector": "Manufactured", "industry": "Manufactured", "exchange": "SYNTHETIC", "observation_time": NOW} for s in PILOT]
        value = normalize("FINANCIAL_DATASETS", "COMPANY_FACTS", {"records": rows})
        self.assertEqual(len(value["observations"]), 10)
        for row in value["observations"][1:]:
            self.assertIsNone(row["fields"]["sector"])
            self.assertIn("sector", row["absent_fields"])

    def test_all_corporate_endpoint_contracts(self):
        for endpoint in ENDPOINTS["FINANCIAL_DATASETS"]:
            with self.subTest(endpoint=endpoint):
                value = normalize("FINANCIAL_DATASETS", endpoint, {"records": [{"ticker": "MU", "observation_time": NOW}]})
                self.assertTrue(value["observations"][0]["absent_fields"])

    def test_bigdata_required_times_and_refs_are_explicit(self):
        for endpoint in ENDPOINTS["BIGDATA"]:
            value = normalize("BIGDATA", endpoint, {"records": [{"ticker": "MU", "observation_time": NOW,
                "publication_time": "2026-09-14T13:00:00+00:00", "source_references": ["https://example.invalid/document"], "document_identity": "synthetic-document"}]})
            self.assertEqual(value["observations"][0]["source_references"], ["https://example.invalid/document"])

    def test_alpha_vantage_is_enrichment_contract_only(self):
        value = normalize("ALPHA_VANTAGE", "ENRICHMENT", {"records": [{"ticker": "MU", "indicator": "SYNTHETIC", "value": 5, "observation_time": NOW}]})
        self.assertEqual(value["observations"][0]["fields"]["value"], 5)
        with self.assertRaises(ValueError):
            normalize("ALPHA_VANTAGE", "BULK_SNAPSHOT", {})

    def test_yahoo_candidate_order_and_selection_unchanged(self):
        candidates = [{"ticker": s, "price": 1, "change_pct": n, "volume_ratio": 2, "screeners": ["most_actives"]} for n, s in enumerate(("XLK", "MU", "SPY"))]
        value = normalize("YAHOO", "SCREENER_DISCOVERY", {"candidates": candidates, "snapshot_complete": True})
        self.assertEqual([r["ticker"] for r in value["observations"]], [r["ticker"] for r in candidates])

    def test_duplicate_unexpected_and_partial_status_preserved(self):
        value = normalize("MASSIVE", "BULK_SNAPSHOT", {"status": "PARTIAL", "tickers": [{"ticker": "MU"}, {"ticker": "MU"}, {"ticker": "OUTSIDE"}]})
        self.assertEqual(value["duplicates"], ["MU"])
        self.assertTrue(value["partial_response"])
        self.assertEqual(len(value["observations"]), 3)

    def test_error_text_and_unsafe_reference_rejected(self):
        with self.assertRaisesRegex(ValueError, "PROVIDER_ERROR"):
            normalize("MASSIVE", "BULK_SNAPSHOT", {"error": "UNTRUSTED_PROVIDER_TEXT"})
        with self.assertRaises(ValueError):
            normalize("BIGDATA", "NEWS", {"records": [{"ticker": "MU", "source_references": ["https://user:pass@example.invalid"]}]})
