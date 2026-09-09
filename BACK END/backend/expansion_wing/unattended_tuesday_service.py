"""Fixed-path, owner-local command surface for the one-day unattended policy.

The operational service remains uninstalled. This module has no provider adapter;
therefore its production supervisor cannot spend and fails closed at the cost gate.
"""
from __future__ import annotations
import argparse, fcntl, json, os, stat, time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .unattended_tuesday import (
    LKV_NAME, LOCK_NAME, POLICY_NAME, STATE_NAME, OfflineSession, PolicyStore, _atomic, _hash,
    browser_projection, classify_time, initial_state, make_policy, next_gate,
    transition, validate_policy, validate_session,
)
from .provider_readiness import operational_cost_binding

OPERATIONAL_ROOT = Path.home()/"Library/Application Support/IIOS/UnattendedTuesday"
SUPERVISOR_ROOT = Path.home()/"Library/Application Support/IIOS/UnattendedTuesdaySupervisor"
SUPERVISOR_LOCK_NAME = "unattended-supervisor.lock"
INCIDENT_NAME = "latest-incident.json"
HEARTBEAT_NAME = "supervisor-heartbeat.json"
ROLLBACK_ROOT = Path.home()/"Library/Application Support/IIOS/Rollback/UnattendedTuesday"
ROLLBACK_FILES = frozenset({POLICY_NAME, STATE_NAME, LKV_NAME})
INSTALLATION_MANIFEST = Path.home()/"Library/Application Support/IIOS/UnattendedTuesdaySupervisor/installation-manifest.json"
ACTIVE_RELEASE_MANIFEST = Path.home()/"Library/Application Support/IIOS/Release/active-release.json"

class SupervisorIncidentStore:
    """Bounded owner-only diagnostic state; never persists exception text."""
    def __init__(self,root:Path): self.root=root
    def record(self,exc:Exception,*,phase:str,observed_at:datetime)->None:
        if observed_at.tzinfo is None or observed_at.utcoffset()!=timezone.utc.utcoffset(observed_at):
            raise ValueError("INCIDENT_CLOCK_INVALID")
        if self.root.exists():
            info=self.root.lstat()
            if self.root.is_symlink() or not stat.S_ISDIR(info.st_mode) or stat.S_IMODE(info.st_mode)!=0o700 or info.st_uid!=os.getuid():
                raise ValueError("INCIDENT_ROOT_INVALID")
        else: self.root.mkdir(mode=0o700,parents=False)
        prior=0
        path=self.root/INCIDENT_NAME
        if path.exists():
            try:
                info=path.lstat()
                if path.is_symlink() or not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode)!=0o600 or info.st_uid!=os.getuid():
                    raise ValueError("INCIDENT_FILE_INVALID")
                value=json.loads(path.read_text()); supplied=value.get("content_hash")
                if value.get("schema")!="iios-unattended-supervisor-incident-v1" or supplied!=_hash(value):
                    raise ValueError("INCIDENT_FILE_INVALID")
                prior=int(value.get("sequence",0))
            except (OSError,json.JSONDecodeError): raise ValueError("INCIDENT_FILE_INVALID") from None
        category=str(exc)
        if not category.isupper() or len(category)>64: category="SUPERVISOR_OPERATION_FAILED_CLOSED"
        value={"schema":"iios-unattended-supervisor-incident-v1","sequence":prior+1,
            "observed_at":observed_at.astimezone(timezone.utc).isoformat(),"phase":phase,
            "failure_category":category,"exit_code":4,"content_hash":""}
        value["content_hash"]=_hash(value); _atomic(self.root,INCIDENT_NAME,value)

class SupervisorHeartbeatStore:
    """Atomic, hash-bound evidence from one completed supervisor cycle."""
    def __init__(self,root:Path): self.root=root
    def record(self,evidence:dict,*,observed_at:datetime,next_wake_at:datetime,pid:int|None=None)->dict:
        if (observed_at.tzinfo is None or observed_at.utcoffset()!=timezone.utc.utcoffset(observed_at)
                or next_wake_at.tzinfo is None or next_wake_at.utcoffset()!=timezone.utc.utcoffset(next_wake_at)
                or not observed_at<=next_wake_at<=observed_at+timedelta(seconds=180)):
            raise ValueError("HEARTBEAT_CLOCK_INVALID")
        required={"release_commit","supervisor_manifest_hash","executor_manifest_hash","selected_generation",
                  "plan_identity","executor_state_hash","projection_hash","projection_executor_generation",
                  "ledger_identity","ledger_path_contract_hash"}
        if set(evidence)!=required or any(not isinstance(evidence[key],str) or not evidence[key] for key in required):
            raise ValueError("HEARTBEAT_EVIDENCE_INVALID")
        value={"schema":"iios-unattended-supervisor-heartbeat-v2",**evidence,
            "observed_at":observed_at.isoformat(),"next_wake_at":next_wake_at.isoformat(),
            "pid":os.getpid() if pid is None else pid,"content_hash":""}
        value["content_hash"]=_hash(value); _atomic(self.root,HEARTBEAT_NAME,value); return value

