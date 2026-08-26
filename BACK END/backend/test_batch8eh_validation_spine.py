import unittest
from unittest.mock import patch

import paper_portfolio_freeze as freeze
import paper_portfolio_validation as validation


class Batch8EHValidationTests(
    unittest.TestCase
):

    def test_drawdown_math(self):
        result = (
            validation
            ._max_drawdown_pct(
                [
                    10000.0,
                    10200.0,
                    9600.0,
                    10500.0,
                ]
            )
        )

        self.assertAlmostEqual(
            result,
            5.8824,
            places=4,
        )

    def test_performance_summary(self):
        state = {
            "paper_portfolio_account_id":
                "paper_portfolio_default",

            "nav":
                10500.0,

            "cash":
                8000.0,

            "gross_exposure":
                2500.0,

            "position_count":
                2,

            "transaction_count":
                2,

            "total_pnl":
                500.0,

            "realized_pnl":
                100.0,

            "unrealized_pnl":
                400.0,

            "portfolio_flags":
                [],
        }

        snapshots = [
            {
                "paper_portfolio_account_id":
                    "paper_portfolio_default",
                "nav":
                    10000.0,
            },
            {
                "paper_portfolio_account_id":
                    "paper_portfolio_default",
                "nav":
                    10200.0,
            },
            {
                "paper_portfolio_account_id":
                    "paper_portfolio_default",
                "nav":
                    9600.0,
            },
        ]

        with patch.object(
            validation,
            "build_portfolio_state",
            return_value=state,
        ), patch.object(
            validation,
            "_rows_by_type",
            return_value=snapshots,
        ):
            result = (
                validation
                .portfolio_performance_summary()
            )

        self.assertAlmostEqual(
            result[
                "total_return_pct"
            ],
            5.0,
            places=4,
        )

        self.assertAlmostEqual(
            result[
                "maximum_drawdown_pct"
            ],
            5.8824,
            places=4,
        )

    def test_safety_violation_detected(self):
        def rows(
            object_type,
        ):
            if object_type == (
                "governed_paper_execution"
            ):
                return [{
                    "case_id":
                        "case_bad",

                    "trade_execution_permission":
                        True,

                    "live_execution":
                        False,
                }]

            return []

        with patch.object(
            validation,
            "_rows_by_type",
            side_effect=rows,
        ):
            result = (
                validation
                .safety_audit()
            )

        self.assertFalse(
            result[
                "all_current_safety_invariants_pass"
            ]
        )

        self.assertEqual(
            result[
                "violation_count"
            ],
            1,
        )

    def test_clean_safety_audit(self):
        with patch.object(
            validation,
            "_rows_by_type",
            return_value=[],
        ):
            result = (
                validation
                .safety_audit()
            )

        self.assertTrue(
            result[
                "all_current_safety_invariants_pass"
            ]
        )

    def test_freeze_blocks_insufficient_sample(self):
        scorecard = {
            "paper_mode":
                True,

            "auto_trade_authority":
                False,

            "trade_execution_permission":
                False,

            "live_execution":
                False,

            "performance": {
                "snapshot_count":
                    3,
            },

            "scale": {
                "case_count":
                    8,

                "paper_order_count":
                    1,
            },

            "grok_ab": {
                "completed_pair_count":
                    0,
            },

            "postmortems": {
                "completed_postmortem_count":
                    0,
            },

            "safety": {
                "all_current_safety_invariants_pass":
                    True,
            },
        }

        manifest = (
            freeze
            .build_paper_portfolio_freeze_manifest(
                scorecard=scorecard
            )
        )

        self.assertTrue(
            manifest[
                "structural_freeze_ready"
            ]
        )

        self.assertFalse(
            manifest[
                "empirical_validation_ready"
            ]
        )

        self.assertFalse(
            manifest[
                "paper_portfolio_v1_frozen"
            ]
        )

    def test_freeze_passes_full_sample(self):
        scorecard = {
            "paper_mode":
                True,

            "auto_trade_authority":
                False,

            "trade_execution_permission":
                False,

            "live_execution":
                False,

            "performance": {
                "snapshot_count":
                    25,
            },

            "scale": {
                "case_count":
                    60,

                "paper_order_count":
                    12,
            },

            "grok_ab": {
                "completed_pair_count":
                    15,
            },

            "postmortems": {
                "completed_postmortem_count":
                    6,
            },

            "safety": {
                "all_current_safety_invariants_pass":
                    True,
            },
        }

        manifest = (
            freeze
            .build_paper_portfolio_freeze_manifest(
                scorecard=scorecard
            )
        )

        self.assertTrue(
            manifest[
                "structural_freeze_ready"
            ]
        )

        self.assertTrue(
            manifest[
                "empirical_validation_ready"
            ]
        )

        self.assertTrue(
            manifest[
                "paper_portfolio_v1_frozen"
            ]
        )


if __name__ == "__main__":
    unittest.main()
