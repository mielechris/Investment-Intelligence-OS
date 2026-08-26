import unittest
from unittest.mock import patch

import generic_position_sizing as gps
import capital_entry_watch as watch


EMPTY_PORTFOLIO = {
    "nav": 10000.0,
    "cash": 10000.0,
    "positions": [],
    "position_count": 0,
}


class Batch8CGenericSizingTests(unittest.TestCase):

    def test_capital_must_be_approved(self):
        result = gps.calculate_generic_position_sizing(
            case_id="case_test",
            capital_gate={
                "decision": "WAIT_FOR_ENTRY",
                "current_price": 214.0,
            },
        )

        self.assertEqual(
            result["decision"],
            "BLOCKED",
        )
        self.assertEqual(
            result["reason"],
            "CAPITAL_GATE_NOT_APPROVED",
        )

    def test_default_downside_reference_can_block_all_whole_shares(self):
        profile = {
            "generic_sizing_profile_id":
                "profile_test",
            "enabled": True,
            "invalidation_mode":
                gps.CAPITAL_DOWNSIDE_REFERENCE,
        }

        with patch.object(
            gps,
            "_ticker_for_case",
            return_value="AMZN",
        ), patch.object(
            gps,
            "_ensure_profile",
            return_value=profile,
        ), patch.object(
            gps,
            "build_portfolio_state",
            return_value=EMPTY_PORTFOLIO,
        ), patch.object(
            gps,
            "record_object",
        ), patch.object(
            gps,
            "record_event",
        ):

            result = (
                gps.calculate_generic_position_sizing(
                    case_id="case_test",
                    capital_gate={
                        "decision": "APPROVED",
                        "current_price": 214.0,
                        "downside_reference_value":
                            156.6362,
                    },
                )
            )

        self.assertEqual(
            result["decision"],
            "BLOCKED",
        )

        self.assertEqual(
            result["reason"],
            "NO_POSITION_WITHIN_RISK_LIMIT",
        )

        self.assertEqual(
            result["proposed_shares"],
            0,
        )

        self.assertFalse(
            result["paper_order_permission"]
        )
        self.assertFalse(
            result["live_execution"]
        )

    def test_manual_approved_invalidation_sizes_two_amzn_shares(self):
        profile = {
            "generic_sizing_profile_id":
                "profile_manual",
            "enabled": True,
            "invalidation_mode":
                gps.MANUAL_APPROVED,
            "manual_invalidation_price":
                190.0,
            "invalidation_basis":
                "Human-approved technical/fundamental invalidation",
            "human_approved": True,
        }

        with patch.object(
            gps,
            "_ticker_for_case",
            return_value="AMZN",
        ), patch.object(
            gps,
            "_ensure_profile",
            return_value=profile,
        ), patch.object(
            gps,
            "build_portfolio_state",
            return_value=EMPTY_PORTFOLIO,
        ), patch.object(
            gps,
            "record_object",
        ), patch.object(
            gps,
            "record_event",
        ):

            result = (
                gps.calculate_generic_position_sizing(
                    case_id="case_test",
                    capital_gate={
                        "decision": "APPROVED",
                        "current_price": 214.0,
                        "downside_reference_value":
                            156.6362,
                    },
                )
            )

        self.assertEqual(
            result["decision"],
            "SIZE_READY",
        )

        self.assertEqual(
            result["proposed_shares"],
            2,
        )

        self.assertAlmostEqual(
            result["proposed_notional"],
            428.0,
            places=2,
        )

        self.assertAlmostEqual(
            result[
                "proposed_loss_at_invalidation"
            ],
            48.0,
            places=2,
        )

        self.assertAlmostEqual(
            result[
                "proposed_portfolio_risk_pct"
            ],
            0.0048,
            places=6,
        )

        self.assertFalse(
            result["paper_order_permission"]
        )
        self.assertFalse(
            result["trade_execution_permission"]
        )
        self.assertFalse(
            result["live_execution"]
        )

    def test_nonempty_portfolio_requires_governed_overlap_context(self):
        state = {
            "nav": 10000.0,
            "cash": 8000.0,
            "position_count": 1,
            "positions": [
                {
                    "ticker": "GOOGL",
                    "market_value": 2000.0,
                }
            ],
        }

        profile = {
            "generic_sizing_profile_id":
                "profile_test",
            "enabled": True,
            "invalidation_mode":
                gps.CAPITAL_DOWNSIDE_REFERENCE,
        }

        def latest_object_side_effect(
            object_type,
            case_id=None,
        ):
            if object_type == (
                "prospective_portfolio_observation"
            ):
                return None
            return None

        with patch.object(
            gps,
            "_ticker_for_case",
            return_value="AMZN",
        ), patch.object(
            gps,
            "_ensure_profile",
            return_value=profile,
        ), patch.object(
            gps,
            "build_portfolio_state",
            return_value=state,
        ), patch.object(
            gps,
            "latest_object",
            side_effect=latest_object_side_effect,
        ):

            result = (
                gps.calculate_generic_position_sizing(
                    case_id="case_test",
                    capital_gate={
                        "decision": "APPROVED",
                        "current_price": 214.0,
                        "downside_reference_value":
                            190.0,
                    },
                )
            )

        self.assertEqual(
            result["decision"],
            "BLOCKED",
        )

        self.assertEqual(
            result["reason"],
            "PORTFOLIO_OVERLAP_CONTEXT_REQUIRED",
        )

    def test_entry_watch_calls_generic_sizing_only_after_capital_approval(self):
        qualification = {
            "qualified_buy_candidate": True,
        }

        risk = {
            "decision": "WATCH_ONLY",
            "triggered_rules": [],
        }

        def latest_object_side_effect(
            object_type,
            case_id=None,
        ):
            if object_type == "qualification_assessment":
                return qualification
            if object_type == "risk_authorization":
                return risk
            if object_type == "case":
                return {
                    "topic":
                        "Amazon opportunity review"
                }
            if object_type == "capital_entry_watch":
                return {
                    "stage": "WAIT_FOR_ENTRY"
                }
            return None

        quote = {
            "status": "ok",
            "provider": "SIMULATION_ONLY",
            "current_price": 214.0,
            "items": [],
        }

        generic_capital = {
            "decision": "APPROVED",
            "current_price": 214.0,
            "maximum_qualifying_entry":
                214.0695,
            "reward_risk": 1.503,
            "minimum_reward_risk": 1.5,
            "downside_reference_value":
                156.6362,
            "failed_hard_checks": [],
        }

        sizing = {
            "decision": "SIZE_READY",
            "proposed_shares": 2,
            "proposed_notional": 428.0,
            "paper_authorization_ready":
                False,
            "paper_order_permission": False,
            "trade_execution_permission":
                False,
            "live_execution": False,
        }

        with patch.object(
            watch,
            "latest_object",
            side_effect=latest_object_side_effect,
        ), patch.object(
            watch,
            "_ticker_for_case",
            return_value="AMZN",
        ), patch.object(
            watch,
            "build_generic_thesis_status",
            return_value={
                "status": "ACTIVE_WITH_WATCHES",
                "thesis_invalidated": False,
            },
        ), patch.object(
            watch,
            "build_generic_public_company_stress",
            return_value={},
        ), patch.object(
            watch,
            "assess_generic_public_company_capital",
            return_value=generic_capital,
        ), patch.object(
            watch,
            "calculate_generic_position_sizing",
            return_value=sizing,
        ) as sizing_mock, patch.object(
            watch,
            "record_object",
        ), patch.object(
            watch,
            "record_event",
        ):

            result = (
                watch.refresh_capital_entry_watch(
                    "case_test",
                    quote=quote,
                )
            )

        sizing_mock.assert_called_once()

        self.assertEqual(
            result["stage"],
            "READY_FOR_POSITION_SIZING",
        )

        self.assertEqual(
            result[
                "automatic_sizing"
            ]["decision"],
            "SIZE_READY",
        )

        self.assertFalse(
            result["paper_authorization_ready"]
        )
        self.assertFalse(
            result["paper_order_permission"]
        )
        self.assertFalse(
            result["trade_execution_permission"]
        )
        self.assertFalse(
            result["live_execution"]
        )


if __name__ == "__main__":
    unittest.main()
