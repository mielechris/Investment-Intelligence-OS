from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import iios_paper_performance_qualification as qualification
import iios_portfolio_intelligence as portfolio
import iios_unified_production_browser as unified


class Batch10OperatingSuperbatchTest(unittest.TestCase):
    def test_zero_position_paper_book_is_not_capital_qualified(self) -> None:
        telemetry = {"paper_fund": {"nav": 10000.0, "cash": 10000.0, "position_count": 0, "transaction_count": 0, "positions": [], "cumulative_return_pct": 0.0, "max_drawdown_pct": 0.0}}
        q = qualification.build_qualification(telemetry=telemetry, learning={"complete_session_count": 0, "mature_5d_count": 0}, scorecard={"metrics":{"detection_rate_pct":47.2}})
        p = portfolio.build_portfolio(telemetry=telemetry)
        self.assertEqual(q["status"], "INSUFFICIENT_PAPER_SAMPLE")
        self.assertFalse(q["sample_ready"])
        self.assertEqual(p["status"], "CASH_ONLY_WARM_UP")
        self.assertEqual(p["position_count"], 0)
        self.assertFalse(q["safety"]["auto_advance_to_live"])
        self.assertFalse(p["safety"]["auto_rebalance"])

    def test_mature_paper_sample_only_advances_to_human_readiness_review(self) -> None:
        telemetry = {"paper_fund": {"nav": 11200.0, "cash": 3000.0, "position_count": 2, "transaction_count": 45, "positions": [{"ticker":"A","direction":"LONG","market_value":4100.0},{"ticker":"B","direction":"LONG","market_value":4100.0}], "cumulative_return_pct": 12.0, "max_drawdown_pct": -4.5}}
        q = qualification.build_qualification(telemetry=telemetry, learning={"complete_session_count": 25, "mature_5d_count": 40}, scorecard={})
        self.assertEqual(q["status"], "PAPER_QUALIFIED_FOR_HUMAN_READINESS_REVIEW")
        self.assertFalse(q["safety"]["capital_authority"])
        self.assertFalse(q["safety"]["broker_connection_authority"])
        self.assertFalse(q["safety"]["live_execution"])

    def test_unified_browser_is_view_not_command_surface(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); state = root / "state"; telemetry_dir = root / "telemetry"; state.mkdir(); telemetry_dir.mkdir()
            (state / "shadow_strategy").mkdir(); (state / "browser").mkdir()
            (state / "latest_market_validation.json").write_text(json.dumps({"input":{"benchmark_complete":False,"opportunities":[]},"metrics":{}}))
            (state / "latest_outcome_learning.json").write_text(json.dumps({"status":"WAITING_FOR_COMPLETE_9H_SESSIONS","complete_session_count":0,"mature_5d_count":0,"agent_scorecards":[],"recent_outcomes":[]}))
            (state / "shadow_strategy" / "latest_shadow_counterfactual.json").write_text(json.dumps({"status":"WARMUP_COLLECTING_COMPLETE_SESSIONS","complete_session_count":0,"recommendations":[]}))
            (telemetry_dir / "latest.json").write_text(json.dumps({"generated_at":"2026-08-28T00:00:00+00:00","paper_fund":{"nav":10000.0,"cash":10000.0,"position_count":0,"transaction_count":0,"positions":[],"cumulative_return_pct":0.0,"max_drawdown_pct":0.0}}))
            payload = unified.build_unified(state_dir=state, telemetry_dir=telemetry_dir)
            self.assertEqual(payload["status"], "UNIFIED_OPERATING_BROWSER_READY")
            self.assertEqual(payload["operating_mode"], "GOVERNED_PAPER_RESEARCH_ONLY")
            self.assertFalse(payload["safety"]["browser_is_command_surface"])
            self.assertFalse(payload["safety"]["capital_authority"])
            self.assertFalse(payload["safety"]["live_execution"])


if __name__ == "__main__": unittest.main()
