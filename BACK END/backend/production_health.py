"""Runtime-backed liveness and production readiness probes for IIOS."""
from __future__ import annotations

import hashlib, json, os, re, sqlite3, stat, subprocess, threading, time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

MAX_HEARTBEAT_AGE_SECONDS=180
MAX_PROJECTION_AGE_SECONDS=900
SUPERVISOR_LABEL="com.iios.expansion-wing-unattended-tuesday"
PUBLISHER_LABEL="com.iios.expansion-wing-projection-publisher"
ACTIVE_RELEASE_MANIFEST=Path.home()/"Library/Application Support/IIOS/Release/active-release.json"
AUTHORITY_FIELDS=("broker_authority","paper_order_authority","candidate_promotion_authority",
                  "ledger_write_authority","live_execution_authority")
HEX64=re.compile(r"[0-9a-f]{64}")

def _canonical(value:Any)->bytes:
    return (json.dumps(value,sort_keys=True,separators=(",",":"))+"\n").encode()

def _digest(value:Any)->str:
    clean=dict(value) if isinstance(value,dict) else value
    if isinstance(clean,dict): clean.pop("content_hash",None)
    return hashlib.sha256(_canonical(clean)).hexdigest()

def _utc(value:Any)->datetime:
    try: parsed=datetime.fromisoformat(str(value).replace("Z","+00:00"))
    except (TypeError,ValueError): raise RuntimeError("RUNTIME_TIMESTAMP_INVALID") from None
    if parsed.tzinfo is None or parsed.utcoffset()!=timezone.utc.utcoffset(parsed):
        raise RuntimeError("RUNTIME_TIMESTAMP_INVALID")
    return parsed

def live_probe()->dict[str,Any]:
    return {"status":"LIVE","pid":os.getpid(),"thread":threading.current_thread().name,
            "observed_at":datetime.now(timezone.utc).isoformat(),"probe_monotonic_ns":time.monotonic_ns()}

def _ledger_probe()->str:
    from ledger import DB_PATH
    if not DB_PATH.is_file(): raise RuntimeError("LEDGER_UNAVAILABLE")
    info=DB_PATH.stat(); connection=sqlite3.connect(f"file:{DB_PATH}?mode=ro",uri=True,timeout=2)
    try: row=connection.execute("SELECT 1").fetchone()
    finally: connection.close()
    if row!=(1,): raise RuntimeError("LEDGER_UNAVAILABLE")
    return hashlib.sha256(f"{info.st_dev}:{info.st_ino}:{info.st_size}:{info.st_mtime_ns}".encode()).hexdigest()

def _owner_json(path:Path)->dict[str,Any]:
    info=path.lstat()
    if (path.is_symlink() or not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid()
            or stat.S_IMODE(info.st_mode)!=0o600 or not 0<info.st_size<=1_048_576):
        raise RuntimeError("RUNTIME_ARTIFACT_UNSAFE")
    try: value=json.loads(path.read_bytes())
    except (OSError,json.JSONDecodeError,UnicodeDecodeError): raise RuntimeError("RUNTIME_ARTIFACT_INVALID") from None
    if not isinstance(value,dict): raise RuntimeError("RUNTIME_ARTIFACT_INVALID")
    return value

def _process_pid(label:str)->int:
    result=subprocess.run(("launchctl","print",f"gui/{os.getuid()}/{label}"),check=False,
                          capture_output=True,text=True,timeout=2)
    match=re.search(r"^\s*pid = (\d+)\s*$",result.stdout,re.MULTILINE)
    if result.returncode or not match: raise RuntimeError("RUNTIME_PROCESS_UNAVAILABLE")
    pid=int(match.group(1))
    try: os.kill(pid,0)
    except OSError: raise RuntimeError("RUNTIME_PROCESS_UNAVAILABLE") from None
    return pid

