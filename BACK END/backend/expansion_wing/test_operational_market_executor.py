from __future__ import annotations
import json, os, stat, tempfile, unittest
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from .operational_market_executor import *

class Boundary:
    def __init__(self): self.calls=[]; self.fail=None
    def validate(self): return None
    def request(self,row):
        self.calls.append(row["identity"])
        if self.fail: raise self.fail
        stamp=datetime.now(timezone.utc).isoformat(); payload={"company_facts":{"ticker":row["ticker"]}} if row["endpoint"]=="COMPANY_FACTS" else ({"snapshot":{"ticker":row["ticker"],"time":stamp,"price":1}} if row["endpoint"]=="MARKET_SNAPSHOT" else {"prices":[{"ticker":row["ticker"],"time":stamp,"price":1}]})
        return BoundaryResponse(200,"application/json",json.dumps(payload).encode(),1.0)
class Pre(Exception): transmitted=False
class Amb(Exception): transmitted=True

class OperationalExecutorTests(unittest.TestCase):
    def make(self,rows=None):
        td=tempfile.TemporaryDirectory(); root=Path(td.name)/"executor"; rows=rows or full_plan(); store=ExecutorStore(root); store.initialize(rows,rows[0]["plan"]); boundary=Boundary(); return td,store,boundary,OperationalMarketEvidenceCoordinator(store,rows,boundary),rows
    def gates(self): return {k:True for k in {"immutable_policy","executor","credential_presence","tls_trust","cost_contract","request_plan","state_store","receipt_store"}}
    def test_exact_full_plan(self):
        rows=full_plan(); self.assertEqual((len(rows),len({r['identity'] for r in rows}),sum(r['cost'] for r in rows)),(50,50,50))
        self.assertEqual(sum(r['window']=="OPENING" for r in rows),10); self.assertEqual(sum(r['window']=="INTRADAY" for r in rows),10); self.assertEqual(sum(r['window']=="CLOSING" for r in rows),10)
        self.assertEqual(sum(r['endpoint']=="COMPANY_FACTS" for r in rows),1); self.assertEqual(sum(r['variant']=="FUND_BASELINE" for r in rows),9)
    def test_september_9_plan_is_separate_date_bound_and_exact(self):
        old=full_plan(); rows=september_9_plan()
        self.assertEqual((len(rows),len({r['identity'] for r in rows}),sum(r['cost'] for r in rows)),(50,50,50))
        self.assertTrue(all(r['plan']==SEPTEMBER_9_PLAN and r['session_date']==SEPTEMBER_9_SESSION_DATE for r in rows))
        self.assertFalse({r['identity'] for r in old}&{r['identity'] for r in rows})
        self.assertEqual({r['window'] for r in rows},{'OPENING','BASELINE','INTRADAY','CLOSING'})
        self.assertTrue(all(r['retry'] is False for r in rows))
    def test_september_9_restart_duplicate_suppression_and_automatic_close(self):
        rows=september_9_plan(); td,store,b,c,_=self.make(rows); self.addCleanup(td.cleanup)
        c.preflight(self.gates()); c.release(50); zone=ZoneInfo('America/Los_Angeles')
        c.scheduled_tick(datetime(2026,9,9,6,30,tzinfo=zone)); before=len(b.calls)
        restarted=OperationalMarketEvidenceCoordinator(store,store.read_plan(),b)
        restarted.scheduled_tick(datetime(2026,9,9,6,30,tzinfo=zone))
        self.assertEqual(len(b.calls),before)
        restarted.scheduled_tick(datetime(2026,9,9,9,30,tzinfo=zone))
        self.assertEqual(restarted.scheduled_tick(datetime(2026,9,9,12,55,tzinfo=zone)),'SESSION_CLOSED')
        state=store.read(); self.assertEqual((state['completed'],state['confirmed_credits'],state['released_credits'],state['stage_a']),(50,50,0,'LOCKED'))
        self.assertEqual((len(b.calls),len(set(b.calls))),(50,50))
    def test_september_9_plan_rejects_other_dates_before_dispatch(self):
        rows=september_9_plan(); td,store,b,c,_=self.make(rows); self.addCleanup(td.cleanup); c.preflight(self.gates()); c.release(50)
        self.assertEqual(c.scheduled_tick(datetime(2026,9,8,6,30,tzinfo=ZoneInfo('America/Los_Angeles'))),'SESSION_FAILED_CLOSED')
        self.assertEqual(b.calls,[]); self.assertEqual(store.read()['released_credits'],0)
    def test_late_plan_has_no_opening_and_is_deterministic(self):
        now=datetime(2026,9,8,8,0,tzinfo=ZoneInfo("America/Los_Angeles")); a=partial_session_plan(now); b=partial_session_plan(now)
        self.assertEqual(a,b); self.assertNotIn("OPENING",{r['window'] for r in a}); self.assertEqual(len(a),31); self.assertEqual(plan_identity(a),plan_identity(b))
    def test_full_session_real_coordinator_restart_and_close(self):
        td,store,boundary,c,rows=self.make(); self.addCleanup(td.cleanup); self.assertEqual(c.preflight(self.gates()),"EXECUTOR_READY"); c.release(50)
        for r in rows[:25]: self.assertEqual(c.execute(r["identity"]),"CONFIRMED")
        recovered=OperationalMarketEvidenceCoordinator(store,rows,boundary)
        for r in rows[:25]: self.assertEqual(recovered.execute(r["identity"]),"DUPLICATE_SUPPRESSED")
        for r in rows[25:]: self.assertEqual(recovered.execute(r["identity"]),"CONFIRMED")
        self.assertEqual((len(boundary.calls),len(set(boundary.calls))),(50,50)); recovered.close(); s=store.read(); self.assertEqual((s["completed"],s["confirmed_credits"],s["released_credits"],s["phase"]),(50,50,0,"SESSION_CLOSED"))
        self.assertEqual(len(list((store.root/"receipts").iterdir())),50); self.assertEqual(len(list((store.root/"evidence").iterdir())),50)
    def test_compressed_clock_open_intraday_closing_and_automatic_close(self):
        td,store,b,c,rows=self.make(); self.addCleanup(td.cleanup); c.preflight(self.gates()); c.release(50); zone=ZoneInfo("America/Los_Angeles")
        for hour,minute in ((6,30),(9,30),(12,55)): c.scheduled_tick(datetime(2026,9,8,hour,minute,tzinfo=zone))
        self.assertEqual(c.scheduled_tick(datetime(2026,9,8,13,6,tzinfo=zone)),"SESSION_CLOSED")
        s=store.read(); self.assertEqual((s["completed"],s["released_credits"],s["stage_a"]),(50,0,"LOCKED"))
    def test_ambiguous_never_repeats_and_pretransmission_remains_unspent(self):
        td,store,b,c,rows=self.make(); self.addCleanup(td.cleanup); c.preflight(self.gates()); c.release(50)
        b.fail=Amb(); self.assertEqual(c.execute(rows[0]["identity"]),"AMBIGUOUS"); b.fail=None; self.assertEqual(c.execute(rows[0]["identity"]),"DUPLICATE_SUPPRESSED")
        s=store.read(); self.assertEqual((s["ambiguous_credits"],s["confirmed_credits"],s["released_credits"]),(1,0,0))
        self.assertEqual(c.execute(rows[1]["identity"]),"REQUEST_BLOCKED")
    def test_crash_recovery_marks_dispatched_ambiguous(self):
        td,store,b,c,rows=self.make(); self.addCleanup(td.cleanup); c.preflight(self.gates()); c.release(50); s=store.read(); s["requests"][rows[0]["identity"]]["lifecycle"]="DISPATCH_STARTED"; c._recount(s); c._write(s)
        self.assertEqual(c.recover()["requests"][rows[0]["identity"]]["lifecycle"],"AMBIGUOUS"); self.assertEqual(c.execute(rows[0]["identity"]),"DUPLICATE_SUPPRESSED")
    def test_gates_tamper_permissions_and_projection(self):
        td,store,b,c,rows=self.make(); self.addCleanup(td.cleanup); bad=self.gates(); bad["tls_trust"]=False; self.assertEqual(c.preflight(bad),"EXECUTOR_PREFLIGHT_FAILED_CLOSED")
        self.assertTrue(c.projection()["authority"]==LOCKED_AUTHORITY); store.state_path.chmod(0o644)
        with self.assertRaisesRegex(ValueError,"EXECUTOR_FILE_INVALID"): store.read()
    def test_terminal_errors_lock_and_zero_allowance(self):
        td,store,b,c,rows=self.make(); self.addCleanup(td.cleanup); c.preflight(self.gates()); c.release(50); c.close("EXECUTOR_UNAVAILABLE"); s=store.read(); self.assertEqual((s["released_credits"],s["stage_a"],s["stage_b"],s["stage_c"]),(0,"LOCKED","LOCKED","LOCKED"))
    def test_production_contract_is_fixed_and_inert(self):
        value=production_contract(); self.assertFalse(value["network_enabled_by_default"]); self.assertFalse(value["retry"]); self.assertEqual((value["host"],value["port"],value["auth_header"]),("api.financialdatasets.ai",443,"X-API-KEY")); self.assertFalse(any(value["authority"].values()))
    def test_canary_is_one_immutable_row_and_closes_allowance(self):
        rows=canary_plan(); self.assertEqual((len(rows),rows[0]["ticker"],rows[0]["path"],rows[0]["cost"]),(1,"SPY","/prices/snapshot",1))
        td,store,b,c,_=self.make(rows); self.addCleanup(td.cleanup); self.assertEqual(store.read_plan(),rows)
        c.preflight(self.gates()); c.release(1); self.assertEqual(c.execute(rows[0]["identity"]),"CONFIRMED")
        s=store.read(); self.assertEqual((s["phase"],s["released_credits"],s["completed"]),("CANARY_CONFIRMED",0,1))
    def test_post_transmission_schema_failure_is_ambiguous_and_locked(self):
        rows=canary_plan(); td,store,b,c,_=self.make(rows); self.addCleanup(td.cleanup); c.preflight(self.gates()); c.release(1)
        def bad(_): return BoundaryResponse(200,"application/json",b'{"data":[]}',1.0)
        b.request=bad; self.assertEqual(c.execute(rows[0]["identity"]),"AMBIGUOUS")
        s=store.read(); self.assertEqual((s["phase"],s["ambiguous_credits"],s["released_credits"],s["stage_a"]),("FAILED_CLOSED",1,0,"LOCKED"))
    def test_post_0930_adopts_canary_and_completes_without_duplicate(self):
        rows=canary_plan(); td,store,b,c,_=self.make(rows); self.addCleanup(td.cleanup); c.preflight(self.gates()); c.release(1)
        self.assertEqual(c.execute(rows[0]["identity"]),"CONFIRMED"); canary_calls=list(b.calls); now=datetime.now(ZoneInfo("America/Los_Angeles")).replace(hour=10,minute=0)
        state=c.migrate_canary_to_post_0930(now); self.assertEqual((state["planned"],state["completed"],state["adopted_canary_count"]),(20,1,1))
        migrated=store.read_plan(); self.assertEqual({r["window"] for r in migrated},{"INTRADAY","CLOSING"}); self.assertTrue(all(r["endpoint"]=="MARKET_SNAPSHOT" for r in migrated))
        self.assertTrue(store.adoption_path.is_file()); self.assertEqual(len(list((store.root/"receipts").iterdir())),1)
        c.release(19); self.assertIn("INTRADAY",c.scheduled_tick(now)); self.assertEqual(store.read()["completed"],10)
        restarted=OperationalMarketEvidenceCoordinator(store,store.read_plan(),b)
        for row in store.read_plan():
            if row["window"]=="INTRADAY": self.assertEqual(restarted.execute(row["identity"]),"DUPLICATE_SUPPRESSED")
        self.assertEqual(c.scheduled_tick(now.replace(hour=12,minute=55)),"SESSION_CLOSED")
        final=store.read(); self.assertEqual((final["completed"],final["confirmed_credits"],final["released_credits"]),(20,20,0))
        self.assertEqual((len(b.calls),len(set(b.calls))),(20,20)); self.assertEqual(b.calls.count(canary_calls[0]),1)
    def test_invalid_canary_receipt_cannot_migrate_or_change_plan(self):
        rows=canary_plan(); td,store,b,c,_=self.make(rows); self.addCleanup(td.cleanup); c.preflight(self.gates()); c.release(1); c.execute(rows[0]["identity"])
        receipt=store.root/"receipts"/(rows[0]["identity"]+".json"); value=json.loads(receipt.read_text()); value["ticker"]="NOPE"; receipt.write_text(json.dumps(value)); receipt.chmod(0o600)
        with self.assertRaisesRegex(ValueError,"CANARY_ADOPTION_REJECTED"): c.migrate_canary_to_post_0930(datetime.now(ZoneInfo("America/Los_Angeles")).replace(hour=10))
        self.assertEqual(store.read_plan(),rows); self.assertEqual(store.read()["classification"],CANARY_PLAN)

if __name__=="__main__": unittest.main()
