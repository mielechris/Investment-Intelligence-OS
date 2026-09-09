from __future__ import annotations

import tempfile
import threading
import unittest
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import production_health


class AliveThread:
    def is_alive(self):
        return True


class ProductionHealthTests(unittest.TestCase):
    def test_live_probe_uses_runtime_evidence(self):
        result = production_health.live_probe()
        self.assertEqual(result["status"], "LIVE")
        self.assertGreater(result["pid"], 0)
        self.assertEqual(result["thread"], threading.current_thread().name)
        self.assertIn("+00:00", result["observed_at"])

    def test_ready_probe_checks_ledger_threads_and_authority(self):
        with tempfile.TemporaryDirectory() as temporary:
            db = Path(temporary) / "ledger.db"
            import sqlite3
            connection = sqlite3.connect(db); connection.execute("CREATE TABLE probe (id INTEGER)"); connection.close()
            safe = {"all_invariants_pass": True, "current_matches_proven_envelope": True,
                "auto_trade_authority": False, "paper_order_permission": False,
                "trade_execution_permission": False, "live_execution": False}
            modules={"ledger":SimpleNamespace(DB_PATH=db),
                "monitoring_engine":SimpleNamespace(_scheduler_thread=AliveThread()),
                "opportunity_scheduler":SimpleNamespace(_scheduler_thread=AliveThread()),
                "jesse_scheduler":SimpleNamespace(_thread=AliveThread()),
                "production_safety_freeze":SimpleNamespace(production_freeze_manifest=lambda:safe)}
            with patch.dict(sys.modules,modules):
                ready, result = production_health.ready_probe()
        self.assertTrue(ready); self.assertEqual(result["status"], "READY")
        self.assertTrue(all(value == "READY" for value in result["checks"].values()))

    def test_ready_probe_fails_closed_for_dead_scheduler(self):
        safe={"all_invariants_pass":True,"current_matches_proven_envelope":True,
            "auto_trade_authority":False,"paper_order_permission":False,"trade_execution_permission":False,"live_execution":False}
        modules={"monitoring_engine":SimpleNamespace(_scheduler_thread=None),
            "opportunity_scheduler":SimpleNamespace(_scheduler_thread=AliveThread()),
            "jesse_scheduler":SimpleNamespace(_thread=AliveThread()),
            "production_safety_freeze":SimpleNamespace(production_freeze_manifest=lambda:safe)}
        with patch("production_health._ledger_probe",return_value="READY"),patch.dict(sys.modules,modules):
            ready, result = production_health.ready_probe()
        self.assertFalse(ready); self.assertEqual(result["status"], "NOT_READY")
        self.assertEqual(result["checks"]["monitoring_scheduler"], "UNAVAILABLE")

    def test_app_exposes_distinct_live_and_ready_routes(self):
        source=(Path(__file__).parent/"app.py").read_text()
        self.assertIn('@app.get("/health/live")',source)
        self.assertIn('@app.get("/health/ready")',source)
        self.assertIn("status_code=503",source)


if __name__ == "__main__":
    unittest.main()
