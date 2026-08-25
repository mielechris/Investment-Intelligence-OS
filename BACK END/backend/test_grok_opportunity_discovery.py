import unittest
from unittest.mock import patch

import grok_opportunity_discovery as discovery


class GrokOpportunityDiscoveryTests(unittest.TestCase):
    @patch.object(discovery, "fetch_grok_social_context")
    @patch.object(discovery, "grok_plan")
    @patch.object(discovery, "record_object")
    @patch.object(discovery, "record_event")
    def test_discovery_requires_verified_source_diversity_and_never_promotes(self, event, record, plan, fetch):
        plan.return_value = {"enabled": True, "api_key_configured": True}
        fetch.return_value = {
            "citation_urls": [
                "https://x.com/a/status/1",
                "https://x.com/b/status/2",
            ],
            "raw_candidate_tickers": [
                {
                    "ticker": "ABC",
                    "rationale": "Two independent discussions flag a new catalyst.",
                    "confidence": 0.9,
                    "source_urls": ["https://x.com/a/status/1", "https://x.com/b/status/2"],
                },
                {
                    "ticker": "XYZ",
                    "rationale": "Only one cited account.",
                    "confidence": 0.7,
                    "source_urls": ["https://x.com/a/status/1"],
                },
            ],
            "usage": {},
        }
        result = discovery.discover_grok_opportunities("fast moving stocks", persist=True)
        self.assertEqual(result["nominated_count"], 1)
        self.assertEqual(result["quarantined_count"], 1)
        self.assertFalse(result["automatic_promotion"])
        self.assertEqual(result["agents_started"], 0)
        self.assertFalse(result["trade_execution_permission"])
        nominated = result["nominations"][0]
        self.assertFalse(nominated["eligible_for_standard_promotion"])
        self.assertLessEqual(nominated["advisory_confidence"], 0.60)

    @patch.object(discovery, "get_object")
    @patch.object(discovery, "fetch_market_quote")
    @patch.object(discovery, "fetch_gdelt_news")
    @patch.object(discovery, "score_candidate")
    @patch.object(discovery, "record_object")
    @patch.object(discovery, "record_event")
    def test_revalidation_creates_standard_candidate_but_does_not_promote_case(self, event, record, score, news, quote, get_object):
        get_object.return_value = {
            "grok_opportunity_candidate_id": "grok_opportunity_1",
            "ticker": "ABC",
            "rationale": "test",
            "eligible_for_iios_revalidation": True,
            "standard_candidate_id": None,
        }
        quote.return_value = {"status": "ok", "current_price": 10.0, "provider": "test", "items": [{"claim": "quote"}]}
        news.return_value = [{"claim": "news1"}, {"claim": "news2"}]
        score.return_value = {
            "ticker": "ABC",
            "score": 70.0,
            "priority": "HIGH",
            "eligible_for_promotion": True,
            "reason_codes": ["TEST"],
            "catalyst_categories": ["earnings"],
            "news_count": 2,
            "source_count": 2,
            "recent_24h_count": 2,
            "quote_ok": True,
            "trade_signal": False,
            "direction": "UNSPECIFIED",
            "paper_mode": True,
            "paper_order_permission": False,
            "trade_execution_permission": False,
            "live_execution": False,
        }
        result = discovery.revalidate_grok_candidate("grok_opportunity_1")
        self.assertTrue(result["standard_promotion_available"])
        self.assertFalse(result["automatic_promotion"])
        self.assertEqual(result["agents_started"], 0)
        self.assertTrue(result["next_step"].startswith("POST /opportunities/opportunity_"))
        self.assertIsNone(result["standard_candidate"]["promoted_case_id"])

    def test_plan_requires_standard_iios_gate(self):
        plan = discovery.grok_opportunity_plan()
        self.assertFalse(plan["grok_can_create_governed_case_directly"])
        self.assertTrue(plan["standard_quote_required"])
        self.assertTrue(plan["standard_news_required"])
        self.assertTrue(plan["standard_opportunity_score_required"])
        self.assertFalse(plan["automatic_promotion"])
        self.assertFalse(plan["automatic_agent_run"])
        self.assertFalse(plan["trade_execution_permission"])


if __name__ == "__main__":
    unittest.main()
