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
from .operational_market_executor import CANARY_PLAN, ExecutorStore, canary_plan, plan_identity

INSTALL_SCHEMA="iios-operational-market-executor-installation-v1"
INSTALL_ROOT=Path.home()/"Library/Application Support/IIOS/OperationalMarketExecutor"
STATE_ROOT=INSTALL_ROOT/"state"
RECOVERY_ROOT=INSTALL_ROOT/"recovery"
ARTIFACT_ROOT=INSTALL_ROOT/"installed-artifacts"
MANIFEST=INSTALL_ROOT/"installation-manifest.json"
ROLLBACK_ROOT=Path.home()/"Library/Application Support/IIOS/Rollback/OperationalMarketExecutor"
COORDINATOR="expansion_wing.operational_market_executor.OperationalMarketEvidenceCoordinator"
APPROVED_ENDPOINTS=("/company/facts","/prices","/prices/snapshot")
ARTIFACTS=("operational_market_executor.py","operational_market_executor_installer.py",
           "operational_market_executor_service.py","financial_datasets.py","financial_datasets_tls.py",
           "keychain_adapter.py")

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
    allowed={"installation-manifest.json","state","recovery","installed-artifacts"}
    if {p.name for p in root.iterdir()}!=allowed: raise ValueError("INSTALL_INVENTORY_INVALID")
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
    return manifest

def browser_projection(root:Path=INSTALL_ROOT)->dict[str,Any]:
    """Authenticated, sanitized status derived from one installed generation."""
    from .tuesday_whole_factory import LOCKED_AUTHORITY
    if not root.exists():
        return {"schema_version":"iios-operational-market-executor-browser-v1","phase":"NOT_INSTALLED",
                "installed":False,"authority":LOCKED_AUTHORITY.copy()}
    try:
        validate_installed(root); state=ExecutorStore(root/"state").read()
        phases={"EXECUTOR_READY_DISABLED":"CANARY_READY","STAGE_A_RUNNING":"CANARY_RUNNING",
                "CANARY_CONFIRMED":"CANARY_CONFIRMED","FAILED_CLOSED":"FAILED_CLOSED",
                "SESSION_FAILED_CLOSED":"FAILED_CLOSED","SESSION_CLOSED":"INSTALLED_DISABLED"}
        return {"schema_version":"iios-operational-market-executor-browser-v1","installed":True,
                "phase":phases.get(state["phase"],"UNAVAILABLE"),"classification":state["classification"],
                "generation":state["generation"],"planned":state["planned"],"dispatched":state["dispatched"],
                "completed":state["completed"],"failed":state["failed"],"ambiguous":state["ambiguous"],
                "confirmed_credits":state["confirmed_credits"],"ambiguous_credits":state["ambiguous_credits"],
                "released_credits":state["released_credits"],"keychain_accesses":state["keychain_accesses"],
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
