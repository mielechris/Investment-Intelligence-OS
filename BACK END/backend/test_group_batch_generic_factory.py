import unittest
from unittest.mock import patch

import factory_room_api as room
import generic_primary_evidence as generic
import required_evidence_reconciler as reconciler


class GenericPrimaryFactoryTests(
    unittest.TestCase
):

    def test_generic_capture_builds_governed_evidence(self):
        case = {
            "case_id":
                "case_test",
            "topic":
                "Microsoft (MSFT) opportunity review",
        }

        sec_items = [
            {
                "source":
                    "SEC EDGAR",
                "url":
                    "https://data.sec.gov/test",
                "title":
                    "Microsoft Revenues",
                "claim":
                    "Revenues=100 USD",
                "timestamp":
                    "2026-08-01",
            },
            {
                "source":
                    "SEC EDGAR",
                "url":
                    "https://data.sec.gov/test",
                "title":
                    "Microsoft OperatingIncomeLoss",
                "claim":
                    "OperatingIncomeLoss=20 USD",
                "timestamp":
                    "2026-08-01",
            },
        ]

        quote = {
            "status":
                "ok",
            "current_price":
                500.0,
            "items": [
                {
                    "source":
                        "Yahoo Finance",
                    "url":
                        "https://finance.yahoo.com",
                    "title":
                        "MSFT market snapshot",
                    "claim":
                        "MSFT price=500",
                    "timestamp":
                        "2026-08-25",
                }
            ],
        }

        with patch.object(
            generic,
            "_require_case",
            return_value=case,
        ), patch.object(
            generic,
            "_case_ticker",
            return_value="MSFT",
        ), patch.object(
            generic,
            "_resolve_cik",
            return_value="789019",
        ), patch.object(
            generic,
            "fetch_sec_companyfacts",
            return_value=sec_items,
        ), patch.object(
            generic,
            "fetch_market_quote",
            return_value=quote,
        ), patch.object(
            generic,
            "_fetch_stockanalysis",
            return_value=(
                {
                    "year": 2026,
                    "revenue_consensus":
                        300_000_000_000,
                    "eps_consensus":
                        15.0,
                    "updated_at":
                        "2026-08-25",
                    "attribution":
                        "Test consensus",
                },
                "https://stockanalysis.com/test",
            ),
        ), patch.object(
            generic,
            "_fetch_finra",
            return_value=(
                {
                    "settlement_date":
                        "2026-08-14",
                    "current_short":
                        1000,
                    "previous_short":
                        1100,
                    "change_percent":
                        -9.09,
                    "days_to_cover":
                        1.0,
                },
                "https://api.finra.org",
                "https://finra.org",
            ),
        ), patch.object(
            generic,
            "build_portfolio_state",
            return_value={
                "nav":
                    10000.0,
                "cash":
                    10000.0,
                "gross_exposure":
                    0.0,
                "positions":
                    [],
                "current_drawdown_pct":
                    0.0,
            },
        ), patch.object(
            generic,
            "_committee_requirements",
            return_value=[],
        ), patch.object(
            generic,
            "list_objects",
            return_value=[],
        ), patch.object(
            generic,
            "record_object",
        ), patch.object(
            generic,
            "record_event",
        ):

            result = (
                generic
                .capture_generic_primary_evidence(
                    "case_test"
                )
            )

        self.assertGreaterEqual(
            result[
                "records_seen_or_added"
            ],
            6,
        )

        self.assertEqual(
            result["failure_count"],
            0,
        )

        self.assertFalse(
            result[
                "trade_execution_permission"
            ]
        )

        self.assertFalse(
            result["live_execution"]
        )

    def test_operating_requirement_becomes_governed_watch(self):
        result = (
            reconciler
            .reconcile_requirement(
                (
                    "Current production output, "
                    "customer demand, backlog and pricing"
                ),
                {},
                [
                    {
                        "source":
                            "Current company news",
                        "source_type":
                            "news_aggregator",
                        "claim":
                            (
                                "Production volumes and "
                                "customer demand improved "
                                "while backlog remained firm"
                            ),
                        "title":
                            "Operating update",
                    }
                ],
                use_legacy_semiconductor=False,
            )
        )

        self.assertEqual(
            result["overall"],
            "SATISFIED_WITH_WATCH",
        )

    def test_consensus_data_can_satisfy_generic_consensus(self):
        result = (
            reconciler
            .reconcile_requirement(
                (
                    "Current forward EPS consensus "
                    "and valuation multiple"
                ),
                {},
                [
                    {
                        "source":
                            "StockAnalysis",
                        "source_type":
                            "consensus_data",
                        "evidence_type":
                            "analyst_consensus",
                        "claim":
                            "forward EPS consensus=15.0",
                        "title":
                            "governed consensus",
                    }
                ],
                use_legacy_semiconductor=False,
            )
        )

        self.assertEqual(
            result["overall"],
            "SATISFIED",
        )

    def test_factory_room_never_grants_live_authority(self):
        with patch.object(
            room,
            "opportunity_queue",
            return_value=[],
        ), patch.object(
            room,
            "_candidate_case_ids",
            return_value=[],
        ), patch.object(
            room,
            "build_validation_scorecard",
            return_value={
                "performance": {
                    "current_nav":
                        10000.0,
                    "cash":
                        10000.0,
                    "position_count":
                        0,
                    "total_return_pct":
                        0.0,
                    "maximum_drawdown_pct":
                        0.0,
                    "snapshot_count":
                        22,
                },
                "scale": {
                    "case_count":
                        13,
                    "paper_order_count":
                        0,
                },
                "postmortems": {
                    "completed_postmortem_count":
                        0,
                },
                "grok_ab": {
                    "completed_pair_count":
                        0,
                },
                "safety": {
                    "violation_count":
                        0,
                    "all_current_safety_invariants_pass":
                        True,
                },
                "paper_mode":
                    True,
                "auto_trade_authority":
                    False,
                "trade_execution_permission":
                    False,
                "live_execution":
                    False,
            },
        ), patch.object(
            room,
            "build_paper_portfolio_freeze_manifest",
            return_value={
                "structural_freeze_ready":
                    True,
                "empirical_validation_ready":
                    False,
                "freeze_blockers":
                    ["scale_case_sample"],
            },
        ):
            result = (
                room.factory_room_status()
            )

        self.assertTrue(
            result[
                "safety"
            ]["all_invariants"]
        )

        self.assertFalse(
            result[
                "safety"
            ]["live_execution"]
        )

        self.assertFalse(
            result["live_execution"]
        )


if __name__ == "__main__":
    unittest.main()