@dataclass(frozen=True)
class RuntimeReadinessEvidence:
    expected_release:str; supervisor_pid:int; publisher_pid:int
    supervisor_release:str; supervisor_manifest_hash:str
    executor_release:str; executor_manifest_hash:str
    selected_generation:str; plan_identity:str; executor_state_hash:str
    heartbeat_at:datetime; heartbeat_next_wake:datetime; heartbeat_release:str
    heartbeat_supervisor_manifest_hash:str; heartbeat_executor_manifest_hash:str
    heartbeat_generation:str; heartbeat_plan_identity:str; heartbeat_executor_state_hash:str
    heartbeat_projection_hash:str; heartbeat_projection_generation:str
    projection_at:datetime; projection_release:str; projection_hash:str; projection_generation:str
    ledger_identity:str; heartbeat_ledger_identity:str; authorities:dict[str,bool]

    def validate(self,*,now:datetime)->dict[str,str]:
        if now.tzinfo is None or now.utcoffset()!=timezone.utc.utcoffset(now):
            raise RuntimeError("READINESS_CLOCK_INVALID")
        checks={
            "release_binding":"READY" if all(value==self.expected_release for value in
                (self.supervisor_release,self.executor_release,self.heartbeat_release,self.projection_release)) else "UNAVAILABLE",
            "operational_supervisor":"READY" if self.supervisor_pid>0 else "UNAVAILABLE",
            "projection_publisher":"READY" if self.publisher_pid>0 else "UNAVAILABLE",
            "supervisor_heartbeat":"READY" if (0<=(now-self.heartbeat_at).total_seconds()<=MAX_HEARTBEAT_AGE_SECONDS
                and self.heartbeat_next_wake>=self.heartbeat_at
                and (self.heartbeat_next_wake-self.heartbeat_at).total_seconds()<=MAX_HEARTBEAT_AGE_SECONDS) else "UNAVAILABLE",
            "projection_freshness":"READY" if 0<=(now-self.projection_at).total_seconds()<=MAX_PROJECTION_AGE_SECONDS else "UNAVAILABLE",
        }
        hashes=(self.supervisor_manifest_hash,self.executor_manifest_hash,self.plan_identity,
                self.executor_state_hash,self.projection_hash,self.ledger_identity)
        checks["artifact_integrity"]="READY" if all(HEX64.fullmatch(value) for value in hashes) else "UNAVAILABLE"
        coherent=(self.heartbeat_supervisor_manifest_hash==self.supervisor_manifest_hash
            and self.heartbeat_executor_manifest_hash==self.executor_manifest_hash
            and self.heartbeat_generation==self.selected_generation
            and self.heartbeat_plan_identity==self.plan_identity
            and self.heartbeat_executor_state_hash==self.executor_state_hash
            and self.heartbeat_projection_hash==self.projection_hash
            and self.heartbeat_projection_generation==self.projection_generation
            and self.projection_generation==self.selected_generation
            and self.heartbeat_ledger_identity==self.ledger_identity)
        checks["runtime_reconciliation"]="READY" if coherent else "UNAVAILABLE"
        checks["authority_lock"]="READY" if (set(self.authorities)==set(AUTHORITY_FIELDS)
            and all(self.authorities[key] is False for key in AUTHORITY_FIELDS)) else "UNAVAILABLE"
        return checks

