import unittest
from datetime import (
    datetime,
    timedelta,
    timezone,
)
from unittest.mock import patch

import paper_validation_orchestrator as runner
import paper_portfolio_validation as validation


class Batch8EHScaleRunnerTests(
    unittest.TestCase
):

    def test_recent_snapshot_is_not_duplicated(self):
        recent = {
            "created_at":
                datetime.now(
                    timezone.utc
                ).isoformat()
        }

        with patch.object(
            runner,
            "latest_object",
            return_value=recent,
        ), patch.object(
            runner,
            "record_live_portfolio_snapshot",
        ) as snapshot_mock:

            result = (
                runner
                .record_forward_snapshot_if_due()
            )

        self.assertEqual(
            result["status"],
            "NOT_DUE",
        )

        snapshot_mock.assert_not_called()

    def test_due_snapshot_is_recorded(self):
        old = {
            "created_at":
                (
                    datetime.now(
                        timezone.utc
                    )
                    - timedelta(
                        hours=2
                    )
                ).isoformat()
        }

        with patch.object(
            runner,
            "latest_object",
            return_value=old,
        ), patch.object(
            runner,
            "record_live_portfolio_snapshot",
            return_value={
                "paper_portfolio_snapshot_id":
                    "snapshot_test",
                "nav":
                    10000.0,
                "position_count":
                    0,
            },
        ):

            result = (
                runner
                .record_forward_snapshot_if_due()
            )

        self.assertEqual(
            result["status"],
            "RECORDED",
        )

        self.assertTrue(
            result[
                "snapshot_recorded"
            ]
        )

    def test_only_eligible_unpromoted_candidates_dispatch(self):
        scan = {
            "queue": [
                {
                    "opportunity_candidate_id":
                        "c1",
                    "ticker":
                        "AAA",
                    "eligible_for_promotion":
                        True,
                },
                {
                    "opportunity_candidate_id":
                        "c2",
                    "ticker":
                        "BBB",
                    "eligible_for_promotion":
                        False,
                },
                {
                    "opportunity_candidate_id":
                        "c3",
                    "ticker":
                        "CCC",
                    "eligible_for_promotion":
                        True,
                    "promoted_case_id":
                        "case_existing",
                },
            ]
        }

        with patch.object(
            runner,
            "_http_json",
            return_value={
                "case": {
                    "case_id":
                        "case_new"
                },
                "committee": {
                    "disposition":
                        "WATCH"
                },
                "paper_order_permission":
                    False,
                "trade_execution_permission":
                    False,
                "live_execution":
                    False,
            },
        ) as http_mock:

            result = (
                runner
                .dispatch_real_candidates(
                    scan=scan,
                    max_dispatch=5,
                )
            )

        self.assertEqual(
            result[
                "completed_dispatches"
            ],
            1,
        )

        self.assertEqual(
            result[
                "safety_violation_count"
            ],
            0,
        )

        http_mock.assert_called_once()

    def test_incomplete_grok_pair_is_blocked(self):
        result = (
            runner
            .record_grok_ab_pair(
                case_id="case_test",
                baseline_result={},
                grok_result={
                    "disposition":
                        "WATCH"
                },
                measurement_label=
                    "test",
            )
        )

        self.assertEqual(
            result["status"],
            "BLOCKED",
        )

    def test_complete_grok_pair_is_measurement_only(self):
        with patch.object(
            runner,
            "record_object",
        ), patch.object(
            runner,
            "record_event",
        ):

            result = (
                runner
                .record_grok_ab_pair(
                    case_id="case_test",

                    baseline_result={
                        "committee": {
                            "disposition":
                                "WATCH",
                            "confidence":
                                0.80,
                        }
                    },

                    grok_result={
                        "committee": {
                            "disposition":
                                "WATCH",
                            "confidence":
                                0.84,
                        }
                    },

                    measurement_label=
                        "IIOS vs IIOS+Grok",
                )
            )

        self.assertEqual(
            result["status"],
            "COMPLETE",
        )

        self.assertFalse(
            result[
                "automatic_factory_promotion"
            ]
        )

        self.assertFalse(
            result[
                "capital_authority"
            ]
        )

        self.assertFalse(
            result[
                "live_execution"
            ]
        )

    def test_validation_counts_normalized_grok_pairs(self):
        def rows(
            object_type,
        ):
            if object_type == (
                "paper_grok_ab_pair"
            ):
                return [
                    {
                        "status":
                            "COMPLETE",
                        "measurement_complete":
                            True,
                    },
                    {
                        "status":
                            "COMPLETE",
                        "measurement_complete":
                            True,
                    },
                ]

            if object_type == (
                "grok_experiment_scorecard"
            ):
                return []

            return []

        with patch.object(
            validation,
            "_rows_by_type",
            side_effect=rows,
        ):
            result = (
                validation
                .grok_ab_summary()
            )

        self.assertEqual(
            result[
                "completed_pair_count"
            ],
            2,
        )

        self.assertFalse(
            result[
                "promotion_ready"
            ]
        )


if __name__ == "__main__":
    unittest.main()
