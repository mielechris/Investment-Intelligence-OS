"""Fixed-path, non-spending administrator for Tuesday readiness metadata."""
from __future__ import annotations
import argparse, hashlib, json, os, shutil, stat
from datetime import datetime, timezone
from pathlib import Path
from .keychain_adapter import SecurityCommandRunner
from .provider_readiness import (COST_CONTRACT_NAME, CREDENTIAL_STATUS_NAME, READINESS_ROOT,
    SEPTEMBER_9_COST_SCHEMA, cost_contract_document, installed_readiness_projection,
    september_9_cost_evidence_document, validate_prior_cost_contract_for_refresh,
    validate_september_9_cost_evidence)

REFRESH_ROLLBACK_ROOT=READINESS_ROOT.parent/"UnattendedTuesdayReadinessRollback"/"September9Pricing"
REFRESH_SCHEMA="iios-provider-pricing-refresh-rollback-v1"
STAGE_NAME=".provider-cost-contract.september-9.stage"

def _atomic(root:Path,name:str,value:dict)->None:
    root.mkdir(mode=0o700,parents=False,exist_ok=True); os.chmod(root,0o700)
    target=root/name; temp=root/(name+".tmp")
    fd=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    try:
        with os.fdopen(fd,"w") as handle:
            json.dump(value,handle,sort_keys=True,separators=(",",":")); handle.write("\n"); handle.flush(); os.fsync(handle.fileno())
        os.replace(temp,target); os.chmod(target,0o600)
        directory=os.open(root,os.O_RDONLY)
        try: os.fsync(directory)
        finally: os.close(directory)
    finally:
        if temp.exists(): temp.unlink()

def _canonical(value:dict)->bytes:
    return (json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=True)+"\n").encode("ascii")

def _hash_bytes(value:bytes)->str: return hashlib.sha256(value).hexdigest()

def _hash(value:dict)->str: return _hash_bytes(_canonical(value))

def _owner_file(path:Path)->bytes:
    info=path.lstat()
    if path.is_symlink() or not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or stat.S_IMODE(info.st_mode)!=0o600:
        raise ValueError("READINESS_FILE_INVALID")
    return path.read_bytes()

def _owner_root(path:Path,*,exact_inventory:set[str]|None=None)->None:
    info=path.lstat()
    if path.is_symlink() or not stat.S_ISDIR(info.st_mode) or info.st_uid!=os.getuid() or stat.S_IMODE(info.st_mode)!=0o700:
        raise ValueError("READINESS_ROOT_INVALID")
    if exact_inventory is not None and {item.name for item in path.iterdir()}!=exact_inventory:
        raise ValueError("READINESS_INVENTORY_INVALID")

def _backup_value(rollback:Path)->dict:
    _owner_root(rollback,exact_inventory={"prior-provider-cost-contract.json","rollback-receipt.json"})
    prior=_owner_file(rollback/"prior-provider-cost-contract.json")
    receipt=json.loads(_owner_file(rollback/"rollback-receipt.json"))
    body={key:receipt[key] for key in receipt if key!="content_hash"}
    if (set(body)!={"schema","prior_size","prior_sha256","prior_document_hash","target_document_hash","immutable"}
            or receipt.get("content_hash")!=_hash(body) or body.get("schema")!=REFRESH_SCHEMA
            or body.get("immutable") is not True or body.get("prior_size")!=len(prior)
            or body.get("prior_sha256")!=_hash_bytes(prior)
            or not isinstance(body.get("target_document_hash"),str) or len(body["target_document_hash"])!=64):
        raise ValueError("READINESS_ROLLBACK_INVALID")
    validate_prior_cost_contract_for_refresh(json.loads(prior))
    return receipt

