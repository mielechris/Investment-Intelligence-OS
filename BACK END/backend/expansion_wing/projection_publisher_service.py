from __future__ import annotations

import argparse
import fcntl
import json
import os
import signal
import stat
import sys
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
    return PublisherService(builder, GovernedProjectionPublisher(reviewed_projection_root()),
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
