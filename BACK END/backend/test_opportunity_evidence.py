import unittest
from types import SimpleNamespace
from unittest.mock import patch

import opportunity_evidence as evidence
import opportunity_evidence_hardening as hardening


class OpportunityEvidenceTests(unittest.TestCase):
    def test_cnbc_quote_parser_normalizes_public_quote(self):
        payload = {
            "FormattedQuoteResult": {
                "FormattedQuote": [
                    {
                        "symbol": "NVDA",
                        "code": 0,
                        "last": "208.48",
                        "last_time": "2026-08-24T16:00:00.000-0400",
                    }
                ]
            }
        }
        with patch.object(evidence, "_json_request", return_value=payload):
            price, timestamp, url = evidence._fetch_cnbc_quote("NVDA")
        self.assertEqual(price, 208.48)
        self.assertIn("2026-08-24", timestamp)
        self.assertIn("quote.cnbc.com", url)

    def test_two_agreeing_quote_sources_pass(self):
        with patch.object(evidence, "_fetch_cnbc_quote", return_value=(100.0, "2026-08-24T19:00:00+00:00", "https://cnbc.test")), patch.object(evidence, "_fetch_yahoo_chart", return_value=(101.0, "2026-08-24T19:01:00+00:00", "https://yahoo.test")):
            quote = evidence.fetch_crosschecked_quote("TEST")
        self.assertEqual(quote["status"], "ok")
        self.assertTrue(quote["cross_checked"])
        self.assertEqual(quote["provider_count"], 2)
        self.assertEqual(set(quote["providers"]), {"CNBC", "Yahoo Finance"})
        self.assertEqual(quote["current_price"], 101.0)

    def test_material_quote_disagreement_is_rejected(self):
        with patch.object(evidence, "_fetch_cnbc_quote", return_value=(100.0, "2026-08-24T19:00:00+00:00", "https://cnbc.test")), patch.object(evidence, "_fetch_yahoo_chart", return_value=(110.0, "2026-08-24T19:01:00+00:00", "https://yahoo.test")):
            quote = evidence.fetch_crosschecked_quote("TEST")
        self.assertEqual(quote["status"], "conflict")
        self.assertFalse(quote["cross_checked"])
        self.assertIsNone(quote["current_price"])

    def test_single_quote_source_does_not_count_as_crosschecked(self):
        with patch.object(evidence, "_fetch_cnbc_quote", side_effect=ValueError("down")), patch.object(evidence, "_fetch_yahoo_chart", return_value=(101.0, "2026-08-24T19:01:00+00:00", "https://yahoo.test")):
            quote = evidence.fetch_crosschecked_quote("TEST")
        self.assertEqual(quote["status"], "single_source")
        self.assertFalse(quote["cross_checked"])
        self.assertEqual(quote["provider_count"], 1)
        self.assertEqual(quote["providers"], ["Yahoo Finance"])

    def test_two_news_feeds_are_deduplicated(self):
        gdelt = [{"source": "Reuters", "title": "Company raises guidance as AI demand grows", "claim": "Company raises guidance as AI demand grows", "url": "https://reuters.test/a"}]
        google = [
            {"source": "Reuters", "title": "Company raises guidance as AI demand grows - Reuters", "claim": "Company raises guidance as AI demand grows - Reuters", "url": "https://news.google.test/a"},
            {"source": "Bloomberg", "title": "Supply remains tight into next quarter", "claim": "Supply remains tight into next quarter", "url": "https://news.google.test/b"},
        ]
        with patch.object(evidence, "fetch_gdelt_news", return_value=gdelt), patch.object(evidence, "fetch_google_news_rss", return_value=google):
            bundle = evidence.fetch_news_bundle("TEST AI demand", limit=4)
        self.assertEqual(bundle["provider_count"], 2)
        self.assertEqual(bundle["item_count"], 2)
        self.assertFalse(bundle["trade_signal"])
        self.assertFalse(bundle["live_execution"])

    def test_news_fails_soft_if_one_feed_is_down(self):
        google = [{"source": "WSJ", "title": "Demand improves", "claim": "Demand improves", "url": "https://news.google.test/c"}]
        with patch.object(evidence, "fetch_gdelt_news", side_effect=TimeoutError("down")), patch.object(evidence, "fetch_google_news_rss", return_value=google):
            bundle = evidence.fetch_news_bundle("TEST demand", limit=4)
        self.assertEqual(bundle["provider_count"], 1)
        self.assertEqual(bundle["item_count"], 1)
        self.assertIn("GDELT", bundle["failed_providers"])

    def test_adapter_only_replaces_research_inputs(self):
        module = SimpleNamespace(fetch_market_quote=None, fetch_gdelt_news=None)
        hardening.install_opportunity_evidence_hardening(module)
        self.assertIs(module.fetch_market_quote, evidence.fetch_crosschecked_quote)
        self.assertIs(module.fetch_gdelt_news, hardening._multi_provider_news)


if __name__ == "__main__":
    unittest.main()