def _production_heartbeat_evidence()->dict:
    """Read independent installed artifacts; never synthesizes a readiness boolean."""
    import hashlib
    from .operational_market_executor import ExecutorStore,plan_identity
    from .operational_market_executor_installer import INSTALL_ROOT as executor_root,resolve_selected_state_root,validate_installed
    from .projection_runtime import ProjectionStore,reviewed_projection_root
    from .unattended_supervisor_installer import INSTALL_ROOT as supervisor_root,MANIFEST_NAME,validate_installed_root
    import ledger
    supervisor_manifest=json.loads((supervisor_root/MANIFEST_NAME).read_text())
    release=supervisor_manifest["installed_source_commit"]
    validate_installed_root(expected_commit=release,root=supervisor_root)
    executor_manifest=validate_installed(executor_root)
    if executor_manifest.get("installed_source_commit")!=release: raise ValueError("RUNTIME_RELEASE_MISMATCH")
    selected=resolve_selected_state_root(executor_root); store=ExecutorStore(selected); rows,state=store.read_plan(),store.read()
    if state["plan_identity"]!=plan_identity(rows): raise ValueError("REQUEST_PLAN_MISMATCH")
    _,projection=ProjectionStore(reviewed_projection_root()).read()
    ledger_info=ledger.DB_PATH.lstat()
    if (ledger.DB_PATH.is_symlink() or not stat.S_ISREG(ledger_info.st_mode)
            or ledger_info.st_uid!=os.getuid() or stat.S_IMODE(ledger_info.st_mode)!=0o600):
        raise ValueError("RUNTIME_LEDGER_PATH_MISMATCH")
    ledger_identity=hashlib.sha256(f"{ledger_info.st_dev}:{ledger_info.st_ino}:{ledger_info.st_size}:{ledger_info.st_mtime_ns}".encode()).hexdigest()
    from deployment_contract import validate_active_release
    try: release_record=validate_active_release(ACTIVE_RELEASE_MANIFEST,configured_ledger=os.environ.get("IIOS_DB_PATH"))
    except (OSError,RuntimeError,ValueError,json.JSONDecodeError) as error:
        raise ValueError("RUNTIME_RELEASE_MISMATCH") from error
    ledger_path=Path(release_record["operational_ledger_path"])
    ledger_contract=release_record["ledger_path_contract_hash"]
    if release_record["git_commit"]!=release or ledger.DB_PATH.resolve()!=ledger_path.resolve():
        raise ValueError("RUNTIME_LEDGER_PATH_MISMATCH")
    if (projection.get("release_commit")!=release
            or projection.get("executor_generation")!=selected.name
            or projection.get("ledger_path_contract_hash")!=ledger_contract):
        raise ValueError("RUNTIME_PROJECTION_MISMATCH")
    return {"release_commit":release,"supervisor_manifest_hash":supervisor_manifest["canonical_manifest_content_hash"],
        "executor_manifest_hash":executor_manifest["content_hash"],"selected_generation":selected.name,
        "plan_identity":state["plan_identity"],"executor_state_hash":state["content_hash"],
        "projection_hash":projection["projection_sha256"],
        "projection_executor_generation":str(projection["executor_generation"]),
        "ledger_identity":ledger_identity,"ledger_path_contract_hash":ledger_contract}

def _installed_commit(path: Path = INSTALLATION_MANIFEST) -> str:
    info=path.lstat()
    if path.is_symlink() or not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode)!=0o600 or info.st_uid!=os.getuid():
        raise ValueError("POLICY_BINDING_INVALID")
    value=json.loads(path.read_text())
    if value.get("schema")=="iios-unattended-installation-v1" and set(value)=={"schema","installed_commit"}:
        commit=value["installed_commit"]
    elif value.get("schema")=="iios-unattended-supervisor-installation-v1":
        from .unattended_supervisor_installer import validate_manifest
        validate_manifest(value,path.parent/"installed-artifacts")
        commit=value["installed_source_commit"]
    else: raise ValueError("POLICY_BINDING_INVALID")
    if not isinstance(commit,str) or len(commit)!=40 or any(c not in "0123456789abcdef" for c in commit): raise ValueError("POLICY_BINDING_INVALID")
    return commit

