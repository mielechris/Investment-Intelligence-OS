"""Owner-only command surface for the disabled executor and SPY canary."""
from __future__ import annotations

import argparse
import json
import os
import stat
from pathlib import Path

from .financial_datasets import KEYCHAIN_SERVICE, SecurityFrameworkCredentialProvider
from .financial_datasets_tls import FinancialDatasetsHTTPSTransport, TrustBundlePolicy
from .keychain_adapter import KeychainAdapter, SecurityFrameworkAPI
from .operational_market_executor import (
    CANARY_PLAN, ExecutorStore, FinancialDatasetsOperationalBoundary,
    OperationalMarketEvidenceCoordinator, canary_plan,
)
from .operational_market_executor_installer import INSTALL_ROOT, STATE_ROOT, install_disabled, validate_installed

TRUST_ROOT=Path.home()/"Library/Application Support/IIOS/ExpansionWingFinancialDatasets"
TRUST_BUNDLE=TRUST_ROOT/"cacert.pem"
TRUST_MANIFEST=TRUST_ROOT/"trust-manifest.json"

def _trust_policy()->TrustBundlePolicy:
    info=TRUST_MANIFEST.lstat()
    if TRUST_MANIFEST.is_symlink() or not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or info.st_mode&(stat.S_IWGRP|stat.S_IWOTH):
        raise ValueError("TRUST_MANIFEST_INVALID")
    value=json.loads(TRUST_MANIFEST.read_text())
    if (value.get("trust_state")!="READY" or value.get("approved_host")!="api.financialdatasets.ai"
            or value.get("approved_port")!=443 or value.get("certificate_verification_required") is not True
            or value.get("hostname_verification_required") is not True or value.get("minimum_tls")!="TLS_1_2"):
        raise ValueError("TRUST_MANIFEST_INVALID")
    return TrustBundlePolicy(TRUST_BUNDLE,value.get("ca_bundle_sha256"))

def production_coordinator()->OperationalMarketEvidenceCoordinator:
    validate_installed()
    store=ExecutorStore(STATE_ROOT); rows=store.read_plan()
    if rows!=canary_plan(): raise ValueError("CANARY_PLAN_MISMATCH")
    adapter=KeychainAdapter(SecurityFrameworkAPI(),service=KEYCHAIN_SERVICE)
    boundary=FinancialDatasetsOperationalBoundary(SecurityFrameworkCredentialProvider(adapter),FinancialDatasetsHTTPSTransport(_trust_policy()))
    return OperationalMarketEvidenceCoordinator(store,rows,boundary)

def run_canary()->str:
    coordinator=production_coordinator()
    gates={key:True for key in {"immutable_policy","executor","credential_presence","tls_trust","cost_contract","request_plan","state_store","receipt_store"}}
    if coordinator.preflight(gates)!="EXECUTOR_READY": raise ValueError("CANARY_PREFLIGHT_FAILED_CLOSED")
    state=coordinator.store.read()
    if state["classification"]!=CANARY_PLAN or state["planned"]!=1 or state["confirmed_credits"]+state["ambiguous_credits"]>0:
        raise ValueError("CANARY_ALREADY_TERMINAL")
    coordinator.release(1)
    try: return coordinator.execute(canary_plan()[0]["identity"])
    finally:
        final=coordinator.store.read()
        if final["released_credits"]!=0: coordinator.close("CANARY_TERMINAL_SAFETY_CLOSE")

def main(argv:list[str]|None=None)->int:
    parser=argparse.ArgumentParser(); group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--install-disabled",action="store_true")
    group.add_argument("--validate-installed",action="store_true")
    group.add_argument("--run-spy-canary",action="store_true")
    parser.add_argument("--source-root"); parser.add_argument("--authorized-commit")
    parser.add_argument("--owner-authorized",action="store_true"); parser.add_argument("--browser",action="store_true",help=argparse.SUPPRESS)
    args=parser.parse_args(argv)
    try:
        if args.browser: raise ValueError("BROWSER_INVOCATION_REJECTED")
        if args.install_disabled:
            if not args.source_root or not args.authorized_commit: raise ValueError("INSTALL_AUTHORIZATION_MISSING")
            status=install_disabled(Path(args.source_root).resolve(),args.authorized_commit)
        elif args.validate_installed:
            validate_installed(); status="EXECUTOR_INSTALLATION_VALID"
        else:
            if not args.owner_authorized: raise ValueError("OWNER_CANARY_AUTHORIZATION_REQUIRED")
            status=run_canary()
        print(json.dumps({"status":status},sort_keys=True)); return 0
    except (OSError,ValueError,RuntimeError) as exc:
        category=str(exc)
        if not category.isupper() or len(category)>72: category="EXECUTOR_COMMAND_FAILED_CLOSED"
        print(json.dumps({"status":category},sort_keys=True)); return 5

if __name__=="__main__": raise SystemExit(main())
