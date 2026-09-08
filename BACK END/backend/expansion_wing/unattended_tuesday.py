"""Governed, one-day unattended Tuesday Stage A policy and offline engine.

There is deliberately no HTTP, Keychain, provider, broker, paper, ledger, or
projection adapter in this module. Production installation remains a separate
owner-authorized operation; clocks and provider stubs are injectable only into
the pure rehearsal engine.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import stat
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

from .tuesday_controller_v2 import STATE_SCHEMA_V2
from .tuesday_whole_factory import LOCKED_AUTHORITY, PILOT_BY_PRODUCT

POLICY_SCHEMA = "iios-unattended-market-session-policy-v1"
SESSION_SCHEMA = "iios-unattended-market-session-state-v1"
BROWSER_SCHEMA = "iios-unattended-market-session-browser-v1"
TARGET_DATE = "2026-09-08"
TARGET_ZONE = "America/Los_Angeles"
CALENDAR_ID = "IIOS_SOURCE_CONTROLLED_US_MARKET_CALENDAR_2026_09"
APPROVED_COMMIT = "a59187b64eb280b49861d83227d161f4b09b2b7b"
MAX_OWNER_APPROVAL_AGE_SECONDS = 1800
DAILY_CEILING = 200
STAGE_A_MAXIMUM = 100
PER_INSTRUMENT_MAXIMUM = 10
PER_ENDPOINT_MAXIMUM = 100
POLICY_NAME = "unattended-policy.json"
STATE_NAME = "unattended-session.json"
LKV_NAME = "unattended-session.last-known-valid.json"
LOCK_NAME = "unattended-session.lock"
FIXED_INVENTORY = frozenset({POLICY_NAME, STATE_NAME, LKV_NAME, LOCK_NAME})

PHASES = (
    "UNATTENDED_POLICY_NOT_INSTALLED", "TUESDAY_POLICY_INSTALLED_DISABLED",
    "TUESDAY_WAITING_FOR_PREFLIGHT", "TUESDAY_PREFLIGHT_RUNNING",
    "TUESDAY_PREFLIGHT_FAILED_CLOSED", "TUESDAY_READY_FOR_OPEN",
    "TUESDAY_STAGE_A_RUNNING", "TUESDAY_STAGE_A_PARTIAL",
    "TUESDAY_STAGE_A_COMPLETED", "TUESDAY_STAGE_A_LOCKED",
    "TUESDAY_SESSION_CLOSED", "TUESDAY_EMERGENCY_STOPPED",
)
ALLOWED_TRANSITIONS = {
    "TUESDAY_POLICY_INSTALLED_DISABLED": {"TUESDAY_WAITING_FOR_PREFLIGHT", "TUESDAY_EMERGENCY_STOPPED"},
    "TUESDAY_WAITING_FOR_PREFLIGHT": {"TUESDAY_PREFLIGHT_RUNNING", "TUESDAY_EMERGENCY_STOPPED"},
    "TUESDAY_PREFLIGHT_RUNNING": {"TUESDAY_PREFLIGHT_FAILED_CLOSED", "TUESDAY_READY_FOR_OPEN", "TUESDAY_EMERGENCY_STOPPED"},
    "TUESDAY_READY_FOR_OPEN": {"TUESDAY_STAGE_A_RUNNING", "TUESDAY_STAGE_A_PARTIAL", "TUESDAY_EMERGENCY_STOPPED"},
    "TUESDAY_STAGE_A_RUNNING": {"TUESDAY_STAGE_A_PARTIAL", "TUESDAY_STAGE_A_COMPLETED", "TUESDAY_EMERGENCY_STOPPED"},
    "TUESDAY_STAGE_A_PARTIAL": {"TUESDAY_STAGE_A_LOCKED", "TUESDAY_EMERGENCY_STOPPED"},
    "TUESDAY_STAGE_A_COMPLETED": {"TUESDAY_STAGE_A_LOCKED", "TUESDAY_EMERGENCY_STOPPED"},
    "TUESDAY_STAGE_A_LOCKED": {"TUESDAY_SESSION_CLOSED", "TUESDAY_EMERGENCY_STOPPED"},
    "TUESDAY_PREFLIGHT_FAILED_CLOSED": {"TUESDAY_SESSION_CLOSED", "TUESDAY_EMERGENCY_STOPPED"},
    "TUESDAY_EMERGENCY_STOPPED": {"TUESDAY_SESSION_CLOSED"},
}
SCHEDULE = {
    "RECOVERY": "05:55", "PREFLIGHT": "06:00", "READINESS": "06:20",
    "OPEN": "06:30", "INTRADAY": "09:30", "CLOSE_READY": "12:55", "CLOSE": "13:00",
}
POLICY_FIELDS = frozenset({
    "schema_version", "policy_identity", "session_date", "timezone", "calendar_identity",
    "controller_schema", "approved_commit", "request_plan_identity", "approved_instruments",
    "approved_endpoints", "not_before", "expires_at", "created_at", "owner_authorization_identity",
    "owner_authorization_timestamp", "recurring", "immutable", "stage_a_maximum", "daily_ceiling",
    "automatic_retry", "automatic_reload", "automatic_budget_expansion", "browser_invocation",
    "authority", "content_hash",
})


def _hash(value: Any) -> str:
    clean = dict(value) if isinstance(value, dict) else value
    if isinstance(clean, dict): clean.pop("content_hash", None)
    return hashlib.sha256((json.dumps(clean, sort_keys=True, separators=(",", ":")) + "\n").encode()).hexdigest()


def _utc(value: str, category: str) -> datetime:
    if not isinstance(value, str) or not value.endswith(("Z", "+00:00")):
        raise ValueError(category)
    try: parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc: raise ValueError(category) from exc
    if parsed.tzinfo != timezone.utc: raise ValueError(category)
    return parsed


def validate_owner_authorization(approval_timestamp: str | None, *, command_time: datetime) -> None:
    if approval_timestamp is None: raise ValueError("OWNER_AUTHORIZATION_MISSING")
    approval = _utc(approval_timestamp, "OWNER_AUTHORIZATION_TIMESTAMP_INVALID")
    if command_time.tzinfo != timezone.utc: raise ValueError("COMMAND_TIME_INVALID")
    age = (command_time - approval).total_seconds()
    if age < 0: raise ValueError("OWNER_AUTHORIZATION_FUTURE")
    if age > MAX_OWNER_APPROVAL_AGE_SECONDS: raise ValueError("OWNER_AUTHORIZATION_EXPIRED")


def request_plan(policy_identity: str) -> tuple[dict[str, Any], ...]:
    windows = (
        ("OPENING_SESSION", "MARKET_SNAPSHOT", "06:30", "07:00"),
        ("POINT_IN_TIME_OHLCV", "HISTORICAL_OHLCV", "06:30", "08:00"),
        ("APPLICABLE_FACTS", "COMPANY_FACTS_OR_INSTRUMENT_PROFILE", "07:00", "10:00"),
        ("INTRADAY_MARK", "MARKET_SNAPSHOT", "09:30", "10:30"),
        ("CLOSING_MARK", "MARKET_SNAPSHOT", "12:55", "13:05"),
    )
    rows = []
    for room, (instrument, _) in PILOT_BY_PRODUCT.items():
        for category, endpoint, earliest, latest in windows:
            applicable = "COMPANY_FACTS" if instrument == "MU" and category == "APPLICABLE_FACTS" else (
                "INSTRUMENT_PROFILE" if category == "APPLICABLE_FACTS" else endpoint)
            seed = "|".join((TARGET_DATE, instrument, applicable, category, earliest, policy_identity, "fd-contract-v1"))
            rows.append({"instrument": instrument, "product_room": room, "endpoint": applicable,
                         "evidence_category": category, "earliest": earliest, "latest": latest,
                         "estimated_cost": 1, "request_identity": "stage-a-" + hashlib.sha256(seed.encode()).hexdigest(),
                         "provider_contract": "fd-contract-v1", "retry": False})
    return tuple(rows)


def plan_identity(policy_identity: str) -> str:
    return _hash({"requests": request_plan(policy_identity)})


def make_policy(*, owner_identity: str, approval_timestamp: str, command_time: datetime,
                policy_identity: str = "tuesday-2026-09-08-stage-a") -> dict[str, Any]:
    validate_owner_authorization(approval_timestamp, command_time=command_time)
    if not isinstance(owner_identity, str) or not 8 <= len(owner_identity) <= 96: raise ValueError("OWNER_IDENTITY_INVALID")
    instruments = [x[0] for x in PILOT_BY_PRODUCT.values()]
    endpoints = sorted({x["endpoint"] for x in request_plan(policy_identity)})
    value = {
        "schema_version": POLICY_SCHEMA, "policy_identity": policy_identity, "session_date": TARGET_DATE,
        "timezone": TARGET_ZONE, "calendar_identity": CALENDAR_ID, "controller_schema": STATE_SCHEMA_V2,
        "approved_commit": APPROVED_COMMIT, "request_plan_identity": plan_identity(policy_identity),
        "approved_instruments": instruments, "approved_endpoints": endpoints,
        "not_before": "2026-09-08T05:55:00-07:00", "expires_at": "2026-09-08T13:05:00-07:00",
        "created_at": command_time.isoformat(), "owner_authorization_identity": owner_identity,
        "owner_authorization_timestamp": approval_timestamp, "recurring": False, "immutable": True,
        "stage_a_maximum": STAGE_A_MAXIMUM, "daily_ceiling": DAILY_CEILING, "automatic_retry": False,
        "automatic_reload": False, "automatic_budget_expansion": False, "browser_invocation": False,
        "authority": LOCKED_AUTHORITY.copy(),
    }
    value["content_hash"] = _hash(value)
    return validate_policy(value)


def validate_policy(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != POLICY_FIELDS or value.get("schema_version") != POLICY_SCHEMA:
        raise ValueError("POLICY_SCHEMA_INVALID")
    if value.get("session_date") != TARGET_DATE or value.get("timezone") != TARGET_ZONE or value.get("calendar_identity") != CALENDAR_ID:
        raise ValueError("POLICY_CALENDAR_INVALID")
    if value.get("not_before") != "2026-09-08T05:55:00-07:00" or value.get("expires_at") != "2026-09-08T13:05:00-07:00":
        raise ValueError("POLICY_WINDOW_INVALID")
    if value.get("controller_schema") != STATE_SCHEMA_V2 or value.get("approved_commit") != APPROVED_COMMIT:
        raise ValueError("POLICY_BINDING_INVALID")
    if not isinstance(value.get("policy_identity"),str) or not 8<=len(value["policy_identity"])<=96:
        raise ValueError("POLICY_IDENTITY_INVALID")
    if value.get("recurring") is not False or value.get("immutable") is not True:
        raise ValueError("POLICY_RECURRENCE_INVALID")
    if value.get("stage_a_maximum") != 100 or value.get("daily_ceiling") != 200:
        raise ValueError("POLICY_BUDGET_INVALID")
    if any(value.get(k) is not False for k in ("automatic_retry", "automatic_reload", "automatic_budget_expansion", "browser_invocation")):
        raise ValueError("POLICY_AUTOMATION_INVALID")
    if value.get("authority") != LOCKED_AUTHORITY: raise ValueError("POLICY_AUTHORITY_INVALID")
    if value.get("approved_instruments") != [x[0] for x in PILOT_BY_PRODUCT.values()]: raise ValueError("POLICY_INSTRUMENTS_INVALID")
    if value.get("approved_endpoints") != sorted({x["endpoint"] for x in request_plan(value["policy_identity"])}): raise ValueError("POLICY_ENDPOINTS_INVALID")
    if value.get("request_plan_identity") != plan_identity(value["policy_identity"]): raise ValueError("POLICY_PLAN_INVALID")
    if value.get("content_hash") != _hash(value): raise ValueError("POLICY_HASH_INVALID")
    created=_utc(value.get("created_at"), "POLICY_TIMESTAMP_INVALID")
    approval=_utc(value.get("owner_authorization_timestamp"), "POLICY_TIMESTAMP_INVALID")
    if not isinstance(value.get("owner_authorization_identity"),str) or not 8<=len(value["owner_authorization_identity"])<=96 or not 0<=(created-approval).total_seconds()<=MAX_OWNER_APPROVAL_AGE_SECONDS:
        raise ValueError("POLICY_AUTHORIZATION_INVALID")
    return value


def initial_state(policy: dict[str, Any]) -> dict[str, Any]:
    validate_policy(policy)
    value = {"schema_version": SESSION_SCHEMA, "policy_identity": policy["policy_identity"], "sequence": 1,
             "phase": "TUESDAY_POLICY_INSTALLED_DISABLED", "phase_history": ["TUESDAY_POLICY_INSTALLED_DISABLED"],
             "released_credits": 0, "planned": 50, "completed": 0, "failed": 0, "ambiguous": 0,
             "confirmed_credits": 0, "ambiguous_credits": 0, "completed_request_identities": [],
             "evidence_receipts": [], "preflight_status": "NOT_RUN", "failure_category": None,
             "emergency_stop": False, "authority_locked": True, "authority": LOCKED_AUTHORITY.copy()}
    value["content_hash"] = _hash(value); return validate_session(value, policy)


def validate_session(value: Any, policy: dict[str, Any]) -> dict[str, Any]:
    validate_policy(policy)
    required = {"schema_version","policy_identity","sequence","phase","phase_history","released_credits","planned",
                "completed","failed","ambiguous","confirmed_credits","ambiguous_credits","completed_request_identities",
                "evidence_receipts","preflight_status","failure_category","emergency_stop","authority_locked","authority","content_hash"}
    if not isinstance(value, dict) or set(value) != required or value.get("schema_version") != SESSION_SCHEMA: raise ValueError("SESSION_SCHEMA_INVALID")
    if value.get("policy_identity") != policy["policy_identity"] or value.get("phase") not in PHASES: raise ValueError("SESSION_BINDING_INVALID")
    h=value.get("phase_history");
    if not isinstance(h,list) or not h or h[-1] != value["phase"] or any(b not in ALLOWED_TRANSITIONS.get(a,set()) for a,b in zip(h,h[1:])): raise ValueError("PHASE_HISTORY_INVALID")
    ids=value.get("completed_request_identities")
    if not isinstance(ids,list) or len(ids)!=len(set(ids)) or any(x not in {r['request_identity'] for r in request_plan(policy['policy_identity'])} for x in ids): raise ValueError("REQUEST_IDENTITY_INVALID")
    for k in ("sequence","released_credits","planned","completed","failed","ambiguous","confirmed_credits","ambiguous_credits"):
        if not isinstance(value.get(k),int) or isinstance(value[k],bool) or value[k]<0: raise ValueError("ACCOUNTING_INVALID")
    active_allowance = value["released_credits"] if value["phase"] in {"TUESDAY_STAGE_A_RUNNING", "TUESDAY_STAGE_A_PARTIAL"} else STAGE_A_MAXIMUM
    if value["planned"] != 50 or value["completed"] != len(ids) or value["released_credits"] > 100 or value["confirmed_credits"]+value["ambiguous_credits"] > active_allowance: raise ValueError("ACCOUNTING_INVALID")
    if value.get("authority") != LOCKED_AUTHORITY or value.get("authority_locked") is not True: raise ValueError("AUTHORITY_INVALID")
    if value.get("content_hash") != _hash(value): raise ValueError("SESSION_HASH_INVALID")
    return value


def transition(state: dict[str, Any], policy: dict[str, Any], phase: str, *, failure: str | None = None) -> dict[str, Any]:
    validate_session(state, policy)
    if phase not in ALLOWED_TRANSITIONS.get(state["phase"], set()): raise ValueError("PHASE_TRANSITION_INVALID")
    result=json.loads(json.dumps(state)); result["phase"]=phase; result["phase_history"].append(phase); result["sequence"]+=1
    result["failure_category"]=failure
    if phase in {"TUESDAY_STAGE_A_LOCKED","TUESDAY_SESSION_CLOSED","TUESDAY_EMERGENCY_STOPPED","TUESDAY_PREFLIGHT_FAILED_CLOSED"}: result["released_credits"]=0
    if phase=="TUESDAY_EMERGENCY_STOPPED": result["emergency_stop"]=True
    result["content_hash"]=_hash(result); return validate_session(result,policy)


def classify_time(now: datetime) -> str:
    if now.tzinfo is None: raise ValueError("CLOCK_INVALID")
    local=now.astimezone(ZoneInfo(TARGET_ZONE))
    if local.date().isoformat()!=TARGET_DATE or local.weekday()!=1: return "SESSION_INELIGIBLE"
    hm=local.strftime("%H:%M")
    if hm<SCHEDULE["RECOVERY"]: return "WAIT"
    if hm<SCHEDULE["PREFLIGHT"]: return "RECOVERY"
    if hm<SCHEDULE["READINESS"]: return "PREFLIGHT"
    if hm<SCHEDULE["OPEN"]: return "READINESS"
    if hm<SCHEDULE["CLOSE_READY"]: return "OPEN_OR_INTRADAY"
    if hm<SCHEDULE["CLOSE"]: return "CLOSE_READY"
    if hm<="13:05": return "CLOSE"
    return "SESSION_EXPIRED"


def preflight(gates: dict[str,bool], *, costs: dict[str,int] | None, emergency_closed: bool=False) -> tuple[bool,str|None]:
    if emergency_closed: return False,"EMERGENCY_MARKET_CLOSURE"
    required={"code_identity","controller_integrity","monday_receipt","single_supervisor","protected_services",
              "projection_integrity","paper_unchanged","authorities_locked","stage_bc_locked","plan_valid",
              "calendar_clock","network_bounds","no_conflicting_policy","no_browser_authorization"}
    if set(gates)!=required or not all(gates.values()): return False,"PREFLIGHT_GATE_FAILED"
    endpoints={r["endpoint"] for r in request_plan("tuesday-2026-09-08-stage-a")}
    if costs is None or set(costs)!=endpoints or any(not isinstance(v,int) or isinstance(v,bool) or v<=0 for v in costs.values()): return False,"ENDPOINT_COST_UNKNOWN"
    projected=sum(costs[r["endpoint"]] for r in request_plan("tuesday-2026-09-08-stage-a"))
    return (projected<=STAGE_A_MAXIMUM, None if projected<=STAGE_A_MAXIMUM else "STAGE_A_COST_EXCEEDED")


@dataclass
class OfflineSession:
    policy: dict[str,Any]
    state: dict[str,Any]
    outbound_calls: int=0
    def release_stage_a(self, gates: dict[str,bool], costs: dict[str,int]|None) -> str:
        ok,why=preflight(gates,costs=costs)
        if not ok:
            self.state=transition(self.state,self.policy,"TUESDAY_PREFLIGHT_FAILED_CLOSED",failure=why); return why or "FAILED_CLOSED"
        self.state=transition(self.state,self.policy,"TUESDAY_READY_FOR_OPEN"); self.state=transition(self.state,self.policy,"TUESDAY_STAGE_A_RUNNING")
        self.state["released_credits"]=100; self.state["content_hash"]=_hash(self.state); validate_session(self.state,self.policy); return "STAGE_A_RUNNING"
    def observe(self,row:dict[str,Any], provider:Callable[[dict[str,Any]],str]) -> str:
        validate_session(self.state,self.policy)
        rid=row["request_identity"]
        if rid in self.state["completed_request_identities"]: return "CACHED_ZERO_CREDIT"
        if self.state["phase"] not in {"TUESDAY_STAGE_A_RUNNING","TUESDAY_STAGE_A_PARTIAL"} or self.state["emergency_stop"]: return "REQUEST_BLOCKED"
        cost=row["estimated_cost"]
        if self.state["confirmed_credits"]+self.state["ambiguous_credits"]+cost>self.state["released_credits"]: return "REQUEST_BLOCKED"
        self.outbound_calls+=1; result=provider(row)
        self.state["completed_request_identities"].append(rid); self.state["completed"]+=1
        if result=="CONFIRMED": self.state["confirmed_credits"]+=cost
        elif result=="AMBIGUOUS": self.state["ambiguous"]+=1; self.state["ambiguous_credits"]+=cost
        else: self.state["failed"]+=1
        self.state["evidence_receipts"].append({"category":result,"request_identity":rid,"cost":cost})
        self.state["sequence"]+=1; self.state["content_hash"]=_hash(self.state); validate_session(self.state,self.policy); return result
    def emergency_stop(self)->str:
        if self.state["phase"]=="TUESDAY_EMERGENCY_STOPPED": return "ALREADY_STOPPED"
        self.state=transition(self.state,self.policy,"TUESDAY_EMERGENCY_STOPPED",failure="OWNER_EMERGENCY_STOP"); return "EMERGENCY_STOPPED"


def browser_projection(policy: dict[str,Any]|None,state:dict[str,Any]|None,*,read_at:str) -> dict[str,Any]:
    if policy is None or state is None:
        return {"schema_version":BROWSER_SCHEMA,"policy_installed":False,"policy_status":"NOT_INSTALLED","session_date":TARGET_DATE,
                "phase":"UNATTENDED_POLICY_NOT_INSTALLED","next_gate":"OWNER_POLICY_INSTALLATION","preflight_status":"NOT_RUN",
                "stage_a_status":"LOCKED","stage_a_maximum":100,"released_credits":0,"planned":50,"completed":0,"failed":0,
                "ambiguous":0,"confirmed_credits":0,"ambiguous_credits":0,"pilot_rooms":10,"readiness_rooms":4,
                "structural_rooms":10,"market_session":"REGULAR_SESSION_PLANNED","failure_category":None,
                "authority_locked":True,"last_coherent_read_timestamp":read_at,"generation_sequence":0}
    validate_session(state,validate_policy(policy))
    return {"schema_version":BROWSER_SCHEMA,"policy_installed":True,"policy_status":"ONE_DAY_IMMUTABLE",
            "session_date":policy["session_date"],"phase":state["phase"],"next_gate":next_gate(state["phase"]),
            "preflight_status":state["preflight_status"],"stage_a_status":"RUNNING" if state["phase"]=="TUESDAY_STAGE_A_RUNNING" else "COMPLETE" if state["phase"] in {"TUESDAY_STAGE_A_COMPLETED","TUESDAY_STAGE_A_LOCKED","TUESDAY_SESSION_CLOSED"} else "LOCKED",
            "stage_a_maximum":100,"released_credits":state["released_credits"],"planned":50,"completed":state["completed"],
            "failed":state["failed"],"ambiguous":state["ambiguous"],"confirmed_credits":state["confirmed_credits"],
            "ambiguous_credits":state["ambiguous_credits"],"pilot_rooms":10,"readiness_rooms":4,"structural_rooms":10,
            "market_session":"REGULAR_SESSION","failure_category":state["failure_category"],"authority_locked":True,
            "last_coherent_read_timestamp":read_at,"generation_sequence":state["sequence"]}


def next_gate(phase:str)->str:
    return {"TUESDAY_POLICY_INSTALLED_DISABLED":"05:55 RECOVERY","TUESDAY_WAITING_FOR_PREFLIGHT":"06:00 PREFLIGHT",
            "TUESDAY_PREFLIGHT_RUNNING":"06:20 READINESS","TUESDAY_READY_FOR_OPEN":"06:30 STAGE A",
            "TUESDAY_STAGE_A_RUNNING":"12:55 CLOSE READINESS","TUESDAY_STAGE_A_PARTIAL":"13:00 CLOSE",
            "TUESDAY_STAGE_A_COMPLETED":"LOCK STAGE A","TUESDAY_STAGE_A_LOCKED":"CLOSE SESSION"}.get(phase,"NONE")


def _atomic(root:Path,name:str,value:dict[str,Any])->None:
    data=(json.dumps(value,sort_keys=True,separators=(",",":"))+"\n").encode(); tmp=root/(name+".tmp")
    fd=os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    try:
        with os.fdopen(fd,"wb",closefd=False) as f: f.write(data); f.flush(); os.fsync(f.fileno())
    finally: os.close(fd)
    os.replace(tmp,root/name); dfd=os.open(root,os.O_RDONLY); os.fsync(dfd); os.close(dfd)


class PolicyStore:
    def __init__(self,root:Path): self.root=root
    def validate_root(self)->None:
        s=self.root.lstat()
        if not stat.S_ISDIR(s.st_mode) or self.root.is_symlink() or stat.S_IMODE(s.st_mode)!=0o700 or s.st_uid!=os.getuid(): raise ValueError("POLICY_ROOT_INVALID")
        names={p.name for p in self.root.iterdir()}
        if not names<=FIXED_INVENTORY: raise ValueError("POLICY_INVENTORY_INVALID")
        for p in self.root.iterdir():
            x=p.lstat()
            if not stat.S_ISREG(x.st_mode) or p.is_symlink() or stat.S_IMODE(x.st_mode)!=0o600 or x.st_uid!=os.getuid() or x.st_size>1_000_000: raise ValueError("POLICY_FILE_INVALID")
    def lock(self):
        self.validate_root(); f=open(self.root/LOCK_NAME,"a+b"); os.chmod(self.root/LOCK_NAME,0o600)
        try: fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError: f.close(); raise ValueError("POLICY_LOCK_UNAVAILABLE")
        return f
    def install(self,policy:dict[str,Any])->None:
        validate_policy(policy); lock=self.lock()
        try:
            if (self.root/POLICY_NAME).exists(): raise ValueError("POLICY_DUPLICATE_OR_AMBIGUOUS")
            state=initial_state(policy); _atomic(self.root,POLICY_NAME,policy); _atomic(self.root,STATE_NAME,state); _atomic(self.root,LKV_NAME,state)
        finally: fcntl.flock(lock,fcntl.LOCK_UN); lock.close()
