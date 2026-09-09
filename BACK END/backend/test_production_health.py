from __future__ import annotations

import sqlite3,sys,tempfile,threading,unittest
from dataclasses import replace
from datetime import datetime,timedelta,timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import production_health

NOW=datetime(2026,9,9,17,tzinfo=timezone.utc)
COMMIT="a"*40
DIGEST="b"*64
GENERATION="2026-09-09-shadow"

class AliveThread:
    def is_alive(self): return True

def evidence(**updates):
    value=production_health.RuntimeReadinessEvidence(
        COMMIT,11,12,COMMIT,DIGEST,COMMIT,DIGEST,GENERATION,DIGEST,DIGEST,
        NOW-timedelta(seconds=30),NOW+timedelta(seconds=30),COMMIT,DIGEST,DIGEST,
        GENERATION,DIGEST,DIGEST,DIGEST,GENERATION,NOW-timedelta(seconds=20),COMMIT,DIGEST,
        GENERATION,DIGEST,DIGEST,{key:False for key in production_health.AUTHORITY_FIELDS})
    return replace(value,**updates)

class ProductionHealthTests(unittest.TestCase):
    def modules(self,db:Path):
        safe={"all_invariants_pass":True,"current_matches_proven_envelope":True,
              "auto_trade_authority":False,"paper_order_permission":False,
              "trade_execution_permission":False,"live_execution":False}
        return {"ledger":SimpleNamespace(DB_PATH=db),"monitoring_engine":SimpleNamespace(_scheduler_thread=AliveThread()),
            "opportunity_scheduler":SimpleNamespace(_scheduler_thread=AliveThread()),
            "jesse_scheduler":SimpleNamespace(_thread=AliveThread()),
            "production_safety_freeze":SimpleNamespace(production_freeze_manifest=lambda:safe)}

    def probe(self,runtime):
        with tempfile.TemporaryDirectory() as raw:
            db=Path(raw)/"ledger.db"; connection=sqlite3.connect(db)
            connection.execute("CREATE TABLE probe (id INTEGER)"); connection.close()
            with patch.dict(sys.modules,self.modules(db)):
                return production_health.ready_probe(runtime_probe=lambda **_:runtime,now=NOW)

    def test_live_probe_uses_runtime_evidence(self):
        result=production_health.live_probe()
        self.assertEqual(result["status"],"LIVE"); self.assertGreater(result["pid"],0)
        self.assertEqual(result["thread"],threading.current_thread().name)

    def test_ready_probe_reconciles_all_runtime_evidence(self):
        ready,result=self.probe(evidence())
        self.assertTrue(ready); self.assertEqual(result["status"],"READY")
        self.assertTrue(all(value=="READY" for value in result["checks"].values()))

    def test_dead_supervisor_fails_closed(self):
        ready,result=self.probe(evidence(supervisor_pid=0))
        self.assertFalse(ready); self.assertEqual(result["checks"]["operational_supervisor"],"UNAVAILABLE")

    def test_stale_supervisor_heartbeat_fails_closed(self):
        ready,result=self.probe(evidence(heartbeat_at=NOW-timedelta(seconds=181)))
        self.assertFalse(ready); self.assertEqual(result["checks"]["supervisor_heartbeat"],"UNAVAILABLE")

    def test_wrong_release_manifest_fails_closed(self):
        ready,result=self.probe(evidence(executor_release="c"*40))
        self.assertFalse(ready); self.assertEqual(result["checks"]["release_binding"],"UNAVAILABLE")

    def test_corrupt_executor_state_root_fails_closed(self):
        ready,result=self.probe(evidence(executor_state_hash="INVALID"))
        self.assertFalse(ready); self.assertEqual(result["checks"]["artifact_integrity"],"UNAVAILABLE")

    def test_mismatched_selected_generation_fails_closed(self):
        ready,result=self.probe(evidence(heartbeat_generation="other-generation"))
        self.assertFalse(ready); self.assertEqual(result["checks"]["runtime_reconciliation"],"UNAVAILABLE")

    def test_dead_projection_publisher_fails_closed(self):
        ready,result=self.probe(evidence(publisher_pid=0))
        self.assertFalse(ready); self.assertEqual(result["checks"]["projection_publisher"],"UNAVAILABLE")

    def test_stale_projection_fails_closed(self):
        ready,result=self.probe(evidence(projection_at=NOW-timedelta(seconds=901)))
        self.assertFalse(ready); self.assertEqual(result["checks"]["projection_freshness"],"UNAVAILABLE")

    def test_projection_release_mismatch_fails_closed(self):
        ready,result=self.probe(evidence(projection_release="d"*40))
        self.assertFalse(ready); self.assertEqual(result["checks"]["release_binding"],"UNAVAILABLE")

    def test_authority_violation_fails_closed(self):
        unsafe={key:False for key in production_health.AUTHORITY_FIELDS}; unsafe["broker_authority"]=True
        ready,result=self.probe(evidence(authorities=unsafe))
        self.assertFalse(ready); self.assertEqual(result["checks"]["authority_lock"],"UNAVAILABLE")

    def test_runtime_probe_exception_fails_all_operational_checks(self):
        def broken(**_): raise RuntimeError("CORRUPT")
        with tempfile.TemporaryDirectory() as raw:
            db=Path(raw)/"ledger.db"; connection=sqlite3.connect(db); connection.execute("CREATE TABLE x (id INTEGER)"); connection.close()
            with patch.dict(sys.modules,self.modules(db)):
                ready,result=production_health.ready_probe(runtime_probe=broken,now=NOW)
        self.assertFalse(ready); self.assertEqual(result["checks"]["runtime_reconciliation"],"UNAVAILABLE")

    def test_app_exposes_distinct_live_and_ready_routes(self):
        source=(Path(__file__).parent/"app.py").read_text()
        self.assertIn('@app.get("/health/live")',source); self.assertIn('@app.get("/health/ready")',source)
        self.assertIn("status_code=503",source)

if __name__=="__main__": unittest.main()
