from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import market_benchmark as benchmark


class MarketBenchmarkTest(unittest.TestCase):
    def setUp(self) -> None:
        self.start = datetime(2026, 8, 28, 13, 30, tzinfo=timezone.utc)
        self.end = datetime(2026, 8, 28, 20, 0, tzinfo=timezone.utc)

    def _snapshot(self, observed: datetime, change: float = 1.0) -> dict:
        return {
            "observed_at": observed.isoformat(),
            "screeners_successful": list(benchmark.SCREENER_IDS),
            "snapshot_complete": True,
            "provider_errors": [],
            "candidates": [
                {
                    "ticker": "TEST",
                    "company": "Test Corp",
                    "screeners": ["day_gainers"],
                    "change_pct": change,
                    "volume_ratio": 1.2,
                }
            ],
        }

    def test_full_session_builds_complete_truth_set_with_first_seen_time(self) -> None:
        snapshots = []
        for index in range(79):
            observed = self.start + timedelta(minutes=5 * index)
            change = 1.0 if index < 2 else 3.2 + (index / 100.0)
            snapshots.append(self._snapshot(observed, change))

        result = benchmark.build_opportunity_benchmark(
            snapshots,
            session_start=self.start,
            session_end=self.end,
        )

        self.assertTrue(result["benchmark_complete"])
        self.assertEqual(result["opportunities"][0]["ticker"], "TEST")
        self.assertEqual(
            result["opportunities"][0]["event_at"],
            (self.start + timedelta(minutes=10)).isoformat(),
        )
        self.assertEqual(
            result["opportunities"][0]["source"],
            benchmark.SOURCE,
        )
        self.assertTrue(
            result["benchmark_meta"]["independent_of_iios_promotion_decisions"]
        )
        self.assertFalse(result["benchmark_meta"]["ledger_read"])
        self.assertFalse(result["benchmark_meta"]["ledger_write"])

    def test_partial_session_is_explicitly_incomplete(self) -> None:
        snapshots = [
            self._snapshot(self.start + timedelta(minutes=5 * index), 4.0)
            for index in range(8)
        ]
        result = benchmark.build_opportunity_benchmark(
            snapshots,
            session_start=self.start,
            session_end=self.end,
        )
        self.assertFalse(result["benchmark_complete"])
        self.assertFalse(result["benchmark_meta"]["closing_coverage"])

    @patch.object(benchmark, "_strict_universe_aliases")
    @patch.object(benchmark, "_yahoo_screener")
    def test_collector_has_no_ledger_dependency(self, screener, universe) -> None:
        universe.return_value = ({"TEST"}, {"TEST": "TEST"})
        screener.return_value = [
            {
                "symbol": "TEST",
                "shortName": "Test Corp",
                "regularMarketPrice": 100.0,
                "regularMarketChangePercent": 5.0,
                "regularMarketVolume": 2_000_000,
                "averageDailyVolume3Month": 1_000_000,
            }
        ]
        result = benchmark.collect_independent_snapshot(observed_at=self.start)
        self.assertTrue(result["snapshot_complete"])
        self.assertTrue(result["independent_of_iios_promotion_decisions"])
        self.assertFalse(result["ledger_read"])
        self.assertFalse(result["ledger_write"])
        self.assertFalse(result["live_execution"])


if __name__ == "__main__":
    unittest.main()
