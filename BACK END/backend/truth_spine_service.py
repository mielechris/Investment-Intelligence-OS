"""Actual disabled scheduler, automatic publisher and read-only backend integration."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import signal
import sqlite3
import stat
import subprocess
import sys
import threading
from decimal import Decimal
from datetime import datetime, timezone
from pathlib import Path

from truth_spine_contract import Topology, bind, canonical, locked, normalize, seal, universe, utc, verified
from truth_spine_replay import connect, registered_agents, replay, validate_ledger


def read(path: Path) -> dict:
    info = path.lstat()
    if path.is_symlink() or not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise ValueError("OWNER_ONLY_ARTIFACT_REQUIRED")
    if not 0 < info.st_size <= 4_000_000:
        raise ValueError("ARTIFACT_SIZE_INVALID")
    return json.loads(path.read_bytes())


def atomic(path: Path, value: dict) -> None:
    if path.is_symlink() or path.parent.is_symlink():
        raise ValueError("SYMLINK_REJECTED")
    temp = path.with_name("." + path.name + ".tmp")
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(canonical(value)); f.flush(); os.fsync(f.fileno())
        os.replace(temp, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        temp.unlink(missing_ok=True)


def sha(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise ValueError("REGULAR_ARTIFACT_REQUIRED")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def configuration(path: Path) -> tuple[dict, Topology]:
    config = verified(read(path))
    required = {"schema", "root", "topology", "topology_hash", "universe_hash", "receipt_hash", "evidence_hash", "content_hash"}
    if set(config) != required or config["schema"] != "iios-truth-service-v1":
        raise ValueError("SERVICE_CONFIG_INVALID")
    root = Path(config["root"])
    if root != path.parent or root.is_symlink() or root.stat().st_mode & 0o077 or root.stat().st_uid != os.getuid():
        raise ValueError("ISOLATION_ROOT_INVALID")
    topology_file = root / "active-topology.json"
    if config["topology"] != topology_file.name or sha(topology_file) != config["topology_hash"]:
        raise ValueError("ACTIVE_TOPOLOGY_MISSING_OR_MISMATCHED")
    topology = Topology.parse(read(topology_file))
    if topology.mode != "ISOLATED_SHADOW" or Path(topology.ledger_path) != root / "shadow-ledger.db":
        raise ValueError("ONLY_ISOLATED_SHADOW_SUPPORTED")
    for name, key in [("universe-source.json", "universe_hash"), ("receipt.json", "receipt_hash"), ("evidence.json", "evidence_hash")]:
        if sha(root / name) != config[key]:
            raise ValueError("INPUT_ARTIFACT_MISMATCH")
    return config, topology


def release_check(topology: Topology) -> None:
    root = Path(topology.release_root)
    manifest_path = root / "truth-release.json"
    if sha(manifest_path) != topology.release_manifest_hash:
        raise ValueError("RELEASE_MANIFEST_MISMATCH")
    manifest = verified(read(manifest_path))
    if manifest["source_commit"] != topology.source_commit or manifest["release_id"] != topology.release_id:
        raise ValueError("RELEASE_IDENTITY_MISMATCH")
    expected = {"truth-release.json"}
    for row in manifest["inventory"]:
        p = root / row["path"]
        if ".." in Path(row["path"]).parts or Path(row["path"]).is_absolute() or sha(p) != row["sha256"] or p.stat().st_size != row["size"] or p.stat().st_mode & 0o222:
            raise ValueError("RELEASE_ARTIFACT_MISMATCH")
        expected.add(row["path"])
    if {str(p.relative_to(root)) for p in root.rglob("*") if p.is_file()} != expected:
        raise ValueError("RELEASE_INVENTORY_MISMATCH")
    if sha(Path(topology.interpreter)) != topology.interpreter_hash or sha(Path(topology.runtime_manifest)) != topology.runtime_manifest_hash:
        raise ValueError("RUNTIME_IDENTITY_MISMATCH")
    runtime = verified(read(Path(topology.runtime_manifest)))
    if (runtime["schema"] != "iios-truth-runtime-v1" or runtime["runtime_id"] != topology.runtime_id or runtime["release_commit"] != topology.source_commit
            or runtime["interpreter"] != topology.interpreter
            or runtime["interpreter_sha256"] != topology.interpreter_hash
            or Path(runtime["runtime_root"]) != Path(topology.runtime_manifest).parent):
        raise ValueError("RUNTIME_IDENTITY_MISMATCH")
    if sha(Path(runtime["process_executable"])) != runtime["process_executable_hash"]:
        raise ValueError("PROCESS_EXECUTABLE_MISMATCH")
    for row in runtime["platform_dependencies"]:
        if sha(Path(row["path"])) != row["sha256"]:
            raise ValueError("PLATFORM_RUNTIME_MISMATCH")
    for row in runtime["file_inventory"]:
        p = Path(topology.runtime_manifest).parent / row["path"]
        if sha(p) != row["sha256"] or p.stat().st_size != row["size"] or p.stat().st_mode & 0o222:
            raise ValueError("RUNTIME_ARTIFACT_MISMATCH")


def bindings(topology: Topology) -> dict:
    return {"topology_identity": topology.record()["content_hash"], "release_id": topology.release_id,
            "generation_id": topology.generation_id, "session_id": topology.session_id}


def heartbeat(config_path: Path, role: str, topology: Topology, *, result: str) -> None:
    atomic(config_path.parent / f"{role}-heartbeat.json", seal({**bindings(topology),
        "schema": "iios-truth-heartbeat-v1", "role": role, "pid": os.getpid(),
        "runtime_id": topology.runtime_id, "ledger_identity": topology.ledger_identity,
        "observed_at": datetime.now(timezone.utc).isoformat(), "status": result,
        "network_dispatch_enabled": False, "allowance": 0}))


def process_probe(config_path: Path, role: str, topology: Topology, at: datetime | None = None) -> dict:
    hb = verified(read(config_path.parent / f"{role}-heartbeat.json")); bind(hb, topology)
    # Read first, then sample time: a concurrent atomic heartbeat can be newer than request start.
    at = at or datetime.now(timezone.utc)
    if (hb.get("role") != role or hb.get("runtime_id") != topology.runtime_id
            or hb.get("ledger_identity") != topology.ledger_identity
            or not 0 <= (at - utc(hb["observed_at"])).total_seconds() <= 15
            or hb.get("network_dispatch_enabled") is not False or hb.get("allowance") != 0):
        raise ValueError("HEARTBEAT_STALE_OR_MISMATCHED")
    # Real OS discovery, not a harness-supplied PID resolver.
    result = subprocess.run(["ps", "-p", str(int(hb["pid"])), "-o", "command="], capture_output=True, text=True, timeout=2, check=False)
    command = result.stdout.strip()
    if result.returncode or "-m truth_spine_service" not in command or f"--role {role}" not in command or str(config_path) not in command:
        raise ValueError("REQUIRED_PROCESS_UNAVAILABLE")
    runtime = verified(read(Path(topology.runtime_manifest)))
    if not command.startswith(runtime["process_executable"] + " "):
        raise ValueError("PROCESS_EXECUTABLE_MISMATCH")
    return hb


def publish(root: Path, topology: Topology) -> dict:
    result = validate_ledger(Path(topology.ledger_path), topology)
    if result is None:
        raise ValueError("REPLAY_NOT_YET_PERSISTED")
    with connect(Path(topology.ledger_path), readonly=True) as db:
        row = db.execute("SELECT payload_json FROM ledger_objects WHERE object_type='paper_portfolio_snapshot' ORDER BY created_at DESC LIMIT 1").fetchone()
    paper = json.loads(row[0]) if row else {}
    projection = seal({**bindings(topology), "schema": "iios-truth-projection-v1", "classification": "REPLAY",
        "runtime_id": topology.runtime_id, "ledger_identity": topology.ledger_identity,
        "phase": topology.phase, "market_readiness": "DISABLED_ZERO_ALLOWANCE", "research_readiness": "OFFLINE_REPLAY_ONLY",
        "provider_states": {"FINANCIAL_DATASETS": "PERSISTED_EVIDENCE_NO_NETWORK"},
        "room_states": {result["evidence"]["room_id"]: "REPLAY"}, "agent_states": result["analysis"]["routing"],
        "case_id": result["case_id"], "trace_id": result["trace_id"], "case_state": result["decision"],
        "committee_state": result["committee_state"], "risk": result["risk"], "paper": result["paper"],
        "outcome": result["outcome"], "memory": result["memory"], "reason_codes": result["reason_codes"],
        # Decimal strings keep Python/JavaScript canonical bytes identical (10000.0 != 10000).
        "paper_fund": {"nav": money(paper.get("nav")), "cash": money(paper.get("cash")), "source": "ISOLATED_LEDGER_SNAPSHOT",
                       "reconciled_at": paper.get("created_at"), "live_account_reconciliation": False},
        "evidence_ids": [result["evidence"]["evidence_id"]], "receipt_id": result["evidence"]["receipt_id"],
        "event_ids": result["event_ids"], "authority": dict(topology.authorities),
        "universe": {"source": "GOVERNED_INDEX_TRACKER_MIRROR", "direct_membership": False,
                     "eligibility": "CAPTURED_MEMBERS_ONLY_NO_TICKER_SUBSTITUTION"},
        "observed_at": datetime.now(timezone.utc).isoformat(), "model_classification": "DETERMINISTIC_ACCEPTANCE_ONLY",
        "narrative": None, "memory_animation": False})
    atomic(root / "projection.json", projection)
    return projection


def money(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not Decimal(str(value)).is_finite():
        raise ValueError("PAPER_VALUE_INVALID")
    return str(Decimal(str(value)))


def health(config_path: Path, kind: str) -> tuple[int, dict]:
    now = datetime.now(timezone.utc)
    if kind == "live":
        return 200, {"status": "LIVE", "pid": os.getpid(), "observed_at": now.isoformat(), "factory_readiness_claimed": False}
    try:
        config, topology = configuration(config_path); release_check(topology)
        if os.environ.get("IIOS_DB_PATH") != topology.ledger_path or str(Path(sys.executable)) != topology.interpreter:
            raise ValueError("LEDGER_PATH_MISMATCH")
        result = validate_ledger(Path(topology.ledger_path), topology)
        process_probe(config_path, "scheduler", topology); process_probe(config_path, "publisher", topology)
        projection = read(config_path.parent / "projection.json")
        now = datetime.now(timezone.utc)
        projection_check(projection, topology, result, now)
        response = {**bindings(topology), "runtime_id": topology.runtime_id, "ledger_identity": topology.ledger_identity,
                    "observed_at": now.isoformat(), "phase": topology.phase, "classification": "REPLAY", "authority": dict(topology.authorities)}
        if kind == "market-readiness":
            u = universe((config_path.parent / "universe-source.json").read_bytes(), config["universe_hash"], topology, at=now)
            from high_speed_market_radar import _strict_universe
            radar_symbols, _ = _strict_universe()
            if radar_symbols != u["symbols"]:
                raise ValueError("RADAR_UNIVERSE_MISMATCH")
            return 503, {**response, "status": "NOT_READY", "market_date": topology.market_date, "plan_id": topology.plan_id,
                         "universe": u["status"], "universe_source": u["source_classification"], "radar_members": len(radar_symbols), "ready_to_observe": False,
                         "ready_to_execute": False, "entitlement": "REPLAY_STORAGE_ONLY", "allowance": 0,
                         "stage_a": "LOCKED", "stage_b": "LOCKED", "stage_c": "LOCKED",
                         "reason_codes": ["NO_OPERATIONAL_AUTHORIZATION", "HISTORICAL_REPLAY_NOT_CURRENT_MARKET"]}
        if kind == "research-readiness":
            registered_agents()
            return 200, {**response, "status": "REPLAY_READY", "live_research_ready": False,
                         "case_builder": "AVAILABLE", "evidence": "HASH_VALID", "model_routes": list(topology.model_routes),
                         "committee": result["committee_state"], "risk": result["risk"]["state"],
                         "memory_retrieval": "EMPTY_VALIDATED_MEMORY", "paper_execution_ready": False}
        return 200, {**response, "status": "READY", "scope": "ISOLATED_INTERNAL_REPLAY_RUNTIME"}
    except (OSError, ValueError, KeyError, TypeError, sqlite3.Error, subprocess.SubprocessError):
        return 503, {"status": "NOT_READY", "observed_at": now.isoformat(), "reason_codes": ["REQUIRED_BINDING_UNAVAILABLE"], "authority": dict.fromkeys(("broker", "paper_order", "promotion", "ledger_write", "live_execution"), False)}


def projection_check(projection: dict, topology: Topology, result: dict | None, now: datetime) -> None:
    bind(projection, topology); locked(projection["authority"])
    if (not 0 <= (now - utc(projection["observed_at"])).total_seconds() <= 15
            or projection["runtime_id"] != topology.runtime_id or projection["ledger_identity"] != topology.ledger_identity
            or projection["phase"] != topology.phase or projection["classification"] != "REPLAY"
            or result is None or projection["event_ids"] != result["event_ids"]
            or projection["case_id"] != result["case_id"] or projection["trace_id"] != result["trace_id"]
            or projection["case_state"] != result["decision"] or projection["risk"] != result["risk"]
            or projection["paper"] != result["paper"] or projection["outcome"] != result["outcome"]
            or projection["receipt_id"] != result["evidence"]["receipt_id"]):
        raise ValueError("PROJECTION_INCOHERENT_OR_STALE")


def run(config_path: Path, role: str) -> None:
    config, topology = configuration(config_path); release_check(topology)
    if Path(sys.executable) != Path(topology.interpreter):
        raise ValueError("INTERPRETER_BINDING_INVALID")
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set()); signal.signal(signal.SIGINT, lambda *_: stop.set())
    import fcntl
    fd = os.open(config_path.parent / f"{role}.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        while not stop.is_set():
            try:
                if role == "scheduler":
                    u = universe((config_path.parent / "universe-source.json").read_bytes(), config["universe_hash"], topology, at=datetime.now(timezone.utc))
                    if u["status"] != "CURRENT":
                        raise ValueError("UNIVERSE_STALE")
                    evidence = normalize(read(config_path.parent / "receipt.json"), (config_path.parent / "evidence.json").read_bytes(), topology=topology, universe_record=u, storage_policy="FD_REVIEWED_INTERNAL_EVIDENCE_REPLAY_V1")
                    replay(Path(topology.ledger_path), topology, evidence)
                else:
                    publish(config_path.parent, topology)
                heartbeat(config_path, role, topology, result="DISABLED_REPLAY_HEALTHY")
            except (ValueError, OSError, sqlite3.Error, KeyError) as exc:
                # Persist fixed categories, never unrestricted exception strings or input payloads.
                atomic(config_path.parent / f"{role}-incident.json", seal({"schema": "iios-truth-incident-v1", **bindings(topology),
                    "category": type(exc).__name__, "status": "FAILED_CLOSED", "observed_at": datetime.now(timezone.utc).isoformat()}))
            stop.wait(2)
    finally:
        os.close(fd)


if __name__ == "__main__":
    from truth_spine_isolation import enforce_offline
    enforce_offline()
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--role", choices=("scheduler", "publisher"), required=True)
    args = parser.parse_args()
    run(args.config, args.role)
