import unittest
from unittest.mock import patch

import operations_visibility as visibility


class Batch10DOperationsVisibilityTests(unittest.TestCase):
    @patch.object(visibility, "build_options_shadow_status")
    @patch.object(visibility, "latest_object")
    @patch.object(visibility, "resolve_case_profile")
    @patch.object(visibility, "build_closed_loop_overview")
    @patch.object(visibility, "build_portfolio_state")
    def test_visibility_aggregates_governed_paper_watch_and_options_state(
        self,
        build_portfolio_state,
        build_closed_loop_overview,
        resolve_case_profile,
        latest_object,
        build_options_shadow_status,
    ):
        build_portfolio_state.return_value = {
            "nav": 10000.0,
            "cash": 10000.0,
            "position_count": 0,
            "transaction_count": 0,
            "accounting_scope": "PAPER_ONLY",
        }
        build_closed_loop_overview.return_value = {
            "cases": [
                {
                    "case_id": "case_mu",
                    "topic": "Micron Technology opportunity review",
                    "current_stage": "RESEARCH_NOT_QUALIFIED",
                    "continuity_state": "CLOSED_LOOP_NO_CAPITAL_PATH",
                    "committee_disposition": "NO_TRADE",
                    "risk_decision": "VETOED",
                    "qualified_buy_candidate": False,
                    "capital_stage": "RESEARCH_NOT_QUALIFIED",
                    "paper_execution_complete": False,
                    "monitoring_active": True,
                    "valid_no_capital_outcome": True,
                    "dead_end": False,
                    "missing_continuation": [],
                }
            ]
        }
        resolve_case_profile.return_value = {
            "ticker": "MU",
            "company": "Micron Technology",
        }
        latest_object.side_effect = lambda object_type, case_id=None: {
            "deep_watch_obligation_set": {
                "obligation_count": 8,
                "material_change_count": 0,
                "policy_version": "structured-v2",
            },
            "deep_watch_reunderwrite": {
                "committee": {"disposition": "NO_TRADE", "confidence": 0.9}
            },
            "qualification_assessment": {
                "qualified_buy_candidate": False,
                "unmet_requirements": ["committee_watch", "risk_clear_for_watch"],
            },
            "committee_decision": {
                "required_evidence": ["Fresh financials"],
                "disposition": "NO_TRADE",
            },
            "risk_authorization": {
                "decision": "VETOED",
                "triggered_rules": ["COMMITTEE_NO_TRADE"],
            },
            "gap_hunt": {},
        }.get(object_type, {})
        build_options_shadow_status.return_value = {
            "mode": "SHADOW_OBSERVATION_ONLY",
            "observation_count": 3,
            "option_order_permission": False,
            "live_execution": False,
        }

        result = visibility.build_operations_visibility(limit=25)

        self.assertEqual(result["portfolio"]["nav"], 10000.0)
        self.assertEqual(result["portfolio"]["capital_deployed"], 0.0)
        self.assertEqual(result["summary"]["deep_watch_cases"], 1)
        self.assertEqual(result["summary"]["open_obligations"], 8)
        self.assertEqual(result["summary"]["material_change_cases"], 0)
        self.assertEqual(result["summary"]["options_shadow_cases"], 1)
        self.assertEqual(result["summary"]["options_observations"], 3)
        self.assertEqual(result["summary"]["dead_end_count"], 0)

        row = result["cases"][0]
        self.assertEqual(row["ticker"], "MU")
        self.assertEqual(row["attention"], "WATCHING")
        self.assertEqual(row["capital_reason"]["state"], "RESEARCH_NOT_QUALIFIED")
        self.assertEqual(row["deep_watch"]["obligation_count"], 8)
        self.assertFalse(row["options_shadow"]["option_order_permission"])
        self.assertFalse(row["live_execution"])

    @patch.object(visibility, "build_options_shadow_status")
    @patch.object(visibility, "latest_object")
    @patch.object(visibility, "resolve_case_profile")
    @patch.object(visibility, "build_closed_loop_overview")
    @patch.object(visibility, "build_portfolio_state")
    def test_visibility_flags_material_change_without_execution_authority(
        self,
        build_portfolio_state,
        build_closed_loop_overview,
        resolve_case_profile,
        latest_object,
        build_options_shadow_status,
    ):
        build_portfolio_state.return_value = {"nav": 10000.0, "cash": 9000.0, "position_count": 1}
        build_closed_loop_overview.return_value = {
            "cases": [
                {
                    "case_id": "case_watch",
                    "current_stage": "DEEP_WATCH",
                    "continuity_state": "CLOSED_LOOP_NO_CAPITAL_PATH",
                    "committee_disposition": "WATCH",
                    "risk_decision": "WATCH_ONLY",
                    "qualified_buy_candidate": False,
                    "paper_execution_complete": False,
                    "monitoring_active": True,
                    "valid_no_capital_outcome": True,
                    "dead_end": False,
                }
            ]
        }
        resolve_case_profile.return_value = {"ticker": "ABC", "company": "ABC Corp"}
        latest_object.side_effect = lambda object_type, case_id=None: {
            "deep_watch_obligation_set": {"obligation_count": 4, "material_change_count": 2},
            "deep_watch_reunderwrite": {},
            "qualification_assessment": {},
            "committee_decision": {"disposition": "WATCH"},
            "risk_authorization": {"decision": "WATCH_ONLY"},
            "gap_hunt": {},
        }.get(object_type, {})
        build_options_shadow_status.return_value = {
            "mode": "SHADOW_OBSERVATION_ONLY",
            "observation_count": 0,
        }

        result = visibility.build_operations_visibility()
        row = result["cases"][0]

        self.assertEqual(row["attention"], "MATERIAL_CHANGE")
        self.assertEqual(result["summary"]["material_change_cases"], 1)
        self.assertFalse(result["paper_order_permission"])
        self.assertFalse(result["option_order_permission"])
        self.assertFalse(result["trade_execution_permission"])
        self.assertFalse(result["live_execution"])


if __name__ == "__main__":
    unittest.main()