def create_pricing_refresh_backup(*,target_document_hash:str,root:Path=READINESS_ROOT,
                                  rollback:Path=REFRESH_ROLLBACK_ROOT)->dict:
    _owner_root(root,exact_inventory={COST_CONTRACT_NAME,CREDENTIAL_STATUS_NAME})
    prior=_owner_file(root/COST_CONTRACT_NAME); old=json.loads(prior); validate_prior_cost_contract_for_refresh(old)
    _owner_file(root/CREDENTIAL_STATUS_NAME)
    if rollback.exists(): raise ValueError("READINESS_ROLLBACK_EXISTS")
    rollback.parent.mkdir(mode=0o700,parents=True,exist_ok=True); os.chmod(rollback.parent,0o700)
    building=rollback.parent/(rollback.name+".building")
    if building.exists(): shutil.rmtree(building)
    building.mkdir(mode=0o700)
    target=building/"prior-provider-cost-contract.json"
    descriptor=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(descriptor,"wb") as handle: handle.write(prior); handle.flush(); os.fsync(handle.fileno())
    body={"schema":REFRESH_SCHEMA,"prior_size":len(prior),"prior_sha256":_hash_bytes(prior),
          "prior_document_hash":old["document_hash"],"target_document_hash":target_document_hash,"immutable":True}
    _atomic(building,"rollback-receipt.json",body|{"content_hash":_hash(body)})
    _backup_value(building); os.replace(building,rollback)
    descriptor=os.open(rollback.parent,os.O_RDONLY)
    try: os.fsync(descriptor)
    finally: os.close(descriptor)
    return _backup_value(rollback)

def _bind_backup_target(rollback:Path,target_hash:str)->None:
    receipt=_backup_value(rollback)
    if receipt["target_document_hash"]!=target_hash: raise ValueError("READINESS_ROLLBACK_INVALID")

def restore_prior_pricing(*,root:Path=READINESS_ROOT,rollback:Path=REFRESH_ROLLBACK_ROOT)->str:
    receipt=_backup_value(rollback); prior=_owner_file(rollback/"prior-provider-cost-contract.json")
    stage=root/STAGE_NAME
    if stage.exists(): stage.unlink()
    temp=root/(COST_CONTRACT_NAME+".restore")
    if temp.exists(): temp.unlink()
    descriptor=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(descriptor,"wb") as handle: handle.write(prior); handle.flush(); os.fsync(handle.fileno())
    os.replace(temp,root/COST_CONTRACT_NAME); os.chmod(root/COST_CONTRACT_NAME,0o600)
    descriptor=os.open(root,os.O_RDONLY)
    try: os.fsync(descriptor)
    finally: os.close(descriptor)
    restored=_owner_file(root/COST_CONTRACT_NAME)
    if _hash_bytes(restored)!=receipt["prior_sha256"]: raise ValueError("READINESS_ROLLBACK_INVALID")
    validate_prior_cost_contract_for_refresh(json.loads(restored))
    return "PRIOR_PRICING_RESTORED"

