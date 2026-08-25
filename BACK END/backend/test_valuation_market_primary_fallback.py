import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from evidence_engine import normalize_item
from primary_evidence_contracts import coverage_for_requirement
from valuation_market_primary_fallback import _options_record, _summary_records, install_valuation_market_primary_fallback


VALUATION_REQUIREMENT = (
    "Current MU price, diluted shares, forward consensus revenue and EPS with revisions, "
    "valuation multiples, short interest, options positioning, and portfolio factor overlap."
)


class ValuationMarketPrimaryFallbackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fake = SimpleNamespace(
            _capture_market=lambda case_id, case: ([], []),
            _lane_status=lambda case_id, lane, records: {"facts": []},
        )
        install_valuation_market_primary_fallback(fake)

    def test_contract_includes_portfolio_overlap_and_requires_it(self):
        items = [
            {"primary_fact_key": "market_price", "claim": "MU price"},
            {"primary_fact_key": "diluted_shares", "claim": "diluted shares"},
            {"primary_fact_key": "consensus", "claim": "consensus"},
            {"primary_fact_key": "valuation", "claim": "forward P/E"},
            {"primary_fact_key": "short_interest", "claim": "shares short"},
            {"primary_fact_key": "options", "claim": "put/call"},
        ]
        coverage = coverage_for_requirement(VALUATION_REQUIREMENT, items)
        self.assertIsNotNone(coverage)
        self.assertEqual(coverage["total_facts"], 7)
        self.assertEqual(coverage["covered_facts"], 6)
        self.assertIn("portfolio_overlap", coverage["missing_critical_fact_keys"])
        self.assertFalse(coverage["coverage_gate_passed"])

    def test_latest_completed_market_session_survives_weekend(self):
        now = datetime.now(timezone.utc)
        item = normalize_item(
            {
                "claim": "MU latest completed-session price=100",
                "source": "Stooq",
                "source_type": "market_data",
                "evidence_type": "market_session",
                "observed_at": (now - timedelta(hours=48)).isoformat(),
                "reliability_score": 0.90,
            },
            now=now,
        )
        self.assertFalse(item["stale"])
        self.assertGreaterEqual(item["quality_score"], 0.65)

    def test_summary_records_keep_consensus_valuation_and_short_separate(self):
        summary = {
            "price": {"regularMarketPrice": {"raw": 100.0}},
            "summaryDetail": {"forwardPE": {"raw": 20.0}},
            "defaultKeyStatistics": {
                "sharesShort": {"raw": 1000},
                "sharesShortPriorMonth": {"raw": 1200},
                "shortPercentOfFloat": {"raw": 0.025},
                "shortRatio": {"raw": 1.2},
                "dateShortInterest": {"raw": 1787000000},
            },
            "earningsTrend": {
                "trend": [
                    {
                        "period": "+1y",
                        "epsTrend": {"current": {"raw": 5.0}, "30daysAgo": {"raw": 4.5}},
                        "revenueEstimate": {"avg": {"raw": 50000000000}},
                    }
                ]
            },
        }
        rows = _summary_records("MU", summary, "https://example.test/summary", datetime.now(timezone.utc).isoformat())
        self.assertEqual({key for key, _ in rows}, {"consensus", "valuation", "short_interest"})

    def test_options_record_is_single_purpose(self):
        result = {
            "options": [
                {
                    "expirationDate": {"raw": 1788000000},
                    "calls": [{"openInterest": {"raw": 100}, "volume": {"raw": 50}, "impliedVolatility": {"raw": 0.4}}],
                    "puts": [{"openInterest": {"raw": 50}, "volume": {"raw": 25}, "impliedVolatility": {"raw": 0.5}}],
                }
            ]
        }
        parsed = _options_record("MU", result, "https://example.test/options", datetime.now(timezone.utc).isoformat())
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed[0], "options")
        self.assertIn("put/call open-interest ratio=0.5", parsed[1]["claim"])


if __name__ == "__main__":
    unittest.main()
