import unittest

import institutional_intelligence as ii


class InstitutionalIntelligenceTests(unittest.TestCase):
    def test_institutional_ownership_preserves_13f_lag(self):
        parsed = ii.parse_institutional_ownership(
            {
                "institutionOwnership": {
                    "ownershipList": [
                        {
                            "organization": "Example Capital",
                            "position": {"raw": 1000},
                            "value": {"raw": 250000},
                            "pctHeld": {"raw": 0.01},
                            "pctChange": {"raw": 0.12},
                            "reportDate": {"raw": 1785542400},
                        },
                        {
                            "organization": "Second Fund",
                            "position": {"raw": 500},
                            "value": {"raw": 125000},
                            "pctHeld": {"raw": 0.005},
                            "pctChange": {"raw": -0.08},
                            "reportDate": {"raw": 1785542400},
                        },
                    ]
                }
            }
        )
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["directional_context"], "MIXED")
        self.assertIn("lagged", parsed["summary"])
        self.assertEqual(len(parsed["details"]["holders"]), 2)

    def test_analyst_revisions_detect_upward_eps_change(self):
        parsed = ii.parse_analyst_revisions(
            {
                "earningsTrend": {
                    "trend": [
                        {
                            "period": "+1y",
                            "epsTrend": {
                                "current": {"raw": 14.0},
                                "30daysAgo": {"raw": 12.0},
                            },
                            "revenueEstimate": {"avg": {"raw": 50000000000}},
                            "earningsEstimate": {"avg": {"raw": 14.0}},
                        }
                    ]
                }
            }
        )
        self.assertEqual(parsed["directional_context"], "REVISING_UP")
        self.assertEqual(parsed["details"]["revised_up"], 1)

    def test_short_interest_change_is_explicit(self):
        parsed = ii.parse_short_interest(
            {
                "defaultKeyStatistics": {
                    "sharesShort": {"raw": 110},
                    "sharesShortPriorMonth": {"raw": 100},
                    "shortRatio": {"raw": 2.5},
                    "shortPercentOfFloat": {"raw": 0.025},
                    "dateShortInterest": {"raw": 1785542400},
                }
            }
        )
        self.assertEqual(parsed["directional_context"], "SHORTS_INCREASING")
        self.assertAlmostEqual(parsed["details"]["change_vs_prior_month"], 0.10)

    def test_options_positioning_uses_oi_and_keeps_hedging_caveat(self):
        parsed = ii.parse_options_positioning(
            {
                "options": [
                    {
                        "expirationDate": {"raw": 1788134400},
                        "calls": [
                            {"openInterest": {"raw": 100}, "volume": {"raw": 50}, "impliedVolatility": {"raw": 0.4}},
                            {"openInterest": {"raw": 100}, "volume": {"raw": 50}, "impliedVolatility": {"raw": 0.5}},
                        ],
                        "puts": [
                            {"openInterest": {"raw": 300}, "volume": {"raw": 100}, "impliedVolatility": {"raw": 0.6}},
                        ],
                    }
                ]
            }
        )
        self.assertEqual(parsed["directional_context"], "PUT_HEAVY")
        self.assertAlmostEqual(parsed["details"]["put_call_open_interest_ratio"], 1.5)
        self.assertIn("hedging", parsed["summary"])

    def test_catalyst_calendar_extracts_earnings_window(self):
        parsed = ii.parse_catalyst_calendar(
            {
                "calendarEvents": {
                    "earnings": {
                        "earningsDate": [{"raw": 1790812800}],
                        "earningsAverage": {"raw": 3.5},
                        "revenueAverage": {"raw": 12000000000},
                    }
                }
            }
        )
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["directional_context"], "CATALYST_PENDING")
        self.assertEqual(parsed["details"]["earnings_average"], 3.5)

    def test_institutional_evidence_is_never_gap_resolution_eligible(self):
        original_list_objects = ii.list_objects
        try:
            ii.list_objects = lambda case_id, object_type: [
                {
                    "institutional_signal_id": "institutional_1",
                    "lane": "analyst_revisions",
                    "lane_label": "Analyst Estimate Revisions",
                    "summary": "EPS estimates moved higher",
                    "directional_context": "REVISING_UP",
                    "source_name": "Yahoo Finance public market data",
                    "source_url": "https://finance.yahoo.com/",
                    "reliability_score": 0.76,
                    "data_as_of": ii.utc_now(),
                    "fresh": True,
                    "admission_status": "CORROBORATING_CONTEXT",
                    "gap_requirement": "Current valuation and consensus revisions",
                }
            ]
            evidence = ii.institutional_evidence("case_test")
        finally:
            ii.list_objects = original_list_objects
        self.assertEqual(len(evidence), 1)
        self.assertFalse(evidence[0]["gap_resolution_eligible"])
        self.assertTrue(evidence[0]["primary_corroboration_required"])


if __name__ == "__main__":
    unittest.main()
