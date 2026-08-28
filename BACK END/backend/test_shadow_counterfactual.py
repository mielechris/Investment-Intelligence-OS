from __future__ import annotations

import copy
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

import shadow_counterfactual as shadow


class ShadowCounterfactualTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp.name) / "iios_ledger.db"
        self.db = sqlite3.connect(self.db_path)
        self.db.execute(
            """
            CREATE TABLE ledger_objects (
                object_id TEXT PRIMARY KEY,
                object_type TEXT NOT NULL,
                case_id TEXT NOT NULL,
                parent_id TEXT,
                topic TEXT,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        self.cycle_time = "2026-08-28T14:00:00+00:00"
        self._seed_cycle()

    def tearDown(self) -> None:
        self.db.close()
        self.temp.cleanup()

    def _seed_cycle(self) -> None:
        ranked = [
            {"ticker": "GOOD", "rank_score": 90.0},
            {"ticker": "LOWER", "rank_score": 85.0},
            {"ticker": "BLOCK", "rank_score": 80.0},
            {"ticker": "NOISE", "rank_score": 75.0},
            {"ticker": "OTHER", "rank_score": 70.0},
        ]
        promotions = [
            {
                "ticker": "GOOD",
                "score": 50.0,
                "radar_rank_score": 90.0,
                "quote_ok": True,
                "news_count": 4,
                "reason_codes": ["CURRENT_MARKET_QUOTE"],
            },
            {
                "ticker": "LOWER",
                "score": 42.0,
                "radar_rank_score": 85.0,
                "quote_ok": True,
                "news_count": 4,
                "reason_codes": ["CURRENT_MARKET_QUOTE"],
            },
            {
                "ticker": "BLOCK",
                "score": 90.0,
                "radar_rank_score": 80.0,
                "quote_ok": True,
                "news_count": 8,
                "reason_codes": ["RECENT_GOVERNED_CASE_EXISTS"],
            },
            {
                "ticker": "NOISE",
                "score": 60.0,
                "radar_rank_score": 75.0,
                "quote_ok": True,
                "news_count": 4,
                "reason_codes": ["CURRENT_MARKET_QUOTE"],
            },
        ]
        payload = {
            "high_speed_market_radar_cycle_id": "cycle_1",
            "last_cycle_completed_at": self.cycle_time,
            "created_at": self.cycle_time,
            "ranked_candidates": ranked,
            "promotion_candidates": promotions,
        }
        self.db.execute(
            """
            INSERT INTO ledger_objects
            (object_id, object_type, case_id, parent_id, topic, payload_json, created_at)
            VALUES (?, ?, ?, NULL, NULL, ?, ?)
            """,
            (
                "cycle_1",
                shadow.RADAR_CYCLE_TYPE,
                "high_speed_market_radar",
                json.dumps(payload),
                self.cycle_time,
            ),
        )
        self.db.commit()

    def _benchmark(self, *, complete: bool = True) -> dict:
        return {
            "session_id": "2026-08-28",
            "session_start": "2026-08-28T13:30:00+00:00",
            "session_end": "2026-08-28T20:00:00+00:00",
            "benchmark_complete": complete,
            "opportunities": [
                {
                    "opportunity_id": "bench_good",
                    "ticker": "GOOD",
                    "event_at": "2026-08-28T13:55:00+00:00",
                    "importance": "HIGH",
                },
                {
                    "opportunity_id": "bench_lower",
                    "ticker": "LOWER",
                    "event_at": "2026-08-28T13:55:00+00:00",
                    "importance": "MEDIUM",
                },
            ],
        }

    def _scorecard(self) -> dict:
        return {"metrics": {"detection_rate_pct": 50.0}}

    def count_objects(self) -> int:
        return int(self.db.execute("SELECT COUNT(*) FROM ledger_objects").fetchone()[0])

    def test_shadow_session_is_read_only_and_preserves_hard_blocks(self) -> None:
        before = self.count_objects()
        result = shadow.build_session_counterfactual(
            self._benchmark(),
            self._scorecard(),
            self.db_path,
            promotion_scores=(40.0, 45.0),
            case_capacities=(5,),
            radar_breadths=(2, 5),
        )
        after = self.count_objects()

        self.assertEqual(before, after)
        self.assertEqual(result["status"], "SESSION_COUNTERFACTUAL_COMPLETE")
        self.assertTrue(result["safety"]["shadow_only"])
        self.assertFalse(result["safety"]["live_execution"])

        baseline = result["baseline"]
        self.assertEqual(baseline["captured_count"], 1)
        self.assertEqual(baseline["captured_tickers"], ["GOOD"])
        self.assertNotIn("BLOCK", baseline["captured_tickers"])

        lower_floor = next(
            row
            for row in result["promotion_scenarios"]
            if row["scenario_id"] == "score_40_capacity_5"
        )
        self.assertEqual(lower_floor["captured_count"], 2)
        self.assertEqual(lower_floor["vs_baseline"]["marginal_captured_count"], 1)
        self.assertEqual(
            lower_floor["vs_baseline"]["marginal_extra_nonbenchmark_ticker_count"],
            0,
        )
        self.assertEqual(lower_floor["hard_blocked_candidate_events"], 1)

        breadth_two = next(
            row for row in result["radar_breadth_analysis"] if row["radar_top_n"] == 2
        )
        self.assertEqual(breadth_two["captured_count"], 2)
        self.assertFalse(breadth_two["promotion_inference"])

    def test_incomplete_benchmark_fails_closed(self) -> None:
        result = shadow.build_session_counterfactual(
            self._benchmark(complete=False),
            self._scorecard(),
            self.db_path,
        )
        self.assertEqual(result["status"], "BENCHMARK_INCOMPLETE")
        self.assertEqual(result["recommendations"], [])
        self.assertFalse(result["safety"]["auto_apply_threshold_changes"])

    def test_rollup_requires_five_complete_sessions_before_advice(self) -> None:
        one = shadow.build_session_counterfactual(
            self._benchmark(),
            self._scorecard(),
            self.db_path,
            promotion_scores=(40.0, 45.0),
            case_capacities=(5,),
            radar_breadths=(8,),
        )

        warmup = []
        for index in range(4):
            row = copy.deepcopy(one)
            row["session_id"] = f"2026-08-{20 + index:02d}"
            warmup.append(row)
        warmup_rollup = shadow.aggregate_counterfactual_sessions(warmup)
        self.assertEqual(
            warmup_rollup["status"],
            "WARMUP_COLLECTING_COMPLETE_SESSIONS",
        )
        self.assertEqual(warmup_rollup["recommendations"], [])

        fifth = copy.deepcopy(one)
        fifth["session_id"] = "2026-08-24"
        ready_rollup = shadow.aggregate_counterfactual_sessions([*warmup, fifth])
        self.assertEqual(ready_rollup["status"], "ADVISORY_READY")
        self.assertGreaterEqual(len(ready_rollup["advisory_frontier"]), 1)
        self.assertEqual(
            ready_rollup["recommendations"][0]["action"],
            "HUMAN_REVIEW_ONLY",
        )
        self.assertFalse(
            ready_rollup["safety"]["auto_apply_threshold_changes"]
        )


if __name__ == "__main__":
    unittest.main()
