import unittest

from primary_evidence_contracts import coverage_for_requirement, fact_matches


HBM_ECONOMICS_REQUIREMENT = (
    "Verified Micron HBM revenue, shipment volumes, margins, customer concentration, "
    "capacity allocation, and ASP sensitivity."
)


class PrimaryEvidenceSingleFactTests(unittest.TestCase):
    def test_explicit_shipment_record_cannot_satisfy_customer_concentration(self):
        item = {
            "primary_fact_key": "hbm_shipments",
            "claim": "HBM4 is in high-volume shipments for a lead customer and samples shipped to multiple end-customers.",
            "source": "Micron",
            "url": "https://investors.micron.com/example",
        }
        shipment_fact = {
            "key": "hbm_shipments",
            "terms": ("hbm", "shipment", "high-volume"),
        }
        concentration_fact = {
            "key": "customer_concentration",
            "terms": ("hbm", "customer", "concentration", "customer base"),
        }

        self.assertTrue(fact_matches(item, shipment_fact))
        self.assertFalse(fact_matches(item, concentration_fact))

    def test_unclassified_raw_evidence_can_still_use_semantic_matching(self):
        item = {
            "claim": "Micron says the HBM customer base includes six customers.",
            "source": "Micron",
            "url": "https://investors.micron.com/example",
        }
        concentration_fact = {
            "key": "customer_concentration",
            "terms": ("hbm", "customer", "concentration", "customer base"),
        }
        self.assertTrue(fact_matches(item, concentration_fact))

    def test_five_hbm_facts_still_leave_customer_concentration_open(self):
        items = [
            {"primary_fact_key": "hbm_revenue", "claim": "HBM revenue"},
            {"primary_fact_key": "hbm_shipments", "claim": "HBM shipments"},
            {"primary_fact_key": "hbm_margin", "claim": "HBM higher-margin mix contribution"},
            {"primary_fact_key": "capacity_allocation", "claim": "HBM capacity allocation"},
            {"primary_fact_key": "hbm_asp_sensitivity", "claim": "HBM pricing premium"},
        ]
        coverage = coverage_for_requirement(HBM_ECONOMICS_REQUIREMENT, items)
        self.assertIsNotNone(coverage)
        self.assertEqual(coverage["covered_facts"], 5)
        self.assertEqual(coverage["missing_fact_keys"], ["customer_concentration"])
        self.assertFalse(coverage["coverage_gate_passed"])


if __name__ == "__main__":
    unittest.main()