def refresh_september_9_cost_contract(*,document:dict,root:Path=READINESS_ROOT,
        rollback:Path=REFRESH_ROLLBACK_ROOT,now:datetime|None=None,interrupt_at:str|None=None,
        post_select_validator=None)->str:
    current=datetime.now(timezone.utc) if now is None else now
    validate_september_9_cost_evidence(document,now=current)
    if interrupt_at=="before_backup": raise RuntimeError("SIMULATED_INTERRUPTION")
    stage=root/STAGE_NAME
    if stage.exists(): _owner_file(stage); stage.unlink()
    _owner_root(root,exact_inventory={COST_CONTRACT_NAME,CREDENTIAL_STATUS_NAME})
    _owner_file(root/CREDENTIAL_STATUS_NAME)
    current_raw=_owner_file(root/COST_CONTRACT_NAME); current_doc=json.loads(current_raw)
    if current_doc.get("schema")==SEPTEMBER_9_COST_SCHEMA:
        validate_september_9_cost_evidence(current_doc,now=current)
        receipt=_backup_value(rollback)
        if current_doc!=document or receipt["target_document_hash"]!=document["document_hash"]:
            raise ValueError("READINESS_REFRESH_CONFLICT")
        return "SEPTEMBER_9_COST_CONTRACT_ALREADY_INSTALLED"
    validate_prior_cost_contract_for_refresh(current_doc)
    if not rollback.exists(): create_pricing_refresh_backup(target_document_hash=document["document_hash"],root=root,rollback=rollback)
    else: _backup_value(rollback)
    if interrupt_at=="backup": raise RuntimeError("SIMULATED_INTERRUPTION")
    _bind_backup_target(rollback,document["document_hash"])
    descriptor=os.open(stage,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(descriptor,"wb") as handle: handle.write(_canonical(document)); handle.flush(); os.fsync(handle.fileno())
    staged=json.loads(_owner_file(stage)); validate_september_9_cost_evidence(staged,now=current)
    if interrupt_at=="staging": raise RuntimeError("SIMULATED_INTERRUPTION")
    if interrupt_at=="selection": raise RuntimeError("SIMULATED_INTERRUPTION")
    try:
        os.replace(stage,root/COST_CONTRACT_NAME)
        descriptor=os.open(root,os.O_RDONLY)
        try: os.fsync(descriptor)
        finally: os.close(descriptor)
        if interrupt_at=="after_selection": raise RuntimeError("SIMULATED_INTERRUPTION")
        selected=json.loads(_owner_file(root/COST_CONTRACT_NAME)); validate_september_9_cost_evidence(selected,now=current)
        if selected!=document: raise ValueError("READINESS_SELECTION_INVALID")
        if post_select_validator: post_select_validator(root)
    except Exception:
        restore_prior_pricing(root=root,rollback=rollback)
        raise
    _owner_root(root,exact_inventory={COST_CONTRACT_NAME,CREDENTIAL_STATUS_NAME})
    return "SEPTEMBER_9_COST_CONTRACT_INSTALLED"

def install_cost_contract(*,root:Path=READINESS_ROOT)->str:
    if (root/COST_CONTRACT_NAME).exists(): raise ValueError("COST_CONTRACT_DUPLICATE")
    _atomic(root,COST_CONTRACT_NAME,cost_contract_document()); return "COST_CONTRACT_INSTALLED"

def probe_credential_once(*,root:Path=READINESS_ROOT,runner=None,clock=None)->str:
    if (root/CREDENTIAL_STATUS_NAME).exists(): raise ValueError("CREDENTIAL_PRESENCE_ALREADY_CHECKED")
    from .financial_datasets import KEYCHAIN_ACCOUNT,KEYCHAIN_SERVICE
    try:
        result=(runner or SecurityCommandRunner()).exists(service=KEYCHAIN_SERVICE,account=KEYCHAIN_ACCOUNT)
        status="AVAILABLE" if result else "UNAVAILABLE"
    except RuntimeError as exc:
        status="ACCESS_DENIED" if str(exc)=="KEYCHAIN_COMMAND_FAILED" else "AMBIGUOUS"
    now=(clock or (lambda:datetime.now(timezone.utc)))()
    _atomic(root,CREDENTIAL_STATUS_NAME,{"schema":"iios-credential-presence-v1","status":status,"checked_at":now.isoformat()})
    return status

def main(argv=None)->int:
    p=argparse.ArgumentParser(); g=p.add_mutually_exclusive_group(required=True)
    g.add_argument("--install-reviewed-cost-contract",action="store_true")
    g.add_argument("--probe-credential-presence-once",action="store_true")
    g.add_argument("--readiness",action="store_true")
    g.add_argument("--refresh-september-9-cost-contract",action="store_true")
    p.add_argument("--observed-at"); p.add_argument("--expires-at"); p.add_argument("--observation-identity")
    p.add_argument("--browser",action="store_true",help=argparse.SUPPRESS)
    a=p.parse_args(argv)
    try:
        if a.browser: raise ValueError("BROWSER_INVOCATION_REJECTED")
        if a.install_reviewed_cost_contract: status=install_cost_contract()
        elif a.probe_credential_presence_once: status=probe_credential_once()
        elif a.refresh_september_9_cost_contract:
            document=september_9_cost_evidence_document(observed_at=a.observed_at,expires_at=a.expires_at,
                observation_identity=a.observation_identity)
            status=refresh_september_9_cost_contract(document=document)
        else: status=installed_readiness_projection()
        print(json.dumps({"status":status},sort_keys=True)); return 0
    except (OSError,TypeError,ValueError):
        print(json.dumps({"status":"READINESS_ADMIN_FAILED_CLOSED"},sort_keys=True)); return 5
if __name__=="__main__": raise SystemExit(main())
