import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi import APIRouter

import paper_fund_portfolio_context_bridge as bridge


class PaperFundPortfolioContextBridgeTests(unittest.TestCase):
    @patch.object(bridge, "record_event")
    @patch.object(bridge, "record_object")
    @patch.object(bridge, "build_portfolio_state")
    @patch.object(bridge, "resolve_case_profile")
    @patch.object(bridge, "get_object")
    def test_cash_only_is_valid_current_context(
        self,
        get_object,
        resolve_case_profile,
        build_portfolio_state,
        record_object,
        record_event,
    ):
        get_object.return_value = {"case_id": "case_mu", "topic": "Micron"}
        resolve_case_profile.return_value = {
            "ticker": "MU",
            "sector_profile": "SEMICONDUCTORS",
        }
        build_portfolio_state.return_value = {
            "paper_portfolio_account_id": "paper_portfolio_default",
            "cash": 10000.0,
            "nav": 10000.0,
            "positions": [],
            "accounting_scope": "GOVERNED_PAPER_EXECUTIONS_ONLY",
            "generated_at": "2026-08-28T00:00:00+00:00",
        }

        snapshot = bridge.build_paper_fund_portfolio_context("case_mu")

        self.assertEqual(snapshot["context_state"], "CURRENT_CASH_ONLY")
        self.assertEqual(snapshot["position_count"], 0)
        self.assertEqual(snapshot["cash_weight_pct"], 100.0)
        self.assertEqual(snapshot["overlap"]["combined_overlap_weight_pct"], 0.0)
        self.assertTrue(snapshot["first_party_governed_source"])
        self.assertFalse(snapshot["trade_execution_permission"])
        self.assertFalse(snapshot["live_execution"])
        record_object.assert_called_once()
        record_event.assert_called_once()

    @patch.object(bridge, "COMPANY_PROFILES", {
        "MU": {"sector": "SEMICONDUCTORS"},
        "NVDA": {"sector": "SEMICONDUCTORS"},
        "JPM": {"sector": "FINANCIALS"},
    })
    def test_exact_and_sector_overlap_use_actual_paper_weights(self):
        state = {
            "nav": 10000.0,
            "positions": [
                {"ticker": "MU", "quantity": 10, "market_value": 1000.0},
                {"ticker": "NVDA", "quantity": 5, "market_value": 2000.0},
                {"ticker": "JPM", "quantity": 10, "market_value": 1000.0},
            ],
        }
        positions = bridge._position_rows(state)
        overlap = bridge._overlap("MU", "SEMICONDUCTORS", positions)

        self.assertEqual(overlap["exact_ticker_weight_pct"], 10.0)
        self.assertEqual(overlap["same_sector_weight_pct"], 30.0)
        self.assertEqual(overlap["combined_overlap_weight_pct"], 30.0)
        self.assertEqual(overlap["concentration_level"], "MODERATE")
        self.assertEqual(overlap["factor_overlap_weight_pct"], 0.0)

    @patch.object(bridge, "COMPANY_PROFILES", {})
    def test_unknown_sector_does_not_manufacture_sector_overlap(self):
        state = {
            "nav": 10000.0,
            "positions": [
                {"ticker": "ABC", "quantity": 10, "market_value": 2500.0},
            ],
        }
        positions = bridge._position_rows(state)
        overlap = bridge._overlap("XYZ", "GENERIC_PUBLIC_COMPANY", positions)
        self.assertEqual(overlap["same_sector_weight_pct"], 0.0)
        self.assertEqual(overlap["combined_overlap_weight_pct"], 0.0)

    @patch.object(bridge, "build_paper_fund_portfolio_context")
    def test_install_wraps_existing_monitor_refresh(self, build_context):
        build_context.return_value = {"context_state": "CURRENT_CASH_ONLY"}
        monitoring = SimpleNamespace(
            refresh_profile=lambda profile: {"profile": profile},
            router=APIRouter(),
        )

        bridge.install_paper_fund_portfolio_context_bridge(monitoring)
        result = monitoring.refresh_profile({"case_id": "case_mu"})

        self.assertEqual(
            result["paper_fund_portfolio_context"]["context_state"],
            "CURRENT_CASH_ONLY",
        )
        build_context.assert_called_once_with("case_mu")

    def test_bridge_routes_have_no_execution_authority(self):
        paths = {route.path.lower() for route in bridge.router.routes}
        self.assertIn("/portfolio-context/{case_id}/paper-fund", paths)
        self.assertIn("/portfolio-context/{case_id}/sync-paper-fund", paths)
        self.assertFalse(any("execute" in path or "broker" in path or "authorization" in path for path in paths))


if __name__ == "__main__":
    unittest.main()