def _read(store:PolicyStore):
    store.validate_root()
    policy=json.loads((store.root/POLICY_NAME).read_text()); state=json.loads((store.root/STATE_NAME).read_text())
    return validate_policy(policy),validate_session(state,policy)

def _write_state(store:PolicyStore,state,policy):
    validate_session(state,policy); _atomic(store.root,STATE_NAME,state); _atomic(store.root,LKV_NAME,state)

def install(owner:str,approval:str,authorized_commit:str,*,command_time:datetime|None=None,root:Path|None=None,
            manifest:Path|None=None,readiness_root:Path|None=None)->str:
    # Production never accepts an injected time or path from argv/environment.
    now=datetime.now(timezone.utc) if command_time is None else command_time
    installed=_installed_commit(INSTALLATION_MANIFEST if manifest is None else manifest)
    if authorized_commit != installed: raise ValueError("POLICY_BINDING_INVALID")
    binding=operational_cost_binding(now=now, **({} if readiness_root is None else {"root":readiness_root}))
    policy=make_policy(owner_identity=owner,approval_timestamp=approval,command_time=now,
        installed_commit=installed,authorized_commit=authorized_commit,cost_binding=binding)
    target=OPERATIONAL_ROOT if root is None else root
    if not target.exists(): target.mkdir(mode=0o700,parents=False)
    PolicyStore(target).install(policy); return "ONE_DAY_POLICY_INSTALLED_DISABLED"

def validate_installed(*,root:Path|None=None)->str:
    _read(PolicyStore(OPERATIONAL_ROOT if root is None else root)); return "POLICY_VALID"

def emergency_stop(*,root:Path|None=None)->str:
    store=PolicyStore(OPERATIONAL_ROOT if root is None else root); lock=store.lock()
    try:
        policy,state=_read(store)
        if state["phase"]=="TUESDAY_EMERGENCY_STOPPED": return "ALREADY_STOPPED"
        stopped=transition(state,policy,"TUESDAY_EMERGENCY_STOPPED",failure="OWNER_EMERGENCY_STOP")
        _write_state(store,stopped,policy); return "EMERGENCY_STOPPED"
    finally: fcntl.flock(lock,fcntl.LOCK_UN); lock.close()

def _validate_rollback(root:Path,policy:dict|None=None)->tuple[dict,dict,dict]:
    if root.is_symlink() or not root.is_dir() or stat.S_IMODE(root.stat().st_mode)!=0o700:
        raise ValueError("ROLLBACK_ROOT_INVALID")
    if {item.name for item in root.iterdir()} != ROLLBACK_FILES:
        raise ValueError("ROLLBACK_INVENTORY_INVALID")
    values=[]
    for name in (POLICY_NAME,STATE_NAME,LKV_NAME):
        path=root/name; info=path.lstat()
        if not stat.S_ISREG(info.st_mode) or path.is_symlink() or stat.S_IMODE(info.st_mode)!=0o600:
            raise ValueError("ROLLBACK_FILE_INVALID")
        values.append(json.loads(path.read_text()))
    restored_policy=validate_policy(values[0]); restored_state=validate_session(values[1],restored_policy)
    restored_lkv=validate_session(values[2],restored_policy)
    if restored_state != restored_lkv: raise ValueError("ROLLBACK_STATE_AMBIGUOUS")
    if policy is not None and restored_policy != policy: raise ValueError("ROLLBACK_POLICY_MISMATCH")
    return restored_policy,restored_state,restored_lkv

def remove_with_rollback(*,root:Path|None=None,rollback:Path|None=None)->str:
    target=OPERATIONAL_ROOT if root is None else root; backup=ROLLBACK_ROOT if rollback is None else rollback
    store=PolicyStore(target); lock=store.lock()
    try:
        policy,state=_read(store)
        if backup.exists(): raise ValueError("ROLLBACK_ALREADY_EXISTS")
        backup.mkdir(mode=0o700,parents=False)
        _atomic(backup,POLICY_NAME,policy); _atomic(backup,STATE_NAME,state); _atomic(backup,LKV_NAME,state)
        _validate_rollback(backup,policy)
        for name in (POLICY_NAME,STATE_NAME,LKV_NAME): (target/name).unlink()
        fd=os.open(target,os.O_RDONLY)
        try: os.fsync(fd)
        finally: os.close(fd)
        return "ONE_DAY_POLICY_REMOVED_ROLLBACK_READY"
    finally: fcntl.flock(lock,fcntl.LOCK_UN); lock.close()

