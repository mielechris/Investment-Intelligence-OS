from __future__ import annotations
import json, os, stat, tempfile, unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .unattended_tuesday import *
from . import unattended_tuesday_service as service

NOW=datetime(2026,9,7,23,0,tzinfo=timezone.utc)
APPROVAL="2026-09-07T22:59:00+00:00"
OWNER="OPAQUE_OWNER_APPROVAL_28"
COMMIT="b"*40
BINDING={"request_plan_identity":__import__('expansion_wing.provider_readiness',fromlist=['revised_plan_identity']).revised_plan_identity(),"cost_contract_hash":"c"*64}

def gates(value=True):
    return {k:value for k in {"code_identity","controller_integrity","monday_receipt","single_supervisor","protected_services","projection_integrity","paper_unchanged","authorities_locked","stage_bc_locked","plan_valid","calendar_clock","network_bounds","no_conflicting_policy","no_browser_authorization"}}

class PolicyContractTests(unittest.TestCase):
    def policy(self): return make_policy(owner_identity=OWNER,approval_timestamp=APPROVAL,command_time=NOW,installed_commit=COMMIT,authorized_commit=COMMIT,cost_binding=BINDING)
    def test_authorization_boundaries(self):
        for age in (0,1,1799,1800): validate_owner_authorization((NOW-timedelta(seconds=age)).isoformat(),command_time=NOW)
        cases=((NOW-timedelta(seconds=1801)).isoformat(),"OWNER_AUTHORIZATION_EXPIRED"),((NOW+timedelta(seconds=1)).isoformat(),"OWNER_AUTHORIZATION_FUTURE"),("bad","OWNER_AUTHORIZATION_TIMESTAMP_INVALID"),("2026-09-07T22:59:00","OWNER_AUTHORIZATION_TIMESTAMP_INVALID")
        for value,category in cases:
            with self.subTest(category=category),self.assertRaisesRegex(ValueError,category): validate_owner_authorization(value,command_time=NOW)
        with self.assertRaisesRegex(ValueError,"OWNER_AUTHORIZATION_MISSING"): validate_owner_authorization(None,command_time=NOW)
    def test_policy_is_one_day_immutable_and_bound(self):
        p=self.policy(); self.assertEqual(p["schema_version"],POLICY_SCHEMA); self.assertFalse(p["recurring"]); self.assertTrue(p["immutable"])
        self.assertEqual((p["session_date"],p["timezone"],p["approved_commit"]),(TARGET_DATE,TARGET_ZONE,COMMIT)); self.assertEqual(p["authority"],LOCKED_AUTHORITY)
        self.assertFalse(any((p["automatic_retry"],p["automatic_reload"],p["automatic_budget_expansion"],p["browser_invocation"])))
    def test_policy_tamper_and_wrong_binding_rejected(self):
        for field,value,category in (("approved_commit","0"*40,"POLICY_BINDING_INVALID"),("recurring",True,"POLICY_RECURRENCE_INVALID"),("content_hash","0"*64,"POLICY_HASH_INVALID")):
            p=self.policy(); p[field]=value
            with self.subTest(field=field),self.assertRaisesRegex(ValueError,category): validate_policy(p,installed_commit=COMMIT)
    def test_plan_has_exactly_fifty_bound_unique_identities(self):
        p=self.policy(); rows=request_plan(p["policy_identity"]); self.assertEqual(len(rows),50); self.assertEqual(len({x["request_identity"] for x in rows}),50)
        self.assertEqual({x["instrument"] for x in rows},{"MU","SPY","XLK","VNQ","TLT","GLD","UUP","IBIT","PFF","BIL"})
        self.assertEqual(sum(x["estimated_cost"] for x in rows),50); self.assertTrue(all(x["retry"] is False for x in rows))
        self.assertEqual(sum(x["endpoint"]=="COMPANY_FACTS" for x in rows),1)
    def test_store_permissions_duplicates_symlink_and_inventory(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)/"state"; root.mkdir(mode=0o700); store=PolicyStore(root); store.install(self.policy())
            self.assertEqual({x.name for x in root.iterdir()},FIXED_INVENTORY); self.assertTrue(all(stat.S_IMODE(x.stat().st_mode)==0o600 for x in root.iterdir()))
            with self.assertRaisesRegex(ValueError,"POLICY_DUPLICATE_OR_AMBIGUOUS"): store.install(self.policy())
            (root/"unknown").write_text("x")
            with self.assertRaisesRegex(ValueError,"POLICY_INVENTORY_INVALID"): store.validate_root()
        with tempfile.TemporaryDirectory() as td:
            real=Path(td)/"real"; real.mkdir(mode=0o700); link=Path(td)/"link"; link.symlink_to(real)
            with self.assertRaisesRegex(ValueError,"POLICY_ROOT_INVALID"): PolicyStore(link).validate_root()

