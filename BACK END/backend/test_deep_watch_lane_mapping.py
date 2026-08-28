import unittest
from types import SimpleNamespace

import deep_watch_lane_mapping as mapping


class DeepWatchLaneMappingTests(unittest.TestCase):
    def _module(self):
        def base_classify(requirement):
            text = str(requirement).lower()
            if "portfolio holdings" in text:
                return {
                    "kind": "PORTFOLIO_CONTEXT",
                    "lane": "portfolio_context",
                    "lane_label": "Portfolio Context",
                }
            return {
                "kind": "CONTEXT_EVIDENCE",
                "lane": None,
                "lane_label": "Context Evidence",
            }

        return SimpleNamespace(
            classify_requirement=base_classify,
            obligation_snapshot=lambda primary, case_id, requirement: {
                "kind": "CONTEXT_EVIDENCE",
                "status": "NO_MATERIAL_CONTEXT_MATCH",
            },
        )

    def test_micron_financial_obligation_maps_to_structured_financial_and_hbm_lanes(self):
        module = self._module()
        mapping.install_deep_watch_lane_mapping(module)
        row = module.classify_requirement(
            "Latest Micron 10-Q, earnings release, and guidance covering HBM/DRAM mix, ASPs, margins, inventory, cash flow, capex, debt, capacity, yields, dilution, and customer concentration."
        )
        self.assertEqual(row["kind"], "PRIMARY_EVIDENCE")
        self.assertIn("micron_financials", row["lanes"])
        self.assertIn("micron_hbm_economics", row["lanes"])
        self.assertIn("supply_inventory", row["lanes"])
        self.assertTrue(row["multi_lane"])

    def test_hyperscaler_obligation_maps_to_hyperscaler_demand(self):
        module = self._module()
        mapping.install_deep_watch_lane_mapping(module)
        row = module.classify_requirement(
            "Independent server-demand, hyperscaler-capex, backlog-conversion, customer-inventory, and channel-inventory evidence distinguishing end consumption from restocking."
        )
        self.assertEqual(row["kind"], "PRIMARY_EVIDENCE")
        self.assertIn("hyperscaler_demand", row["lanes"])

    def test_pricing_and_competitor_obligation_maps_to_memory_and_supply(self):
        module = self._module()
        mapping.install_deep_watch_lane_mapping(module)
        row = module.classify_requirement(
            "Current HBM and DRAM pricing, supply-demand balances, competitor capacity plans, customer qualification status, and evidence of negotiated pricing power."
        )
        self.assertEqual(row["kind"], "PRIMARY_EVIDENCE")
        self.assertIn("memory_pricing", row["lanes"])
        self.assertIn("supply_inventory", row["lanes"])

    def test_cycle_and_consensus_obligation_maps_to_valuation_and_financials(self):
        module = self._module()
        mapping.install_deep_watch_lane_mapping(module)
        row = module.classify_requirement(
            "Forward consensus and normalized-cycle earnings with bear-case HBM pricing, margin, capex, and valuation sensitivities."
        )
        self.assertEqual(row["kind"], "PRIMARY_EVIDENCE")
        self.assertIn("valuation_market", row["lanes"])
        self.assertIn("micron_financials", row["lanes"])

    def test_market_positioning_obligation_maps_to_valuation_market(self):
        module = self._module()
        mapping.install_deep_watch_lane_mapping(module)
        row = module.classify_requirement(
            "Fresh MU OHLCV, volatility, options, short-interest, liquidity, flows, catalyst-calendar, and support/resistance data."
        )
        self.assertEqual(row["kind"], "PRIMARY_EVIDENCE")
        self.assertIn("valuation_market", row["lanes"])

    def test_portfolio_obligation_stays_portfolio_context(self):
        module = self._module()
        mapping.install_deep_watch_lane_mapping(module)
        row = module.classify_requirement(
            "Portfolio holdings and factor-exposure data, plus verified geographic, water, power, packaging, logistics, and export-control dependencies."
        )
        self.assertEqual(row["kind"], "PORTFOLIO_CONTEXT")
        self.assertEqual(row["lane"], "portfolio_context")

    def test_multilane_snapshot_aggregates_governed_lane_state(self):
        module = self._module()
        mapping.install_deep_watch_lane_mapping(module)

        class Primary:
            @staticmethod
            def list_objects(case_id, object_type):
                return []

            @staticmethod
            def _lane_status(case_id, lane, records):
                if lane == "memory_pricing":
                    return {
                        "status": "PARTIAL",
                        "coverage_pct": 50,
                        "facts": [
                            {"key": "hbm_pricing", "covered": True},
                            {"key": "dram_pricing", "covered": False},
                        ],
                        "current_high_quality_records": 1,
                        "source_count": 1,
                        "latest_records": [],
                    }
                return {
                    "status": "OPEN",
                    "coverage_pct": 0,
                    "facts": [
                        {"key": "capacity", "covered": False},
                        {"key": "inventory", "covered": False},
                    ],
                    "current_high_quality_records": 0,
                    "source_count": 0,
                    "latest_records": [],
                }

        snap = module.obligation_snapshot(
            Primary(),
            "case_x",
            "Current HBM and DRAM pricing, supply-demand balances, competitor capacity plans, customer qualification status, and evidence of negotiated pricing power.",
        )
        self.assertEqual(snap["kind"], "PRIMARY_EVIDENCE")
        self.assertEqual(snap["lane"], "MULTI_LANE")
        self.assertEqual(set(snap["lanes"]), {"memory_pricing", "supply_inventory"})
        self.assertEqual(snap["status"], "PARTIAL")
        self.assertIn("memory_pricing:hbm_pricing", snap["covered_fact_keys"])
        self.assertIn("supply_inventory:capacity", snap["missing_fact_keys"])


if __name__ == "__main__":
    unittest.main()
