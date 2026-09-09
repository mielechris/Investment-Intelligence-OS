"""Fixed, owner-only installation for the operational evidence executor.

Installation never enables provider network access.  The canary is a separate,
explicit owner-authorized one-shot command.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import subprocess
from pathlib import Path
from typing import Any

from .financial_datasets import API_HOST, KEYCHAIN_ACCOUNT, KEYCHAIN_SERVICE
from .operational_market_executor import (CANARY_PLAN, POST_0930_PLAN, SEPTEMBER_9_PLAN,
    ExecutorStore, canary_plan, plan_identity, post_0930_plan, september_9_plan)
from .september_9_canonical_plan import (OBSOLETE_EXECUTOR_IDENTITY,
    canonical_plan_identity, obsolete_c40_plan, validate_canonical_plan)

INSTALL_SCHEMA="iios-operational-market-executor-installation-v1"
INSTALL_ROOT=Path.home()/"Library/Application Support/IIOS/OperationalMarketExecutor"
STATE_ROOT=INSTALL_ROOT/"state"
RECOVERY_ROOT=INSTALL_ROOT/"recovery"
ARTIFACT_ROOT=INSTALL_ROOT/"installed-artifacts"
MANIFEST=INSTALL_ROOT/"installation-manifest.json"
ROLLBACK_ROOT=Path.home()/"Library/Application Support/IIOS/Rollback/OperationalMarketExecutor"
UPGRADE_ROLLBACK_ROOT=Path.home()/"Library/Application Support/IIOS/Rollback/OperationalMarketExecutorUpgrade"
SESSIONS_NAME="sessions"
SELECTOR_NAME="selected-session.json"
ARCHIVE_SCHEMA="iios-operational-market-session-archive-v1"
SELECTOR_SCHEMA="iios-operational-market-session-selector-v1"
CORRECTED_SELECTOR_SCHEMA="iios-operational-market-session-selector-v2"
SUPERSESSION_SCHEMA="iios-operational-market-generation-supersession-v1"
CORRECTED_GENERATION_NAME="2026-09-09-canonical-v2"
SUPERSESSION_NAME="2026-09-09-c40-supersession.json"
COORDINATOR="expansion_wing.operational_market_executor.OperationalMarketEvidenceCoordinator"
APPROVED_ENDPOINTS=("/company/facts","/prices","/prices/snapshot")
ARTIFACTS=("operational_market_executor.py","operational_market_executor_installer.py",
           "operational_market_executor_service.py","financial_datasets.py","financial_datasets_tls.py",
           "keychain_adapter.py","september_9_canonical_plan.py")

def _sha(path:Path)->str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def _write(path:Path,value:dict[str,Any])->None:
    data=(json.dumps(value,sort_keys=True,separators=(",",":"))+"\n").encode()
    temp=path.parent/("."+path.name+".tmp"); fd=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    try: os.write(fd,data); os.fsync(fd)
    finally: os.close(fd)
    os.replace(temp,path); dfd=os.open(path.parent,os.O_RDONLY)
    try: os.fsync(dfd)
    finally: os.close(dfd)

def _write_bytes(path:Path,data:bytes)->None:
    temp=path.parent/("."+path.name+".tmp"); fd=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    try: os.write(fd,data); os.fsync(fd)
    finally: os.close(fd)
    os.replace(temp,path); dfd=os.open(path.parent,os.O_RDONLY)
    try: os.fsync(dfd)
    finally: os.close(dfd)

def _hash_document(value:dict[str,Any])->str:
    clean=dict(value); clean.pop("content_hash",None)
    return hashlib.sha256((json.dumps(clean,sort_keys=True,separators=(",",":"))+"\n").encode()).hexdigest()

def _regular_owner_file(path:Path)->None:
    info=path.lstat()
    if path.is_symlink() or not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode)!=0o600 or info.st_uid!=os.getuid():
        raise ValueError("SESSION_GENERATION_FILE_INVALID")

def _copy_session_archive(source:Path,target:Path)->dict[str,Any]:
    target.mkdir(mode=0o700,parents=True,exist_ok=True); os.chmod(target,0o700)
    inventory=[]
    for path in sorted(source.rglob("*")):
        relative=path.relative_to(source)
        if path.name=="executor.lock": continue
        info=path.lstat()
        destination=target/relative
        if path.is_symlink() or not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)):
            raise ValueError("SESSION_ARCHIVE_SOURCE_INVALID")
        if path.is_dir(): destination.mkdir(mode=0o700,parents=True,exist_ok=True); os.chmod(destination,0o700)
        else:
            destination.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
            _write_bytes(destination,path.read_bytes())
            inventory.append({"path":str(relative),"bytes":info.st_size,"sha256":_sha(path)})
    value={"schema":ARCHIVE_SCHEMA,"session_date":"2026-09-08","classification":POST_0930_PLAN,
        "source_plan_identity":plan_identity(post_0930_plan()),"files":inventory,"content_hash":""}
    value["content_hash"]=_hash_document(value); _write(target/"archive-manifest.json",value); return value

def _validate_archive(root:Path)->dict[str,Any]:
    info=root.lstat()
    if root.is_symlink() or not stat.S_ISDIR(info.st_mode) or stat.S_IMODE(info.st_mode)!=0o700 or info.st_uid!=os.getuid(): raise ValueError("SESSION_ARCHIVE_INVALID")
    manifest_path=root/"archive-manifest.json"; _regular_owner_file(manifest_path); value=json.loads(manifest_path.read_text())
    if (value.get("schema")!=ARCHIVE_SCHEMA or value.get("session_date")!="2026-09-08"
            or value.get("classification")!=POST_0930_PLAN or value.get("source_plan_identity")!=plan_identity(post_0930_plan())
            or value.get("content_hash")!=_hash_document(value)): raise ValueError("SESSION_ARCHIVE_INVALID")
    expected={row["path"]:row for row in value.get("files",[])}
    observed={str(p.relative_to(root)) for p in root.rglob("*") if p.is_file() and p.name!="archive-manifest.json"}
    if observed!=set(expected): raise ValueError("SESSION_ARCHIVE_INVENTORY_INVALID")
    for relative,row in expected.items():
        path=root/relative; _regular_owner_file(path)
        if path.stat().st_size!=row["bytes"] or _sha(path)!=row["sha256"]: raise ValueError("SESSION_ARCHIVE_HASH_MISMATCH")
    return value

def _selector(archive:dict[str,Any])->dict[str,Any]:
    value={"schema":SELECTOR_SCHEMA,"selected_session":"2026-09-09","selected_root":"sessions/2026-09-09",
        "plan_classification":SEPTEMBER_9_PLAN,"plan_identity":plan_identity(september_9_plan()),
        "september_8_archive_hash":archive["content_hash"],"content_hash":""}
    value["content_hash"]=_hash_document(value); return value

def _obsolete_selector(archive:dict[str,Any])->dict[str,Any]:
    value={"schema":SELECTOR_SCHEMA,"selected_session":"2026-09-09","selected_root":"sessions/2026-09-09",
        "plan_classification":SEPTEMBER_9_PLAN,"plan_identity":OBSOLETE_EXECUTOR_IDENTITY,
        "september_8_archive_hash":archive["content_hash"],"content_hash":""}
    value["content_hash"]=_hash_document(value); return value

def _generation_inventory(root:Path)->list[dict[str,Any]]:
    rows=[]
    for path in sorted(root.rglob("*")):
        info=path.lstat(); relative=str(path.relative_to(root))
        if path.is_symlink() or info.st_uid!=os.getuid(): raise ValueError("SUPERSESSION_INVENTORY_INVALID")
        if path.is_dir():
            if stat.S_IMODE(info.st_mode)!=0o700: raise ValueError("SUPERSESSION_INVENTORY_INVALID")
            continue
        if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode)!=0o600: raise ValueError("SUPERSESSION_INVENTORY_INVALID")
        rows.append({"path":relative,"bytes":info.st_size,"sha256":_sha(path)})
    return rows

def _validate_obsolete_generation(root:Path)->dict[str,Any]:
    rows=ExecutorStore(root).read_plan(); state=ExecutorStore(root).read()
    if (rows!=obsolete_c40_plan() or state.get("plan_identity")!=OBSOLETE_EXECUTOR_IDENTITY
            or state.get("released_credits")!=0 or any(state.get(k)!="LOCKED" for k in ("stage_a","stage_b","stage_c"))
            or any(state.get(k)!=0 for k in ("dispatched","completed","ambiguous","failed","confirmed_credits","ambiguous_credits","keychain_accesses"))
            or any(item.get("lifecycle")!="PLANNED" for item in state.get("requests",{}).values())
            or any(any((root/name).iterdir()) for name in ("receipts","evidence"))):
        raise ValueError("SUPERSESSION_SAFETY_GATE_FAILED")
    return state

def _supersession_document(root:Path)->dict[str,Any]:
    _validate_obsolete_generation(root)
    body={"schema":SUPERSESSION_SCHEMA,"session_date":"2026-09-09",
        "superseded_generation":"sessions/2026-09-09","superseded_plan_identity":OBSOLETE_EXECUTOR_IDENTITY,
        "reason":"READINESS_EXECUTOR_IDENTITY_AND_SEMANTIC_CONTRACT_MISMATCH",
        "inventory":_generation_inventory(root),"allowance_released":False,"provider_activity":False,
        "immutable":True}
    return body|{"content_hash":_hash_document(body)}

def _validate_supersession(path:Path,root:Path)->dict[str,Any]:
    _regular_owner_file(path); value=json.loads(path.read_text()); body=dict(value); content=body.pop("content_hash",None)
    if value.get("schema")!=SUPERSESSION_SCHEMA or content!=_hash_document(body) or value!=_supersession_document(root):
        raise ValueError("SUPERSESSION_RECEIPT_INVALID")
    return value

def _corrected_selector(archive:dict[str,Any],supersession:dict[str,Any])->dict[str,Any]:
    value={"schema":CORRECTED_SELECTOR_SCHEMA,"selected_session":"2026-09-09",
        "selected_root":f"sessions/{CORRECTED_GENERATION_NAME}","plan_classification":SEPTEMBER_9_PLAN,
        "plan_identity":canonical_plan_identity(),"september_8_archive_hash":archive["content_hash"],
        "supersession_receipt_hash":supersession["content_hash"],"content_hash":""}
    value["content_hash"]=_hash_document(value); return value

def resolve_selected_state_root(root:Path=INSTALL_ROOT)->Path:
    selector_path=root/SELECTOR_NAME
    if not selector_path.exists(): return root/"state"
    _regular_owner_file(selector_path); value=json.loads(selector_path.read_text())
    archive=_validate_archive(root/SESSIONS_NAME/"2026-09-08")
    if value.get("schema")==SELECTOR_SCHEMA:
        if value!=_obsolete_selector(archive): raise ValueError("SESSION_SELECTOR_INVALID")
        selected=root/SESSIONS_NAME/"2026-09-09"; _validate_obsolete_generation(selected); return selected
    if value.get("schema")!=CORRECTED_SELECTOR_SCHEMA: raise ValueError("SESSION_SELECTOR_INVALID")
    receipt_path=root/"incidents"/SUPERSESSION_NAME
    receipt=_validate_supersession(receipt_path,root/SESSIONS_NAME/"2026-09-09")
    if value!=_corrected_selector(archive,receipt): raise ValueError("SESSION_SELECTOR_INVALID")
    selected=root/SESSIONS_NAME/CORRECTED_GENERATION_NAME; rows=ExecutorStore(selected).read_plan(); state=ExecutorStore(selected).read()
    identities={row["identity"]:row for row in rows}
    receipts={p.stem:p for p in (selected/"receipts").iterdir()}; evidence={p.stem:p for p in (selected/"evidence").iterdir()}
    if (rows!=september_9_plan() or state["classification"]!=SEPTEMBER_9_PLAN or state["plan_identity"]!=plan_identity(rows)
            or set(state["requests"])!=set(identities) or set(receipts)!=set(evidence) or not set(receipts)<=set(identities)):
        raise ValueError("SELECTED_SESSION_MIXED")
    for identity,path in receipts.items():
        _regular_owner_file(path); _regular_owner_file(evidence[identity]); receipt=json.loads(path.read_text()); row=identities[identity]
        if (receipt.get("request_identity")!=identity or receipt.get("ticker")!=row["ticker"]
                or receipt.get("window")!=row["window"] or receipt.get("endpoint")!=row["endpoint"]
                or receipt.get("credit_cost")!=1 or receipt.get("evidence_hash")!=_sha(evidence[identity])):
            raise ValueError("SELECTED_SESSION_MIXED")
    return selected

def reselect_corrected_september_9_generation(root:Path=INSTALL_ROOT,*,readiness_root:Path|None=None,
        interrupt_after:str|None=None,post_select_validator=None)->str:
    """Quarantine c40 and atomically select a distinct corrected locked generation."""
    validate_installed(root); archive=_validate_archive(root/SESSIONS_NAME/"2026-09-08")
    current_selector=root/SELECTOR_NAME; _regular_owner_file(current_selector); original=current_selector.read_bytes()
    if json.loads(original)!=_obsolete_selector(archive): raise ValueError("OBSOLETE_SELECTION_REQUIRED")
    obsolete=root/SESSIONS_NAME/"2026-09-09"; _validate_obsolete_generation(obsolete)
    from .provider_readiness import READINESS_ROOT,operational_cost_binding
    binding=operational_cost_binding(root=READINESS_ROOT if readiness_root is None else readiness_root)
    if binding.get("request_plan_identity")!=canonical_plan_identity(): raise ValueError("CORRECTED_PRICING_BINDING_REQUIRED")
    incidents=root/"incidents"; incidents.mkdir(mode=0o700,exist_ok=True); os.chmod(incidents,0o700)
    receipt_path=incidents/SUPERSESSION_NAME; expected=_supersession_document(obsolete)
    if receipt_path.exists():
        if _validate_supersession(receipt_path,obsolete)!=expected: raise ValueError("SUPERSESSION_RECEIPT_INVALID")
    else: _write(receipt_path,expected)
    if interrupt_after=="quarantine": raise RuntimeError("INTERRUPTED_QUARANTINE")
    corrected=root/SESSIONS_NAME/CORRECTED_GENERATION_NAME; stage=root/SESSIONS_NAME/("."+CORRECTED_GENERATION_NAME+".tmp")
    if not corrected.exists():
        if stage.exists(): shutil.rmtree(stage)
        ExecutorStore(stage).initialize(september_9_plan(),SEPTEMBER_9_PLAN)
        if interrupt_after=="generation": raise RuntimeError("INTERRUPTED_CORRECTED_GENERATION")
        os.replace(stage,corrected)
    rows=ExecutorStore(corrected).read_plan(); state=ExecutorStore(corrected).read(); validate_canonical_plan(rows)
    if (state.get("plan_identity")!=canonical_plan_identity(rows) or state.get("released_credits")!=0
            or any(state.get(k)!="LOCKED" for k in ("stage_a","stage_b","stage_c"))):
        raise ValueError("CORRECTED_GENERATION_INVALID")
    receipt=_validate_supersession(receipt_path,obsolete); candidate=_corrected_selector(archive,receipt)
    temp=root/("."+SELECTOR_NAME+".corrected.tmp")
    if temp.exists():
        _regular_owner_file(temp)
        if json.loads(temp.read_text())!=candidate: raise ValueError("CORRECTED_SELECTOR_STAGE_INVALID")
        temp.unlink()
    _write(temp,candidate)
    if interrupt_after=="selection": raise RuntimeError("INTERRUPTED_CORRECTED_SELECTION")
    try:
        os.replace(temp,current_selector); dfd=os.open(root,os.O_RDONLY)
        try: os.fsync(dfd)
        finally: os.close(dfd)
        if interrupt_after=="after_selection": raise RuntimeError("INTERRUPTED_AFTER_CORRECTED_SELECTION")
        if resolve_selected_state_root(root)!=corrected: raise ValueError("CORRECTED_SELECTION_FAILED")
        if post_select_validator: post_select_validator(root)
    except Exception:
        _write_bytes(current_selector,original)
        if resolve_selected_state_root(root)!=obsolete: raise ValueError("OBSOLETE_SELECTION_RESTORE_FAILED")
        raise
    return "SEPTEMBER_9_CORRECTED_GENERATION_SELECTED_LOCKED"

def prepare_september_9_generation(root:Path=INSTALL_ROOT,*,interrupt_after:str|None=None)->str:
    """Archive September 8 and atomically select a locked September 9 generation."""
    validate_installed(root); source=ExecutorStore(root/"state"); state=source.read(); rows=source.read_plan()
    terminal={"CONFIRMED","AMBIGUOUS","FAILED_PRETRANSMISSION"}
    if (state["classification"]!=POST_0930_PLAN or rows!=post_0930_plan() or state["phase"]!="SESSION_CLOSED"
            or state["released_credits"]!=0 or any(state[key]!="LOCKED" for key in ("stage_a","stage_b","stage_c"))
            or any(row["lifecycle"] not in terminal for row in state["requests"].values())
            or state["completed"]+state["ambiguous"]+state["failed"]!=state["planned"]):
        raise ValueError("SEPTEMBER_8_NOT_TERMINAL")
    sessions=root/SESSIONS_NAME; sessions.mkdir(mode=0o700,exist_ok=True); os.chmod(sessions,0o700)
    archive=sessions/"2026-09-08"; archive_stage=sessions/".2026-09-08.archive.tmp"
    if not archive.exists():
        document=_copy_session_archive(root/"state",archive_stage); _validate_archive(archive_stage)
        if interrupt_after=="archive": raise RuntimeError("INTERRUPTED_ARCHIVAL")
        os.replace(archive_stage,archive)
    document=_validate_archive(archive)
    generation=sessions/"2026-09-09"; generation_stage=sessions/".2026-09-09.generation.tmp"
    if not generation.exists():
        if generation_stage.exists(): shutil.rmtree(generation_stage)
        ExecutorStore(generation_stage).initialize(obsolete_c40_plan(),SEPTEMBER_9_PLAN)
        if interrupt_after=="generation": raise RuntimeError("INTERRUPTED_GENERATION")
        os.replace(generation_stage,generation)
    store=ExecutorStore(generation)
    if store.read_plan()!=obsolete_c40_plan() or store.read()["released_credits"]!=0: raise ValueError("SEPTEMBER_9_GENERATION_INVALID")
    selector=_obsolete_selector(document); selector_temp=root/("."+SELECTOR_NAME+".tmp"); _write(selector_temp,selector)
    if interrupt_after=="selection": raise RuntimeError("INTERRUPTED_SELECTION")
    os.replace(selector_temp,root/SELECTOR_NAME); dfd=os.open(root,os.O_RDONLY)
    try: os.fsync(dfd)
    finally: os.close(dfd)
    if resolve_selected_state_root(root)!=generation: raise ValueError("SESSION_SELECTION_FAILED")
    return "SEPTEMBER_9_GENERATION_SELECTED_LOCKED"

def recover_session_transition(root:Path=INSTALL_ROOT)->str:
    selector_temp=root/("."+SELECTOR_NAME+".tmp")
    if (root/SELECTOR_NAME).exists(): resolve_selected_state_root(root); return "SESSION_SELECTION_VALID"
    if selector_temp.exists():
        _regular_owner_file(selector_temp); value=json.loads(selector_temp.read_text())
        archive=_validate_archive(root/SESSIONS_NAME/"2026-09-08")
        if value!=_obsolete_selector(archive): raise ValueError("SESSION_SELECTOR_INVALID")
        selected=root/SESSIONS_NAME/"2026-09-09"
        if ExecutorStore(selected).read_plan()!=obsolete_c40_plan(): raise ValueError("SELECTED_SESSION_MIXED")
        os.replace(selector_temp,root/SELECTOR_NAME)
        resolve_selected_state_root(root); return "SESSION_SELECTION_RECOVERED"
    # Pre-selection interruptions remain safely on the untouched September 8 root.
    return "SEPTEMBER_8_REMAINS_SELECTED"

def render_manifest(source_root:Path,commit:str)->dict[str,Any]:
    if len(commit)!=40 or any(c not in "0123456789abcdef" for c in commit): raise ValueError("INSTALL_COMMIT_INVALID")
    base=source_root/"BACK END/backend/expansion_wing"
    inventory=[]
    for name in ARTIFACTS:
        path=base/name
        if path.is_symlink() or not path.is_file(): raise ValueError("INSTALL_ARTIFACT_INVALID")
        inventory.append({"path":"expansion_wing/"+name,"bytes":path.stat().st_size,"sha256":_sha(path)})
    value={"schema":INSTALL_SCHEMA,"installed_source_commit":commit,"coordinator":COORDINATOR,
           "provider_host":API_HOST,"approved_endpoints":list(APPROVED_ENDPOINTS),
           "credential_selector":{"service":KEYCHAIN_SERVICE,"account":KEYCHAIN_ACCOUNT},
           "plan":{"classification":CANARY_PLAN,"identity":plan_identity(canary_plan()),"requests":1,"credits":1,"retry":False},
           "roots":{"state":"state","evidence":"state/evidence","receipts":"state/receipts","recovery":"recovery"},
           "network_enabled":False,"full_session_authorized":False,"late_session_authorized":False,
           "artifacts":inventory,"content_hash":""}
    clean=dict(value); clean.pop("content_hash"); value["content_hash"]=hashlib.sha256((json.dumps(clean,sort_keys=True,separators=(",",":"))+"\n").encode()).hexdigest()
    return value

def validate_manifest(value:Any,source_root:Path|None=None)->dict[str,Any]:
    if not isinstance(value,dict) or value.get("schema")!=INSTALL_SCHEMA: raise ValueError("INSTALL_MANIFEST_INVALID")
    clean=dict(value); observed=clean.pop("content_hash",None)
    expected=hashlib.sha256((json.dumps(clean,sort_keys=True,separators=(",",":"))+"\n").encode()).hexdigest()
    if observed!=expected or value.get("network_enabled") is not False or value.get("full_session_authorized") is not False or value.get("late_session_authorized") is not False: raise ValueError("INSTALL_MANIFEST_INVALID")
    if value.get("coordinator")!=COORDINATOR or value.get("provider_host")!=API_HOST or tuple(value.get("approved_endpoints",()))!=APPROVED_ENDPOINTS: raise ValueError("INSTALL_MANIFEST_INVALID")
    if value.get("credential_selector")!={"service":KEYCHAIN_SERVICE,"account":KEYCHAIN_ACCOUNT}: raise ValueError("INSTALL_MANIFEST_INVALID")
    if value.get("plan")!={"classification":CANARY_PLAN,"identity":plan_identity(canary_plan()),"requests":1,"credits":1,"retry":False}: raise ValueError("INSTALL_MANIFEST_INVALID")
    if source_root is not None:
        expected_manifest=render_manifest(source_root,value["installed_source_commit"])
        if value!=expected_manifest: raise ValueError("INSTALL_ARTIFACT_HASH_MISMATCH")
    return value

def validate_installed(root:Path=INSTALL_ROOT)->dict[str,Any]:
    info=root.lstat()
    if root.is_symlink() or not stat.S_ISDIR(info.st_mode) or stat.S_IMODE(info.st_mode)!=0o700 or info.st_uid!=os.getuid(): raise ValueError("INSTALL_ROOT_INVALID")
    base={"installation-manifest.json","state","recovery","installed-artifacts"}; observed_root={p.name for p in root.iterdir()}
    allowed=base|{SESSIONS_NAME,SELECTOR_NAME,"incidents","."+SELECTOR_NAME+".corrected.tmp"}
    if not base<=observed_root or not observed_root<=allowed: raise ValueError("INSTALL_INVENTORY_INVALID")
    for directory in (STATE_ROOT if root==INSTALL_ROOT else root/"state",RECOVERY_ROOT if root==INSTALL_ROOT else root/"recovery",ARTIFACT_ROOT if root==INSTALL_ROOT else root/"installed-artifacts"):
        i=directory.lstat()
        if directory.is_symlink() or not stat.S_ISDIR(i.st_mode) or stat.S_IMODE(i.st_mode)!=0o700 or i.st_uid!=os.getuid(): raise ValueError("INSTALL_ROOT_INVALID")
    path=root/"installation-manifest.json"; i=path.lstat()
    if path.is_symlink() or not stat.S_ISREG(i.st_mode) or stat.S_IMODE(i.st_mode)!=0o600 or i.st_uid!=os.getuid(): raise ValueError("INSTALL_MANIFEST_INVALID")
    manifest=validate_manifest(json.loads(path.read_text()))
    artifact_root=root/"installed-artifacts"
    expected={row["path"]:row for row in manifest["artifacts"]}
    observed={"expansion_wing/"+p.name for p in artifact_root.iterdir()}
    if observed!=set(expected): raise ValueError("INSTALL_ARTIFACT_INVENTORY_INVALID")
    for relative,row in expected.items():
        artifact=artifact_root/Path(relative).name; a=artifact.lstat()
        if artifact.is_symlink() or not stat.S_ISREG(a.st_mode) or stat.S_IMODE(a.st_mode)!=0o600 or a.st_uid!=os.getuid() or a.st_size!=row["bytes"] or _sha(artifact)!=row["sha256"]:
            raise ValueError("INSTALL_ARTIFACT_HASH_MISMATCH")
    if SELECTOR_NAME in observed_root: resolve_selected_state_root(root)
    return manifest

def browser_projection(root:Path=INSTALL_ROOT)->dict[str,Any]:
    """Authenticated, sanitized status derived from one installed generation."""
    from .tuesday_whole_factory import LOCKED_AUTHORITY
    if not root.exists():
        return {"schema_version":"iios-operational-market-executor-browser-v1","phase":"NOT_INSTALLED",
                "installed":False,"authority":LOCKED_AUTHORITY.copy()}
    try:
        validate_installed(root); state=ExecutorStore(resolve_selected_state_root(root)).read()
        phases={"EXECUTOR_READY_DISABLED":"CANARY_READY","POST_0930_PARTIAL_READY":"POST_0930_PARTIAL_SESSION",
                "CANARY_CONFIRMED":"CANARY_CONFIRMED","FAILED_CLOSED":"FAILED_CLOSED",
                "SESSION_FAILED_CLOSED":"FAILED_CLOSED","SESSION_CLOSED":"INSTALLED_DISABLED"}
        phase="POST_0930_PARTIAL_SESSION" if state["classification"]=="POST_0930_PARTIAL_SESSION" and state["phase"]=="STAGE_A_RUNNING" else phases.get(state["phase"],"UNAVAILABLE")
        return {"schema_version":"iios-operational-market-executor-browser-v1","installed":True,
                "phase":phase,"classification":state["classification"],
                "generation":state["generation"],"planned":state["planned"],"dispatched":state["dispatched"],
                "completed":state["completed"],"failed":state["failed"],"ambiguous":state["ambiguous"],
                "confirmed_credits":state["confirmed_credits"],"ambiguous_credits":state["ambiguous_credits"],
                "released_credits":state["released_credits"],"keychain_accesses":state["keychain_accesses"],
                "remaining":state["planned"]-state["completed"]-state["ambiguous"]-state["failed"],
                "adopted_canary_count":state.get("adopted_canary_count",0),
                "stage_a":state["stage_a"],"stage_b":state["stage_b"],"stage_c":state["stage_c"],
                "next_gate":state["next_gate"],"authority":state["authority"]}
    except (OSError,ValueError,json.JSONDecodeError):
        return {"schema_version":"iios-operational-market-executor-browser-v1","phase":"UNAVAILABLE",
                "installed":None,"authority":LOCKED_AUTHORITY.copy()}

def install_disabled(source_root:Path,commit:str,root:Path=INSTALL_ROOT,rollback:Path=ROLLBACK_ROOT,*,observed_commit:str|None=None)->str:
    if observed_commit is None:
        head=subprocess.run(("git","rev-parse","HEAD"),cwd=source_root,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,check=False)
        status=subprocess.run(("git","status","--porcelain"),cwd=source_root,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,check=False)
        if head.returncode or status.returncode or status.stdout: raise ValueError("INSTALL_SOURCE_NOT_CLEAN")
        observed_commit=head.stdout.strip()
    if observed_commit!=commit: raise ValueError("INSTALL_COMMIT_MISMATCH")
    candidate=render_manifest(source_root,commit); validate_manifest(candidate,source_root)
    if root.exists(): raise ValueError("EXECUTOR_ALREADY_INSTALLED")
    if rollback.exists(): raise ValueError("ROLLBACK_ALREADY_EXISTS")
    rollback.mkdir(mode=0o700,parents=True); _write(rollback/"prior-installation.json",{"present":False,"content_hash":hashlib.sha256(b"absent\n").hexdigest()})
    root.mkdir(mode=0o700,parents=True); (root/"recovery").mkdir(mode=0o700); (root/"installed-artifacts").mkdir(mode=0o700)
    source_base=source_root/"BACK END/backend/expansion_wing"
    for name in ARTIFACTS:
        data=(source_base/name).read_bytes(); path=root/"installed-artifacts"/name
        fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        try: os.write(fd,data); os.fsync(fd)
        finally: os.close(fd)
    ExecutorStore(root/"state").initialize(canary_plan(),CANARY_PLAN)
    _write(root/"installation-manifest.json",candidate)
    validate_installed(root); return "EXECUTOR_INSTALLED_DISABLED"

def rollback_install(root:Path=INSTALL_ROOT,rollback:Path=ROLLBACK_ROOT)->str:
    marker=rollback/"prior-installation.json"
    if not marker.is_file() or json.loads(marker.read_text()).get("present") is not False: raise ValueError("ROLLBACK_INVALID")
    validate_installed(root)
    shutil.rmtree(root)
    if root.exists(): raise ValueError("ROLLBACK_FAILED")
    return "EXECUTOR_INSTALLATION_ABSENT_RESTORED"

def upgrade_disabled(source_root:Path,commit:str,root:Path=INSTALL_ROOT,rollback:Path=UPGRADE_ROLLBACK_ROOT,*,observed_commit:str|None=None)->str:
    validate_installed(root)
    if observed_commit is None:
        head=subprocess.run(("git","rev-parse","HEAD"),cwd=source_root,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,check=False)
        status=subprocess.run(("git","status","--porcelain"),cwd=source_root,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,check=False)
        if head.returncode or status.returncode or status.stdout: raise ValueError("INSTALL_SOURCE_NOT_CLEAN")
        observed_commit=head.stdout.strip()
    if observed_commit!=commit or rollback.exists(): raise ValueError("INSTALL_COMMIT_MISMATCH" if observed_commit!=commit else "ROLLBACK_ALREADY_EXISTS")
    candidate=render_manifest(source_root,commit); validate_manifest(candidate,source_root)
    shutil.copytree(root,rollback,copy_function=shutil.copy2)
    for directory in [rollback,*[p for p in rollback.rglob("*") if p.is_dir()]]: os.chmod(directory,0o700)
    for path in [p for p in rollback.rglob("*") if p.is_file()]: os.chmod(path,0o600)
    before_state=(root/"state"/"executor-state.json").read_bytes(); before_lkv=(root/"state"/"executor-state.last-known-valid.json").read_bytes()
    source_base=source_root/"BACK END/backend/expansion_wing"
    for name in ARTIFACTS: _write_bytes(root/"installed-artifacts"/name,(source_base/name).read_bytes())
    _write(root/"installation-manifest.json",candidate)
    validate_installed(root)
    if before_state!=(root/"state"/"executor-state.json").read_bytes() or before_lkv!=(root/"state"/"executor-state.last-known-valid.json").read_bytes(): raise ValueError("INSTALL_STATE_MUTATED")
    return "EXECUTOR_UPGRADED_DISABLED"