def _operational_runtime_probe(*,now:datetime,ledger_identity:str)->RuntimeReadinessEvidence:
    from expansion_wing.operational_market_executor import ExecutorStore,plan_identity
    from expansion_wing.operational_market_executor_installer import (INSTALL_ROOT as EXECUTOR_ROOT,
        SELECTOR_NAME,resolve_selected_state_root,validate_installed)
    from expansion_wing.projection_runtime import (MANIFEST_NAME as PROJECTION_MANIFEST_NAME,
        ProjectionStore,reviewed_projection_root)
    from expansion_wing.unattended_supervisor_installer import (INSTALL_ROOT as SUPERVISOR_ROOT,
        MANIFEST_NAME as SUPERVISOR_MANIFEST_NAME,validate_installed_root)
    from expansion_wing.unattended_tuesday_service import HEARTBEAT_NAME

    release=_owner_json(ACTIVE_RELEASE_MANIFEST)
    if (release.get("schema")!="iios-active-immutable-release-v1" or release.get("content_hash")!=_digest(release)
            or not re.fullmatch(r"[0-9a-f]{40}",str(release.get("git_commit")))):
        raise RuntimeError("EXPECTED_RELEASE_UNAVAILABLE")
    expected=release["git_commit"]
    supervisor_root=SUPERVISOR_ROOT; executor_root=EXECUTOR_ROOT; projection_root=reviewed_projection_root()
    supervisor_manifest=_owner_json(supervisor_root/SUPERVISOR_MANIFEST_NAME)
    validate_installed_root(expected_commit=expected,root=supervisor_root)
    executor_manifest=validate_installed(executor_root)
    selected=resolve_selected_state_root(executor_root); store=ExecutorStore(selected)
    rows,state=store.read_plan(),store.read(); selector=_owner_json(executor_root/SELECTOR_NAME)
    if (state.get("plan_identity")!=plan_identity(rows)
            or selector.get("selected_root")!=str(selected.relative_to(executor_root))
            or selector.get("plan_identity")!=state["plan_identity"]):
        raise RuntimeError("EXECUTOR_GENERATION_INCOHERENT")
    heartbeat=_owner_json(supervisor_root/HEARTBEAT_NAME)
    if heartbeat.get("schema")!="iios-unattended-supervisor-heartbeat-v1" or heartbeat.get("content_hash")!=_digest(heartbeat):
        raise RuntimeError("SUPERVISOR_HEARTBEAT_INVALID")
    _,projection_manifest=ProjectionStore(projection_root).read(now=now)
    projection_file=_owner_json(projection_root/PROJECTION_MANIFEST_NAME)
    if projection_manifest!=projection_file: raise RuntimeError("PROJECTION_MANIFEST_INVALID")
    return RuntimeReadinessEvidence(
        expected,_process_pid(SUPERVISOR_LABEL),_process_pid(PUBLISHER_LABEL),
        str(supervisor_manifest.get("installed_source_commit","")),str(supervisor_manifest.get("canonical_manifest_content_hash","")),
        str(executor_manifest.get("installed_source_commit","")),str(executor_manifest.get("content_hash","")),
        selected.name,state["plan_identity"],state["content_hash"],_utc(heartbeat.get("observed_at")),
        _utc(heartbeat.get("next_wake_at")),str(heartbeat.get("release_commit","")),
        str(heartbeat.get("supervisor_manifest_hash","")),str(heartbeat.get("executor_manifest_hash","")),
        str(heartbeat.get("selected_generation","")),str(heartbeat.get("plan_identity","")),
        str(heartbeat.get("executor_state_hash","")),str(heartbeat.get("projection_hash","")),
        str(heartbeat.get("projection_generation","")),_utc(projection_manifest["generated_at"]),
        str(projection_file.get("release_commit","")),
        str(projection_manifest["projection_sha256"]),str(projection_manifest["source_cycle_id"]),
        ledger_identity,str(heartbeat.get("ledger_identity","")),
        {"broker_authority":state.get("authority",{}).get("broker"),
         "paper_order_authority":state.get("authority",{}).get("paper_order"),
         "candidate_promotion_authority":state.get("authority",{}).get("automatic_promotion"),
         "ledger_write_authority":state.get("authority",{}).get("ledger_write"),
         "live_execution_authority":state.get("authority",{}).get("live_execution")})

def ready_probe(*,runtime_probe:Callable[...,RuntimeReadinessEvidence]=_operational_runtime_probe,
                now:datetime|None=None)->tuple[bool,dict[str,Any]]:
    import jesse_scheduler,monitoring_engine,opportunity_scheduler
    from production_safety_freeze import production_freeze_manifest
    observed=(now or datetime.now(timezone.utc)).astimezone(timezone.utc); checks={}; ledger_identity=""
    try: ledger_identity=_ledger_probe(); checks["ledger"]="READY"
    except (OSError,RuntimeError,sqlite3.Error): checks["ledger"]="UNAVAILABLE"
    for name,thread in {"monitoring_scheduler":monitoring_engine._scheduler_thread,
        "opportunity_scheduler":opportunity_scheduler._scheduler_thread,"jesse_scheduler":jesse_scheduler._thread}.items():
        checks[name]="READY" if thread is not None and thread.is_alive() else "UNAVAILABLE"
    try:
        safety=production_freeze_manifest(); safe=(safety.get("all_invariants_pass") is True
            and safety.get("current_matches_proven_envelope") is True
            and all(safety.get(key) is False for key in ("auto_trade_authority","paper_order_permission",
                                                          "trade_execution_permission","live_execution")))
        checks["backend_authority_lock"]="READY" if safe else "UNAVAILABLE"
    except (OSError,RuntimeError,ValueError,KeyError): checks["backend_authority_lock"]="UNAVAILABLE"
    try: checks.update(runtime_probe(now=observed,ledger_identity=ledger_identity).validate(now=observed))
    except (OSError,RuntimeError,ValueError,KeyError,TypeError):
        for name in ("release_binding","operational_supervisor","projection_publisher","supervisor_heartbeat",
                     "projection_freshness","artifact_integrity","runtime_reconciliation","authority_lock"):
            checks[name]="UNAVAILABLE"
    ready=all(value=="READY" for value in checks.values())
    return ready,{"status":"READY" if ready else "NOT_READY","checks":checks,"observed_at":observed.isoformat()}
