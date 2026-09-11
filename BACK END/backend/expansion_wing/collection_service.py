"""Explicit collection CLI. Import and disabled validation never construct credentials."""
from __future__ import annotations

import argparse
import json
import os
import signal
import time
from datetime import datetime, timezone
from pathlib import Path

from .collection_plan import (KEYCHAIN_ACCOUNT, KEYCHAIN_SERVICE, SessionPlan,
                              canonical, require_plan, verify_document)
from .collection_runtime import install_disabled, validate_installed
from .collection_session import CollectionSession, Journal, exclusive, read_bytes


def documents(root, account_hash, authority_hash):
    account = json.loads(read_bytes(root / "inputs" / "account.json"))
    grant = json.loads(read_bytes(root / "inputs" / "authority.json"))
    verify_document(account, account_hash)
    verify_document(grant, authority_hash)
    return account, grant


class CollectionCredentials:
    """Collection-only selector; never fall back to the legacy provider selector."""
    def __init__(self, adapter):
        if adapter.service != KEYCHAIN_SERVICE.encode("ascii"):
            raise ValueError("FINANCIAL_DATASETS_SELECTOR_REQUIRED")
        self.adapter = adapter

    def retrieve(self):
        from .financial_datasets import CREDENTIAL_MIN_BYTES, CREDENTIAL_MAX_BYTES, validate_credential
        try:
            value = self.adapter.retrieve_opaque(KEYCHAIN_ACCOUNT,
                minimum_bytes=CREDENTIAL_MIN_BYTES, maximum_bytes=CREDENTIAL_MAX_BYTES)
        except RuntimeError as exc:
            category = str(exc)
            if category in {"KEY_RECORD_MISSING", "KEY_RECORD_INACCESSIBLE_OR_AMBIGUOUS", "INVALID_KEYCHAIN_QUERY"}:
                raise RuntimeError(category) from None
            raise RuntimeError("KEYCHAIN_UNAVAILABLE") from None
        return validate_credential(value)


def production_boundary(root, manifest, stopped, *, plan):
    require_plan(plan)
    # Imports are deliberately delayed until a verified, armed tick is eligible.
    from .collection_transport import CollectionBoundary
    from .financial_datasets_tls import FinancialDatasetsHTTPSTransport, TrustBundlePolicy
    from .keychain_adapter import KeychainAdapter, SecurityFrameworkAPI
    credentials = CollectionCredentials(KeychainAdapter(SecurityFrameworkAPI(), service=KEYCHAIN_SERVICE))
    transport = FinancialDatasetsHTTPSTransport(TrustBundlePolicy(root / "release" / "cacert.pem",
                                              manifest["files"]["cacert.pem"]["sha256"]))
    return CollectionBoundary(credentials, transport, plan=plan, stopped=stopped)


class DeferredBoundary:
    def __init__(self, factory):
        self.factory = factory

    def request(self, row, deadline):
        return self.factory().request(row, deadline)


def supervise(session, *, stop_requested, sleep=time.sleep):
    while not stop_requested():
        status = session.tick()
        if status in ("CLOSED", "FAILED_CLOSED", "DISABLED"):
            return status
        sleep(1)
    session.journal.disarm(session.clock())
    session.tick()
    return "STOPPED"


def main(argv=None, *, clock=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("install-disabled", "validate", "arm", "supervise", "disarm"))
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--release-sha256", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--session-date", required=True, help="Explicit YYYY-MM-DD XNYS session; no date inference")
    parser.add_argument("--payload", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--account", type=Path)
    parser.add_argument("--authority", type=Path)
    parser.add_argument("--account-sha256")
    parser.add_argument("--authority-sha256")
    args = parser.parse_args(argv)
    # Dependency injection is for synthetic native tests only. The CLI exposes no
    # clock override and the installed byte inventory rejects altered entrypoints.
    clock = clock or (lambda: datetime.now(timezone.utc))
    try:
        plan = SessionPlan(args.session_date)
        if args.command == "install-disabled":
            if args.payload is None or args.manifest is None:
                raise ValueError("COMPLETE_RELEASE_INPUTS_REQUIRED")
            result = install_disabled(args.root, args.payload, args.manifest, args.release_sha256, args.source_commit, plan=plan)
        else:
            executing = args.command in ("arm", "supervise")
            verify = lambda: validate_installed(args.root, args.release_sha256, args.source_commit, plan=plan, executing=executing)
            manifest = verify()
            journal = Journal(args.root, args.release_sha256, plan=plan)
            if args.command == "validate":
                print(json.dumps({"status": "VALIDATED_NO_CREDENTIAL_ACCESS", "armed": bool(journal.events())}))
                return 0
            if args.command == "disarm":
                journal.disarm(clock())
                result = "DISARMED_NO_PROCESS_KILL"
            else:
                if args.command == "arm":
                    if args.account is None or args.authority is None:
                        raise ValueError("INDEPENDENT_ACCOUNT_AND_OWNER_INPUTS_REQUIRED")
                    account = json.loads(read_bytes(args.account))
                    grant = json.loads(read_bytes(args.authority))
                    verify_document(account, args.account_sha256)
                    verify_document(grant, args.authority_sha256)
                else:
                    account, grant = documents(args.root, args.account_sha256, args.authority_sha256)
                stopped = [False]
                session = CollectionSession(journal, account, args.account_sha256, grant, args.authority_sha256,
                    clock=clock, verify_runtime=verify, boundary=DeferredBoundary(
                        lambda: production_boundary(args.root, manifest, lambda: stopped[0] or journal.disarmed(), plan=plan)))
                if args.command == "arm":
                    session.gates(arming=True)
                    # Inputs are fresh, exclusive and become parents of the arm receipt.
                    exclusive(args.root / "inputs" / "account.json", canonical(account))
                    exclusive(args.root / "inputs" / "authority.json", canonical(grant))
                    session.arm()
                    result = "ARMED"
                else:
                    def stop(_signum, _frame):
                        stopped[0] = True
                    previous = {sig: signal.getsignal(sig) for sig in (signal.SIGTERM, signal.SIGINT)}
                    try:
                        for sig in previous:
                            signal.signal(sig, stop)
                        try:
                            with journal.lock("supervisor.lock"):
                                with journal.lock():
                                    if journal.events():
                                        journal.append("SUPERVISOR_STARTED", clock(), pid=os.getpid(), ppid=os.getppid(),
                                            executable=manifest["runtime"]["executable"], root=str(args.root),
                                            release_sha256=args.release_sha256, authority_sha256=args.authority_sha256)
                                result = supervise(session, stop_requested=lambda: stopped[0])
                        except BlockingIOError:
                            print(json.dumps({"status": "DUPLICATE_STARTUP_REJECTED"}))
                            return 75
                    finally:
                        for sig, handler in previous.items():
                            signal.signal(sig, handler)
        print(json.dumps({"status": result}))
        return 78 if result == "FAILED_CLOSED" else 0
    except Exception:
        # Preserve a fresh diagnostic when the root is admitted. No exception text.
        try:
            journal = Journal(args.root, args.release_sha256, plan=SessionPlan(args.session_date))
            with journal.lock():
                journal.append("FAILED", clock(), category="SERVICE_FAILED_CLOSED", released_credits=0)
        except Exception:
            pass
        print(json.dumps({"status": "SERVICE_FAILED_CLOSED"}))
        return 78  # LaunchAgent has no automatic restart; failure remains a failure.


if __name__ == "__main__":
    raise SystemExit(main())