class ScheduleAndSafetyTests(unittest.TestCase):
    def policy(self): return make_policy(owner_identity=OWNER,approval_timestamp=APPROVAL,command_time=NOW,installed_commit=COMMIT,authorized_commit=COMMIT,cost_binding=BINDING)
    def test_calendar_schedule_and_dst(self):
        zone=ZoneInfo(TARGET_ZONE)
        expected=(("05:54","WAIT"),("05:55","RECOVERY"),("06:00","PREFLIGHT"),("06:20","READINESS"),("06:30","OPEN_OR_INTRADAY"),("12:55","CLOSE_READY"),("13:00","CLOSE"),("13:06","SESSION_EXPIRED"))
        for hm,result in expected:
            h,m=map(int,hm.split(":")); self.assertEqual(classify_time(datetime(2026,9,8,h,m,tzinfo=zone)),result)
        self.assertEqual(classify_time(datetime(2026,9,7,6,0,tzinfo=zone)),"SESSION_INELIGIBLE")
        self.assertEqual(classify_time(datetime(2026,9,12,6,0,tzinfo=zone)),"SESSION_INELIGIBLE")
        with self.assertRaisesRegex(ValueError,"CLOCK_INVALID"): classify_time(datetime(2026,9,8,6,0))
    def test_strict_forward_phases_duplicate_and_backward_rejected(self):
        p=self.policy(); s=initial_state(p); s=transition(s,p,"TUESDAY_WAITING_FOR_PREFLIGHT"); s=transition(s,p,"TUESDAY_PREFLIGHT_RUNNING")
        with self.assertRaisesRegex(ValueError,"PHASE_TRANSITION_INVALID"): transition(s,p,"TUESDAY_WAITING_FOR_PREFLIGHT")
        with self.assertRaisesRegex(ValueError,"PHASE_TRANSITION_INVALID"): transition(s,p,"TUESDAY_PREFLIGHT_RUNNING")
    def test_cost_gate_and_all_preflight_gates(self):
        endpoints={x["endpoint"] for x in operational_request_plan()}; costs={x:1 for x in endpoints}
        self.assertEqual(preflight(gates(),costs=costs),(True,None)); self.assertEqual(preflight(gates(),costs=None),(False,"ENDPOINT_COST_UNKNOWN"))
        bad=gates(); bad["paper_unchanged"]=False; self.assertEqual(preflight(bad,costs=costs),(False,"PREFLIGHT_GATE_FAILED")); self.assertEqual(preflight(gates(),costs=costs,emergency_closed=True),(False,"EMERGENCY_MARKET_CLOSURE"))
    def test_end_to_end_stub_restart_no_double_charge_and_close(self):
        p=self.policy(); s=initial_state(p); s=transition(s,p,"TUESDAY_WAITING_FOR_PREFLIGHT"); s=transition(s,p,"TUESDAY_PREFLIGHT_RUNNING")
        endpoints={x["endpoint"] for x in operational_request_plan()}; session=OfflineSession(p,s); self.assertEqual(session.release_stage_a(gates(),{x:1 for x in endpoints}),"STAGE_A_RUNNING")
        rows=operational_request_plan(); first=rows[:23]; rest=rows[23:]
        for row in first: self.assertEqual(session.observe(row,lambda _:"CONFIRMED"),"CONFIRMED")
        recovered=OfflineSession(p,json.loads(json.dumps(session.state)),outbound_calls=session.outbound_calls)
        for row in first: self.assertEqual(recovered.observe(row,lambda _:"CONFIRMED"),"CACHED_ZERO_CREDIT")
        for row in rest: self.assertEqual(recovered.observe(row,lambda _:"CONFIRMED"),"CONFIRMED")
        self.assertEqual((recovered.outbound_calls,recovered.state["confirmed_credits"]),(50,50))
        recovered.state=transition(recovered.state,p,"TUESDAY_STAGE_A_COMPLETED"); recovered.state=transition(recovered.state,p,"TUESDAY_STAGE_A_LOCKED"); recovered.state=transition(recovered.state,p,"TUESDAY_SESSION_CLOSED")
        self.assertEqual(recovered.state["released_credits"],0); self.assertEqual(recovered.state["authority"],LOCKED_AUTHORITY)
    def test_ambiguous_is_charged_failed_is_not_retried_and_emergency_is_idempotent(self):
        p=self.policy(); s=initial_state(p); s=transition(s,p,"TUESDAY_WAITING_FOR_PREFLIGHT"); s=transition(s,p,"TUESDAY_PREFLIGHT_RUNNING")
        endpoints={x["endpoint"] for x in operational_request_plan()}; x=OfflineSession(p,s); x.release_stage_a(gates(),{k:1 for k in endpoints}); rows=operational_request_plan()
        self.assertEqual(x.observe(rows[0],lambda _:"AMBIGUOUS"),"AMBIGUOUS"); self.assertEqual(x.observe(rows[0],lambda _:"CONFIRMED"),"CACHED_ZERO_CREDIT"); self.assertEqual(x.state["ambiguous_credits"],1)
        self.assertEqual(x.emergency_stop(),"EMERGENCY_STOPPED"); self.assertEqual(x.emergency_stop(),"ALREADY_STOPPED"); self.assertEqual(x.observe(rows[1],lambda _:"CONFIRMED"),"REQUEST_BLOCKED"); self.assertEqual(x.state["released_credits"],0)
    def test_browser_projection_is_scalar_and_contains_no_private_identity(self):
        p=self.policy(); s=initial_state(p); v=browser_projection(p,s,read_at="2026-09-08T12:55:00+00:00")
        self.assertEqual((v["pilot_rooms"],v["readiness_rooms"],v["structural_rooms"]),(10,4,10)); self.assertTrue(v["authority_locked"])
        text=json.dumps(v); self.assertNotIn("request_identity",text); self.assertNotIn("content_hash",text); self.assertNotIn(OWNER,text)
    def test_no_network_keychain_broker_ledger_or_browser_surface(self):
        source=Path(__file__).with_name("unattended_tuesday.py").read_text()
        for token in ("X-API-KEY","security find-generic-password","requests.get(","urlopen(","broker.connect","ledger.write"):
            self.assertNotIn(token,source)
    def test_command_surface_rejects_browser_and_has_no_run_now(self):
        self.assertEqual(service.main(["--validate-policy","--browser"]),3)
        source=Path(service.__file__).read_text(); self.assertNotIn("--run-now",source); self.assertNotIn("--state-root",source)
    def test_exact_rollback_removal_and_byte_identical_restore(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)/"state"; backup=Path(td)/"rollback"; root.mkdir(mode=0o700)
            PolicyStore(root).install(self.policy())
            before={name:(root/name).read_bytes() for name in (POLICY_NAME,STATE_NAME,LKV_NAME)}
            self.assertEqual(service.remove_with_rollback(root=root,rollback=backup),"ONE_DAY_POLICY_REMOVED_ROLLBACK_READY")
            self.assertFalse(any((root/name).exists() for name in before))
            self.assertEqual(service.restore_from_rollback(root=root,rollback=backup),"ONE_DAY_POLICY_RESTORED_DISABLED")
            self.assertEqual(before,{name:(root/name).read_bytes() for name in before})
            with self.assertRaisesRegex(ValueError,"POLICY_DUPLICATE_OR_AMBIGUOUS"):
                service.restore_from_rollback(root=root,rollback=backup)
    def test_persistent_tick_fails_closed_at_unavailable_operational_binding(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)/"state"; root.mkdir(mode=0o700); PolicyStore(root).install(self.policy()); store=PolicyStore(root)
            self.assertEqual(service.tick(store,datetime(2026,9,8,5,55,tzinfo=ZoneInfo(TARGET_ZONE))),"TUESDAY_WAITING_FOR_PREFLIGHT")
            self.assertEqual(service.tick(store,datetime(2026,9,8,6,0,tzinfo=ZoneInfo(TARGET_ZONE))),"TUESDAY_PREFLIGHT_RUNNING")
            self.assertEqual(service.tick(store,datetime(2026,9,8,6,20,tzinfo=ZoneInfo(TARGET_ZONE))),"TUESDAY_PREFLIGHT_FAILED_CLOSED")
            _,state=service._read(store); self.assertEqual((state["failure_category"],state["released_credits"],state["completed"]),("OPERATIONAL_COST_BINDING_UNAVAILABLE",0,0))

if __name__=="__main__": unittest.main()
