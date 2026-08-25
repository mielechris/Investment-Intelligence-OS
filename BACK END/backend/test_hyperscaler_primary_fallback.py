import unittest

from hyperscaler_primary_fallback import HYPERSCALER_PRIMARY_SNAPSHOTS
from primary_evidence_contracts import contract_for_requirement, coverage_for_requirement


HYPERSCALER_REQUIREMENT = (
    "Primary or independently corroborated hyperscaler AI-capex plans linked to server shipments, "
    "memory content, delivery schedules, backlog, cancellations, and enforceable purchasing terms."
)


class HyperscalerPrimaryFallbackTests(unittest.TestCase):
    def test_current_committee_requirement_maps_to_hyperscaler_contract(self):
        lane, contract = contract_for_requirement(HYPERSCALER_REQUIREMENT)
        self.assertEqual(lane, "hyperscaler_demand")
        self.assertEqual(contract["label"], "Hyperscaler Demand")
        self.assertEqual(contract["minimum_fraction"], 1.0)

    def test_primary_snapshots_cover_four_disclosed_facts(self):
        fact_keys = {str(row["fact_key"]) for row in HYPERSCALER_PRIMARY_SNAPSHOTS}
        self.assertEqual(
            fact_keys,
            {"ai_capex", "server_activity", "backlog", "memory_terms"},
        )
        self.assertNotIn("cancellations", fact_keys)

    def test_four_of_five_remains_partial_with_cancellations_open(self):
        items = [
            {
                "primary_fact_key": str(row["fact_key"]),
                "claim": str(row["claim"]),
                "source": str(row["source"]),
                "url": str(row["url"]),
            }
            for row in HYPERSCALER_PRIMARY_SNAPSHOTS
        ]

        coverage = coverage_for_requirement(HYPERSCALER_REQUIREMENT, items)

        self.assertIsNotNone(coverage)
        self.assertEqual(coverage["covered_facts"], 4)
        self.assertEqual(coverage["missing_fact_keys"], ["cancellations"])
        self.assertFalse(coverage["threshold_passed"])
        self.assertFalse(coverage["coverage_gate_passed"])

    def test_all_five_are_required_for_resolution(self):
        items = [
            {
                "primary_fact_key": str(row["fact_key"]),
                "claim": str(row["claim"]),
                "source": str(row["source"]),
                "url": str(row["url"]),
            }
            for row in HYPERSCALER_PRIMARY_SNAPSHOTS
        ]

        items.append(
            {
                "primary_fact_key": "cancellations",
                "claim": "Direct hyperscaler disclosure quantifying cancellations or pushouts.",
                "source": "Qualified hyperscaler primary source",
                "url": "https://example.com/primary",
            }
        )

        coverage = coverage_for_requirement(HYPERSCALER_REQUIREMENT, items)

        self.assertEqual(coverage["covered_facts"], 5)
        self.assertEqual(coverage["missing_fact_keys"], [])
        self.assertTrue(coverage["coverage_gate_passed"])


if __name__ == "__main__":
    unittest.main()
