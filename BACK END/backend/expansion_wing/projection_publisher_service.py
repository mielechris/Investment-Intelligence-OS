from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import plistlib
import signal
import stat
import sys
import re
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Sequence

from .projection_bindings import load_binding_manifest, read_bound_artifacts
from .projection_input_snapshot import EnvelopeSnapshotBuilder, operational_input_root
from .projection_publisher import GovernedProjectionPublisher
from .projection_runtime import reviewed_projection_root
from .projection_source_adapters import adapt_source
from .projection_source_registry import source_registry, validate_envelope

SERVICE_SCHEMA = "iios-projection-publisher-service-v1"
SERVICE_LABEL = "com.iios.expansion-wing-projection-publisher"
MINIMUM_INTERVAL_SECONDS = 60
STATUS_LIMIT_BYTES = 65_536
ACTIVE_RELEASE_MANIFEST=Path.home()/"Library/Application Support/IIOS/Release/active-release.json"
PUBLISHER_PLIST_TEMPLATE=Path(__file__).resolve().parents[3]/"config/com.iios.expansion-wing-projection-publisher.plist.template"

def render_launch_plist(*,release_root:Path,ledger_path:Path,python:str) -> bytes:
    backend=release_root/"source/BACK END/backend"
    if (not release_root.is_absolute() or not ledger_path.is_absolute() or release_root in ledger_path.parents
            or not python.startswith("/") or "/GitHub/" in python): raise ValueError("PUBLISHER_DEPLOYMENT_CONTRACT_INVALID")
    raw=PUBLISHER_PLIST_TEMPLATE.read_text().replace("__IMMUTABLE_PYTHON__",python)
    raw=raw.replace("__IMMUTABLE_RELEASE__",str(release_root))
    raw=raw.replace("__OPERATIONAL_LEDGER_PATH__",str(ledger_path)).encode()
    value=plistlib.loads(raw); environment=value.get("EnvironmentVariables")
    if (value.get("Label")!=SERVICE_LABEL or value.get("WorkingDirectory")!=str(backend)
            or environment!={"PYTHONPATH":str(backend),"IIOS_DB_PATH":str(ledger_path),"PYTHONDONTWRITEBYTECODE":"1"}
            or value.get("ProgramArguments")!=[python,"-m","expansion_wing.projection_publisher","--operational"]):
        raise ValueError("PUBLISHER_DEPLOYMENT_CONTRACT_INVALID")
    return raw

def _active_release_contract()->tuple[str,str]:
    from deployment_contract import validate_active_release
    try: value=validate_active_release(ACTIVE_RELEASE_MANIFEST,configured_ledger=os.environ.get("IIOS_DB_PATH"))
    except (OSError,RuntimeError,ValueError,json.JSONDecodeError) as error:
        raise RuntimeError("PUBLISHER_RELEASE_UNAVAILABLE") from error
    commit=value["git_commit"]; ledger_path=Path(value["operational_ledger_path"])
    info=ledger_path.lstat()
    if (ledger_path.is_symlink() or not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid()
            or stat.S_IMODE(info.st_mode)!=0o600): raise RuntimeError("PUBLISHER_LEDGER_UNAVAILABLE")
    connection=sqlite3.connect(f"file:{ledger_path}?mode=ro",uri=True,timeout=2)
    try:
        if connection.execute("SELECT 1").fetchone()!=(1,): raise RuntimeError("PUBLISHER_LEDGER_UNAVAILABLE")
    finally: connection.close()
    return str(commit),str(value["ledger_path_contract_hash"])


def _selected_executor_generation()->str:
    from .operational_market_executor import ExecutorStore,plan_identity
    from .operational_market_executor_installer import INSTALL_ROOT,resolve_selected_state_root,validate_installed
    validate_installed(INSTALL_ROOT); selected=resolve_selected_state_root(INSTALL_ROOT)
    store=ExecutorStore(selected); rows,state=store.read_plan(),store.read()
    if state.get("plan_identity")!=plan_identity(rows): raise RuntimeError("PUBLISHER_EXECUTOR_GENERATION_INVALID")
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,120}",selected.name): raise RuntimeError("PUBLISHER_EXECUTOR_GENERATION_INVALID")
    return selected.name


def operational_service_root() -> Path:
    return Path.home() / "Library" / "Application Support" / "IIOS" / "ExpansionWingPublisher"


