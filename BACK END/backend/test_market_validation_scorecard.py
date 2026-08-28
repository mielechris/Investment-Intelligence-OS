from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

import market_validation_scorecard as scorecard


class MarketValidationScorecardTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp.name) / "iios_ledger.db"
        self.db = sqlite3.connect(self.db_path)
        self.db.executescript(
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
            CREATE TABLE audit_events (
                event_id TEXT PRIMARY KEY,
                case_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                entity_id TEXT,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )
        self.session_start = "2026-08-28T16:00:00+00:00"
        self.session_end = "2026-08-28T23:00:00+00:00"

    def tearDown(self) -> None:
        self.db.close()
        self.temp.cleanup()

    def object(
        self,
        object_id: str,
        object_type: str,
        case_id: str,
        payload: dict,
        *,
        created_at: str,
    ) -> None:
        self.db.execute(
            """
            INSERT INTO ledger_objects
            (object_id, object_type, case_id, parent_id, topic, payload_json, created_at)
            VALUES (?, ?, ?, NULL, NULL, ?, ?)
            """,
            (
                object_id,
                object_type,
                case_id,
                json.dumps(payload),
                created_at,
            ),
        )
        self.db.commit()

    def counts(self) -> tuple[int, int]:
        return (
            int(
                self.db.execute(
                    "SELECT COUNT(*) FROM ledger_objects"
                ).fetchone()[0]
            ),
            int(
                self.db.execute(
                    "SELECT COUNT(*) FROM audit_events"
                ).fetchone()[0]
            ),
        )

    def seed(self) -> None:
        candidate_time = "2026-08-28T17:05:00+00:00"
        case_id = "case_AAA"

        self.object(
            "candidate_AAA",
            "opportunity_candidate",
            "opportunity_acquisition",
            {
                "opportunity_candidate_id": "candidate_AAA",
                "ticker": "AAA",
                "score": 92.0,
                "radar_rank_score": 95.0,
                "promoted_case_id": case_id,
                "promoted_at": "2026-08-28T17:06:00+00:00",
                "created_at": candidate_time,
            },
            created_at=candidate_time,
        )
        self.object(
            "candidate_BBB",
            "opportunity_candidate",
            "opportunity_acquisition",
            {
                "opportunity_candidate_id": "candidate_BBB",
                "ticker": "BBB",
                "score": 75.0,
                "radar_rank_score": 79.0,
                "created_at": "2026-08-28T19:00:00+00:00",
            },
            created_at="2026-08-28T19:00:00+00:00",
        )
        self.object(
            case_id,
            "case",
            case_id,
            {
                "case_id": case_id,
                "topic": "AAA opportunity review",
                "source_candidate_id": "candidate_AAA",
                "created_at": "2026-08-28T17:06:00+00:00",
            },
            created_at="2026-08-28T17:06:00+00:00",
        )
        for index, key in enumerate(
            (
                "policy",
                "macro",
                "fundamentals",
                "market_structure",
                "commodities",
                "geo_weather",
                "skeptic",
                "portfolio",
            )
        ):
            self.object(
                f"agent_{index}",
                "agent_result",
                case_id,
                {
                    "agent_result_id": f"agent_{index}",
                    "case_id": case_id,
                    "agent_key": key,
                    "created_at": "2026-08-28T17:07:00+00:00",
                },
                created_at="2026-08-28T17:07:00+00:00",
            )
        self.object(
            "committee_AAA",
            "committee_decision",
            case_id,
            {
                "decision_id": "committee_AAA",
                "case_id": case_id,
                "disposition": "BUY",
                "confidence": 0.86,
                "created_at": "2026-08-28T17:08:00+00:00",
            },
            created_at="2026-08-28T17:08:00+00:00",
        )
        self.object(
            "risk_AAA",
            "risk_authorization",
            case_id,
            {
                "risk_authorization_id": "risk_AAA",
                "case_id": case_id,
                "decision": "APPROVED",
                "triggered_rules": [],
                "created_at": "2026-08-28T17:09:00+00:00",
            },
            created_at="2026-08-28T17:09:00+00:00",
        )
        self.object(
            "execution_AAA",
            "governed_paper_execution",
            case_id,
            {
                "execution_id": "execution_AAA",
                "case_id": case_id,
                "status": "COMPLETE",
                "execution": "PAPER_ORDER_CREATED",
                "shares": 5,
                "entry_price": 100.0,
                "notional": 500.0,
                "created_at": "2026-08-28T17:10:00+00:00",
            },
            created_at="2026-08-28T17:10:00+00:00",
        )
        self.object(
            "fill_AAA",
            "paper_portfolio_transaction",
            "paper_portfolio",
            {
                "paper_portfolio_transaction_id": "fill_AAA",
                "source_execution_id": "execution_AAA",
                "source_case_id": case_id,
                "ticker": "AAA",
                "side": "BUY",
                "direction": "LONG",
                "quantity": 5,
                "price": 100.0,
                "notional": 500.0,
                "created_at": "2026-08-28T17:11:00+00:00",
                "paper_mode": True,
                "live_execution": False,
            },
            created_at="2026-08-28T17:11:00+00:00",
        )
        self.object(
            "paper_portfolio_default",
            "paper_portfolio_account",
            "paper_portfolio",
            {
                "starting_cash": 10000.0,
                "created_at": self.session_start,
            },
            created_at=self.session_start,
        )
        self.object(
            "snapshot_AAA",
            "paper_portfolio_snapshot",
            "paper_portfolio",
            {
                "paper_portfolio_snapshot_id": "snapshot_AAA",
                "starting_cash": 10000.0,
                "nav": 10050.0,
                "cash": 9500.0,
                "market_value": 550.0,
                "realized_pnl": 0.0,
                "unrealized_pnl": 50.0,
                "total_pnl": 50.0,
                "gross_exposure": 550.0,
                "position_count": 1,
                "transaction_count": 1,
                "positions": [],
                "created_at": "2026-08-28T20:00:00+00:00",
            },
            created_at="2026-08-28T20:00:00+00:00",
        )

    def test_scorecard_measures_detection_miss_order_and_fill(self) -> None:
        self.seed()
        benchmark = {
            "session_id": "2026-08-28",
            "session_start": self.session_start,
            "session_end": self.session_end,
            "benchmark_complete": True,
            "opportunities": [
                {
                    "opportunity_id": "market_AAA",
                    "ticker": "AAA",
                    "event_at": "2026-08-28T17:00:00+00:00",
                    "label": "AAA catalyst",
                    "move_pct": 8.0,
                    "importance": "HIGH",
                },
                {
                    "opportunity_id": "market_MISS",
                    "ticker": "MISS",
                    "event_at": "2026-08-28T18:00:00+00:00",
                    "label": "Missed opportunity",
                    "move_pct": -10.0,
                    "importance": "HIGH",
                },
            ],
        }

        before = self.counts()
        result = scorecard.build_market_validation_scorecard(
            benchmark,
            self.db_path,
        )
        after = self.counts()

        self.assertEqual(before, after)
        metrics = result["metrics"]
        self.assertEqual(metrics["opportunity_count"], 2)
        self.assertEqual(metrics["detected_count"], 1)
        self.assertEqual(metrics["missed_count"], 1)
        self.assertEqual(metrics["detection_rate_pct"], 50.0)
        self.assertEqual(metrics["opportunity_miss_rate_pct"], 50.0)
        self.assertEqual(metrics["promoted_count"], 1)
        self.assertEqual(metrics["committee_decision_count"], 1)
        self.assertEqual(metrics["risk_decision_count"], 1)
        self.assertEqual(metrics["paper_order_count"], 1)
        self.assertEqual(metrics["paper_fill_count"], 1)
        self.assertEqual(
            metrics["median_detection_latency_minutes"],
            5.0,
        )
        self.assertEqual(
            metrics["factory_candidate_ticker_count"],
            2,
        )
        self.assertEqual(
            metrics["unmatched_factory_candidate_ticker_count"],
            1,
        )
        self.assertEqual(metrics["false_positive_rate_pct"], 50.0)
        self.assertEqual(metrics["nav"], 10050.0)
        self.assertEqual(metrics["total_pnl"], 50.0)

        aaa = result["opportunities"][0]
        self.assertTrue(aaa["detected"])
        self.assertTrue(aaa["promoted"])
        self.assertEqual(
            aaa["paper_order"]["execution"],
            "PAPER_ORDER_CREATED",
        )
        self.assertEqual(
            aaa["paper_fill"]["fill_id"],
            "fill_AAA",
        )
        self.assertFalse(result["safety"]["live_execution"])

    def test_incomplete_benchmark_does_not_claim_false_positive_rate(
        self,
    ) -> None:
        self.seed()
        benchmark = {
            "session_id": "2026-08-28",
            "session_start": self.session_start,
            "session_end": self.session_end,
            "benchmark_complete": False,
            "opportunities": [
                {
                    "ticker": "AAA",
                    "event_at": "2026-08-28T17:00:00+00:00",
                }
            ],
        }
        result = scorecard.build_market_validation_scorecard(
            benchmark,
            self.db_path,
        )
        self.assertIsNone(
            result["metrics"]["false_positive_rate_pct"]
        )


if __name__ == "__main__":
    unittest.main()
