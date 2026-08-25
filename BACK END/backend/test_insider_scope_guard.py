import unittest
from datetime import datetime, timezone

import insider_scope_guard as guard


class InsiderScopeGuardTests(unittest.TestCase):
    def test_political_secondary_record_is_out_of_scope(self):
        record = {
            "secondary_source": True,
            "reporting_owner": "Julia Letlow House (R-LA)",
            "reporting_owner_role": "Role reported by secondary public source",
        }
        self.assertTrue(guard._is_non_corporate_secondary(record))
        self.assertFalse(guard._in_scope(record))

    def test_corporate_secondary_record_remains_in_scope(self):
        record = {
            "secondary_source": True,
            "reporting_owner": "Sanjay Mehrotra",
            "reporting_owner_role": "CEO",
        }
        self.assertFalse(guard._is_non_corporate_secondary(record))
        self.assertTrue(guard._in_scope(record))

    def test_secondary_only_coverage_does_not_claim_10b5_or_ownership(self):
        coverage = guard._coverage([
            {
                "secondary_source": True,
                "source_type": "secondary_public_aggregator",
                "reporting_owner": "Sanjay Mehrotra",
            }
        ])
        self.assertEqual(coverage["active_source_tier"], "SECONDARY_PUBLIC_CONTEXT")
        self.assertTrue(coverage["open_market_direction_covered"])
        self.assertFalse(coverage["plan_10b5_1_covered"])
        self.assertFalse(coverage["beneficial_ownership_covered"])
        self.assertTrue(coverage["secondary_requires_primary_corroboration"])

    def test_stale_dataset_does_not_claim_current_activity(self):
        now = datetime(2026, 8, 23, tzinfo=timezone.utc)
        freshness = guard._freshness(
            [{"transaction_date": "2025-10-20", "secondary_source": True}],
            now=now,
        )
        self.assertFalse(freshness["recent_activity_covered"])
        self.assertTrue(freshness["historical_only"])
        self.assertGreater(freshness["latest_record_age_days"], 90)

    def test_recent_dataset_can_support_current_window(self):
        now = datetime(2026, 8, 23, tzinfo=timezone.utc)
        freshness = guard._freshness(
            [{"transaction_date": "2026-08-01", "secondary_source": True}],
            now=now,
        )
        self.assertTrue(freshness["recent_activity_covered"])
        self.assertFalse(freshness["historical_only"])
        self.assertLess(freshness["latest_record_age_days"], 90)

    def test_records_sort_by_transaction_date_descending(self):
        rows = guard._sorted_records([
            {"transaction_date": "2025-09-02"},
            {"transaction_date": "2026-07-24"},
            {"transaction_date": "2026-01-10"},
        ])
        self.assertEqual(rows[0]["transaction_date"], "2026-07-24")
        self.assertEqual(rows[-1]["transaction_date"], "2025-09-02")


if __name__ == "__main__":
    unittest.main()