class SingleFlightLock:
    def __init__(self, path: Path) -> None:
        self.path, self.fd = path, None

    def acquire(self) -> bool:
        info = self.path.parent.lstat()
        if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o700:
            raise RuntimeError("PUBLISHER_STATE_ROOT_UNSAFE")
        self.fd = os.open(self.path, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
        os.fchmod(self.fd, 0o600)
        try: fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(self.fd); self.fd = None; return False
        return True

    def release(self) -> None:
        if self.fd is not None:
            fcntl.flock(self.fd, fcntl.LOCK_UN); os.close(self.fd); self.fd = None


class BoundedStatusLog:
    def __init__(self, path: Path, maximum: int = STATUS_LIMIT_BYTES) -> None:
        self.path, self.maximum = path, maximum

    def write(self, category: str) -> None:
        allowed = {"OBSERVATION_UNCHANGED", "OBSERVATION_PUBLISHED", "OBSERVATION_FAILED_CLOSED",
                   "BINDINGS_VALID", "LOCK_CONTENDED", "SERVICE_STARTED", "SERVICE_STOPPED"}
        category = category if category in allowed else "OBSERVATION_FAILED_CLOSED"
        line = json.dumps({"schema_version": SERVICE_SCHEMA, "category": category}, separators=(",", ":")) + "\n"
        prior = b""
        if self.path.exists(): prior = self.path.read_bytes()[-(self.maximum // 2):]
        encoded = (prior + line.encode("ascii"))[-self.maximum:]
        temporary = self.path.with_name(f".{self.path.name}.{os.getpid()}.tmp")
        fd = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        try:
            os.write(fd, encoded); os.fsync(fd)
        finally: os.close(fd)
        os.replace(temporary, self.path)


class PublisherService:
    def __init__(self, builder: EnvelopeSnapshotBuilder, publisher: GovernedProjectionPublisher,
                 lock: SingleFlightLock, status_log: BoundedStatusLog,
                 *, clock: Callable[[], datetime] | None = None, sleeper: Callable[[float], None] = time.sleep) -> None:
        self.builder, self.publisher, self.lock, self.status_log = builder, publisher, lock, status_log
        self.clock = clock or (lambda: datetime.now(timezone.utc)); self.sleeper = sleeper; self.stopping = False

    def stop(self, *_: object) -> None: self.stopping = True

    def observe(self) -> str:
        if not self.lock.acquire(): self.status_log.write("LOCK_CONTENDED"); return "LOCK_CONTENDED"
        try:
            now = self.clock(); envelopes, snapshot = self.builder.build(now=now)
            result = self.publisher.evaluate(envelopes, now=now)
            category = "OBSERVATION_PUBLISHED" if result.changed else (
                "OBSERVATION_UNCHANGED" if result.state == "UNCHANGED" else "OBSERVATION_FAILED_CLOSED")
            self.status_log.write(category); return category
        except (ValueError, RuntimeError, OSError):
            self.status_log.write("OBSERVATION_FAILED_CLOSED"); return "OBSERVATION_FAILED_CLOSED"
        finally: self.lock.release()

    def run(self, *, interval: int = MINIMUM_INTERVAL_SECONDS, maximum_observations: int | None = None) -> int:
        if interval < MINIMUM_INTERVAL_SECONDS: raise ValueError("PUBLISHER_INTERVAL_UNSAFE")
        count = 0; self.status_log.write("SERVICE_STARTED")
        while not self.stopping:
            start = time.monotonic(); self.observe(); count += 1
            if maximum_observations is not None and count >= maximum_observations: break
            remaining = interval - (time.monotonic() - start)
            if remaining > 0: self.sleeper(remaining)
        self.status_log.write("SERVICE_STOPPED"); return count


def _operational_service() -> PublisherService:
    state_root = operational_service_root()
    if not state_root.exists(): raise RuntimeError("PUBLISHER_STATE_ROOT_MISSING")
    bindings = load_binding_manifest()
    builder = EnvelopeSnapshotBuilder(operational_input_root(), bindings)
    release_commit,ledger_contract=_active_release_contract()
    return PublisherService(builder, GovernedProjectionPublisher(reviewed_projection_root(),release_commit=release_commit,
        executor_generation_reader=_selected_executor_generation,ledger_path_contract_hash=ledger_contract),
        SingleFlightLock(state_root / "publisher.lock"), BoundedStatusLog(state_root / "publisher-status.jsonl"))


def validate_operational_bindings(*, now: datetime | None = None) -> dict[str, str]:
    bindings = load_binding_manifest(); artifacts = read_bound_artifacts(bindings)
    clock = now or datetime.now(timezone.utc); results: dict[str, str] = {}
    for name, binding in bindings.items():
        envelope = adapt_source(name, binding, artifacts[name])
        validate_envelope(envelope, source_registry()[name], now=clock)
        results[name] = "AVAILABLE" if artifacts[name] is not None else (
            "REQUIRED_AVAILABILITY_UNAVAILABLE" if binding.required else "OPTIONAL_UNAVAILABLE")
    return results


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m expansion_wing.projection_publisher")
    parser.add_argument("--operational", action="store_true")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--once", action="store_true")
    modes.add_argument("--validate-bindings", action="store_true")
    parser.add_argument("--interval", type=int, default=MINIMUM_INTERVAL_SECONDS)
    args = parser.parse_args(argv)
    if not args.operational: parser.error("--operational is required")
    if args.interval < MINIMUM_INTERVAL_SECONDS: parser.error("interval below 60 seconds is prohibited")
    return args


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.validate_bindings:
            validate_operational_bindings()
            print("BINDINGS_VALID"); return 0
        service = _operational_service()
        signal.signal(signal.SIGTERM, service.stop); signal.signal(signal.SIGINT, service.stop)
        if args.once: return 0 if service.observe() != "OBSERVATION_FAILED_CLOSED" else 2
        service.run(interval=args.interval); return 0
    except (RuntimeError, ValueError, OSError):
        print("PUBLISHER_FAILED_CLOSED", file=sys.stderr); return 2