def restore_from_rollback(*,root:Path|None=None,rollback:Path|None=None)->str:
    target=OPERATIONAL_ROOT if root is None else root; backup=ROLLBACK_ROOT if rollback is None else rollback
    policy,state,lkv=_validate_rollback(backup)
    if not target.exists(): target.mkdir(mode=0o700,parents=False)
    store=PolicyStore(target); lock=store.lock()
    try:
        existing={item.name for item in target.iterdir() if item.name != LOCK_NAME}
        if existing: raise ValueError("POLICY_DUPLICATE_OR_AMBIGUOUS")
        _atomic(target,POLICY_NAME,policy); _atomic(target,STATE_NAME,state); _atomic(target,LKV_NAME,lkv)
        store.validate_root(); _read(store); return "ONE_DAY_POLICY_RESTORED_DISABLED"
    finally: fcntl.flock(lock,fcntl.LOCK_UN); lock.close()

def tick(store:PolicyStore,now:datetime,*,readiness_root:Path|None=None)->str:
    policy,state=_read(store); moment=classify_time(now)
    if moment=="SESSION_INELIGIBLE" or moment=="SESSION_EXPIRED": return "SESSION_INELIGIBLE"
    if moment=="WAIT": return "BOUNDED_IDLE_WAIT"
    transitions={
        ("TUESDAY_POLICY_INSTALLED_DISABLED","RECOVERY"):"TUESDAY_WAITING_FOR_PREFLIGHT",
        ("TUESDAY_POLICY_INSTALLED_DISABLED","PREFLIGHT"):"TUESDAY_WAITING_FOR_PREFLIGHT",
        ("TUESDAY_WAITING_FOR_PREFLIGHT","PREFLIGHT"):"TUESDAY_PREFLIGHT_RUNNING",
    }
    target=transitions.get((state["phase"],moment))
    if target:
        # With no operational provider-cost adapter, readiness must remain zero-call.
        state=transition(state,policy,target,failure="ENDPOINT_COST_UNKNOWN" if target.endswith("FAILED_CLOSED") else None)
        _write_state(store,state,policy); return target
    if state["phase"]=="TUESDAY_PREFLIGHT_RUNNING" and moment=="READINESS":
        try:
            binding=operational_cost_binding(now=now,**({} if readiness_root is None else {"root":readiness_root}))
            if (binding["cost_contract_hash"]!=policy["cost_contract_hash"]
                    or binding["request_plan_identity"]!=policy["request_plan_identity"]
                    or binding["exact_planned_cost_credits"]!=policy["stage_a_authorized_allowance_credits"]):
                raise ValueError("OPERATIONAL_COST_BINDING_UNAVAILABLE")
            state=transition(state,policy,"TUESDAY_READY_FOR_OPEN")
            state["preflight_status"]="PASSED"; state["content_hash"]=_hash(state)
            _write_state(store,state,policy); return "TUESDAY_READY_FOR_OPEN"
        except (OSError,ValueError):
            state=transition(state,policy,"TUESDAY_PREFLIGHT_FAILED_CLOSED",failure="OPERATIONAL_COST_BINDING_UNAVAILABLE")
            _write_state(store,state,policy); return "TUESDAY_PREFLIGHT_FAILED_CLOSED"
    if state["phase"]=="TUESDAY_READY_FOR_OPEN" and moment=="OPEN_OR_INTRADAY":
        if state["released_credits"] != 0: return "STAGE_A_ALLOWANCE_CONTRACT_UNSUPPORTED"
        state=transition(state,policy,"TUESDAY_STAGE_A_RUNNING")
        state["released_credits"]=policy["stage_a_authorized_allowance_credits"]
        state["content_hash"]=_hash(state); validate_session(state,policy); _write_state(store,state,policy)
        return "TUESDAY_STAGE_A_RUNNING"
    return "NO_ELIGIBLE_TRANSITION"

