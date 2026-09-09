"""Restart-safe operational market evidence execution.

Nothing in this module enables execution by default.  The production boundary
must be explicitly constructed by the unattended supervisor after an immutable
policy and every readiness gate have validated.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import stat
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol
from zoneinfo import ZoneInfo

from .financial_datasets import API_HOST, AUTH_HEADER, KEYCHAIN_ACCOUNT, KEYCHAIN_SERVICE, SecurityFrameworkCredentialProvider
from .tuesday_market_evidence import PILOT_INSTRUMENTS
from .tuesday_whole_factory import LOCKED_AUTHORITY
from .september_9_canonical_plan import (PLAN_CLASSIFICATION as CANONICAL_SEPTEMBER_9_PLAN,
    SESSION_DATE as CANONICAL_SEPTEMBER_9_DATE, canonical_plan_identity,
    corrected_september_9_plan, validate_canonical_plan)

SCHEMA = "iios-operational-market-executor-v1"
RECEIPT_SCHEMA = "iios-operational-market-evidence-receipt-v1"
PLAN_SCHEMA = "iios-operational-market-request-plan-v1"
FULL_PLAN = "FULL_SESSION_50"
LATE_PLAN = "PARTIAL_SESSION_LATE_START"
CANARY_PLAN = "SPY_SNAPSHOT_CANARY_1"
POST_0930_PLAN = "POST_0930_PARTIAL_SESSION"
SEPTEMBER_9_PLAN = CANONICAL_SEPTEMBER_9_PLAN
SEPTEMBER_9_SESSION_DATE = CANONICAL_SEPTEMBER_9_DATE
ADOPTION_SCHEMA = "iios-operational-market-canary-adoption-v1"
LIFECYCLES = {"PLANNED", "RESERVED", "DISPATCH_STARTED", "CONFIRMED", "AMBIGUOUS", "FAILED_PRETRANSMISSION"}
TERMINAL = {"CONFIRMED", "AMBIGUOUS", "FAILED_PRETRANSMISSION"}
PATHS = {"MARKET_SNAPSHOT": "/prices/snapshot", "HISTORICAL_OHLCV": "/prices", "COMPANY_FACTS": "/company/facts"}
WINDOWS = {"CANARY": ("00:00", "23:59"), "OPENING": ("06:30", "07:00"), "BASELINE": ("06:30", "09:30"),
           "INTRADAY": ("09:30", "12:55"), "CLOSING": ("12:55", "13:05")}
MAX_BODY = 2_000_000
PILOTS = tuple(row[0] for row in PILOT_INSTRUMENTS)

def _digest(value: Any) -> str:
    clean = dict(value) if isinstance(value, dict) else value
    if isinstance(clean, dict): clean.pop("content_hash", None)
    return hashlib.sha256((json.dumps(clean, sort_keys=True, separators=(",", ":")) + "\n").encode()).hexdigest()

def _identity(plan: str, window: str, endpoint: str, ticker: str) -> str:
    seed = f"2026-09-08|{plan}|{window}|{endpoint}|{ticker}|fd-operational-v1"
    return "market-evidence-" + hashlib.sha256(seed.encode()).hexdigest()

def _dated_identity(session_date: str, plan: str, window: str, endpoint: str, ticker: str) -> str:
    seed = f"{session_date}|{plan}|{window}|{endpoint}|{ticker}|fd-operational-v1"
    return "market-evidence-" + hashlib.sha256(seed.encode()).hexdigest()

def full_plan() -> tuple[dict[str, Any], ...]:
    rows: list[dict[str, Any]] = []
    for ticker in PILOTS:
        rows.append(_row(FULL_PLAN, "OPENING", "MARKET_SNAPSHOT", ticker))
        rows.append(_row(FULL_PLAN, "BASELINE", "HISTORICAL_OHLCV", ticker))
        rows.append(_row(FULL_PLAN, "INTRADAY", "MARKET_SNAPSHOT", ticker))
        rows.append(_row(FULL_PLAN, "CLOSING", "MARKET_SNAPSHOT", ticker))
    rows.append(_row(FULL_PLAN, "BASELINE", "COMPANY_FACTS", "MU"))
    for ticker in PILOTS:
        if ticker != "MU": rows.append(_row(FULL_PLAN, "BASELINE", "HISTORICAL_OHLCV", ticker, variant="FUND_BASELINE"))
    return tuple(rows)

def _row(plan: str, window: str, endpoint: str, ticker: str, *, variant: str = "STANDARD") -> dict[str, Any]:
    start, end = WINDOWS[window]
    return {"identity": _identity(plan, window, endpoint + ":" + variant, ticker), "plan": plan,
            "window": window, "endpoint": endpoint, "path": PATHS[endpoint], "ticker": ticker,
            "earliest": start, "latest": end, "cost": 1, "retry": False, "variant": variant}

def _dated_row(session_date: str, plan: str, window: str, endpoint: str, ticker: str, *, variant: str = "STANDARD") -> dict[str, Any]:
    start, end = WINDOWS[window]
    return {"identity": _dated_identity(session_date, plan, window, endpoint + ":" + variant, ticker),
            "plan": plan, "session_date": session_date, "window": window, "endpoint": endpoint,
            "path": PATHS[endpoint], "ticker": ticker, "earliest": start, "latest": end,
            "cost": 1, "retry": False, "variant": variant}

def september_9_plan() -> tuple[dict[str, Any], ...]:
    """The sole corrected, provider-bound September 9 operational plan."""
    return validate_canonical_plan(corrected_september_9_plan())

def partial_session_plan(now_local: datetime) -> tuple[dict[str, Any], ...]:
    if now_local.tzinfo is None or now_local.date().isoformat() != "2026-09-08": raise ValueError("LATE_START_CLOCK_INVALID")
    hm = now_local.strftime("%H:%M")
    rows = []
    # Missed opening evidence is never reconstructed.
    for ticker in PILOTS:
        if hm < WINDOWS["INTRADAY"][1]: rows.append(_row(LATE_PLAN, "INTRADAY", "MARKET_SNAPSHOT", ticker))
        if hm < WINDOWS["CLOSING"][1]: rows.append(_row(LATE_PLAN, "CLOSING", "MARKET_SNAPSHOT", ticker))
        if hm < WINDOWS["BASELINE"][1]: rows.append(_row(LATE_PLAN, "BASELINE", "HISTORICAL_OHLCV", ticker))
    if hm < WINDOWS["BASELINE"][1]: rows.append(_row(LATE_PLAN, "BASELINE", "COMPANY_FACTS", "MU"))
    return tuple(rows)

def canary_plan() -> tuple[dict[str, Any], ...]:
    """The only plan accepted by the separately owner-authorized canary command."""
    return (_row(CANARY_PLAN, "CANARY", "MARKET_SNAPSHOT", "SPY"),)

def post_0930_plan() -> tuple[dict[str, Any], ...]:
    rows=[]
    for ticker in PILOTS:
        rows.append(_row(POST_0930_PLAN,"INTRADAY","MARKET_SNAPSHOT",ticker))
        rows.append(_row(POST_0930_PLAN,"CLOSING","MARKET_SNAPSHOT",ticker))
    return tuple(rows)

def plan_identity(rows: tuple[dict[str, Any], ...]) -> str:
    if rows and rows[0].get("session_date") == SEPTEMBER_9_SESSION_DATE and rows[0].get("provider"):
        validate_canonical_plan(rows)
        return canonical_plan_identity(rows)
    return hashlib.sha256(json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

@dataclass(frozen=True)
class BoundaryResponse:
    status: int
    content_type: str
    body: bytes
    latency_ms: float
    transmitted: bool = True

class ProviderBoundary(Protocol):
    def validate(self) -> None: ...
    def request(self, row: dict[str, Any]) -> BoundaryResponse: ...

class FinancialDatasetsOperationalBoundary:
    """Credential bytes exist only for the duration of one exact header call."""
    def __init__(self, credentials: SecurityFrameworkCredentialProvider, transport: Any):
        self.credentials=credentials; self.transport=transport; self.credential_accesses=0
    def validate(self)->None:
        if self.credentials.adapter.service!=KEYCHAIN_SERVICE.encode("ascii") or self.transport.trust_readiness()!="READY": raise ValueError("OPERATIONAL_BOUNDARY_INVALID")
    def request(self,row:dict[str,Any])->BoundaryResponse:
        if row.get("path") not in PATHS.values() or row.get("cost")!=1: raise ValueError("ENDPOINT_NOT_ALLOWED")
        self.credential_accesses+=1; secret=self.credentials.retrieve()
        try:
            status,content_type,body,latency=self.transport.operational_request(path=row["path"],ticker=row["ticker"],credential=secret,
                start_date=row.get("start_date"),end_date=row.get("end_date"))
            return BoundaryResponse(status,content_type,body,latency,True)
        finally: secret=b""

class ExecutorStore:
    def __init__(self, root: Path): self.root = root
    @property
    def state_path(self) -> Path: return self.root / "executor-state.json"
    @property
    def lkv_path(self) -> Path: return self.root / "executor-state.last-known-valid.json"
    @property
    def plan_path(self) -> Path: return self.root / "request-plan.json"
    @property
    def adoption_path(self) -> Path: return self.root / "canary-adoption.json"
    def initialize(self, rows: tuple[dict[str, Any], ...], classification: str) -> dict[str, Any]:
        if self.root.exists(): raise ValueError("EXECUTOR_STORE_ALREADY_EXISTS")
        self.root.mkdir(mode=0o700, parents=False); (self.root / "receipts").mkdir(mode=0o700); (self.root / "evidence").mkdir(mode=0o700)
        plan={"schema_version":PLAN_SCHEMA,"classification":classification,"plan_identity":plan_identity(rows),
              "rows":list(rows),"content_hash":""}
        plan["content_hash"]=_digest(plan); _atomic(self.root,self.plan_path.name,plan)
        state = {"schema_version": SCHEMA, "generation": 1, "classification": classification,
                 "plan_identity": plan_identity(rows), "planned": len(rows), "dispatched": 0, "completed": 0,
                 "failed": 0, "ambiguous": 0, "confirmed_credits": 0, "ambiguous_credits": 0,
                 "released_credits": 0, "stage_a": "LOCKED", "stage_b": "LOCKED", "stage_c": "LOCKED",
                 "phase": "EXECUTOR_READY_DISABLED", "next_gate": "OWNER_CANARY_AUTHORIZATION",
                 "keychain_accesses":0,"requests": {r["identity"]: {"lifecycle": "PLANNED", "cost": 1} for r in rows},
                 "authority": LOCKED_AUTHORITY.copy(), "content_hash": ""}
        state["content_hash"] = _digest(state); self.write(state); return state
    def validate_root(self) -> None:
        info=self.root.lstat()
        if self.root.is_symlink() or not stat.S_ISDIR(info.st_mode) or stat.S_IMODE(info.st_mode)!=0o700 or info.st_uid!=os.getuid(): raise ValueError("EXECUTOR_ROOT_INVALID")
        allowed={"executor-state.json","executor-state.last-known-valid.json","request-plan.json","canary-adoption.json","executor.lock","receipts","evidence"}
        if {p.name for p in self.root.iterdir()}-allowed: raise ValueError("EXECUTOR_INVENTORY_INVALID")
        for dirname in ("receipts","evidence"):
            p=self.root/dirname; i=p.lstat()
            if p.is_symlink() or not stat.S_ISDIR(i.st_mode) or stat.S_IMODE(i.st_mode)!=0o700 or i.st_uid!=os.getuid(): raise ValueError("EXECUTOR_ROOT_INVALID")
    def lock(self):
        self.validate_root(); p=self.root/"executor.lock"; f=open(p,"a+"); os.chmod(p,0o600); fcntl.flock(f,fcntl.LOCK_EX); return f
    def read(self) -> dict[str, Any]:
        self.validate_root(); state=_read_json(self.state_path); lkv=_read_json(self.lkv_path)
        if state != lkv: raise ValueError("EXECUTOR_STATE_AMBIGUOUS")
        return validate_state(state)
    def read_plan(self) -> tuple[dict[str,Any],...]:
        value=_read_json(self.plan_path)
        if (value.get("schema_version")!=PLAN_SCHEMA or value.get("content_hash")!=_digest(value)
                or not isinstance(value.get("rows"),list)):
            raise ValueError("REQUEST_PLAN_INVALID")
        rows=tuple(value["rows"])
        if value.get("plan_identity")!=plan_identity(rows) or value.get("classification") not in {FULL_PLAN,LATE_PLAN,CANARY_PLAN,POST_0930_PLAN,SEPTEMBER_9_PLAN}:
            raise ValueError("REQUEST_PLAN_INVALID")
        return rows
    def write_plan(self,rows:tuple[dict[str,Any],...],classification:str)->None:
        value={"schema_version":PLAN_SCHEMA,"classification":classification,"plan_identity":plan_identity(rows),"rows":list(rows),"content_hash":""}
        value["content_hash"]=_digest(value); _atomic(self.root,self.plan_path.name,value)
    def write(self, state: dict[str, Any]) -> None:
        validate_state(state)
        _atomic(self.root, self.state_path.name, state); _atomic(self.root, self.lkv_path.name, state)
    def receipt(self, identity: str, receipt: dict[str, Any], raw: bytes) -> None:
        if not re.fullmatch(r"market-evidence-[0-9a-f]{64}", identity): raise ValueError("REQUEST_IDENTITY_INVALID")
        _atomic_bytes(self.root/"evidence", identity+".json", raw)
        _atomic(self.root/"receipts", identity+".json", receipt)

def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(_read_bytes(path))

def _read_bytes(path: Path) -> bytes:
    i=path.lstat()
    if path.is_symlink() or not stat.S_ISREG(i.st_mode) or stat.S_IMODE(i.st_mode)!=0o600 or i.st_uid!=os.getuid() or not 0<i.st_size<=MAX_BODY: raise ValueError("EXECUTOR_FILE_INVALID")
    return path.read_bytes()

def _atomic_bytes(root: Path, name: str, payload: bytes) -> None:
    if len(payload)>MAX_BODY: raise ValueError("RESPONSE_TOO_LARGE")
    temp=root/("."+name+".tmp"); fd=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    try: os.write(fd,payload); os.fsync(fd)
    finally: os.close(fd)
    os.replace(temp,root/name); d=os.open(root,os.O_RDONLY)
    try: os.fsync(d)
    finally: os.close(d)

def _atomic(root: Path, name: str, value: dict[str, Any]) -> None:
    _atomic_bytes(root,name,(json.dumps(value,sort_keys=True,separators=(",",":"))+"\n").encode())

def validate_state(s: Any) -> dict[str, Any]:
    if not isinstance(s,dict) or s.get("schema_version")!=SCHEMA or s.get("content_hash")!=_digest(s): raise ValueError("EXECUTOR_STATE_INVALID")
    if s.get("authority")!=LOCKED_AUTHORITY or any(s.get(k)!="LOCKED" for k in ("stage_b","stage_c")): raise ValueError("EXECUTOR_AUTHORITY_INVALID")
    if not isinstance(s.get("keychain_accesses"),int) or s["keychain_accesses"]<0: raise ValueError("EXECUTOR_ACCOUNTING_INVALID")
    req=s.get("requests")
    if not isinstance(req,dict) or len(req)!=s.get("planned") or any(v.get("lifecycle") not in LIFECYCLES for v in req.values()): raise ValueError("EXECUTOR_REQUEST_STATE_INVALID")
    confirmed=sum(v["lifecycle"]=="CONFIRMED" for v in req.values()); ambiguous=sum(v["lifecycle"]=="AMBIGUOUS" for v in req.values())
    dispatched=sum(v["lifecycle"] in {"DISPATCH_STARTED","CONFIRMED","AMBIGUOUS"} for v in req.values())
    if (s.get("completed")!=confirmed or s.get("ambiguous")!=ambiguous or s.get("dispatched")!=dispatched or
        s.get("confirmed_credits")!=confirmed or s.get("ambiguous_credits")!=ambiguous): raise ValueError("EXECUTOR_ACCOUNTING_INVALID")
    return s

class OperationalMarketEvidenceCoordinator:
    def __init__(self, store: ExecutorStore, rows: tuple[dict[str,Any],...], boundary: ProviderBoundary): self.store,self.rows,self.boundary=store,rows,boundary
    def preflight(self, gates: dict[str,bool]) -> str:
        required={"immutable_policy","executor","credential_presence","tls_trust","cost_contract","request_plan","state_store","receipt_store"}
        if set(gates)!=required or not all(gates.values()) or len(self.rows)>50 or any(r["cost"]!=1 for r in self.rows): return "EXECUTOR_PREFLIGHT_FAILED_CLOSED"
        self.boundary.validate(); s=self.store.read()
        if s["plan_identity"]!=plan_identity(self.rows) or self.store.read_plan()!=self.rows: raise ValueError("REQUEST_PLAN_MISMATCH")
        return "EXECUTOR_READY"
    def release(self, credits: int) -> None:
        s=self.store.read()
        allowed=s["phase"]=="EXECUTOR_READY_DISABLED" and credits==len(self.rows)
        allowed=allowed or (s["phase"]=="POST_0930_PARTIAL_READY" and credits==s["planned"]-s["completed"]-s["ambiguous"])
        if not allowed: raise ValueError("ALLOWANCE_RELEASE_REJECTED")
        s["released_credits"]=credits; s["stage_a"]="RUNNING"; s["phase"]="STAGE_A_RUNNING"; self._write(s)
    def migrate_canary_to_post_0930(self,now_local:datetime)->dict[str,Any]:
        if now_local.tzinfo is None or now_local.astimezone(ZoneInfo("America/Los_Angeles")).date().isoformat()!="2026-09-08": raise ValueError("POST_0930_CLOCK_INVALID")
        local=now_local.astimezone(ZoneInfo("America/Los_Angeles")); hm=local.strftime("%H:%M")
        if not WINDOWS["INTRADAY"][0]<=hm<WINDOWS["INTRADAY"][1]: raise ValueError("INTRADAY_WINDOW_CLOSED")
        lock=self.store.lock()
        try:
            s=self.store.read(); old_rows=self.store.read_plan()
            if s["classification"]!=CANARY_PLAN or old_rows!=canary_plan() or s["phase"]!="CANARY_CONFIRMED" or s["completed"]!=1 or s["confirmed_credits"]!=1 or s["ambiguous_credits"]!=0 or s["released_credits"]!=0: raise ValueError("CANARY_ADOPTION_REJECTED")
            old=old_rows[0]; old_id=old["identity"]; receipt=_read_json(self.store.root/"receipts"/(old_id+".json")); evidence=_read_bytes(self.store.root/"evidence"/(old_id+".json"))
            if (old["ticker"]!="SPY" or old["path"]!="/prices/snapshot" or receipt.get("ticker")!="SPY"
                    or receipt.get("endpoint")!="MARKET_SNAPSHOT" or receipt.get("credit_cost")!=1
                    or receipt.get("status")!="CONFIRMED" or receipt.get("content_hash")!=_digest(receipt)
                    or receipt.get("evidence_hash")!=hashlib.sha256(evidence).hexdigest()): raise ValueError("CANARY_ADOPTION_REJECTED")
            try: provider_time=datetime.fromisoformat(str(receipt["provider_timestamp"]).replace("Z","+00:00")).astimezone(ZoneInfo("America/Los_Angeles"))
            except (KeyError,ValueError): raise ValueError("CANARY_ADOPTION_REJECTED") from None
            if provider_time.date().isoformat()!="2026-09-08" or not WINDOWS["INTRADAY"][0]<=provider_time.strftime("%H:%M")<WINDOWS["INTRADAY"][1]: raise ValueError("CANARY_ADOPTION_REJECTED")
            rows=post_0930_plan(); adopted=next(r for r in rows if r["window"]=="INTRADAY" and r["ticker"]=="SPY")
            link={"schema_version":ADOPTION_SCHEMA,"source_identity":old_id,"adopted_identity":adopted["identity"],"provider":"FINANCIAL_DATASETS","session_date":"2026-09-08","ticker":"SPY","path":"/prices/snapshot","credit_cost":1,"evidence_hash":receipt["evidence_hash"],"receipt_hash":receipt["content_hash"],"content_hash":""}
            link["content_hash"]=_digest(link); _atomic(self.store.root,self.store.adoption_path.name,link)
            self.store.write_plan(rows,POST_0930_PLAN)
            requests={r["identity"]:{"lifecycle":"CONFIRMED" if r["identity"]==adopted["identity"] else "PLANNED","cost":1} for r in rows}
            s.update({"classification":POST_0930_PLAN,"plan_identity":plan_identity(rows),"planned":20,"requests":requests,"dispatched":1,"completed":1,"failed":0,"ambiguous":0,"confirmed_credits":1,"ambiguous_credits":0,"released_credits":0,"stage_a":"LOCKED","stage_b":"LOCKED","stage_c":"LOCKED","phase":"POST_0930_PARTIAL_READY","next_gate":"INTRADAY","adopted_canary_count":1,"failure_category":None})
            self.rows=rows; self._write(s); return s
        finally: fcntl.flock(lock,fcntl.LOCK_UN); lock.close()
    def recover(self) -> dict[str,Any]:
        s=self.store.read(); changed=False
        for identity,value in s["requests"].items():
            if value["lifecycle"]=="DISPATCH_STARTED":
                receipt=self.store.root/"receipts"/(identity+".json")
                if receipt.exists():
                    documented=_read_json(receipt)
                    if documented.get("schema_version")!=RECEIPT_SCHEMA or documented.get("request_identity")!=identity or documented.get("content_hash")!=_digest(documented): raise ValueError("RECEIPT_INVALID")
                    evidence=self.store.root/"evidence"/(identity+".json")
                    if hashlib.sha256(_read_bytes(evidence)).hexdigest()!=documented.get("evidence_hash"): raise ValueError("EVIDENCE_INVALID")
                    value["lifecycle"]="CONFIRMED"
                else: value["lifecycle"]="AMBIGUOUS"
                changed=True
            elif value["lifecycle"]=="RESERVED": value["lifecycle"]="PLANNED"; changed=True
        if changed: self._recount(s); self._write(s)
        return s
    def execute(self, identity: str) -> str:
        row=next((r for r in self.rows if r["identity"]==identity),None)
        if row is None: raise ValueError("REQUEST_IDENTITY_INVALID")
        lock=self.store.lock()
        try:
            s=self.recover(); life=s["requests"][identity]["lifecycle"]
            if life in TERMINAL: return "DUPLICATE_SUPPRESSED"
            if s["stage_a"]!="RUNNING" or s["released_credits"]<1: return "REQUEST_BLOCKED"
            s["requests"][identity]["lifecycle"]="RESERVED"; self._write(s)
            s["requests"][identity]["lifecycle"]="DISPATCH_STARTED"; self._recount(s); self._write(s)
            before=int(getattr(self.boundary,"credential_accesses",0))
            try: response=self.boundary.request(row)
            except Exception as exc:
                s=self.store.read(); s["keychain_accesses"]+=max(0,int(getattr(self.boundary,"credential_accesses",before))-before); transmitted=getattr(exc,"transmitted",getattr(exc,"request_started",True))
                s["requests"][identity]["lifecycle"]="AMBIGUOUS" if transmitted else "FAILED_PRETRANSMISSION"
                if not transmitted: s["failed"]+=1
                self._recount(s); self._terminalize(s,"PROVIDER_BOUNDARY_FAILED"); return s["requests"][identity]["lifecycle"]
            s=self.store.read(); s["keychain_accesses"]+=max(0,int(getattr(self.boundary,"credential_accesses",before))-before); self._write(s)
            try: clean=_validate_response(row,response)
            except Exception as exc:
                s=self.store.read(); s["requests"][identity]["lifecycle"]="AMBIGUOUS"
                self._recount(s); self._terminalize(s,_safe_category(exc,"PROVIDER_RESPONSE_REJECTED")); return "AMBIGUOUS"
            receipt={"schema_version":RECEIPT_SCHEMA,"request_identity":identity,"ticker":row["ticker"],"endpoint":row["endpoint"],
                     "window":row["window"],"status":"CONFIRMED","credit_cost":1,"observed_at":datetime.now(timezone.utc).isoformat(),
                     "response_bytes":len(response.body),"latency_ms":response.latency_ms,"evidence_hash":hashlib.sha256(response.body).hexdigest(),
                     "provider_timestamp":clean["provider_timestamp"],"freshness":clean["freshness"],
                     "normalized_hash":_digest(clean),"content_hash":""}
            receipt["content_hash"]=_digest(receipt); self.store.receipt(identity,receipt,response.body)
            s=self.store.read(); s["requests"][identity]["lifecycle"]="CONFIRMED"; self._recount(s)
            if s["classification"]==CANARY_PLAN: self._terminalize(s,None,phase="CANARY_CONFIRMED")
            else: self._write(s)
            return "CONFIRMED"
        finally: fcntl.flock(lock,fcntl.LOCK_UN); lock.close()
    def scheduled_tick(self, now_local: datetime) -> str:
        """Run only identities in the current immutable window; never releases allowance."""
        expected_date = SEPTEMBER_9_SESSION_DATE if self.rows and self.rows[0]["plan"]==SEPTEMBER_9_PLAN else "2026-09-08"
        if now_local.tzinfo is None or now_local.date().isoformat()!=expected_date:
            self.close("SESSION_TIME_INVALID"); return "SESSION_FAILED_CLOSED"
        hm=now_local.strftime("%H:%M")
        if hm>"13:05": self.close(); return "SESSION_CLOSED"
        windows=[name for name,(start,end) in WINDOWS.items() if start<=hm<end]
        if not windows: return "BOUNDED_WAIT"
        state=self.store.read()
        if state["stage_a"]!="RUNNING": return "STAGE_A_LOCKED"
        for row in self.rows:
            if row["window"] in windows: self.execute(row["identity"])
        current=self.store.read()
        if self.rows and self.rows[0]["plan"] in {POST_0930_PLAN,SEPTEMBER_9_PLAN} and "CLOSING" in windows and current["completed"]+current["ambiguous"]+current["failed"]==current["planned"]:
            self.close(); return "SESSION_CLOSED"
        final=windows[-1]; state=self.store.read(); state["next_gate"]={"OPENING":"INTRADAY","BASELINE":"INTRADAY","INTRADAY":"CLOSE_READINESS","CLOSING":"SESSION_CLOSE"}[final]; self._write(state)
        return "+".join(windows)+"_OBSERVED"
    def close(self, failure: str|None=None) -> None:
        s=self.store.read(); s["released_credits"]=0; s["stage_a"]="LOCKED"; s["stage_b"]="LOCKED"; s["stage_c"]="LOCKED"
        s["phase"]="SESSION_CLOSED" if failure is None else "SESSION_FAILED_CLOSED"; s["next_gate"]="NONE"; s["failure_category"]=failure; self._write(s)
    def projection(self) -> dict[str,Any]:
        s=self.store.read(); result={k:s[k] for k in ("schema_version","generation","classification","phase","next_gate","planned","dispatched","completed","failed","ambiguous","confirmed_credits","ambiguous_credits","released_credits","keychain_accesses","stage_a","stage_b","stage_c","authority")}
        result["remaining"]=s["planned"]-s["completed"]-s["ambiguous"]-s["failed"]; result["adopted_canary_count"]=s.get("adopted_canary_count",0); return result
    def _recount(self,s):
        vals=list(s["requests"].values()); s["dispatched"]=sum(v["lifecycle"] in {"DISPATCH_STARTED","CONFIRMED","AMBIGUOUS"} for v in vals); s["completed"]=sum(v["lifecycle"]=="CONFIRMED" for v in vals); s["ambiguous"]=sum(v["lifecycle"]=="AMBIGUOUS" for v in vals); s["confirmed_credits"]=s["completed"]; s["ambiguous_credits"]=s["ambiguous"]
    def _write(self,s): s["generation"]+=1; s["content_hash"]=_digest(s); self.store.write(s)
    def _terminalize(self,s,failure,*,phase="FAILED_CLOSED"):
        s["released_credits"]=0
        for key in ("stage_a","stage_b","stage_c"): s[key]="LOCKED"
        s["phase"]=phase; s["next_gate"]="NONE"; s["failure_category"]=failure; self._write(s)

def _safe_category(exc:Exception,default:str)->str:
    value=str(exc)
    return value if re.fullmatch(r"[A-Z][A-Z0-9_]{2,63}",value) else default

def _validate_response(row:dict[str,Any], response:BoundaryResponse)->dict[str,Any]:
    if not response.transmitted or response.status!=200 or response.content_type.split(";",1)[0].strip().lower()!="application/json" or not 0<len(response.body)<=MAX_BODY: raise ValueError("PROVIDER_RESPONSE_REJECTED")
    try: value=json.loads(response.body)
    except (UnicodeDecodeError,json.JSONDecodeError): raise ValueError("PROVIDER_SCHEMA_REJECTED") from None
    if not isinstance(value,dict): raise ValueError("PROVIDER_SCHEMA_REJECTED")
    if row["endpoint"]=="MARKET_SNAPSHOT": rows=[value.get("snapshot")]
    elif row["endpoint"]=="COMPANY_FACTS": rows=[value.get("company_facts")]
    else: rows=value.get("prices") or value.get("data")
    if not isinstance(rows,list) or not rows or not isinstance(rows[0],dict) or rows[0].get("ticker")!=row["ticker"]: raise ValueError("PROVIDER_SCHEMA_REJECTED")
    stamp=rows[0].get("time") or rows[0].get("timestamp")
    if row["endpoint"]!="COMPANY_FACTS" and not isinstance(stamp,str): raise ValueError("PROVIDER_TIMESTAMP_MISSING")
    if row["endpoint"]=="MARKET_SNAPSHOT" and (not isinstance(rows[0].get("price"),(int,float)) or isinstance(rows[0].get("price"),bool)):
        raise ValueError("PROVIDER_SCHEMA_REJECTED")
    freshness="UNAVAILABLE"
    if stamp is not None:
        try: parsed=datetime.fromisoformat(stamp.replace("Z","+00:00"))
        except ValueError: raise ValueError("PROVIDER_TIMESTAMP_INVALID") from None
        if parsed.tzinfo is None or parsed.utcoffset()!=timezone.utc.utcoffset(parsed): raise ValueError("PROVIDER_TIMESTAMP_INVALID")
        age=(datetime.now(timezone.utc)-parsed).total_seconds()
        if age < -60: raise ValueError("PROVIDER_TIMESTAMP_FUTURE")
        freshness="CURRENT" if age<=900 else "STALE"
    return {"ticker":row["ticker"],"provider_timestamp":stamp,"freshness":freshness,"field_count":len(rows[0])}

def production_contract() -> dict[str,Any]:
    """Static contract only; construction performs no Keychain or network access."""
    return {"provider":"FINANCIAL_DATASETS","host":API_HOST,"port":443,"auth_header":AUTH_HEADER,
            "keychain_service":KEYCHAIN_SERVICE,"keychain_account":KEYCHAIN_ACCOUNT,"paths":tuple(sorted(PATHS.values())),
            "network_enabled_by_default":False,"retry":False,"authority":LOCKED_AUTHORITY.copy()}
