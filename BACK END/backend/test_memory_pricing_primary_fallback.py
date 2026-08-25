import unittest

from memory_pricing_primary_fallback import MEMORY_PRICING_SNAPSHOTS
from primary_evidence_contracts import coverage_for_requirement


MEMORY_REQUIREMENT = (
    "Independent HBM, DRAM and NAND pricing using at least two unrelated pricing sources."
)


class MemoryPricingPrimaryFallbackTests(unittest.TestCase):
    def test_snapshots_cover_all_three_pricing_facts(self):
        keys = {row["fact_key"] for row in MEMORY_PRICING_SNAPSHOTS}
        self.assertTrue(
            {"hbm_pricing", "dram_pricing", "nand_pricing"}.issubset(keys)
        )

    def test_two_unrelated_domains_exist(self):
        domains = {
            row["url"].split("/")[2].lower()
            for row in MEMORY_PRICING_SNAPSHOTS
            if row.get("url", "").startswith("http")
        }
        self.assertIn("www.trendforce.com", domains)
        self.assertIn("www.sec.gov", domains)
        self.assertGreaterEqual(len(domains), 2)

    def test_no_synthetic_independent_source_record_exists(self):
        self.assertNotIn(
            "independent_sources",
            {row["fact_key"] for row in MEMORY_PRICING_SNAPSHOTS},
        )

    def test_memory_pricing_reaches_four_of_four_from_real_source_diversity(self):
        items = [
            {
                "primary_fact_key": row["fact_key"],
                "claim": row["claim"],
                "source": row["source"],
                "url": row["url"],
            }
            for row in MEMORY_PRICING_SNAPSHOTS
        ]

        coverage = coverage_for_requirement(MEMORY_REQUIREMENT, items)

        self.assertIsNotNone(coverage)
        self.assertEqual(coverage["covered_facts"], 4)
        self.assertEqual(coverage["total_facts"], 4)
        self.assertEqual(coverage["missing_fact_keys"], [])
        self.assertTrue(coverage["coverage_gate_passed"])


if __name__ == "__main__":
    unittest.main()
