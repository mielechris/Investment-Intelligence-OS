import unittest
from datetime import datetime, timezone

from gap_quality import build_resolution_matrix, curate_gap_evidence


NOW = datetime.now(timezone.utc).isoformat()


class GapQualityTests(unittest.TestCase):
    def test_quality_firewall_rejects_low_quality_news_and_caps_source(self):
        items = [
            {
                "source": "weak blog",
                "source_type": "news_aggregator",
                "evidence_type": "news",
                "url": f"https://weak.example/{i}",
                "claim": f"memory rumor {i}",
                "timestamp": NOW,
                "reliability_score": 0.20,
            }
            for i in range(4)
        ]
        result = curate_gap_evidence(items)
        self.assertEqual(result["admitted_count"], 0)
        self.assertEqual(result["rejected_count"], 4)
        self.assertTrue(all(row["reason"] == "QUALITY_BELOW_ADMISSION_FLOOR" for row in result["rejected"]))

    def test_resolution_requires_quality_and_source_diversity(self):
        requirement = "Current independent HBM and DRAM pricing evidence"
        supporting = [
            {
                "source": "Primary Company",
                "source_type": "company",
                "evidence_type": "fundamental",
                "url": "https://company.example/pricing",
                "claim": "HBM and DRAM pricing increased in the current quarter",
                "timestamp": NOW,
                "reliability_score": 0.93,
                "gap_requirement": requirement,
            },
            {
                "source": "Independent Market Data",
                "source_type": "market_data",
                "evidence_type": "market_data",
                "url": "https://market.example/dram",
                "claim": "Current DRAM price index is higher quarter over quarter",
                "timestamp": NOW,
                "reliability_score": 0.90,
                "gap_requirement": requirement,
            },
        ]
        matrix = build_resolution_matrix([requirement], supporting)
        self.assertEqual(len(matrix), 1)
        self.assertTrue(matrix[0]["resolved"])
        self.assertGreaterEqual(matrix[0]["independent_sources"], 2)
        self.assertGreaterEqual(matrix[0]["high_quality_items"], 2)

    def test_one_source_cannot_resolve_requirement(self):
        requirement = "Verified hyperscaler orders and HBM qualification status"
        supporting = [
            {
                "source": "One Source",
                "source_type": "company",
                "evidence_type": "fundamental",
                "url": "https://one.example/a",
                "claim": "Hyperscaler order and HBM qualification details",
                "timestamp": NOW,
                "reliability_score": 0.95,
                "gap_requirement": requirement,
            },
            {
                "source": "One Source",
                "source_type": "company",
                "evidence_type": "fundamental",
                "url": "https://one.example/b",
                "claim": "More hyperscaler order and HBM qualification details",
                "timestamp": NOW,
                "reliability_score": 0.95,
                "gap_requirement": requirement,
            },
        ]
        matrix = build_resolution_matrix([requirement], supporting)
        self.assertFalse(matrix[0]["resolved"])
        self.assertIn("INSUFFICIENT_SOURCE_DIVERSITY", matrix[0]["blockers"])


if __name__ == "__main__":
    unittest.main()
