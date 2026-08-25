import unittest

from thesis_invalidation_contract import (
    assess_mu_thesis,
    build_mu_invalidation_contract,
)


class ThesisInvalidationContractTests(
    unittest.TestCase
):

    def test_contract_contains_four_hard_rules(self):
        contract = (
            build_mu_invalidation_contract()
        )

        self.assertEqual(
            len(contract["rules"]),
            4,
        )

        self.assertTrue(
            all(
                row["severity"] == "HARD"
                for row in contract["rules"]
            )
        )

    def test_no_trigger_keeps_thesis_active(self):
        result = assess_mu_thesis()

        self.assertEqual(
            result["status"],
            "ACTIVE",
        )

        self.assertFalse(
            result["thesis_invalidated"]
        )

    def test_memory_pricing_break_invalidates(self):
        result = assess_mu_thesis(
            memory_pricing_break=True,
        )

        self.assertEqual(
            result["status"],
            "INVALIDATED",
        )

        self.assertIn(
            "MEMORY_PRICING_BREAK",
            result["triggered_rules"],
        )

    def test_supply_reversal_requires_all_three_conditions(self):
        partial = assess_mu_thesis(
            supplier_inventory_rising=True,
            bit_supply_outgrowing_demand=True,
        )

        self.assertFalse(
            partial["thesis_invalidated"]
        )

        full = assess_mu_thesis(
            supplier_inventory_rising=True,
            bit_supply_outgrowing_demand=True,
            verified_end_demand_weakening=True,
        )

        self.assertIn(
            "SUPPLY_DEMAND_REVERSAL",
            full["triggered_rules"],
        )

    def test_hyperscaler_break_requires_cancellation_and_activity(self):
        partial = assess_mu_thesis(
            hyperscaler_cancellations_material=True,
        )

        self.assertFalse(
            partial["thesis_invalidated"]
        )

        full = assess_mu_thesis(
            hyperscaler_cancellations_material=True,
            server_activity_weakening=True,
        )

        self.assertIn(
            "HYPERSCALER_DEMAND_BREAK",
            full["triggered_rules"],
        )

    def test_earnings_quality_requires_two_signals(self):
        one = assess_mu_thesis(
            eps_revisions_deteriorating=True,
        )

        self.assertFalse(
            one["thesis_invalidated"]
        )

        two = assess_mu_thesis(
            eps_revisions_deteriorating=True,
            normalized_cycle_break=True,
        )

        self.assertIn(
            "EARNINGS_QUALITY_BREAK",
            two["triggered_rules"],
        )

    def test_invalidation_never_executes(self):
        result = assess_mu_thesis(
            memory_pricing_break=True,
        )

        self.assertFalse(
            result["governance"][
                "automatic_sell_order"
            ]
        )

        self.assertFalse(
            result["governance"][
                "trade_execution_permission"
            ]
        )


if __name__ == "__main__":
    unittest.main()
