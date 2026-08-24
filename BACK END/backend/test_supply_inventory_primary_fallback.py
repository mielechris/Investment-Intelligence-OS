import unittest

from primary_evidence_contracts import coverage_for_requirement
from supply_inventory_primary_fallback import REQUIRED_SUPPLIERS, SUPPLY_PRIMARY_SNAPSHOTS


SUPPLY_REQUIREMENT = (
    "Supplier-level data for Micron, SK hynix, Samsung, and CXMT covering bit shipments, "
    "wafer starts, utilization, inventories, capacity additions, HBM packaging capacity, yields, "
    "and qualification timelines."
)


class SupplyInventoryPrimaryFallbackTests(unittest.TestCase):
    def test_snapshots_cover_all_named_suppliers(self):
        suppliers = {str(row.get("supplier")) for row in SUPPLY_PRIMARY_SNAPSHOTS}
        self.assertEqual(set(REQUIRED_SUPPLIERS) - suppliers, set())
        self.assertEqual(set(REQUIRED_SUPPLIERS), suppliers)

    def test_snapshots_cover_four_operational_facts_only(self):
        fact_keys = {str(row.get("fact_key")) for row in SUPPLY_PRIMARY_SNAPSHOTS}
        self.assertTrue({"inventory", "bit_shipments", "capacity", "hbm_packaging_yield"}.issubset(fact_keys))
        self.assertNotIn("wafer_starts", fact_keys)
        self.assertNotIn("utilization", fact_keys)

    def test_supplier_coverage_passes_but_operational_fact_coverage_remains_partial(self):
        items = [
            {
                "primary_fact_key": row["fact_key"],
                "claim": row["claim"],
                "source": row["source"],
                "url": row["url"],
                "supplier": row["supplier"],
            }
            for row in SUPPLY_PRIMARY_SNAPSHOTS
        ]
        coverage = coverage_for_requirement(SUPPLY_REQUIREMENT, items)
        self.assertIsNotNone(coverage)
        self.assertEqual(coverage["lane"], "supply_inventory")
        self.assertEqual(coverage["covered_facts"], 4)
        self.assertEqual(set(coverage["missing_fact_keys"]), {"wafer_starts", "utilization"})
        self.assertEqual(set(coverage["covered_suppliers"]), set(REQUIRED_SUPPLIERS))
        self.assertEqual(coverage["missing_suppliers"], [])
        self.assertTrue(coverage["supplier_coverage_gate_passed"])
        self.assertFalse(coverage["threshold_passed"])
        self.assertFalse(coverage["coverage_gate_passed"])

    def test_five_of_six_can_pass_once_all_named_suppliers_are_covered(self):
        items = [
            {
                "primary_fact_key": row["fact_key"],
                "claim": row["claim"],
                "source": row["source"],
                "url": row["url"],
                "supplier": row["supplier"],
            }
            for row in SUPPLY_PRIMARY_SNAPSHOTS
        ]
        items.append({
            "primary_fact_key": "utilization",
            "claim": "Verified current memory-production utilization measurement",
            "source": "Qualified primary source",
            "supplier": "Micron",
            "url": "https://investors.micron.com/example",
        })
        coverage = coverage_for_requirement(SUPPLY_REQUIREMENT, items)
        self.assertIsNotNone(coverage)
        self.assertEqual(coverage["covered_facts"], 5)
        self.assertTrue(coverage["threshold_passed"])
        self.assertEqual(coverage["missing_suppliers"], [])
        self.assertTrue(coverage["coverage_gate_passed"])


if __name__ == "__main__":
    unittest.main()
