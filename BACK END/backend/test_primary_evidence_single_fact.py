import unittest

from primary_evidence_contracts import fact_matches


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


if __name__ == "__main__":
    unittest.main()
