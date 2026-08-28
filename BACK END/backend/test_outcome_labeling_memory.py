from __future__ import annotations

import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from outcome_labeling_memory import (
    aggregate_outcome_memory,
    build_browser_summary,
    build_price_horizons,
    build_session_outcome_memory,
    classify_decision_quality,
    classify_market_outcome,
)


class OutcomeLabelingMemoryTest(unittest.TestCase):
    def _bars(self):
        intraday = [
            {"timestamp": "2026-08-24T14:00:00+00:00", "close": 100.0},
            {"timestamp": "2026-08-24T15:00:00+00:00", "close": 104.0},
            {"timestamp": "2026-08-24T20:00:00+00:00", "close": 106.0},
        ]
        daily = [
            {"timestamp": "2026-08-25T20:00:00+00:00", "close": 108.0},
            {"timestamp": "2026-08-26T20:00:00+00:00", "close": 109.0},
            {"timestamp": "2026-08-27T20:00:00+00:00", "close": 110.0},
            {"timestamp": "2026-08-28T20:00:00+00:00", "close": 111.0},
            {"timestamp": "2026-08-31T20:00:00+00:00", "close": 112.0},
        ]
        return intraday, daily

    def _db(self, root: Path) -> Path:
        path = root / "iios_ledger.db"
        connection = sqlite3.connect(path)
        connection.executescript(
            """
            CREATE TABLE ledger_objects (
                object_id TEXT PRIMARY KEY,
                object_type TEXT NOT NULL,
                case_id TEXT NOT NULL,
                parent_id TEXT,
                topic TEXT,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE ledger_events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                case_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                entity_id TEXT,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )
        connection.commit()
        connection.close()
        return path

    def test_price_horizons_capture_1h_close_next_and_fifth_session(self):
        intraday, daily = self._bars()
        result = build_price_horizons(
            {"event_at": "2026-08-24T14:00:00+00:00"},
            intraday_bars=intraday,
            daily_bars=daily,
            now=datetime(2026, 9, 1, tzinfo=timezone.utc),
        )
        self.assertEqual(result["anchor"]["price"], 100.0)
        self.assertEqual(result["horizons"]["plus_1h"]["return_pct"], 4.0)
        self.assertEqual(result["horizons"]["session_close"]["return_pct"], 6.0)
        self.assertEqual(result["horizons"]["next_session_close"]["return_pct"], 8.0)
        self.assertEqual(result["horizons"]["fifth_session_close"]["return_pct"], 12.0)
        self.assertTrue(result["five_session_mature"])

    def test_decision_quality_separates_market_outcome_from_no_trade_quality(self):
        self.assertEqual(classify_market_outcome(8.0), "STRONG_UPSIDE")
        self.assertEqual(
            classify_decision_quality(
                detected=True,
                committee_disposition="NO_TRADE",
                paper_fill={},
                forward_return_pct=8.0,
            ),
            "NO_TRADE_FOREGONE_UPSIDE",
        )
        self.assertEqual(
            classify_decision_quality(
                detected=True,
                committee_disposition="NO_TRADE",
                paper_fill={},
                forward_return_pct=-8.0,
            ),
            "NO_TRADE_AVOIDED_DOWNSIDE",
        )

    def test_complete_session_builds_browser_ready_memory_without_ledger_mutation(self):
        intraday, daily = self._bars()
        benchmark = {
            "session_id": "2026-08-24",
            "benchmark_complete": True,
            "opportunities": [
                {
                    "opportunity_id": "opp_test",
                    "ticker": "TEST",
                    "event_at": "2026-08-24T14:00:00+00:00",
                    "move_pct": 4.5,
                    "importance": "MEDIUM",
                }
            ],
        }
        scorecard = {
            "opportunities": [
                {
                    "opportunity_id": "opp_test",
                    "ticker": "TEST",
                    "detected": True,
                    "case_id": None,
                    "candidate_id": "candidate_test",
                    "detected_at": "2026-08-24T14:05:00+00:00",
                    "detection_latency_minutes": 5.0,
                    "committee": {"disposition": "NO_TRADE", "confidence": 0.9},
                    "risk": {},
                    "paper_order": {},
                    "paper_fill": {},
                }
            ]
        }
        with tempfile.TemporaryDirectory() as tmp:
            db = self._db(Path(tmp))
            before = sqlite3.connect(db).execute("SELECT COUNT(*) FROM ledger_objects").fetchone()[0]
            result = build_session_outcome_memory(
                benchmark,
                scorecard,
                {"TEST": {"intraday": intraday, "daily": daily}},
                db,
                now=datetime(2026, 9, 1, tzinfo=timezone.utc),
            )
            after = sqlite3.connect(db).execute("SELECT COUNT(*) FROM ledger_objects").fetchone()[0]
        self.assertEqual(before, after)
        self.assertEqual(result["outcomes"][0]["decision_quality"], "NO_TRADE_FOREGONE_UPSIDE")
        self.assertTrue(result["outcomes"][0]["postmortem_ready"])
        self.assertFalse(result["outcomes"][0]["judgment_bank_auto_write"])
        memory = aggregate_outcome_memory([result])
        browser = build_browser_summary(memory)
        self.assertEqual(browser["outcome_count"], 1)
        self.assertEqual(browser["judgment_bank_review_queue_count"], 1)
        self.assertTrue(browser["safety"]["read_only_browser_payload"])
        self.assertFalse(browser["safety"]["auto_write_judgment_bank"])

    def test_incomplete_benchmark_fails_closed(self):
        result = build_session_outcome_memory(
            {"session_id": "2026-08-28", "benchmark_complete": False, "opportunities": []},
            {},
            {},
        )
        self.assertEqual(result["status"], "BENCHMARK_INCOMPLETE")
        self.assertEqual(result["outcomes"], [])
        self.assertFalse(result["safety"]["auto_write_judgment_bank"])

    def test_aggregate_agent_scorecard_never_changes_weights_automatically(self):
        memory = aggregate_outcome_memory(
            [
                {
                    "status": "OUTCOME_MEMORY_UPDATED",
                    "outcomes": [
                        {
                            "event_at": "2026-08-24T14:00:00+00:00",
                            "five_session_mature": True,
                            "decision_quality": "WATCH_VALIDATED_BY_UPSIDE",
                            "market_outcome": "STRONG_UPSIDE",
                            "agents": [
                                {
                                    "agent_key": "skeptic",
                                    "agent": "Skeptic",
                                    "confidence": 0.8,
                                    "alignment": "ALIGNED",
                                }
                            ],
                        }
                    ],
                    "judgment_bank_candidates": [],
                }
            ]
        )
        self.assertEqual(memory["agent_scorecards"][0]["alignment_rate_pct"], 100.0)
        self.assertFalse(memory["agent_scorecards"][0]["automatic_weight_change_authority"])
        self.assertTrue(memory["agent_scorecards"][0]["human_review_required"])


if __name__ == "__main__":
    unittest.main()
