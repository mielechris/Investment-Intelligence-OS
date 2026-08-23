import unittest

import primary_evidence
from gap_quality import build_resolution_matrix
from primary_evidence import _fact_from_sec_title
from primary_evidence_contracts import contract_for_requirement, coverage_for_requirement, fact_matches
from primary_evidence_semantic_guard import install_primary_evidence_semantic_guard, policy_transmission_supported


install_primary_evidence_semantic_guard(primary_evidence)

FINANCIAL_REQUIREMENT = (
    "Micron's latest filing-based revenue mix, HBM volumes and margins, inventory, free cash flow, "
    "debt and cash, capex commitments, and sensitivity to memory ASP changes."
)
POLICY_CURRENT_REQUIREMENT = (
    "Final tariff scope, effective dates, implementation guidance, and measurable evidence of "
    "supply-chain substitution or memory-market transmission."
)


class PrimaryEvidenceTests(unittest.TestCase):
    def test_round7_financial_requirement_maps_to_fact_contract(self):
        lane, contract = contract_for_requirement(FINANCIAL_REQUIREMENT)
        self.assertEqual(lane, "micron_financials")
        self.assertEqual(contract["label"], "Micron Filing Financials")
        self.assertGreaterEqual(len(contract["facts"]), 8)

    def test_current_policy_wording_maps_to_policy_contract(self):
        lane, contract = contract_for_requirement(POLICY_CURRENT_REQUIREMENT)
        self.assertEqual(lane, "policy")
        self.assertEqual(contract["label"], "Policy / Regulation")

    def test_sec_tag_mapping_is_specific(self):
        self.assertEqual(
            _fact_from_sec_title("Micron Technology InventoryNet"),
            ("micron_financials", "inventory"),
        )
        self.assertEqual(
            _fact_from_sec_title("Micron Technology WeightedAverageNumberOfDilutedSharesOutstanding"),
            ("valuation_market", "diluted_shares"),
        )

    def test_bare_hbm_does_not_prove_margin_or_packaging_yield(self):
        self.assertIsNone(primary_evidence._fact_from_keyword("micron_financials", "HBM"))
        self.assertIsNone(primary_evidence._fact_from_keyword("supply_inventory", "HBM"))
        self.assertEqual(primary_evidence._fact_from_keyword("micron_financials", "HBM volume and margin"), "hbm_margin")
        self.assertEqual(primary_evidence._fact_from_keyword("supply_inventory", "HBM packaging capacity"), "capacity")

    def test_static_micron_financial_keywords_map_to_specific_facts(self):
        cases = {
            "Revenue": "revenue",
            "Inventories": "inventory",
            "net cash provided by operating activities": "cash_flow",
            "cash and cash equivalents": "cash",
            "Long-term debt": "debt",
            "capital expenditures": "capex",
            "prices increased in the low-60s percentage range": "asp_sensitivity",
            "Margins improved primarily due to increases in average selling prices": "asp_sensitivity",
            "HBM4 volume shipment": "hbm_margin",
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(primary_evidence._fact_from_keyword("micron_financials", text), expected)

    def test_policy_transmission_requires_policy_and_supply_mechanism_at_ingestion(self):
        self.assertFalse(policy_transmission_supported("Domestic semiconductor supply capacity is expanding."))
        self.assertFalse(policy_transmission_supported("A 25 percent tariff applies to covered chips."))
        self.assertTrue(
            policy_transmission_supported(
                "A 25 percent tariff does not apply to imports used to strengthen the United States technology supply chain and domestic manufacturing capacity."
            )
        )

    def test_policy_text_alone_cannot_prove_measured_transmission(self):
        transmission_fact = {"key": "transmission", "label": "Measured supply-demand transmission", "terms": ("imports", "shipments", "production")}
        white_house = {
            "primary_fact_key": "transmission",
            "source": "White House",
            "url": "https://www.whitehouse.gov/presidential-actions/example",
            "claim": "A 25 percent tariff supports domestic manufacturing capacity and the technology supply chain.",
        }
        measured_market = {
            "primary_fact_key": "transmission",
            "source": "Independent Trade Data",
            "url": "https://trade.example/semiconductors",
            "claim": "Following implementation, covered semiconductor imports fell 18 percent and domestic production volume rose 7 percent.",
        }
        self.assertFalse(fact_matches(white_house, transmission_fact))
        self.assertTrue(fact_matches(measured_market, transmission_fact))

    def test_measured_transmission_is_mandatory_when_committee_explicitly_requests_it(self):
        items = [
            {"primary_fact_key": "incentives", "claim": "CHIPS incentive award"},
            {"primary_fact_key": "export_controls", "claim": "BIS export controls"},
            {"primary_fact_key": "tariffs", "claim": "25 percent semiconductor tariff"},
            {"primary_fact_key": "effective_dates", "claim": "effective date 2026-01-15"},
        ]
        coverage = coverage_for_requirement(POLICY_CURRENT_REQUIREMENT, items)
        self.assertIsNotNone(coverage)
        self.assertEqual(coverage["covered_facts"], 4)
        self.assertTrue(coverage["threshold_passed"])
        self.assertEqual(coverage["missing_critical_fact_keys"], ["transmission"])
        self.assertFalse(coverage["coverage_gate_passed"])

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
                "claim": "Micron HBM volume and margin detail",
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
