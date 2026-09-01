#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import sqlite3
import tempfile
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "iios_nightly_market_reconstruction.py"
ACTIVATE = ROOT / "scripts" / "activate_batch10m7_nightly_market_reconstruction.py"
CONFIG = ROOT / "config" / "iios_batch10m7_nightly_market_reconstruction.json"

spec = importlib.util.spec_from_file_location("nightly", SCRIPT)
assert spec and spec.loader
nightly = importlib.util.module_from_spec(spec)
spec.loader.exec_module(nightly)


class Batch10M7Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = json.loads(CONFIG.read_text(encoding="utf-8"))

    def test_truth_contract_never_counts_backfill_as_live(self) -> None:
        truth = self.config["truth_contract"]
        self.assertEqual(truth["detection_mode"], "RETROSPECTIVE_BACKFILL")
        self.assertFalse(truth["counts_as_live_detection"])
        self.assertFalse(truth["eligible_for_9h_live_score"])
        self.assertEqual(truth["official_9h_score_impact"], "NONE")
        self.assertTrue(truth["association_is_not_causation"])

    def test_safety_contract_has_no_trading_or_routing_authority(self) -> None:
        safety = self.config["safety"]
        self.assertEqual(safety["ledger_mode"], "READ_ONLY")
        for key in ("ledger_write", "backend_8002_change", "production_model_routing_change", "provider_change_authority", "threshold_auto_change", "committee_change_authority", "risk_change_authority", "capital_authority", "broker_connected", "trade_execution_permission", "live_execution"):
            self.assertFalse(safety[key], key)

    def test_read_only_connection_refuses_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ledger.db"
            db = sqlite3.connect(path)
            db.execute("CREATE TABLE ledger_objects (object_type TEXT, payload_json TEXT, created_at TEXT, case_id TEXT)")
            db.commit(); db.close()
            ro = nightly.connect_ro(path)
            with self.assertRaises(sqlite3.OperationalError):
                ro.execute("INSERT INTO ledger_objects VALUES ('x','{}','x','x')")
            ro.close()

    def test_verified_universe_extraction_requires_large_governed_set(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ledger.db"
            db = sqlite3.connect(path)
            db.row_factory = sqlite3.Row
            db.execute("CREATE TABLE ledger_objects (object_type TEXT, payload_json TEXT, created_at TEXT, case_id TEXT)")
            symbols = [f"X{i:03d}" for i in range(519)]
            payload = {"verified_complete": True, "strict_membership": True, "symbols": symbols}
            db.execute("INSERT INTO ledger_objects VALUES (?,?,?,?)", ("production_index_universe_snapshot", json.dumps(payload), "2026-08-31T20:00:00+00:00", None))
            db.commit()
            found, meta = nightly.extract_verified_universe(db, 400, 700)
            self.assertEqual(len(found), 519)
            self.assertEqual(meta["status"], "VERIFIED_GOVERNED_UNIVERSE")
            db.close()

    def test_report_labels_retrospective_misses_without_9h_impact(self) -> None:
        cfg = dict(self.config)
        report = nightly.build_report(
            cfg,
            date(2026, 8, 31),
            {"status": "VERIFIED_GOVERNED_UNIVERSE", "count": 519},
            {"live_detected_tickers": ["AAA"], "live_detected_count": 1},
            {"coverage_pct": 99.0, "material_movers": [{"ticker": "AAA", "move_pct": 4.0}, {"ticker": "BBB", "move_pct": -6.0}], "material_mover_count": 2},
            {"status": "HISTORICAL_STACK_COMPLETE"},
        )
        self.assertEqual(report["status"], "BACKFILL_COMPLETE")
        self.assertEqual(report["comparison"]["missed_live_but_found_retrospectively"], ["BBB"])
        self.assertEqual(report["learning_contract"]["official_9h_score_impact"], "NONE")
        self.assertFalse(report["learning_contract"]["eligible_for_9h_live_detection_score"])

    def test_source_uses_isolated_historical_directories(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")
        self.assertIn('session_root / "historical-research"', text)
        self.assertIn('session_root / "historical-event-reconstruction"', text)
        self.assertIn('session_root / "historical-macro-regime"', text)
        self.assertIn('RETROSPECTIVE_BACKFILL_INPUT', text)
        self.assertNotIn('record_object(', text)
        self.assertNotIn('record_event(', text)
        self.assertNotIn('UPDATE ledger_objects', text)
        self.assertNotIn('INSERT INTO ledger_objects', text)

    def test_activation_uses_terminal_bridge_not_direct_python_launchd(self) -> None:
        text = ACTIVATE.read_text(encoding="utf-8")
        self.assertIn('"/usr/bin/open", "-gj", "-a", "Terminal"', text)
        self.assertIn('run-nightly-reconstruction.command', text)
        self.assertIn('worker.lock', text)
        self.assertIn('9a_9b_9e_9h_9i_touched', text)
        self.assertNotIn('ProgramArguments": [str(python)', text)

    def test_mover_parser_computes_session_return(self) -> None:
        text = "Date,Close\n2026-08-28,100\n2026-08-31,106\n"
        result = nightly.parse_daily_csv(text, "2026-08-31")
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result["move_pct"], 6.0, places=3)


if __name__ == "__main__":
    unittest.main()
