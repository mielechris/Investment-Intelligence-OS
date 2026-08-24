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

    def test_primary_snapshots_only_cover_disclosed_facts(self):
        fact_keys = {str(row["fact_key"]) for row in HYPERSCALER_PRIMARY_SNAPSHOTS}
        self.assertEqual(fact_keys, {"ai_capex", "server_activity", "backlog"})
        self.assertNotIn("cancellations", fact_keys)
        self.assertNotIn("memory_terms", fact_keys)

    def test_three_of_five_hyperscaler_facts_remain_unresolved(self):
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
        self.assertEqual(coverage["covered_facts"], 3)
        self.assertEqual(set(coverage["missing_fact_keys"]), {"cancellations", "memory_terms"})
        self.assertFalse(coverage["coverage_gate_passed"])


if __name__ == "__main__":
    unittest.main()
