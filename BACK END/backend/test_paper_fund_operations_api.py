import unittest
from unittest.mock import patch

import main
import paper_fund_operations_api


class PaperFundOperationsApiTests(unittest.TestCase):
    def test_main_exposes_operations_route(self):
        paths = {route.path for route in main.app.routes}
        self.assertIn("/paper-fund/operations", paths)

    @patch.object(paper_fund_operations_api, "_recent_paper_orders")
    @patch.object(paper_fund_operations_api, "_latest_deepened_case")
    @patch.object(paper_fund_operations_api, "build_performance_history")
    @patch.object(paper_fund_operations_api, "build_portfolio_state")
    @patch.object(paper_fund_operations_api, "latest_object")
    def test_operations_aggregates_real_persisted_state_without_authority(
        self,
        latest_object,
        build_portfolio_state,
        build_performance_history,
        latest_deepened_case,
        recent_paper_orders,
    ):
        observation = {
            "cycle_minutes": 15,
            "last_cycle_completed_at": "2026-08-27T19:30:00+00:00",
            "market_phase": "REGULAR_SESSION",
            "last_scan_status": "complete",
            "last_scan_count": 16,
            "last_queue_count": 10,
            "promoted_case_count": 1,
            "promotions": [
                {
                    "case_id": "case_spy",
                    "ticker": "SPY",
                    "score": 74,
                }
            ],
            "paper_portfolio": {"snapshot_count": 88},
        }
        paper = {
            "cycle_completed_at": "2026-08-27T19:30:00+00:00",
            "market_phase": "REGULAR_SESSION",
            "paper_execution_window_open": True,
            "case_count_inspected": 20,
            "gap_hunts_run": 1,
            "paper_executions_created": 0,
            "cycle_duration_seconds": 1.2,
            "case_results": [
                {
                    "case_id": "case_spy",
                    "ticker": "SPY",
                    "stage": "RESEARCH_NOT_QUALIFIED",
                }
            ],
        }

        def latest_side_effect(object_type, case_id=None, **_kwargs):
            if object_type == paper_fund_operations_api.OBSERVATION_STATE_TYPE:
                return observation
            if object_type == paper_fund_operations_api.PAPER_TRADING_STATE_TYPE:
                return paper
            return {}

        latest_object.side_effect = latest_side_effect
        build_portfolio_state.return_value = {
            "starting_cash": 10000.0,
            "nav": 10000.0,
            "cash": 10000.0,
            "market_value": 0.0,
            "realized_pnl": 0.0,
            "unrealized_pnl": 0.0,
            "total_pnl": 0.0,
            "gross_exposure": 0.0,
            "position_count": 0,
            "transaction_count": 0,
            "positions": [],
        }
        build_performance_history.return_value = {
            "snapshot_count": 88,
            "cumulative_return_pct": 0.0,
            "current_drawdown_pct": 0.0,
            "max_drawdown_pct": 0.0,
        }
        latest_deepened_case.return_value = {
            "case_id": "case_spy",
            "ticker": "SPY",
            "topic": "SPY opportunity review",
            "qualified": False,
            "created_at": "2026-08-27T19:30:00+00:00",
        }
        recent_paper_orders.return_value = []

        result = paper_fund_operations_api.build_paper_fund_operations()

        self.assertEqual(result["observation"]["last_scan_count"], 16)
        self.assertEqual(result["observation"]["last_queue_count"], 10)
        self.assertEqual(result["observation"]["promoted_case_count"], 1)
        self.assertEqual(result["paper_trading"]["case_count_inspected"], 20)
        self.assertEqual(result["portfolio"]["nav"], 10000.0)
        self.assertTrue(result["safety"]["paper_mode"])
        self.assertTrue(result["safety"]["live_capital_locked"])
        self.assertFalse(result["safety"]["broker_connected"])
        self.assertFalse(result["safety"]["trade_execution_permission"])
        self.assertFalse(result["safety"]["live_execution"])
        self.assertFalse(result["authority"]["auto_trade_authority"])
        self.assertFalse(result["authority"]["paper_order_permission"])


if __name__ == "__main__":
    unittest.main()
