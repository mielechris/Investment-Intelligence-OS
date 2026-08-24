import unittest

from paper_sizing_profile import (
    validate_sizing_profile,
)


class PaperSizingProfileTests(
    unittest.TestCase
):

    def test_valid_explicit_inputs_pass(self):
        result = validate_sizing_profile(
            portfolio_nav=100000,
            invalidation_price=660.24,
            invalidation_basis=(
                "Governed thesis-risk level "
                "approved for paper sizing."
            ),
        )

        self.assertEqual(
            result["portfolio_nav"],
            100000.0,
        )

        self.assertEqual(
            result[
                "invalidation_price"
            ],
            660.24,
        )

        self.assertTrue(
            result["inputs_complete"]
        )

    def test_nav_must_be_positive(self):
        with self.assertRaises(
            ValueError
        ):
            validate_sizing_profile(
                portfolio_nav=0,
                invalidation_price=660.24,
                invalidation_basis=(
                    "Governed paper-risk level."
                ),
            )

    def test_invalidation_must_be_positive(self):
        with self.assertRaises(
            ValueError
        ):
            validate_sizing_profile(
                portfolio_nav=100000,
                invalidation_price=0,
                invalidation_basis=(
                    "Governed paper-risk level."
                ),
            )

    def test_basis_must_be_explained(self):
        with self.assertRaises(
            ValueError
        ):
            validate_sizing_profile(
                portfolio_nav=100000,
                invalidation_price=660.24,
                invalidation_basis="stop",
            )

    def test_profile_never_infers_invalidation(self):
        result = validate_sizing_profile(
            portfolio_nav=100000,
            invalidation_price=660.24,
            invalidation_basis=(
                "Explicit governed thesis "
                "risk boundary."
            ),
        )

        governance = result[
            "governance"
        ]

        self.assertTrue(
            governance[
                "invalidation_price_explicit"
            ]
        )

        self.assertFalse(
            governance[
                "invalidation_price_inferred"
            ]
        )

    def test_profile_has_no_execution_authority(self):
        result = validate_sizing_profile(
            portfolio_nav=100000,
            invalidation_price=660.24,
            invalidation_basis=(
                "Explicit governed thesis "
                "risk boundary."
            ),
        )

        governance = result[
            "governance"
        ]

        self.assertFalse(
            governance[
                "sizing_authority"
            ]
        )

        self.assertFalse(
            governance[
                "paper_order_permission"
            ]
        )

        self.assertFalse(
            governance[
                "trade_execution_permission"
            ]
        )

        self.assertFalse(
            governance[
                "live_execution"
            ]
        )


if __name__ == "__main__":
    unittest.main()
