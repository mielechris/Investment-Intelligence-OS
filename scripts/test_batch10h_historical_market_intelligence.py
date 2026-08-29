from __future__ import annotations

import math
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

import iios_historical_market_intelligence as historical


def synthetic_rows(count: int = 520) -> list[dict[str, object]]:
    start = date(2024, 1, 1)
    rows: list[dict[str, object]] = []
    price = 100.0
    for i in range(count):
        cycle = math.sin(i / 11.0) * 0.008 + math.sin(i / 37.0) * 0.004
        shock = -0.035 if i % 83 == 0 else (0.025 if i % 61 == 0 else 0.0)
        price *= 1.0 + cycle + shock + 0.0003
        rows.append({
            "date": (start + timedelta(days=i)).isoformat(),
            "open": price * 0.997,
            "high": price * 1.012,
            "low": price * 0.988,
            "close": price,
            "volume": 1_000_000 + (i % 30) * 25_000,
        })
    return rows


class Batch10HHistoricalMarketIntelligenceTest(unittest.TestCase):
    def test_analog_study_uses_only_prior_feature_windows_and_past_forward_outcomes(self) -> None:
        rows = synthetic_rows()
        study = historical.build_analog_study("TEST", "Synthetic Test", rows, max_analogs=8)
        self.assertEqual(study["status"], "ANALOG_STUDY_READY")
        self.assertEqual(study["method"], "FEATURE_DISTANCE_NO_FUTURE_LEAKAGE")
        self.assertGreater(study["analog_count"], 0)
        current_date = rows[-1]["date"]
        self.assertTrue(all(item["date"] < current_date for item in study["analogs"]))
        cutoff = rows[len(rows) - 1 - 120]["date"]
        self.assertTrue(all(item["date"] <= cutoff for item in study["analogs"]))
        self.assertIn("fwd_20d", study["summary"])

    def test_event_move_can_anchor_current_setup_without_rewriting_history(self) -> None:
        rows = synthetic_rows()
        study = historical.build_analog_study("TEST", "Synthetic Test", rows, event_move_pct=-7.25)
        self.assertAlmostEqual(study["current_setup"]["ret1_pct"], -7.25)
        self.assertEqual(study["event_move_override_pct"], -7.25)
        self.assertGreater(study["analog_count"], 0)

    def test_targets_include_core_market_and_current_opportunity_without_duplicates(self) -> None:
        targets = historical._extract_targets(
            {"input": {"opportunities": [{"ticker": "NVDA", "move_pct": -6.0}, {"ticker": "NVDA", "move_pct": -5.5}]}},
            {"paper_fund": {"positions": [{"symbol": "AAPL"}]}},
        )
        symbols = [item["symbol"] for item in targets]
        self.assertIn("^SPX", symbols)
        self.assertIn("NVDA", symbols)
        self.assertIn("AAPL", symbols)
        self.assertEqual(symbols.count("NVDA"), 1)

    def test_cycle_never_fabricates_history_when_provider_is_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            state = root / "state"; telemetry = root / "telemetry"; research = root / "research"
            state.mkdir(); telemetry.mkdir()
            with patch.object(historical, "_load_or_refresh_history", return_value=([], {"provider": "Stooq", "source_url": None, "provider_fetch": False, "cache_hit": False, "error": "offline"})):
                payload = historical.run_cycle(state_dir=state, telemetry_dir=telemetry, research_dir=research, targets_per_cycle=2)
            self.assertEqual(payload["status"], "HISTORICAL_RESEARCH_DEGRADED")
            self.assertEqual(payload["research_summary"]["studies_ready"], 0)
            self.assertTrue(all(item["row_count"] == 0 for item in payload["coverage"]))
            safety = payload["safety"]
            self.assertTrue(safety["read_only_research"])
            self.assertTrue(safety["twenty_four_seven_worker"])
            self.assertFalse(safety["auto_generate_trades"])
            self.assertFalse(safety["capital_authority"])
            self.assertFalse(safety["trade_execution_permission"])
            self.assertFalse(safety["live_execution"])

    def test_history_coverage_is_reported_from_actual_rows(self) -> None:
        rows = synthetic_rows(300)
        coverage = historical._coverage("TEST", "Test", rows, {"provider": "Fixture", "source_url": "fixture://test", "error": None})
        self.assertEqual(coverage["start_date"], rows[0]["date"])
        self.assertEqual(coverage["end_date"], rows[-1]["date"])
        self.assertEqual(coverage["row_count"], 300)
        self.assertNotEqual(coverage["start_date"], "1792-05-17")


if __name__ == "__main__":
    unittest.main()
