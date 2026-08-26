import unittest
from unittest.mock import patch

import generic_coverage_v2 as coverage
import generic_primary_evidence as generic
import required_evidence_reconciler as reconciler


class GroupBatch6Tests(
    unittest.TestCase
):

    def test_production_volume_not_stock_volume(self):
        targets = (
            coverage
            .generic_company_targets_v2(
                (
                    "Independent server shipment, "
                    "production volumes, backlog, "
                    "deployment and utilization"
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
                "generic_operating_context",
                "operating_kpis",
            ),
            keys,
        )

        self.assertIn(
            (
                "generic_external_context",
                "independent_corroboration",
            ),
            keys,
        )

        self.assertNotIn(
            (
                "generic_market_context",
                "current_market",
            ),
            keys,
        )

        self.assertNotIn(
            (
                "generic_policy_context",
                "official_policy",
            ),
            keys,
        )

    def test_avgo_china_requirement_routes_correctly(self):
        targets = (
            coverage
            .generic_company_targets_v2(
                (
                    "Primary-source disclosures "
                    "on China revenue, export controls, "
                    "tariffs, incentives and effective dates"
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
                "generic_company_financials",
                "filing_financials",
            ),
            keys,
        )

        self.assertIn(
            (
                "generic_policy_context",
                "official_policy",
            ),
            keys,
        )

    def test_portfolio_requirement_is_governed(self):
        targets = (
            coverage
            .generic_company_targets_v2(
                (
                    "Current portfolio holdings, "
                    "weights, risk limits, correlations "
                    "and factor overlap"
                )
            )
        )

        self.assertIn(
            {
                "lane":
                    "generic_portfolio_context",
                "fact_key":
                    "portfolio_state",
            },
            targets,
        )

    def test_two_independent_primary_sources_satisfy(self):
        state = coverage.generic_state_v2(
            [
                {
                    "source":
                        "Dell Investor Relations",
                    "url":
                        "https://investors.dell.com/a",
                    "source_type":
                        "company",
                    "observed_at":
                        "2026-08-25T20:00:00+00:00",
                    "stale":
                        False,
                    "missing_fields":
                        [],
                    "raw": {
                        "source":
                            "Dell Investor Relations",
                        "url":
                            "https://investors.dell.com/a",
                        "source_type":
                            "company",
                        "primary_evidence_lane":
                            "generic_external_context",
                        "primary_fact_key":
                            "independent_corroboration",
                    },
                },
                {
                    "source":
                        "HPE Investor Relations",
                    "url":
                        "https://investors.hpe.com/b",
                    "source_type":
                        "company",
                    "observed_at":
                        "2026-08-25T20:00:00+00:00",
                    "stale":
                        False,
                    "missing_fields":
                        [],
                    "raw": {
                        "source":
                            "HPE Investor Relations",
                        "url":
                            "https://investors.hpe.com/b",
                        "source_type":
                            "company",
                        "primary_evidence_lane":
                            "generic_external_context",
                        "primary_fact_key":
                            "independent_corroboration",
                    },
                },
            ],
            "generic_external_context",
            "independent_corroboration",
        )

        self.assertEqual(
            state["state"],
            "SATISFIED",
        )

        self.assertEqual(
            state[
                "independent_sources"
            ],
            2,
        )

    def test_single_independent_source_is_watch_only(self):
        state = coverage.generic_state_v2(
            [
                {
                    "source":
                        "Dell Investor Relations",
                    "url":
                        "https://investors.dell.com/a",
                    "source_type":
                        "company",
                    "stale":
                        False,
                    "missing_fields":
                        [],
                    "raw": {
                        "source":
                            "Dell Investor Relations",
                        "url":
                            "https://investors.dell.com/a",
                        "source_type":
                            "company",
                        "primary_evidence_lane":
                            "generic_external_context",
                        "primary_fact_key":
                            "independent_corroboration",
                    },
                },
            ],
            "generic_external_context",
            "independent_corroboration",
        )

        self.assertEqual(
            state["state"],
            "WATCHING",
        )

        self.assertFalse(
            state["covered"]
        )

    def test_v2_never_grants_execution_authority(self):
        base = {
            "case_id":
                "case_test",
            "ticker":
                "JPM",
            "records_seen_or_added":
                4,
            "failures":
                [],
            "failure_count":
                0,
            "paper_mode":
                True,
            "trade_execution_permission":
                False,
            "live_execution":
                False,
        }

        with patch.object(
            coverage,
            "_ORIGINAL_CAPTURE",
            return_value=base,
        ), patch.object(
            generic,
            "_require_case",
            return_value={
                "case_id":
                    "case_test",
                "topic":
                    "JPM opportunity",
            },
        ), patch.object(
            generic,
            "_case_ticker",
            return_value="JPM",
        ), patch.object(
            coverage,
            "_capture_sector_operating",
            return_value=([], []),
        ), patch.object(
            coverage,
            "_capture_external_context",
            return_value=([], []),
        ), patch.object(
            coverage,
            "_capture_portfolio_v2",
            return_value=([], []),
        ):
            result = (
                coverage
                .capture_generic_primary_evidence_v2(
                    "case_test"
                )
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
