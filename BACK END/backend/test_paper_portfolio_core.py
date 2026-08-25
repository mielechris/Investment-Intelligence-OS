import tempfile
import unittest
from pathlib import Path

import ledger
import paper_portfolio_core as portfolio


class PaperPortfolioCoreTests(unittest.TestCase):
    def setUp(self):
        self.original_db = ledger.DB_PATH
        self.tempdir = tempfile.TemporaryDirectory()
        ledger.DB_PATH = Path(self.tempdir.name) / "portfolio_test.db"
        ledger.init_ledger()

    def tearDown(self):
        ledger.DB_PATH = self.original_db
        self.tempdir.cleanup()

    def _seed_execution(
        self,
        *,
        suffix: str,
        ticker: str,
        shares: int,
        price: float,
    ):
        candidate_id = f"opportunity_{suffix}"
        case_id = f"case_{suffix}"
        execution_id = f"governed_paper_{suffix}"

        ledger.record_object(
            candidate_id,
            "opportunity_candidate",
            "opportunity_factory",
            {
                "opportunity_candidate_id": candidate_id,
                "ticker": ticker,
                "created_at": ledger.utc_now(),
            },
            topic=ticker,
        )

        ledger.record_object(
            case_id,
            "case",
            case_id,
            {
                "case_id": case_id,
                "topic": f"{ticker} opportunity review",
                "source_candidate_id": candidate_id,
                "created_at": ledger.utc_now(),
            },
            topic=ticker,
        )

        ledger.record_object(
            execution_id,
            "governed_paper_execution",
            case_id,
            {
                "execution_id": execution_id,
                "case_id": case_id,
                "status": "COMPLETE",
                "execution": "PAPER_ORDER_CREATED",
                "shares": shares,
                "entry_price": price,
                "notional": round(shares * price, 2),
                "paper_mode": True,
                "paper_order_permission": True,
                "trade_execution_permission": False,
                "live_execution": False,
                "created_at": ledger.utc_now(),
            },
            topic=ticker,
        )

    def test_empty_portfolio_starts_at_10000(self):
        state = portfolio.build_portfolio_state()

        self.assertEqual(state["starting_cash"], 10000.00)
        self.assertEqual(state["cash"], 10000.00)
        self.assertEqual(state["nav"], 10000.00)
        self.assertEqual(state["position_count"], 0)
        self.assertFalse(state["trade_execution_permission"])
        self.assertFalse(state["live_execution"])

    def test_reconciles_only_governed_paper_executions(self):
        self._seed_execution(
            suffix="one",
            ticker="NVDA",
            shares=10,
            price=100.00,
        )
        self._seed_execution(
            suffix="two",
            ticker="NVDA",
            shares=5,
            price=120.00,
        )

        state = portfolio.build_portfolio_state(
            {"NVDA": 110.00}
        )

        self.assertEqual(state["transaction_count"], 2)
        self.assertEqual(state["position_count"], 1)

        position = state["positions"][0]

        self.assertEqual(position["ticker"], "NVDA")
        self.assertEqual(position["quantity"], 15)
        self.assertEqual(position["cost_basis"], 1600.00)
        self.assertAlmostEqual(
            position["average_cost"],
            106.666667,
            places=5,
        )
        self.assertEqual(position["market_value"], 1650.00)
        self.assertEqual(position["unrealized_pnl"], 50.00)

        self.assertEqual(state["cash"], 8400.00)
        self.assertEqual(state["nav"], 10050.00)
        self.assertEqual(state["total_pnl"], 50.00)

    def test_reconciliation_is_idempotent(self):
        self._seed_execution(
            suffix="one",
            ticker="AMD",
            shares=4,
            price=150.00,
        )

        first = portfolio.reconcile_governed_executions()
        second = portfolio.reconcile_governed_executions()

        self.assertEqual(first["created_transactions"], 1)
        self.assertEqual(second["created_transactions"], 0)
        self.assertEqual(second["existing_transactions"], 1)

        state = portfolio.build_portfolio_state()
        self.assertEqual(state["transaction_count"], 1)

    def test_portfolio_has_no_execution_authority(self):
        plan = portfolio.paper_portfolio_plan()

        self.assertFalse(plan["direct_trade_creation"])
        self.assertFalse(plan["trade_execution_permission"])
        self.assertFalse(plan["live_execution"])


if __name__ == "__main__":
    unittest.main()


class PaperPortfolioPerformanceTests(unittest.TestCase):
    def setUp(self):
        self.original_db = ledger.DB_PATH
        self.tempdir = tempfile.TemporaryDirectory()
        ledger.DB_PATH = Path(self.tempdir.name) / "performance_test.db"
        ledger.init_ledger()

    def tearDown(self):
        ledger.DB_PATH = self.original_db
        self.tempdir.cleanup()

    def test_empty_live_snapshot_keeps_10000_nav(self):
        snapshot = portfolio.record_live_portfolio_snapshot()

        self.assertEqual(snapshot["nav"], 10000.00)
        self.assertEqual(snapshot["position_count"], 0)
        self.assertFalse(snapshot["trade_execution_permission"])
        self.assertFalse(snapshot["live_execution"])

        perf = portfolio.build_performance_history()

        self.assertEqual(perf["snapshot_count"], 1)
        self.assertEqual(perf["latest_nav"], 10000.00)
        self.assertEqual(perf["cumulative_return_pct"], 0.0)

    def test_performance_tracks_return_and_drawdown(self):
        portfolio.ensure_account()

        portfolio.record_portfolio_snapshot({})

        ledger.record_object(
            "paper_portfolio_snapshot_test_up",
            "paper_portfolio_snapshot",
            portfolio.PORTFOLIO_CASE_ID,
            {
                "paper_portfolio_snapshot_id":
                    "paper_portfolio_snapshot_test_up",
                "paper_portfolio_account_id":
                    portfolio.ACCOUNT_ID,
                "nav": 10500.00,
                "cash": 5000.00,
                "market_value": 5500.00,
                "realized_pnl": 0.0,
                "unrealized_pnl": 500.00,
                "total_pnl": 500.00,
                "created_at": "2026-08-25T12:00:00+00:00",
            },
            parent_id=portfolio.ACCOUNT_ID,
        )

        ledger.record_object(
            "paper_portfolio_snapshot_test_down",
            "paper_portfolio_snapshot",
            portfolio.PORTFOLIO_CASE_ID,
            {
                "paper_portfolio_snapshot_id":
                    "paper_portfolio_snapshot_test_down",
                "paper_portfolio_account_id":
                    portfolio.ACCOUNT_ID,
                "nav": 10000.00,
                "cash": 5000.00,
                "market_value": 5000.00,
                "realized_pnl": 0.0,
                "unrealized_pnl": 0.0,
                "total_pnl": 0.0,
                "created_at": "2026-08-25T13:00:00+00:00",
            },
            parent_id=portfolio.ACCOUNT_ID,
        )

        perf = portfolio.build_performance_history()

        self.assertEqual(perf["snapshot_count"], 3)
        self.assertEqual(perf["high_water_mark"], 10500.00)
        self.assertAlmostEqual(
            perf["max_drawdown_pct"],
            -4.7619,
            places=4,
        )
        self.assertEqual(perf["latest_nav"], 10000.00)

    def test_performance_has_no_execution_authority(self):
        perf = portfolio.build_performance_history()

        self.assertFalse(perf["trade_execution_permission"])
        self.assertFalse(perf["live_execution"])
        self.assertFalse(perf["paper_order_permission"])
