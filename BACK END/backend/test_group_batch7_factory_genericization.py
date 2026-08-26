import unittest
from unittest.mock import patch

import factory_genericization as genericize
import generic_coverage_v2 as coverage
import generic_public_company_capital as capital


class GroupBatch7Tests(
    unittest.TestCase
):

    def test_profile_resolves_ticker_from_topic(self):
        with patch.object(
            genericize,
            "get_object",
            return_value={
                "case_id":
                    "case_test",
                "topic":
                    "NVIDIA (NVDA) opportunity review",
            },
        ), patch.object(
            genericize,
            "latest_object",
            return_value=None,
        ):
            result = (
                genericize
                .resolve_case_profile(
                    "case_test"
                )
            )

        self.assertEqual(
            result["ticker"],
            "NVDA",
        )

        self.assertFalse(
            result["is_micron"]
        )

    def test_micron_profile_is_specialized(self):
        with patch.object(
            genericize,
            "get_object",
            return_value={
                "case_id":
                    "case_test",
                "topic":
                    "Micron Technology (MU) review",
            },
        ), patch.object(
            genericize,
            "latest_object",
            return_value=None,
        ):
            result = (
                genericize
                .resolve_case_profile(
                    "case_test"
                )
            )

        self.assertTrue(
            result["is_micron"]
        )

    def test_portfolio_truth_has_no_authority(self):
        with patch.object(
            genericize,
            "resolve_case_profile",
            return_value={
                "ticker":
                    "NVDA",
            },
        ), patch.object(
            genericize,
            "build_portfolio_state",
            return_value={
                "nav":
                    10000.0,
                "cash":
                    10000.0,
                "position_count":
                    0,
                "positions":
                    [],
                "accounting_scope":
                    "GOVERNED_PAPER_EXECUTIONS_ONLY",
            },
        ):
            result = (
                genericize
                .paper_portfolio_truth(
                    "case_test"
                )
            )

        self.assertEqual(
            result["nav"],
            10000.0,
        )

        self.assertEqual(
            result[
                "exact_candidate_overlap_pct"
            ],
            0.0,
        )

        self.assertFalse(
            result[
                "trade_execution_permission"
            ]
        )

        self.assertFalse(
            result["live_execution"]
        )

    def test_generic_consensus_accepts_valuation_fact(self):
        record = {
            "claim":
                (
                    "NVDA forward EPS "
                    "consensus=5.25; "
                    "consensus revenue=200."
                )
        }

        def latest(
            case_id,
            fact_key,
        ):
            if (
                fact_key
                == "valuation_consensus"
            ):
                return record

            return None

        with patch.object(
            capital,
            "_latest_primary",
            side_effect=latest,
        ):
            eps, used = (
                capital._forward_eps(
                    "case_test"
                )
            )

        self.assertEqual(
            eps,
            5.25,
        )

        self.assertIs(
            used,
            record,
        )

    def test_valuation_sentence_does_not_force_filing_lane(self):
        targets = (
            coverage
            .generic_company_targets_v2(
                (
                    "Current price, market cap, "
                    "enterprise value, forward P/E, "
                    "EV/revenue and analyst consensus"
                )
            )
        )

        keys = {
            (
                row["lane"],
                row["fact_key"],
            )
            for row in targets
        }

        self.assertIn(
            (
                "generic_market_context",
                "valuation_consensus",
            ),
            keys,
        )

        self.assertNotIn(
            (
                "generic_company_financials",
                "filing_financials",
            ),
            keys,
        )


if __name__ == "__main__":
    unittest.main()
