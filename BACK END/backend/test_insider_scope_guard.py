import unittest

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


if __name__ == "__main__":
    unittest.main()
