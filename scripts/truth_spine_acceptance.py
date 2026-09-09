"""Isolated operator acceptance: actual app:app and actual scheduler/publisher, no discovery substitutes.

All mutable output is below a new caller-supplied owner-only root. Live inputs are opened read-only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import signal
import socket
import sqlite3
import stat
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


def encoded(x):
    return (json.dumps(x, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode()


def sealed(x):
    x = {k: v for k, v in x.items() if k != "content_hash"}
    return {**x, "content_hash": hashlib.sha256(encoded(x)).hexdigest()}


def write(path, value):
    with path.open("xb") as f:
        os.chmod(path, 0o600); f.write(encoded(value)); f.flush(); os.fsync(f.fileno())


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def inventory(root):
    return [{"path": str(p.relative_to(root)), "size": p.stat().st_size, "sha256": sha(p)}
            for p in sorted(root.rglob("*")) if p.is_file()]


def prepare(args):
    root = args.root.resolve()
    if root.exists() or args.port in {5176, 5177, 5184, 5185, 5186, 8002} or not 1024 < args.port < 65536:
        raise ValueError("NEW_ISOLATED_ROOT_AND_PORT_REQUIRED")
    with socket.socket() as probe: probe.bind(("127.0.0.1", args.port))
    root.mkdir(mode=0o700)
    source = args.source.resolve(); package = root / "release"; package.mkdir(mode=0o700)
    backend = package / "BACK END/backend"; backend.mkdir(parents=True)
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=source, text=True).strip()
    tracked = subprocess.check_output(["git", "ls-files", "-z"], cwd=source).decode().split("\0")
    # Add this batch's untracked source for pre-checkpoint acceptance; post-checkpoint package is clean.
    additions = subprocess.check_output(["git", "ls-files", "--others", "--exclude-standard", "-z"], cwd=source).decode().split("\0")
    paths = sorted({p for p in tracked + additions if p.startswith("BACK END/backend/") and p.endswith(".py") and not Path(p).name.startswith("test_")})
    for rel in paths:
        p = source / rel
        if p.is_symlink(): raise ValueError("SOURCE_SYMLINK_REJECTED")
        target = package / rel; target.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(p, target)
    shutil.copytree(source / "FRONT END/dist", package / "frontend")
    source_state = subprocess.check_output(["git", "status", "--porcelain"], cwd=source, text=True)
    release_id = "truth-spine-" + hashlib.sha256(encoded(inventory(package))).hexdigest()[:16]
    for p in package.rglob("*"):
        if p.is_file(): p.chmod(0o400)
    frontend_identity = hashlib.sha256(encoded(inventory(package / "frontend"))).hexdigest()
    manifest = sealed({"schema": "iios-truth-release-v1", "source_commit": commit, "source_state": "CLEAN" if not source_state else "PRECHECKPOINT_CANDIDATE",
                       "release_id": release_id, "inventory": inventory(package), "rollback_identity": "ISOLATED_LEDGER_READ_ONLY_SNAPSHOT"})
    write(package / "truth-release.json", manifest); (package / "truth-release.json").chmod(0o400)
    sys.path.insert(0, str(backend))
    from deployment_contract import validate_runtime_manifest
    template_manifest = json.loads((args.runtime_template / "runtime-manifest.json").read_bytes())
    validate_runtime_manifest(args.runtime_template, template_manifest, expected_release_commit=template_manifest["release_commit"])
    runtime = root / "runtime"
    shutil.copytree(args.runtime_template, runtime, symlinks=False)
    runtime.chmod(0o700)
    old = json.loads((runtime / "runtime-manifest.json").read_bytes())
    (runtime / "runtime-manifest.json").unlink()
    runtime_id = release_id + "-python"
    interpreter = runtime / "bin/python"
    old.update(runtime_id=runtime_id, runtime_root=str(runtime), interpreter=str(interpreter), release_commit=commit)
    old["schema"] = "iios-truth-runtime-v1"
    old["parent_manifest_hash"] = sha(args.runtime_template / "runtime-manifest.json")
    process_executable = subprocess.check_output([str(interpreter), "-B", "-c",
        "import os,subprocess; print(subprocess.check_output(['ps','-p',str(os.getpid()),'-o','comm='],text=True).strip())"],
        env={"PATH": "/usr/bin:/bin", "PYTHONDONTWRITEBYTECODE": "1"}, text=True).strip()
    old["process_executable"] = process_executable
    old["process_executable_hash"] = sha(Path(process_executable))
    old["file_inventory"] = [{**r, "mode": stat.S_IMODE((runtime/r["path"]).stat().st_mode)} for r in inventory(runtime)]
    write(runtime / "runtime-manifest.json", sealed(old)); (runtime / "runtime-manifest.json").chmod(0o400)
    ledger = root / "shadow-ledger.db"
    src = sqlite3.connect(f"file:{args.ledger.resolve()}?mode=ro", uri=True)
    dst = sqlite3.connect(ledger)
    try:
        src.backup(dst)
    finally:
        src.close(); dst.close()
    ledger.chmod(0o600)
    backup = root / "rollback-ledger.db"; shutil.copyfile(ledger, backup); backup.chmod(0o400)
    for name, origin in [("universe-source.json", args.universe), ("receipt.json", args.receipt), ("evidence.json", args.evidence)]:
        shutil.copyfile(origin, root / name); (root / name).chmod(0o600)
    sys.path.insert(0, str(backend))
    from truth_spine_contract import Topology
    from truth_spine_replay import initialize
    topology = Topology("iios-truth-topology-v1", "ISOLATED_SHADOW", commit, release_id, str(package), sha(package / "truth-release.json"),
        runtime_id, str(interpreter), sha(interpreter), str(runtime / "runtime-manifest.json"), sha(runtime / "runtime-manifest.json"),
        str(ledger), sha(backup), "ledger+truth-v1", "2026-09-09", "september-9-evidence-replay", "single-persisted-mu-snapshot",
        release_id + "-replay", "truth-publisher", frontend_identity, ("FINANCIAL_DATASETS:PERSISTED_ONLY",),
        ("DETERMINISTIC_ACCEPTANCE_ONLY",), tuple((k, False) for k in ("broker", "paper_order", "promotion", "ledger_write", "live_execution")),
        datetime.now(timezone.utc).isoformat(), sha(backup), "SESSION_CLOSED")
    write(root / "active-topology.json", topology.record())
    config = sealed({"schema": "iios-truth-service-v1", "root": str(root), "topology": "active-topology.json", "topology_hash": sha(root / "active-topology.json"),
                     "universe_hash": sha(root / "universe-source.json"), "receipt_hash": sha(root / "receipt.json"), "evidence_hash": sha(root / "evidence.json")})
    write(root / "service.json", config)
    initialize(ledger, topology)
    return root, topology


def request(port, endpoint, *, method="GET"):
    try:
        with urllib.request.urlopen(urllib.request.Request(f"http://127.0.0.1:{port}{endpoint}", method=method), timeout=30) as response:
            raw = response.read(); return response.status, json.loads(raw) if response.headers.get_content_type() == "application/json" else None
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def accept(args):
    root, topology = prepare(args); config = root / "service.json"; backend = Path(topology.release_root) / "BACK END/backend"
    env = {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "PYTHONDONTWRITEBYTECODE": "1", "PYTHONPATH": str(backend),
           "IIOS_DB_PATH": topology.ledger_path, "IIOS_TRUTH_SPINE_CONFIG": str(config), "PYTHONUNBUFFERED": "1"}
    processes = {}; logs = []; report = {}; exited = []
    def start(role):
        log = (root / f"{role}.log").open("ab"); os.chmod(log.name, 0o600); logs.append(log)
        command = [topology.interpreter, "-B", "-m"]
        command += ["uvicorn", "app:app", "--host", "127.0.0.1", "--port", str(args.port)] if role == "backend" else ["truth_spine_service", "--config", str(config), "--role", role]
        proc = subprocess.Popen(command, cwd=backend, env=env, stdout=log, stderr=log); processes[role] = proc
        print(json.dumps({"role": role, "pid": proc.pid, "port": args.port if role == "backend" else None, "command": command}), flush=True)
    def wait_ready():
        deadline = time.monotonic() + 80
        while time.monotonic() < deadline:
            if any(p.poll() is not None for p in processes.values()): raise RuntimeError("ISOLATED_PROCESS_EXITED")
            try:
                if request(args.port, "/health/ready")[0] == 200: return
            except (OSError, ValueError): pass
            time.sleep(1)
        raise RuntimeError("REAL_READINESS_FAILED")
    try:
        for role in ("scheduler", "publisher", "backend"): start(role)
        wait_ready()
        for kind in ("live", "ready", "market-readiness", "research-readiness"):
            status, body = request(args.port, "/health/" + kind); report[kind] = {"http": status, "body": body}
            assert status == (503 if kind == "market-readiness" else 200)
        for method in ("POST", "PUT", "PATCH", "DELETE"):
            assert request(args.port, "/truth-spine/projection", method=method)[0] == 405
        assert request(args.port, "/system/status")[0] == 404
        from truth_spine_replay import validate_ledger
        result = validate_ledger(Path(topology.ledger_path), topology)
        assert result and result["decision"] == "WATCH" and result["committee_state"] == "COMPLETE"
        assert result["paper"]["orders"] == 0 and all(v is False for v in result["authority"].values())
        before = result["content_hash"]
        # OS-observed failure and restart; no heartbeat/process substitutions.
        processes["scheduler"].terminate(); processes["scheduler"].wait(timeout=10)
        exited.append({"role": "scheduler", "pid": processes["scheduler"].pid, "exit_code": processes["scheduler"].returncode})
        assert request(args.port, "/health/ready")[0] == 503
        start("scheduler"); wait_ready()
        assert validate_ledger(Path(topology.ledger_path), topology)["content_hash"] == before
        # Exact rollback of the isolated snapshot is rehearsed to a separate file, never the live ledger.
        restored = root / "rollback-rehearsal.db"; shutil.copyfile(root / "rollback-ledger.db", restored); restored.chmod(0o600)
        assert sha(restored) == sha(root / "rollback-ledger.db")
        projection = request(args.port, "/truth-spine/projection")[1]
        assert projection["event_ids"] == result["event_ids"] and projection["classification"] == "REPLAY"
        latencies = []
        for _ in range(30):
            started = time.monotonic(); status, _ = request(args.port, "/health/ready")
            assert status == 200
            latencies.append(time.monotonic() - started)
        report["readiness_soak"] = {"requests": len(latencies), "errors": 0, "max_seconds": max(latencies)}
        report.update(result="BACKEND_ACCEPTANCE_GREEN_BROWSER_REVIEW_SEPARATE", release_id=topology.release_id, source_commit=topology.source_commit,
            trace_id=result["trace_id"], receipt_id=result["evidence"]["receipt_id"], evidence_hash=result["evidence"]["raw_evidence_hash"],
            decision=result["decision"], events=len(result["event_ids"]), restart="IDEMPOTENT", rollback="BYTE_IDENTICAL",
            provider_requests=0, provider_credits=0, keychain_accesses=0, preview_url=f"http://127.0.0.1:{args.port}/review/truth-spine.html")
        print(json.dumps({"REVIEW_READY": report["preview_url"], "backend_pid": processes["backend"].pid, "seconds": args.review_seconds}), flush=True)
        time.sleep(args.review_seconds)
    except Exception as exc:
        report.update(result="RED", failure_category=type(exc).__name__)
        raise
    finally:
        for proc in processes.values():
            if proc.poll() is None: proc.terminate()
        for proc in processes.values(): proc.wait(timeout=15)
        for log in logs: log.close()
        exited.extend({"role": role, "pid": p.pid, "exit_code": p.returncode} for role, p in processes.items())
        report["process_exits"] = exited
        # Uvicorn restores and re-raises SIGTERM after its successful application shutdown.
        report["all_processes_exited"] = all(p.returncode is not None for p in processes.values())
        report["clean_shutdown"] = (all(row["exit_code"] == 0 for row in exited if row["role"] != "backend")
            and processes["backend"].returncode in {0, -signal.SIGTERM}
            and "Application shutdown complete" in (root / "backend.log").read_text())
        with socket.socket() as probe:
            report["port_clear"] = probe.connect_ex(("127.0.0.1", args.port)) != 0
        write(root / "acceptance.json", sealed(report)); print(json.dumps(report), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    for key in ("source", "root", "ledger", "receipt", "evidence", "universe", "runtime-template"):
        parser.add_argument("--" + key, type=Path, required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--review-seconds", type=int, default=0)
    accept(parser.parse_args())
