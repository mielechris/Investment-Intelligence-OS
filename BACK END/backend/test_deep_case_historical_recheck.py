import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import deep_case_historical_recheck as recheck


class DeepCaseHistoricalRecheckTests(unittest.TestCase):
    def test_deep_watch_baseline_and_material_changes_trigger_recheck(self):
        state = {
            "deep_case": True,
            "deep_reasons": ["COMMITTEE_WATCH", "CAPITAL_ENTRY_WATCH"],
            "historical": {"historical_signal": "MIXED_PRECEDENT"},
            "prior_recheck": {
                "created_at": (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat(),
                "observed_return_pct": -1.0,
                "capital_stage": "WAIT_FOR_ENTRY",
            },
            "thesis": {
                "thesis_status": "REUNDERWRITE_REQUIRED",
                "flags": ["CATALYST_MISSED"],
            },
            "position": {"return_pct": -7.0},
            "capital_control": {
                "stage": "READY_FOR_POSITION_SIZING",
                "entry_gap_pct": 1.5,
                "entry_reference_active": True,
            },
        }

        triggers = recheck.recheck_triggers(state)

        self.assertIn("MATERIAL_THESIS_CHANGE", triggers)
        self.assertIn("MATERIAL_PRICE_MOVE", triggers)
        self.assertIn("CAPITAL_STAGE_CHANGE", triggers)
        self.assertIn("ENTRY_GATE_READY", triggers)
        self.assertIn("NEAR_ENTRY_PRICE", triggers)

    def test_missing_entry_watch_recovers_active_wait_for_entry_reference(self):
        result = recheck.normalize_capital_control(
            qualification={"qualified_buy_candidate": True},
            capital_watch={},
            capital_status={
                "stage": "WAIT_FOR_ENTRY",
                "capital": {
                    "current_price": 105.0,
                    "maximum_qualifying_entry": 102.0,
                    "failed_hard_checks": [],
                },
            },
        )

        self.assertEqual(result["source"], "PAPER_CAPITAL_STATUS")
        self.assertEqual(result["stage"], "WAIT_FOR_ENTRY")
        self.assertEqual(result["maximum_qualifying_entry"], 102.0)
        self.assertAlmostEqual(result["entry_gap_pct"], 2.8571, places=4)
        self.assertTrue(result["entry_reference_active"])
        self.assertEqual(result["entry_reference_status"], "ACTIVE_GOVERNED_ENTRY")

        triggers = recheck.recheck_triggers({
            "deep_case": True,
            "historical": {"historical_signal": "MIXED_PRECEDENT"},
            "prior_recheck": {"capital_stage": "WAIT_FOR_ENTRY", "created_at": datetime.now(timezone.utc).isoformat()},
            "thesis": {},
            "position": {},
            "capital_control": result,
        })
        self.assertIn("NEAR_ENTRY_PRICE", triggers)

    def test_upstream_research_block_never_becomes_active_buy_zone(self):
        result = recheck.normalize_capital_control(
            qualification={"qualified_buy_candidate": False},
            capital_watch={},
            capital_status={
                "stage": "RESEARCH_NOT_QUALIFIED",
                "capital": {
                    "decision": "NOT_EVALUATED",
                    "current_price": None,
                    "maximum_qualifying_entry": None,
                    "failed_hard_checks": ["RESEARCH_NOT_QUALIFIED"],
                },
            },
        )

        self.assertFalse(result["entry_reference_active"])
        self.assertEqual(result["entry_reference_status"], "INACTIVE_UPSTREAM_RESEARCH_GATE")
        self.assertIsNone(result["maximum_qualifying_entry"])

    @patch.object(recheck, "record_event")
    @patch.object(recheck, "record_object")
    @patch.object(recheck, "run_historical_pattern_review")
    @patch.object(recheck, "deep_case_state")
    def test_recheck_runs_history_and_never_gets_trade_authority(
        self,
        deep_case_state,
        run_history,
        record_object,
        record_event,
    ):
        deep_case_state.return_value = {
            "case": {"topic": "Micron memory cycle"},
            "ticker": "MU",
            "deep_case": True,
            "deep_reasons": ["COMMITTEE_WATCH", "CAPITAL_ENTRY_WATCH"],
            "historical": {"historical_signal": "MIXED_PRECEDENT"},
            "prior_recheck": {},
            "committee": {"disposition": "WATCH", "confidence": 0.77},
            "qualification": {"qualified_buy_candidate": True},
            "risk": {"decision": "PASS"},
            "capital_watch": {"stage": "WAIT_FOR_ENTRY", "entry_gap_pct": 2.5},
            "capital_control": {
                "source": "CAPITAL_ENTRY_WATCH",
                "stage": "WAIT_FOR_ENTRY",
                "current_price": 105.0,
                "maximum_qualifying_entry": 102.5,
                "entry_gap_pct": 2.381,
                "entry_reference_active": True,
                "entry_reference_status": "ACTIVE_GOVERNED_ENTRY",
                "failed_hard_checks": [],
                "error": None,
            },
            "position": {"return_pct": -2.0},
            "thesis": {"thesis_status": "INTACT", "flags": []},
            "monitor": {"enabled": True},
            "execution": {},
        }
        run_history.return_value = {
            "historical_pattern_review_id": "historical_pattern_123",
            "historical_signal": "HISTORICAL_SUPPORT",
            "confidence": 0.68,
            "disposition": "WATCH",
            "analog_stats": {"analog_count": 4, "known_outcome_count": 2},
            "trade_execution_permission": False,
            "live_execution": False,
        }

        result = recheck.run_historical_recheck("case_mu")

        run_history.assert_called_once_with("case_mu")
        self.assertEqual(result["status"], "COMPLETE")
        self.assertEqual(result["ticker"], "MU")
        self.assertEqual(result["capital_stage"], "WAIT_FOR_ENTRY")
        self.assertEqual(result["maximum_qualifying_entry"], 102.5)
        self.assertTrue(result["entry_reference_active"])
        self.assertTrue(result["triggered"])
        self.assertTrue(result["historical_signal_changed"])
        self.assertTrue(result["reunderwrite_required"])
        self.assertFalse(result["auto_trade_authority"])
        self.assertFalse(result["paper_order_permission"])
        self.assertFalse(result["trade_execution_permission"])
        self.assertFalse(result["live_execution"])
        record_object.assert_called_once()
        record_event.assert_called_once()

    @patch.object(recheck, "run_historical_pattern_review")
    @patch.object(recheck, "deep_case_state")
    def test_force_never_pulls_shallow_case_into_history(self, state, run_history):
        state.return_value = {
            "case": {"topic": "shallow opportunity"},
            "ticker": "TEST",
            "deep_case": False,
            "deep_reasons": [],
        }

        result = recheck.run_historical_recheck("case_shallow", force=True)

        self.assertEqual(result["status"], "SKIPPED_NOT_DEEP_CASE")
        run_history.assert_not_called()

    @patch.object(recheck, "run_historical_recheck")
    @patch.object(recheck, "_rows_by_type")
    def test_sweep_includes_deep_cases_and_stays_fail_closed(self, rows, run_one):
        rows.return_value = [
            {"case_id": "case_mu"},
            {"case_id": "case_nvda"},
        ]
        run_one.side_effect = [
            {
                "case_id": "case_mu",
                "status": "COMPLETE",
                "triggered": True,
                "historical_signal": "HISTORICAL_SUPPORT",
                "entry_reference_active": True,
                "reunderwrite_required": False,
            },
            {
                "case_id": "case_nvda",
                "status": "SKIPPED_NOT_DUE",
                "triggered": False,
            },
        ]

        result = recheck.sweep_deep_cases()

        self.assertEqual(result["checked_cases"], 2)
        self.assertEqual(result["rechecked_cases"], 1)
        self.assertEqual(result["active_entry_references"], 1)
        self.assertFalse(result["auto_trade_authority"])
        self.assertFalse(result["paper_order_permission"])
        self.assertFalse(result["trade_execution_permission"])
        self.assertFalse(result["live_execution"])


if __name__ == "__main__":
    unittest.main()