import unittest
from unittest.mock import patch

from automatic_paper_sizing import (
    calculate_automatic_paper_sizing,
)


def capital(
    decision="APPROVED",
):
    return {
        "decision": decision,
        "current_price": 800.0,
    }


def profile():
    return {
        "paper_sizing_profile_id":
            "paper_sizing_profile_case_test",
        "enabled": True,
        "inputs_complete": True,
        "portfolio_nav": 100000.0,
        "invalidation_price": 660.24,
        "invalidation_basis":
            "Explicit governed thesis risk boundary.",
    }


def portfolio():
    return {
        "portfolio_snapshot_id":
            "portfolio_snapshot_test",
        "overlap": {
            "combined_overlap_weight_pct":
                30.0,
        },
    }


class AutomaticPaperSizingTests(
    unittest.TestCase
):

    def test_wait_for_entry_never_sizes(self):
        result = (
            calculate_automatic_paper_sizing(
                case_id="case_test",
                capital_gate=capital(
                    "WAIT_FOR_ENTRY"
                ),
            )
        )

        self.assertEqual(
            result["decision"],
            "BLOCKED",
        )

        self.assertEqual(
            result["reason"],
            "CAPITAL_GATE_NOT_APPROVED",
        )

    @patch(
        "automatic_paper_sizing.latest_object"
    )
    def test_profile_is_required(
        self,
        latest,
    ):
        latest.return_value = None

        result = (
            calculate_automatic_paper_sizing(
                case_id="case_test",
                capital_gate=capital(),
            )
        )

        self.assertEqual(
            result["reason"],
            "SIZING_PROFILE_REQUIRED",
        )

    @patch(
        "automatic_paper_sizing.latest_object"
    )
    def test_portfolio_snapshot_is_required(
        self,
        latest,
    ):
        latest.side_effect = [
            profile(),
            None,
        ]

        result = (
            calculate_automatic_paper_sizing(
                case_id="case_test",
                capital_gate=capital(),
            )
        )

        self.assertEqual(
            result["reason"],
            "PORTFOLIO_SNAPSHOT_REQUIRED",
        )

    @patch(
        "automatic_paper_sizing.record_event"
    )
    @patch(
        "automatic_paper_sizing.record_object"
    )
    @patch(
        "automatic_paper_sizing.latest_object"
    )
    def test_approved_entry_can_size(
        self,
        latest,
        record_object,
        record_event,
    ):
        latest.side_effect = [
            profile(),
            portfolio(),
        ]

        result = (
            calculate_automatic_paper_sizing(
                case_id="case_test",
                capital_gate=capital(),
            )
        )

        self.assertEqual(
            result["decision"],
            "SIZE_READY",
        )

        self.assertGreater(
            result["proposed_shares"],
            0,
        )

        self.assertGreater(
            result["proposed_notional"],
            0,
        )

    @patch(
        "automatic_paper_sizing.record_event"
    )
    @patch(
        "automatic_paper_sizing.record_object"
    )
    @patch(
        "automatic_paper_sizing.latest_object"
    )
    def test_sizing_never_authorizes(
        self,
        latest,
        record_object,
        record_event,
    ):
        latest.side_effect = [
            profile(),
            portfolio(),
        ]

        result = (
            calculate_automatic_paper_sizing(
                case_id="case_test",
                capital_gate=capital(),
            )
        )

        self.assertFalse(
            result[
                "paper_authorization_ready"
            ]
        )

        self.assertFalse(
            result[
                "paper_order_permission"
            ]
        )

        self.assertFalse(
            result[
                "trade_execution_permission"
            ]
        )

        self.assertFalse(
            result["live_execution"]
        )


if __name__ == "__main__":
    unittest.main()
