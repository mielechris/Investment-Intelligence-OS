from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import factory_truth


class FactoryTruthTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp.name) / "iios_ledger.db"
        self.db = sqlite3.connect(self.db_path)
        self.db.executescript(
            """
            CREATE TABLE ledger_objects (object_id TEXT PRIMARY KEY, object_type TEXT NOT NULL, case_id TEXT NOT NULL, parent_id TEXT, topic TEXT, payload_json TEXT NOT NULL, created_at TEXT NOT NULL);
            CREATE TABLE audit_events (event_id TEXT PRIMARY KEY, case_id TEXT NOT NULL, event_type TEXT NOT NULL, entity_id TEXT, payload_json TEXT NOT NULL, created_at TEXT NOT NULL);
            """
        )
        self.now = datetime.now(timezone.utc)
        self._seed("high_speed_market_radar_state", "high_speed_market_radar", "last_cycle_completed_at")
        self._seed("observation_operations_state", "observation_operations", "last_cycle_completed_at")
        self._seed("governed_paper_trading_state", "paper_trading_operations", "cycle_completed_at")

    def tearDown(self) -> None:
        self.db.close()
        self.temp.cleanup()

    def _seed(self, object_type: str, case_id: str, time_key: str) -> None:
        timestamp = self.now.isoformat()
        payload = {time_key: timestamp, "created_at": timestamp, "cycle_minutes": 15,
                   "broker_connected": False, "trade_execution_permission": False, "live_execution": False}
        self.db.execute("INSERT INTO ledger_objects VALUES (?, ?, ?, NULL, NULL, ?, ?)", (object_type, object_type, case_id, json.dumps(payload), timestamp))
        self.db.commit()

    def _counts(self) -> tuple[int, int]:
        return tuple(int(self.db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]) for table in ("ledger_objects", "audit_events"))

    def test_contract_is_read_only_and_enforces_authority_locks(self) -> None:
        before = self._counts()
        truth = factory_truth.build_factory_truth(self.db_path, now=self.now)
        self.assertEqual(before, self._counts())
        self.assertEqual(truth["source"]["mode"], "FACTORY_TELEMETRY_V2_SQLITE_READ_ONLY")
        self.assertTrue(truth["live_authority_invariants"]["verified"])
        self.assertFalse(truth["live_authority_invariants"]["live_execution"])
        self.assertEqual(truth["checkpoints"]["9E"]["checkpoint_state"], "RECENT_CHECKPOINT")
        self.assertEqual(truth["runners"]["9B"]["state"], "RUNNER UNVERIFIED")

    def test_reports_mismatch_and_degraded_backend(self) -> None:
        truth = factory_truth.build_factory_truth(
            self.db_path,
            runtime_identity={"checkout": "/runtime", "ledger_path": str(self.db_path)},
            sidecar_identity={"checkout": "/sidecar", "ledger_path": "/other.db"},
            backend_probe=lambda: {"responsive": False, "detail": "timeout"},
            now=self.now + timedelta(minutes=30),
        )
        self.assertIn("BACKEND DEGRADED", truth["truth_states"])
        self.assertIn("EXTERNAL ARTIFACT", truth["truth_states"])
        self.assertIn("CHECKOUT_MISMATCH", truth["artifact"]["mismatches"])
        self.assertIn("SIDECAR_LEDGER_MISMATCH", truth["artifact"]["mismatches"])
        self.assertEqual(truth["checkpoints"]["9A"]["checkpoint_state"], "STALE_CHECKPOINT")


if __name__ == "__main__":
    unittest.main()