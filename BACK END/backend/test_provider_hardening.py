import unittest
from unittest.mock import patch

import provider_hardening as providers


class ProviderHardeningTests(unittest.TestCase):
    @patch.object(providers, "_json_request")
    def test_gdelt_normalizes_timestamp_and_reliability(self, mock_json):
        mock_json.return_value = {
            "articles": [
                {
                    "url": "https://example.com/memory",
                    "title": "HBM demand remains strong",
                    "domain": "example.com",
                    "seendate": "20260822T201500Z",
                    "language": "English",
                    "sourcecountry": "United States",
                }
            ]
        }
        items = providers.fetch_gdelt_news({"query": "HBM memory", "limit": 5})
        self.assertEqual(len(items), 1)
        self.assertTrue(items[0]["timestamp"].startswith("2026-08-22T20:15:00"))
        self.assertEqual(items[0]["reliability_score"], 0.55)

    @patch.object(providers, "_json_request")
    def test_sec_facts_use_fundamental_freshness_class(self, mock_json):
        mock_json.return_value = {
            "entityName": "Micron Technology",
            "facts": {
                "us-gaap": {
                    "InventoryNet": {
                        "units": {
                            "USD": [
                                {
                                    "val": 100,
                                    "end": "2026-05-31",
                                    "filed": "2026-06-30",
                                    "form": "10-Q",
                                    "accn": "test",
                                }
                            ]
                        }
                    }
                }
            },
        }
        items = providers.fetch_sec_companyfacts(
            {"cik": "723125", "tags": ["InventoryNet"], "limit": 5}
        )
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["evidence_type"], "fundamental")
        self.assertEqual(items[0]["reliability_score"], 0.98)
        self.assertIn("InventoryNet", items[0]["claim"])

    def test_market_quote_falls_back_to_yahoo(self):
        with patch.object(providers, "_fetch_stooq_current", side_effect=ValueError("bad current")), \
             patch.object(providers, "_fetch_stooq_history", side_effect=ValueError("bad history")), \
             patch.object(
                 providers,
                 "_fetch_yahoo_chart",
                 return_value=(123.45, "2026-08-22T20:00:00+00:00", "https://example.com/chart"),
             ):
            quote = providers.fetch_market_quote("MU.US")
        self.assertEqual(quote["status"], "ok")
        self.assertEqual(quote["provider"], "Yahoo Finance")
        self.assertEqual(quote["current_price"], 123.45)
        self.assertEqual(len(quote["items"]), 1)

    def test_market_quote_fail_soft(self):
        with patch.object(providers, "_fetch_stooq_current", side_effect=ValueError("a")), \
             patch.object(providers, "_fetch_stooq_history", side_effect=ValueError("b")), \
             patch.object(providers, "_fetch_yahoo_chart", side_effect=ValueError("c")):
            quote = providers.fetch_market_quote("MU.US")
        self.assertEqual(quote["status"], "error")
        self.assertIsNone(quote["current_price"])
        self.assertIn("Yahoo Finance", quote["error"])


if __name__ == "__main__":
    unittest.main()
