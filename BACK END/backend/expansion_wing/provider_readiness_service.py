"""Fixed-path, non-spending administrator for Tuesday readiness metadata."""
from __future__ import annotations
import argparse, json, os
from datetime import datetime, timezone
from pathlib import Path
from .keychain_adapter import SecurityCommandRunner
from .provider_readiness import COST_CONTRACT_NAME, CREDENTIAL_STATUS_NAME, READINESS_ROOT, cost_contract_document, installed_readiness_projection

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
    a=p.parse_args(argv)
    try:
        status=install_cost_contract() if a.install_reviewed_cost_contract else probe_credential_once() if a.probe_credential_presence_once else installed_readiness_projection()
        print(json.dumps({"status":status},sort_keys=True)); return 0
    except (OSError,ValueError):
        print(json.dumps({"status":"READINESS_ADMIN_FAILED_CLOSED"},sort_keys=True)); return 5
if __name__=="__main__": raise SystemExit(main())
