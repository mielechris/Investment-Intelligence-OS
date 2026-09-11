from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

import factory_telemetry as telemetry


class FactoryTelemetryTest(unittest.TestCase):
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
        self.created = "2026-08-28T16:00:00+00:00"

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
        created_at: str | None = None,
    ) -> None:
        timestamp = created_at or payload.get("created_at") or self.created
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
                timestamp,
            ),
        )
        self.db.commit()

    def event(
        self,
        event_id: str,
        case_id: str,
        event_type: str,
        entity_id: str,
        payload: dict,
        *,
        created_at: str | None = None,
    ) -> None:
        self.db.execute(
            """
            INSERT INTO audit_events
            (event_id, case_id, event_type, entity_id, payload_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                case_id,
                event_type,
                entity_id,
                json.dumps(payload),
                created_at or self.created,
            ),
        )
        self.db.commit()

    def seed(self) -> None:
        now = telemetry.utc_now()
        self.object(
            "paper_portfolio_default",
            "paper_portfolio_account",
            "paper_portfolio",
            {
                "starting_cash": 10000.0,
                "created_at": self.created,
            },
        )
        self.object(
            "snapshot_1",
            "paper_portfolio_snapshot",
            "paper_portfolio",
            {
                "paper_portfolio_snapshot_id": "snapshot_1",
                "starting_cash": 10000.0,
                "nav": 10125.0,
                "cash": 8125.0,
                "market_value": 2000.0,
                "realized_pnl": 0.0,
                "unrealized_pnl": 125.0,
                "total_pnl": 125.0,
                "gross_exposure": 2000.0,
                "position_count": 1,
                "transaction_count": 1,
                "positions": [
                    {
                        "ticker": "TEST",
                        "direction": "LONG",
                        "quantity": 10,
                        "average_cost": 187.5,
                        "mark_price": 200.0,
                        "market_value": 2000.0,
                        "unrealized_pnl": 125.0,
                        "unrealized_return_pct": 6.6667,
                    }
                ],
                "created_at": now,
            },
            created_at=now,
        )
        self.object(
            "radar_state",
            "high_speed_market_radar_state",
            "high_speed_market_radar",
            {
                "last_cycle_id": "radar_cycle_1",
                "last_cycle_completed_at": now,
                "governed_universe_count": 518,
                "screener_hit_count": 22,
                "grok_candidate_count": 8,
                "gemini_candidate_count": 4,
                "promotion_candidate_count": 3,
                "promoted_case_count": 1,
                "cycle_duration_seconds": 12.2,
                "created_at": now,
            },
            created_at=now,
        )
        self.object(
            "obs_state",
            "observation_operations_state",
            "observation_operations",
            {
                "last_cycle_completed_at": now,
                "cycle_minutes": 15,
                "created_at": now,
            },
            created_at=now,
        )
        self.object(
            "paper_state",
            "governed_paper_trading_state",
            "paper_trading_operations",
            {
                "cycle_completed_at": now,
                "created_at": now,
            },
            created_at=now,
        )
        candidate_id = "opportunity_1"
        case_id = "case_1"
        self.object(
            candidate_id,
            "opportunity_candidate",
            "opportunity_acquisition",
            {
                "opportunity_candidate_id": candidate_id,
                "ticker": "TEST",
                "score": 88.0,
                "radar_rank_score": 91.0,
                "priority": "HIGH",
                "promoted_case_id": case_id,
                "promoted_at": now,
                "created_at": self.created,
            },
        )
        self.object(
            case_id,
            "case",
            case_id,
            {
                "case_id": case_id,
                "topic": "Test Corp (TEST) opportunity review",
                "source_candidate_id": candidate_id,
                "created_at": now,
            },
            created_at=now,
        )
        for index, agent_key in enumerate(
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
                    "agent_key": agent_key,
                    "created_at": now,
                },
                created_at=now,
            )
        self.object(
            "decision_1",
            "committee_decision",
            case_id,
            {
                "decision_id": "decision_1",
                "case_id": case_id,
                "disposition": "WATCH",
                "confidence": 0.81,
                "created_at": now,
            },
            created_at=now,
        )
        self.object(
            "risk_1",
            "risk_authorization",
            case_id,
            {
                "risk_authorization_id": "risk_1",
                "case_id": case_id,
                "decision": "APPROVED",
                "triggered_rules": [],
                "created_at": now,
            },
            created_at=now,
        )
        self.object(
            "governed_paper_1",
            "governed_paper_execution",
            case_id,
            {
                "execution_id": "governed_paper_1",
                "case_id": case_id,
                "status": "COMPLETE",
                "execution": "PAPER_ORDER_CREATED",
                "shares": 10,
                "entry_price": 187.5,
                "notional": 1875.0,
                "created_at": now,
            },
            created_at=now,
        )
        self.event(
            "event_1",
            case_id,
            "GOVERNED_PAPER_ORDER_CREATED",
            "governed_paper_1",
            {
                "shares": 10,
                "entry_price": 187.5,
                "notional": 1875.0,
                "live_execution": False,
            },
            created_at=now,
        )

    def counts(self) -> tuple[int, int]:
        objects = self.db.execute(
            "SELECT COUNT(*) FROM ledger_objects"
        ).fetchone()[0]
        events = self.db.execute(
            "SELECT COUNT(*) FROM audit_events"
        ).fetchone()[0]
        return int(objects), int(events)

    def test_factory_telemetry_is_read_only_and_complete(self) -> None:
        self.seed()
        before = self.counts()
        snapshot = telemetry.build_factory_telemetry(self.db_path)
        after = self.counts()

        self.assertEqual(before, after)
        self.assertEqual(
            snapshot["source"]["mode"],
            "LOCAL_LEDGER_READ_ONLY",
        )
        self.assertTrue(snapshot["safety"]["telemetry_read_only"])
        self.assertFalse(snapshot["safety"]["live_execution"])
        self.assertEqual(
            snapshot["radar"]["governed_universe_count"],
            518,
        )
        self.assertEqual(
            snapshot["recent_promotions"][0]["ticker"],
            "TEST",
        )
        self.assertTrue(
            snapshot["recent_promotions"][0]["agents"][
                "eight_agent_complete"
            ]
        )
        self.assertEqual(
            snapshot["recent_promotions"][0]["committee"][
                "disposition"
            ],
            "WATCH",
        )
        self.assertEqual(
            snapshot["recent_promotions"][0]["risk"]["decision"],
            "APPROVED",
        )
        self.assertEqual(
            snapshot["recent_promotions"][0]["paper_execution"][
                "execution"
            ],
            "PAPER_ORDER_CREATED",
        )
        self.assertEqual(snapshot["paper_fund"]["nav"], 10125.0)
        self.assertEqual(snapshot["paper_fund"]["total_pnl"], 125.0)
        self.assertEqual(
            snapshot["recent_paper_orders"][0]["execution_id"],
            "governed_paper_1",
        )

    def test_fingerprint_ignores_clock_only_fields(self) -> None:
        self.seed()
        first = telemetry.build_factory_telemetry(self.db_path)
        second = telemetry.build_factory_telemetry(self.db_path)
        self.assertEqual(first["fingerprint"], second["fingerprint"])

    def test_missing_ledger_becomes_explicit_unavailable_state(self) -> None:
        missing = Path(self.temp.name) / "missing.db"
        with self.assertRaises(FileNotFoundError):
            telemetry.build_factory_telemetry(missing)

        fallback = telemetry.build_unavailable_telemetry(
            FileNotFoundError("missing")
        )
        self.assertEqual(
            fallback["health"]["state"],
            "TELEMETRY_UNAVAILABLE",
        )
        self.assertFalse(fallback["safety"]["live_execution"])


if __name__ == "__main__":
    unittest.main()
