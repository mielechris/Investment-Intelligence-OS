import unittest

from institutional_integrity_guard import normalize_secondary_institutional_record


class InstitutionalIntegrityGuardTests(unittest.TestCase):
    def test_secondary_13f_without_verified_report_date_is_lagged(self):
        record = {
            "secondary_source": True,
            "source_tier": "SECONDARY_PUBLIC_CONTEXT",
            "lane": "institutional_ownership",
            "data_as_of": "2026-08-23T00:00:00+00:00",
            "age_days": 0,
            "fresh": True,
            "admission_status": "CORROBORATING_CONTEXT",
            "details": {"buyers_12m": 50, "sellers_12m": 20, "fallback_scope": "13F-derived ownership context; reporting lag applies"},
        }
        normalized = normalize_secondary_institutional_record(record)
        self.assertIsNone(normalized["data_as_of"])
        self.assertIsNone(normalized["age_days"])
        self.assertFalse(normalized["fresh"])
        self.assertEqual(normalized["admission_status"], "LAGGED_CONTEXT")
        self.assertTrue(normalized["details"]["reporting_date_unknown"])

    def test_short_interest_percentages_are_normalized_to_decimal_schema(self):
        record = {
            "secondary_source": True,
            "source_tier": "SECONDARY_PUBLIC_CONTEXT",
            "lane": "short_interest",
            "details": {
                "shares_short": 29_892_897,
                "shares_short_prior": 31_000_000,
                "short_percent_float": 2.65,
                "change_pct": -7.2,
                "days_to_cover": 2.4,
                "fallback_scope": "published short-interest report; periodic and lagged",
            },
        }
        normalized = normalize_secondary_institutional_record(record)
        details = normalized["details"]
        self.assertAlmostEqual(details["short_percent_float"], 0.0265)
        self.assertAlmostEqual(details["change_vs_prior_month"], -0.072)
        self.assertEqual(details["short_ratio"], 2.4)
        self.assertEqual(details["shares_short_prior_month"], 31_000_000)
        self.assertEqual(details["percentage_schema"], "DECIMAL_FRACTION")

    def test_analyst_fallback_is_not_labeled_eps_revision_series(self):
        record = {
            "secondary_source": True,
            "source_tier": "SECONDARY_PUBLIC_CONTEXT",
            "lane": "analyst_revisions",
            "directional_context": "REVISION_BIAS_POSITIVE",
            "details": {"fallback_scope": "analyst ratings and target changes; not true EPS-estimate revision history"},
        }
        normalized = normalize_secondary_institutional_record(record)
        self.assertEqual(normalized["directional_context"], "RATING_TARGET_BIAS_POSITIVE")
        self.assertEqual(normalized["details"]["analyst_feed_kind"], "RATINGS_AND_TARGET_ACTIONS")
        self.assertFalse(normalized["details"]["true_eps_revision_series"])

    def test_primary_records_are_not_rewritten(self):
        record = {
            "secondary_source": False,
            "source_tier": "SECONDARY_PUBLIC_MARKET_DATA",
            "lane": "short_interest",
            "details": {"short_percent_float": 0.0265},
        }
        self.assertEqual(normalize_secondary_institutional_record(record), record)


if __name__ == "__main__":
    unittest.main()