def supervise(*,root:Path|None=None,clock=None,sleep=None,iterations:int|None=None,coordinator_factory=None,
              incident_store:SupervisorIncidentStore|None=None,heartbeat_store:SupervisorHeartbeatStore|None=None,
              heartbeat_evidence_factory=None)->int:
    policy_root=OPERATIONAL_ROOT if root is None else root
    lock_root=SUPERVISOR_ROOT if root is None else root.parent/(root.name+"Supervisor")
    lock_root.mkdir(mode=0o700,parents=False,exist_ok=True); os.chmod(lock_root,0o700)
    lock=open(lock_root/SUPERVISOR_LOCK_NAME,"a+"); os.chmod(lock.name,0o600)
    try: fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError: lock.close(); return 4
    store=PolicyStore(policy_root); now=clock or (lambda:datetime.now(timezone.utc)); wait=sleep or time.sleep; count=0
    incidents=incident_store or SupervisorIncidentStore(lock_root/"incidents")
    heartbeats=heartbeat_store or SupervisorHeartbeatStore(lock_root)
    try:
        while iterations is None or count<iterations:
            cycle_now=now()
            if cycle_now.tzinfo is None: raise ValueError("CLOCK_INVALID")
            # The installed executor is reconstructed from its persisted plan on
            # every supervisor cycle. Recovery is read/write-local only; canary
            # dispatch remains exclusive to the owner-authorized one-shot CLI.
            if root is None or coordinator_factory is not None:
                from .operational_market_executor_installer import INSTALL_ROOT
                if coordinator_factory is not None or INSTALL_ROOT.exists():
                    try:
                        if coordinator_factory is None:
                            from .operational_market_executor_service import production_coordinator
                            coordinator=production_coordinator()
                        else: coordinator=coordinator_factory()
                        state=coordinator.recover()
                        if (state.get("classification") in {"POST_0930_PARTIAL_SESSION","SEPTEMBER_9_MARKET_OPEN_50","SEPTEMBER_9_INTRADAY_RECOVERY"}
                                and state.get("phase") in {"STAGE_A_RUNNING","PRE_SESSION_BOUNDED_WAIT"}):
                            from zoneinfo import ZoneInfo
                            coordinator.scheduled_tick(cycle_now.astimezone(ZoneInfo("America/Los_Angeles")))
                    except (OSError,ValueError,RuntimeError) as exc:
                        incidents.record(exc,phase="OPERATIONAL_COORDINATOR",observed_at=cycle_now.astimezone(timezone.utc)); return 4
            if (policy_root/POLICY_NAME).exists():
                try: tick(store,cycle_now)
                except (OSError,ValueError) as exc:
                    incidents.record(exc,phase="POLICY_TICK",observed_at=cycle_now.astimezone(timezone.utc)); return 4
            if root is None or heartbeat_evidence_factory is not None:
                try:
                    evidence=(heartbeat_evidence_factory or _production_heartbeat_evidence)()
                    observed=cycle_now.astimezone(timezone.utc)
                    heartbeats.record(evidence,observed_at=observed,next_wake_at=observed+timedelta(seconds=60))
                except (OSError,ValueError,RuntimeError,KeyError) as exc:
                    incidents.record(exc,phase="RUNTIME_HEARTBEAT",observed_at=cycle_now.astimezone(timezone.utc))
            count+=1
            if iterations is None or count<iterations: wait(60)
        return 0
    finally: fcntl.flock(lock,fcntl.LOCK_UN); lock.close()

def main(argv:list[str]|None=None)->int:
    p=argparse.ArgumentParser(); group=p.add_mutually_exclusive_group(required=True)
    group.add_argument("--install-one-day-policy",action="store_true"); group.add_argument("--validate-policy",action="store_true")
    group.add_argument("--supervisor",action="store_true"); group.add_argument("--emergency-stop",action="store_true")
    group.add_argument("--operational-supervisor",action="store_true")
    group.add_argument("--remove-policy-with-rollback",action="store_true")
    group.add_argument("--restore-policy-from-rollback",action="store_true")
    p.add_argument("--owner-authorization"); p.add_argument("--approval-timestamp"); p.add_argument("--authorized-commit"); p.add_argument("--browser",action="store_true",help=argparse.SUPPRESS)
    args=p.parse_args(argv)
    if args.browser: print(json.dumps({"status":"BROWSER_INVOCATION_REJECTED"})); return 3
    try:
        if args.install_one_day_policy:
            if not args.owner_authorization or not args.approval_timestamp: raise ValueError("OWNER_AUTHORIZATION_MISSING")
            if not args.authorized_commit: raise ValueError("POLICY_BINDING_INVALID")
            status=install(args.owner_authorization,args.approval_timestamp,args.authorized_commit)
        elif args.validate_policy: status=validate_installed()
        elif args.emergency_stop: status=emergency_stop()
        elif args.remove_policy_with_rollback: status=remove_with_rollback()
        elif args.restore_policy_from_rollback: status=restore_from_rollback()
        else: return supervise()
        print(json.dumps({"status":status},sort_keys=True)); return 0
    except (OSError,ValueError) as exc:
        category=str(exc) if str(exc).isupper() and len(str(exc))<=64 else "UNATTENDED_POLICY_FAILED_CLOSED"
        print(json.dumps({"status":category},sort_keys=True)); return 5

if __name__=="__main__": raise SystemExit(main())
