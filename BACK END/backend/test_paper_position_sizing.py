import unittest

from paper_position_sizing import (
    size_paper_position,
)


def capital(
    decision="APPROVED",
    price=800.0,
):
    return {
        "decision": decision,
        "current_price": price,
    }


def portfolio(overlap=30.0):
    return {
        "portfolio_snapshot_id":
            "portfolio_snapshot_test",
        "overlap": {
            "combined_overlap_weight_pct":
                overlap,
        },
    }


class PaperPositionSizingTests(unittest.TestCase):

    def test_approved_moderate_overlap_sizes_by_risk(self):
        result = size_paper_position(
            capital_gate=capital(),
            portfolio_snapshot=portfolio(30.0),
            portfolio_nav=100000,
            invalidation_price=660.24,
            invalidation_basis=(
                "Severe governed downside scenario"
            ),
        )

        self.assertEqual(
            result["decision"],
            "SIZE_READY",
        )

        self.assertEqual(
            result["proposed_shares"],
            3,
        )

        self.assertEqual(
            result["proposed_notional"],
            2400.0,
        )

        self.assertAlmostEqual(
            result[
                "proposed_loss_at_invalidation"
            ],
            419.28,
            places=2,
        )

        self.assertFalse(
            result["paper_order_permission"]
        )

    def test_wait_for_entry_cannot_be_sized(self):
        result = size_paper_position(
            capital_gate=capital(
                decision="WAIT_FOR_ENTRY"
            ),
            portfolio_snapshot=portfolio(),
            portfolio_nav=100000,
            invalidation_price=660.24,
            invalidation_basis="Stress scenario",
        )

        self.assertEqual(
            result["decision"],
            "BLOCKED",
        )

        self.assertEqual(
            result["reason"],
            "CAPITAL_GATE_NOT_APPROVED",
        )

    def test_high_overlap_blocks_position(self):
        result = size_paper_position(
            capital_gate=capital(),
            portfolio_snapshot=portfolio(60.0),
            portfolio_nav=100000,
            invalidation_price=660.24,
            invalidation_basis="Stress scenario",
        )

        self.assertEqual(
            result["decision"],
            "BLOCKED",
        )

        self.assertEqual(
            result["reason"],
            "PORTFOLIO_OVERLAP_TOO_HIGH",
        )

    def test_missing_portfolio_snapshot_blocks(self):
        result = size_paper_position(
            capital_gate=capital(),
            portfolio_snapshot=None,
            portfolio_nav=100000,
            invalidation_price=660.24,
            invalidation_basis="Stress scenario",
        )

        self.assertEqual(
            result["reason"],
            "PORTFOLIO_SNAPSHOT_REQUIRED",
        )

    def test_invalidation_must_be_below_entry(self):
        with self.assertRaises(ValueError):
            size_paper_position(
                capital_gate=capital(),
                portfolio_snapshot=portfolio(),
                portfolio_nav=100000,
                invalidation_price=810.0,
                invalidation_basis="Invalid level",
            )

    def test_moderate_overlap_cap_can_bind(self):
        result = size_paper_position(
            capital_gate=capital(),
            portfolio_snapshot=portfolio(30.0),
            portfolio_nav=100000,
            invalidation_price=790.0,
            invalidation_basis=(
                "Tight thesis invalidation"
            ),
        )

        self.assertEqual(
            result["proposed_shares"],
            3,
        )

        self.assertEqual(
            result["binding_constraint"],
            "PORTFOLIO_CONCENTRATION_CAP",
        )

    def test_sizing_never_grants_execution(self):
        result = size_paper_position(
            capital_gate=capital(),
            portfolio_snapshot=portfolio(),
            portfolio_nav=100000,
            invalidation_price=660.24,
            invalidation_basis="Stress scenario",
        )

        self.assertEqual(
            result["allowed_notional"],
            0.0,
        )

        self.assertFalse(
            result["paper_order_permission"]
        )

        self.assertFalse(
            result["trade_execution_permission"]
        )


if __name__ == "__main__":
    unittest.main()
