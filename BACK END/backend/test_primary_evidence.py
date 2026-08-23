import unittest

from gap_quality import build_resolution_matrix
from primary_evidence import _fact_from_sec_title
from primary_evidence_contracts import contract_for_requirement, coverage_for_requirement


FINANCIAL_REQUIREMENT = (
    "Micron's latest filing-based revenue mix, HBM volumes and margins, inventory, free cash flow, "
    "debt and cash, capex commitments, and sensitivity to memory ASP changes."
)


class PrimaryEvidenceTests(unittest.TestCase):
    def test_round7_financial_requirement_maps_to_fact_contract(self):
        lane, contract = contract_for_requirement(FINANCIAL_REQUIREMENT)
        self.assertEqual(lane, "micron_financials")
        self.assertEqual(contract["label"], "Micron Filing Financials")
        self.assertGreaterEqual(len(contract["facts"]), 8)

    def test_sec_tag_mapping_is_specific(self):
        self.assertEqual(
            _fact_from_sec_title("Micron Technology InventoryNet"),
            ("micron_financials", "inventory"),
        )
        self.assertEqual(
            _fact_from_sec_title("Micron Technology WeightedAverageNumberOfDilutedSharesOutstanding"),
            ("valuation_market", "diluted_shares"),
        )

    def test_fact_coverage_uses_explicit_primary_fact_keys(self):
        items = [
            {"primary_fact_key": "revenue", "claim": "Revenue=1"},
            {"primary_fact_key": "inventory", "claim": "InventoryNet=2"},
            {"primary_fact_key": "cash_flow", "claim": "Operating cash flow=3"},
            {"primary_fact_key": "cash", "claim": "Cash=4"},
            {"primary_fact_key": "debt", "claim": "Debt=5"},
            {"primary_fact_key": "capex", "claim": "Capex=6"},
        ]
        coverage = coverage_for_requirement(FINANCIAL_REQUIREMENT, items)
        self.assertIsNotNone(coverage)
        self.assertEqual(coverage["covered_facts"], 6)
        self.assertTrue(coverage["coverage_gate_passed"])

    def test_resolution_stays_blocked_when_fact_contract_is_incomplete(self):
        items = [
            {
                "source": "SEC EDGAR",
                "source_type": "filing",
                "evidence_type": "fundamental",
                "url": "https://data.sec.gov/a",
                "claim": "Micron revenue increased",
                "timestamp": "2026-08-22T00:00:00+00:00",
                "reliability_score": 0.99,
                "gap_requirement": FINANCIAL_REQUIREMENT,
                "primary_fact_key": "revenue",
            },
            {
                "source": "Micron IR",
                "source_type": "company",
                "evidence_type": "fundamental",
                "url": "https://investors.micron.com/a",
                "claim": "Micron HBM demand remains strong",
                "timestamp": "2026-08-22T00:00:00+00:00",
                "reliability_score": 0.95,
                "gap_requirement": FINANCIAL_REQUIREMENT,
                "primary_fact_key": "hbm_margin",
            },
        ]
        row = build_resolution_matrix([FINANCIAL_REQUIREMENT], items)[0]
        self.assertFalse(row["resolved"])
        self.assertIn("PRIMARY_FACT_COVERAGE_INCOMPLETE", row["blockers"])

    def test_resolution_can_pass_with_fact_coverage_and_source_diversity(self):
        facts = ["revenue", "hbm_margin", "inventory", "cash_flow", "cash", "debt", "capex"]
        items = []
        for index, fact in enumerate(facts):
            sec = index % 2 == 0
            items.append(
                {
                    "source": "SEC EDGAR" if sec else "Micron IR",
                    "source_type": "filing" if sec else "company",
                    "evidence_type": "fundamental",
                    "url": "https://data.sec.gov/a" if sec else "https://investors.micron.com/a",
                    "claim": f"Verified primary fact {fact}",
                    "timestamp": "2026-08-22T00:00:00+00:00",
                    "reliability_score": 0.99 if sec else 0.95,
                    "gap_requirement": FINANCIAL_REQUIREMENT,
                    "primary_fact_key": fact,
                }
            )
        row = build_resolution_matrix([FINANCIAL_REQUIREMENT], items)[0]
        self.assertTrue(row["fact_coverage"]["coverage_gate_passed"])
        self.assertTrue(row["resolved"])


if __name__ == "__main__":
    unittest.main()
