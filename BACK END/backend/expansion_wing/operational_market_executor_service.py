"""Owner-only command surface for the disabled executor and SPY canary."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
from pathlib import Path
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from .financial_datasets import KEYCHAIN_SERVICE, SecurityFrameworkCredentialProvider
from .financial_datasets_tls import FinancialDatasetsHTTPSTransport, TrustBundlePolicy
from .keychain_adapter import KeychainAdapter, SecurityFrameworkAPI
from .provider_readiness import (READINESS_ROOT, CREDENTIAL_STATUS_NAME, installed_readiness_projection, operational_cost_binding,
    september_9_cost_evidence_document, september_9_request_plan,
    validate_september_9_cost_evidence)
from .operational_market_executor import (
    CANARY_PLAN, POST_0930_PLAN, ExecutorStore, FinancialDatasetsOperationalBoundary,
    OperationalMarketEvidenceCoordinator, OperationalPreflightResult, EndpointCertificationCoordinator, SEPTEMBER_9_RECOVERY_PLAN,
    EndpointCertificationStore, canary_plan, post_0930_plan, september_9_plan, september_9_intraday_recovery_plan,
    plan_identity,
)
from .operational_market_executor_installer import (INSTALL_ROOT, install_disabled,
    authorize_september_9_market_open_50, create_and_select_intraday_recovery, authorize_intraday_recovery,
    resolve_selected_state_root, upgrade_disabled, validate_installed)

TRUST_ROOT=Path.home()/"Library/Application Support/IIOS/ExpansionWingFinancialDatasets"
TRUST_BUNDLE=TRUST_ROOT/"cacert.pem"
TRUST_MANIFEST=TRUST_ROOT/"trust-manifest.json"
CERTIFICATION_ROOT=Path.home()/"Library/Application Support/IIOS/ProviderEndpointCertification31"

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
    from truth_spine_authority import require_capability
    require_capability('provider_requests')
    validate_installed()
    store=ExecutorStore(resolve_selected_state_root()); rows=store.read_plan()
    if rows not in (canary_plan(),post_0930_plan(),september_9_plan()) and not (rows and rows[0].get("plan")==SEPTEMBER_9_RECOVERY_PLAN and rows==september_9_intraday_recovery_plan(rows[0]["activation_time"])): raise ValueError("REQUEST_PLAN_MISMATCH")
    adapter=KeychainAdapter(SecurityFrameworkAPI(),service=KEYCHAIN_SERVICE)
    boundary=FinancialDatasetsOperationalBoundary(SecurityFrameworkCredentialProvider(adapter),FinancialDatasetsHTTPSTransport(_trust_policy()))
    coordinator=OperationalMarketEvidenceCoordinator(store,rows,boundary)
    if coordinator.preflight(verified_operational_preflight(coordinator))!="EXECUTOR_READY":
        raise ValueError("EXECUTOR_PREFLIGHT_FAILED_CLOSED")
    return coordinator

def production_boundary()->FinancialDatasetsOperationalBoundary:
    adapter=KeychainAdapter(SecurityFrameworkAPI(),service=KEYCHAIN_SERVICE)
    return FinancialDatasetsOperationalBoundary(SecurityFrameworkCredentialProvider(adapter),FinancialDatasetsHTTPSTransport(_trust_policy()))

def verified_operational_preflight(coordinator:OperationalMarketEvidenceCoordinator)->OperationalPreflightResult:
    """Build proof states only after each independent runtime check succeeds."""
    manifest=validate_installed()
    state=coordinator.store.read(); rows=coordinator.store.read_plan()
    coordinator.store.validate_root(); coordinator.boundary.validate()
    readiness=installed_readiness_projection()
    if readiness.get("credential_presence_state")!="AVAILABLE": raise ValueError("CREDENTIAL_PRESENCE_UNAVAILABLE")
    if manifest.get("installed_source_commit") is None: raise ValueError("EXECUTOR_INSTALLATION_INVALID")
    if state.get("plan_identity") != plan_identity(rows):
        raise ValueError("REQUEST_PLAN_MISMATCH")
    if not (coordinator.store.root/"receipts").is_dir(): raise ValueError("RECEIPT_STORE_INVALID")
    if rows and rows[0].get("plan")==SEPTEMBER_9_RECOVERY_PLAN:
        pricing=json.loads((coordinator.store.root/"recovery-pricing.json").read_text())
        clean=dict(pricing); supplied=clean.pop("content_hash",None)
        calculated=hashlib.sha256((json.dumps(clean,sort_keys=True,separators=(",",":"))+"\n").encode()).hexdigest()
        if (supplied!=calculated or pricing.get("plan_identity")!=state["plan_identity"]
                or pricing.get("exact_cost")!=len(rows) or pricing.get("retry")!=0):
            raise ValueError("OPERATIONAL_COST_BINDING_UNAVAILABLE")
        cost_hash=supplied
    else:
        binding=operational_cost_binding()
        if binding.get("request_plan_identity")!=state["plan_identity"]: raise ValueError("OPERATIONAL_COST_BINDING_UNAVAILABLE")
        cost_hash=binding["cost_contract_hash"]
    receipt_info=(coordinator.store.root/"receipts").stat()
    receipt_identity=hashlib.sha256(f"{receipt_info.st_dev}:{receipt_info.st_ino}:{stat.S_IMODE(receipt_info.st_mode)}".encode()).hexdigest()
    credential_hash=hashlib.sha256((READINESS_ROOT/CREDENTIAL_STATUS_NAME).read_bytes()).hexdigest()
    trust_hash=hashlib.sha256(TRUST_MANIFEST.read_bytes()).hexdigest()
    manifest_hash=manifest.get("canonical_manifest_content_hash") or hashlib.sha256(json.dumps(manifest,sort_keys=True,separators=(",",":")).encode()).hexdigest()
    bindings=(manifest_hash,state["plan_identity"],state["content_hash"],cost_hash,credential_hash,trust_hash,receipt_identity)
    states={"immutable_policy":"VALID","executor":"INSTALLED_VALID","credential_presence":"AVAILABLE",
        "tls_trust":"READY","cost_contract":"VALID","request_plan":"VALID","state_store":"VALID","receipt_store":"VALID"}
    return OperationalPreflightResult.from_verified_evidence(verified_at=datetime.now(timezone.utc),evidence_bindings=bindings,**states)

def run_endpoint_certification(*,authorized_commit:str)->str:
    manifest=validate_installed()
    if manifest.get("installed_source_commit")!=authorized_commit: raise ValueError("CERTIFICATION_COMMIT_MISMATCH")
    store=EndpointCertificationStore(CERTIFICATION_ROOT)
    store.initialize()
    state=EndpointCertificationCoordinator(store,production_boundary()).run()
    return state["phase"]

def run_canary()->str:
    coordinator=production_coordinator()
    if coordinator.preflight(verified_operational_preflight(coordinator))!="EXECUTOR_READY": raise ValueError("CANARY_PREFLIGHT_FAILED_CLOSED")
    state=coordinator.store.read()
    if state["classification"]!=CANARY_PLAN or state["planned"]!=1 or state["confirmed_credits"]+state["ambiguous_credits"]>0:
        raise ValueError("CANARY_ALREADY_TERMINAL")
    coordinator.release(1)
    try: return coordinator.execute(canary_plan()[0]["identity"])
    finally:
        final=coordinator.store.read()
        if final["released_credits"]!=0: coordinator.close("CANARY_TERMINAL_SAFETY_CLOSE")

def transition_post_0930()->str:
    coordinator=production_coordinator(); now=datetime.now(ZoneInfo("America/Los_Angeles"))
    readiness=installed_readiness_projection(); binding=operational_cost_binding()
    if readiness.get("credential_presence_state")!="AVAILABLE" or binding.get("exact_planned_cost_credits")!=50:
        raise ValueError("POST_0930_PREFLIGHT_FAILED_CLOSED")
    if coordinator.preflight(verified_operational_preflight(coordinator))!="EXECUTOR_READY": raise ValueError("POST_0930_PREFLIGHT_FAILED_CLOSED")
    coordinator.migrate_canary_to_post_0930(now)
    coordinator.release(19)
    result=coordinator.scheduled_tick(now)
    state=coordinator.store.read()
    if state["phase"]=="FAILED_CLOSED" or state["released_credits"]==0 and state["completed"]<10:
        raise ValueError(state.get("failure_category") or "POST_0930_EXECUTION_FAILED_CLOSED")
    return "POST_0930_PARTIAL_SESSION_RUNNING:"+result

def validate_september_9_readiness(*,observed_at:str,expires_at:str,observation_identity:str,
                                   command_time:datetime|None=None)->str:
    """Non-spending administrative validation; never reads Keychain or operational state."""
    document=september_9_cost_evidence_document(observed_at=observed_at,expires_at=expires_at,
        observation_identity=observation_identity)
    validate_september_9_cost_evidence(document,now=command_time or datetime.now(ZoneInfo("UTC")))
    provider_rows=september_9_request_plan(); executor_rows=september_9_plan()
    if (provider_rows!=executor_rows or len(provider_rows)!=50 or len({r["identity"] for r in provider_rows})!=50):
        raise ValueError("SEPTEMBER_9_REQUEST_PLAN_INVALID")
    if any(r["session_date"]!="2026-09-09" or r["retry"] is not False or r["cost"]!=1 for r in executor_rows):
        raise ValueError("SEPTEMBER_9_REQUEST_PLAN_INVALID")
    return "SEPTEMBER_9_READINESS_VALIDATED_NOT_INSTALLED"

def main(argv:list[str]|None=None)->int:
    parser=argparse.ArgumentParser(); group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--install-disabled",action="store_true")
    group.add_argument("--validate-installed",action="store_true")
    group.add_argument("--upgrade-disabled",action="store_true")
    group.add_argument("--run-spy-canary",action="store_true")
    group.add_argument("--transition-post-0930",action="store_true")
    group.add_argument("--validate-september-9-readiness",action="store_true")
    group.add_argument("--authorize-september-9-market-open-50",action="store_true")
    group.add_argument("--run-provider-endpoint-certification",action="store_true")
    group.add_argument("--create-intraday-recovery",action="store_true")
    group.add_argument("--authorize-intraday-recovery",action="store_true")
    parser.add_argument("--source-root"); parser.add_argument("--authorized-commit")
    parser.add_argument("--supervisor-manifest-identity")
    parser.add_argument("--owner-authorized",action="store_true"); parser.add_argument("--browser",action="store_true",help=argparse.SUPPRESS)
    parser.add_argument("--cost-observed-at"); parser.add_argument("--cost-expires-at"); parser.add_argument("--cost-observation-identity")
    parser.add_argument("--activation-time")
    args=parser.parse_args(argv)
    try:
        if args.browser: raise ValueError("BROWSER_INVOCATION_REJECTED")
        if args.install_disabled:
            if not args.source_root or not args.authorized_commit: raise ValueError("INSTALL_AUTHORIZATION_MISSING")
            status=install_disabled(Path(args.source_root).resolve(),args.authorized_commit)
        elif args.validate_installed:
            validate_installed(); status="EXECUTOR_INSTALLATION_VALID"
        elif args.upgrade_disabled:
            if not args.source_root or not args.authorized_commit: raise ValueError("INSTALL_AUTHORIZATION_MISSING")
            status=upgrade_disabled(Path(args.source_root).resolve(),args.authorized_commit)
        elif args.run_spy_canary:
            if not args.owner_authorized: raise ValueError("OWNER_CANARY_AUTHORIZATION_REQUIRED")
            status=run_canary()
        elif args.transition_post_0930:
            if not args.owner_authorized: raise ValueError("OWNER_PARTIAL_SESSION_AUTHORIZATION_REQUIRED")
            status=transition_post_0930()
        elif args.authorize_september_9_market_open_50:
            if not args.owner_authorized or not args.supervisor_manifest_identity: raise ValueError("OWNER_MARKET_OPEN_AUTHORIZATION_REQUIRED")
            from .unattended_supervisor_installer import INSTALL_ROOT as SUPERVISOR_ROOT,_service_probe
            status=authorize_september_9_market_open_50(expected_commit=args.authorized_commit or "",
                supervisor_root=SUPERVISOR_ROOT,supervisor_manifest_identity=args.supervisor_manifest_identity,service_probe=_service_probe)
        elif args.run_provider_endpoint_certification:
            if not args.owner_authorized or not args.authorized_commit: raise ValueError("OWNER_CERTIFICATION_AUTHORIZATION_REQUIRED")
            status=run_endpoint_certification(authorized_commit=args.authorized_commit)
        elif args.create_intraday_recovery:
            if not args.owner_authorized or not args.authorized_commit or not args.activation_time: raise ValueError("OWNER_RECOVERY_AUTHORIZATION_REQUIRED")
            status=create_and_select_intraday_recovery(activation_time=args.activation_time,authorized_commit=args.authorized_commit)
        elif args.authorize_intraday_recovery:
            if not args.owner_authorized: raise ValueError("OWNER_RECOVERY_AUTHORIZATION_REQUIRED")
            status=authorize_intraday_recovery()
        else:
            if not all((args.cost_observed_at,args.cost_expires_at,args.cost_observation_identity)):
                raise ValueError("SEPTEMBER_9_COST_EVIDENCE_MISSING")
            status=validate_september_9_readiness(observed_at=args.cost_observed_at,
                expires_at=args.cost_expires_at,observation_identity=args.cost_observation_identity)
        print(json.dumps({"status":status},sort_keys=True)); return 0
    except (OSError,ValueError,RuntimeError) as exc:
        category=str(exc)
        if not category.isupper() or len(category)>72: category="EXECUTOR_COMMAND_FAILED_CLOSED"
        print(json.dumps({"status":category},sort_keys=True)); return 5

if __name__=="__main__": raise SystemExit(main())
