import unittest
from unittest.mock import patch

import governed_paper_exit as exit_mod
import paper_portfolio_core as portfolio
import paper_trade_postmortem as pm


class Batch8EHExitTests(
    unittest.TestCase
):

    def test_round_trip_realized_pnl(self):
        tx = [
            {
                "ticker": "AMZN",
                "side": "BUY",
                "quantity": 2,
                "notional": 428.0,
            },
            {
                "ticker": "AMZN",
                "side": "SELL",
                "quantity": 2,
                "notional": 440.0,
            },
        ]

        with patch.object(
            portfolio,
            "ensure_account",
            return_value={
                "starting_cash":
                    10000.0,
            },
        ), patch.object(
            portfolio,
            "reconcile_governed_executions",
            return_value={},
        ), patch.object(
            portfolio,
            "_transactions",
            return_value=tx,
        ):
            state = (
                portfolio
                .build_portfolio_state()
            )

        self.assertEqual(
            state["position_count"],
            0,
        )

        self.assertAlmostEqual(
            state["cash"],
            10012.0,
            places=2,
        )

        self.assertAlmostEqual(
            state["realized_pnl"],
            12.0,
            places=2,
        )

        self.assertAlmostEqual(
            state["nav"],
            10012.0,
            places=2,
        )

    def test_partial_sell_reduces_cost_basis(self):
        tx = [
            {
                "ticker": "AMZN",
                "side": "BUY",
                "quantity": 2,
                "notional": 428.0,
            },
            {
                "ticker": "AMZN",
                "side": "SELL",
                "quantity": 1,
                "notional": 220.0,
            },
        ]

        with patch.object(
            portfolio,
            "ensure_account",
            return_value={
                "starting_cash":
                    10000.0,
            },
        ), patch.object(
            portfolio,
            "reconcile_governed_executions",
            return_value={},
        ), patch.object(
            portfolio,
            "_transactions",
            return_value=tx,
        ):
            state = (
                portfolio
                .build_portfolio_state()
            )

        self.assertEqual(
            state["position_count"],
            1,
        )

        position = (
            state["positions"][0]
        )

        self.assertEqual(
            position["quantity"],
            1,
        )

        self.assertAlmostEqual(
            position["cost_basis"],
            214.0,
            places=2,
        )

        self.assertAlmostEqual(
            state["realized_pnl"],
            6.0,
            places=2,
        )

    def test_exit_requires_human_approval(self):
        result = (
            exit_mod
            .create_governed_paper_exit(
                case_id="case_test",
                exit_price=220.0,
                reason="test",
                human_approved=False,
            )
        )

        self.assertEqual(
            result["status"],
            "BLOCKED",
        )

        self.assertEqual(
            result["reason"],
            "HUMAN_EXIT_APPROVAL_REQUIRED",
        )

    def test_full_exit_triggers_postmortem(self):
        state = {
            "positions": [
                {
                    "ticker":
                        "AMZN",

                    "quantity":
                        2,

                    "average_cost":
                        214.0,
                }
            ]
        }

        with patch.object(
            exit_mod,
            "_ticker_for_case",
            return_value="AMZN",
        ), patch.object(
            exit_mod,
            "build_portfolio_state",
            return_value=state,
        ), patch.object(
            exit_mod,
            "record_object",
        ), patch.object(
            exit_mod,
            "record_event",
        ), patch.object(
            exit_mod,
            "build_trade_postmortem",
            return_value={
                "status":
                    "COMPLETE"
            },
        ) as postmortem_mock:

            result = (
                exit_mod
                .create_governed_paper_exit(
                    case_id="case_test",
                    exit_price=220.0,
                    reason=
                        "Human-approved validation exit",
                    human_approved=True,
                )
            )

        self.assertEqual(
            result["status"],
            "COMPLETE",
        )

        self.assertEqual(
            result["remaining_quantity"],
            0,
        )

        postmortem_mock.assert_called_once()

        self.assertFalse(
            result["live_execution"]
        )

    def test_closed_trade_postmortem(self):
        rows = [
            {
                "source_case_id":
                    "case_test",
                "ticker":
                    "AMZN",
                "side":
                    "BUY",
                "quantity":
                    2,
                "notional":
                    428.0,
            },
            {
                "source_case_id":
                    "case_test",
                "ticker":
                    "AMZN",
                "side":
                    "SELL",
                "quantity":
                    2,
                "notional":
                    440.0,
            },
        ]

        with patch.object(
            pm,
            "_ticker_for_case",
            return_value="AMZN",
        ), patch.object(
            pm,
            "_transactions",
            return_value=rows,
        ), patch.object(
            pm,
            "get_object",
            return_value=None,
        ), patch.object(
            pm,
            "latest_object",
            return_value={},
        ), patch.object(
            pm,
            "record_object",
        ), patch.object(
            pm,
            "record_event",
        ):

            result = (
                pm
                .build_trade_postmortem(
                    "case_test"
                )
            )

        self.assertEqual(
            result["status"],
            "COMPLETE",
        )

        self.assertEqual(
            result["outcome"],
            "WIN",
        )

        self.assertAlmostEqual(
            result["realized_pnl"],
            12.0,
            places=2,
        )

        self.assertFalse(
            result[
                "automatic_policy_rewrite"
            ]
        )


if __name__ == "__main__":
    unittest.main()
