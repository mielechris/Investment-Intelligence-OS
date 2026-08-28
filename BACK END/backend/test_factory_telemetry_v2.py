from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

import factory_telemetry_v2 as telemetry


class FactoryTelemetryV2Test(unittest.TestCase):
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
        self.created = "2026-08-28T17:00:00+00:00"

    def tearDown(self) -> None:
        self.db.close()
        self.temp.cleanup()

    def object(
        self,
        object_id: str,
        object_type: str,
        case_id: str,
        payload: dict,
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
                payload.get("created_at") or self.created,
            ),
        )
        self.db.commit()

    def counts(self) -> tuple[int, int]:
        objects = int(
            self.db.execute(
                "SELECT COUNT(*) FROM ledger_objects"
            ).fetchone()[0]
        )
        events = int(
            self.db.execute(
                "SELECT COUNT(*) FROM audit_events"
            ).fetchone()[0]
        )
        return objects, events

    def test_surfaces_persisted_paper_fill_without_mutation(self) -> None:
        self.object(
            "fill_1",
            "paper_portfolio_transaction",
            "paper_portfolio",
            {
                "paper_portfolio_transaction_id": "fill_1",
                "source_execution_id": "execution_1",
                "source_case_id": "case_1",
                "ticker": "TEST",
                "side": "BUY",
                "direction": "LONG",
                "quantity": 5,
                "price": 100.0,
                "notional": 500.0,
                "created_at": self.created,
                "paper_mode": True,
                "live_execution": False,
            },
        )

        before = self.counts()
        snapshot = telemetry.build_factory_telemetry(self.db_path)
        after = self.counts()

        self.assertEqual(before, after)
        self.assertEqual(
            snapshot["source"]["mode"],
            "LOCAL_LEDGER_READ_ONLY",
        )
        self.assertEqual(
            snapshot["schema_version"],
            telemetry.SCHEMA_VERSION,
        )
        self.assertEqual(len(snapshot["recent_paper_fills"]), 1)
        fill = snapshot["recent_paper_fills"][0]
        self.assertEqual(fill["fill_id"], "fill_1")
        self.assertEqual(
            fill["source_execution_id"],
            "execution_1",
        )
        self.assertEqual(
            fill["fill_status"],
            "CONFIRMED_PAPER_FILL",
        )
        self.assertFalse(fill["live_execution"])
        self.assertTrue(snapshot["safety"]["telemetry_read_only"])
        self.assertFalse(snapshot["safety"]["live_execution"])

    def test_fill_changes_meaningful_fingerprint(self) -> None:
        first = telemetry.build_factory_telemetry(self.db_path)
        self.object(
            "fill_2",
            "paper_portfolio_transaction",
            "paper_portfolio",
            {
                "paper_portfolio_transaction_id": "fill_2",
                "source_execution_id": "execution_2",
                "source_case_id": "case_2",
                "ticker": "NEXT",
                "side": "BUY",
                "direction": "LONG",
                "quantity": 2,
                "price": 50.0,
                "notional": 100.0,
                "created_at": self.created,
                "paper_mode": True,
                "live_execution": False,
            },
        )
        second = telemetry.build_factory_telemetry(self.db_path)
        self.assertNotEqual(
            first["fingerprint"],
            second["fingerprint"],
        )


if __name__ == "__main__":
    unittest.main()
