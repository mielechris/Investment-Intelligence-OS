"""Owner-only persistence and browser-safe truth for the disabled Tuesday supervisor."""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import signal
import stat
import tempfile
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .tuesday_controller import AUTHORITY, PILOTS

STATE_SCHEMA = "iios-tuesday-controller-state-v1"
INSTALL_SCHEMA = "iios-tuesday-controller-installation-v1"
BROWSER_SCHEMA = "iios-tuesday-controller-browser-v1"
CONTROLLER_ID = "IIOS_TUESDAY_EVIDENCE_CONTROLLER"
STATE_NAME = "controller-state.json"
INSTALL_NAME = "installation.json"
LOCK_NAME = "controller.lock"
MAX_BYTES = 64_000
PHASE = "TUESDAY_PREMARKET_LOCKED"
AUTHORITY_KEYS = (
    "provider", "credential", "automatic_promotion", "synthetic_observation",
    "paper_order", "broker", "ledger_write", "live_execution", "browser_control",
)
LOCKS = {key: False for key in AUTHORITY_KEYS}
IDENTITY = re.compile(r"^[A-Za-z0-9_.:-]{8,96}$")
STATE_FIELDS = {
    "schema_version", "controller_identity", "installation_identity", "installed",
    "running", "activated", "phase", "phase_history", "sequence", "controller_date",
    "market_session", "pilot_registry_hash", "per_instrument_maximum", "global_credit_ceiling",
    "requests_used", "credits_used", "request_identities", "last_transition_category",
    "monday_rehearsal_status", "restart_recovery_status", "authority", "updated_at",
    "error_category", "content_hash",
}
INSTALL_FIELDS = {
    "schema_version", "controller_identity", "installation_identity", "source_available",
    "installation_prepared", "installed", "launchd_registered", "process_running",
    "controller_activated", "generated_at", "content_hash",
}


def _canonical(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _hash(value: dict[str, Any]) -> str:
    clean = {key: item for key, item in value.items() if key != "content_hash"}
    return hashlib.sha256(_canonical(clean)).hexdigest()


def _timestamp(value: Any, now: datetime | None = None) -> datetime:
    if not isinstance(value, str) or len(value) > 40:
        raise ValueError("TIMESTAMP_INVALID")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("TIMESTAMP_INVALID") from exc
    parsed = parsed.replace(tzinfo=parsed.tzinfo or timezone.utc).astimezone(timezone.utc)
    if parsed > (now or datetime.now(timezone.utc)).astimezone(timezone.utc):
        raise ValueError("FUTURE_TIMESTAMP")
    return parsed


def _regular_owner_file(path: Path) -> None:
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or path.is_symlink():
        raise ValueError("UNSAFE_FILE_TYPE")
    if info.st_uid != os.getuid():
        raise ValueError("OWNER_INVALID")
    if stat.S_IMODE(info.st_mode) != 0o600:
        raise ValueError("FILE_MODE_INVALID")
    if info.st_size > MAX_BYTES:
        raise ValueError("PAYLOAD_TOO_LARGE")


def _directory(root: Path, *, create: bool) -> None:
    if create:
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        root.chmod(0o700)
    info = root.lstat()
    if not stat.S_ISDIR(info.st_mode) or root.is_symlink():
        raise ValueError("UNSAFE_STATE_ROOT")
    if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
        raise ValueError("STATE_ROOT_PERMISSIONS_INVALID")


def _atomic(root: Path, name: str, value: dict[str, Any]) -> None:
    data = _canonical(value)
    if len(data) > MAX_BYTES:
        raise ValueError("PAYLOAD_TOO_LARGE")
    fd, temporary = tempfile.mkstemp(prefix=f".{name}.", dir=root)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb", closefd=True) as stream:
            stream.write(data); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, root / name)
        directory_fd = os.open(root, os.O_RDONLY)
        try: os.fsync(directory_fd)
        finally: os.close(directory_fd)
    finally:
        try: os.unlink(temporary)
        except FileNotFoundError: pass


def installation_manifest(identity: str, *, installed: bool, registered: bool,
                          running: bool, generated_at: str) -> dict[str, Any]:
    value = {
        "schema_version": INSTALL_SCHEMA, "controller_identity": CONTROLLER_ID,
        "installation_identity": identity, "source_available": True,
        "installation_prepared": True, "installed": installed,
        "launchd_registered": registered, "process_running": running,
        "controller_activated": False, "generated_at": generated_at,
    }
    value["content_hash"] = _hash(value)
    return value


def disabled_state(identity: str, *, installed: bool, running: bool, updated_at: str,
                   prior: dict[str, Any] | None = None, transition: str = "COLD_START") -> dict[str, Any]:
    request_ids = [] if prior is None else list(prior["request_identities"])
    history = [PHASE] if prior is None else list(prior["phase_history"])
    sequence = 0 if prior is None else int(prior["sequence"]) + 1
    value = {
        "schema_version": STATE_SCHEMA, "controller_identity": CONTROLLER_ID,
        "installation_identity": identity, "installed": installed, "running": running,
        "activated": False, "phase": PHASE, "phase_history": history, "sequence": sequence,
        "controller_date": "2026-09-08", "market_session": "TUESDAY_PREMARKET_LOCKED",
        "pilot_registry_hash": hashlib.sha256("|".join(PILOTS).encode()).hexdigest(),
        "per_instrument_maximum": 3, "global_credit_ceiling": 30,
        "requests_used": 0 if prior is None else prior["requests_used"],
        "credits_used": 0 if prior is None else prior["credits_used"],
        "request_identities": request_ids, "last_transition_category": transition,
        "monday_rehearsal_status": "PASSED_CLOSED_HOLIDAY",
        "restart_recovery_status": "NOT_REQUIRED" if prior is None else "RESTORED_EXACT_DISABLED_STATE",
        "authority": LOCKS.copy(), "updated_at": updated_at, "error_category": None,
    }
    value["content_hash"] = _hash(value)
    return value


def validate_installation(value: Any, *, now: datetime | None = None) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != INSTALL_FIELDS:
        raise ValueError("INSTALLATION_SCHEMA_INVALID")
    if value.get("schema_version") != INSTALL_SCHEMA or value.get("controller_identity") != CONTROLLER_ID:
        raise ValueError("INSTALLATION_SCHEMA_INVALID")
    if not isinstance(value.get("installation_identity"), str) or not IDENTITY.fullmatch(value["installation_identity"]):
        raise ValueError("INSTALLATION_IDENTITY_INVALID")
    if any(not isinstance(value.get(key), bool) for key in (
        "source_available", "installation_prepared", "installed", "launchd_registered",
        "process_running", "controller_activated")):
        raise ValueError("INSTALLATION_SCHEMA_INVALID")
    if value["controller_activated"] or value["installed"] != value["launchd_registered"]:
        raise ValueError("INSTALLATION_STATE_AMBIGUOUS")
    _timestamp(value["generated_at"], now)
    if value.get("content_hash") != _hash(value):
        raise ValueError("INSTALLATION_HASH_INVALID")
    return value


def validate_state_v1(value: Any, installation: dict[str, Any], *, now: datetime | None = None) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != STATE_FIELDS:
        raise ValueError("STATE_SCHEMA_INVALID")
    if value.get("schema_version") != STATE_SCHEMA or value.get("controller_identity") != CONTROLLER_ID:
        raise ValueError("STATE_SCHEMA_INVALID")
    if value.get("installation_identity") != installation["installation_identity"]:
        raise ValueError("INSTALLATION_IDENTITY_MISMATCH")
    if value.get("installed") is not installation["installed"] or value.get("activated") is not False:
        raise ValueError("STATE_AUTHORITY_INVALID")
    if value.get("phase") != PHASE or value.get("market_session") != PHASE:
        raise ValueError("PHASE_INVALID")
    history = value.get("phase_history")
    if not isinstance(history, list) or not history or len(history) > 32 or history[-1] != PHASE:
        raise ValueError("PHASE_HISTORY_INVALID")
    if not isinstance(value.get("sequence"), int) or value["sequence"] < len(history) - 1:
        raise ValueError("SEQUENCE_INVALID")
    if value.get("per_instrument_maximum") != 3 or value.get("global_credit_ceiling") != 30:
        raise ValueError("BUDGET_CONTRACT_INVALID")
    if not isinstance(value.get("requests_used"), int) or not isinstance(value.get("credits_used"), int):
        raise ValueError("BUDGET_STATE_INVALID")
    if not 0 <= value["credits_used"] <= value["requests_used"] <= 30:
        raise ValueError("BUDGET_STATE_INVALID")
    identities = value.get("request_identities")
    if not isinstance(identities, list) or len(identities) != len(set(identities)) or len(identities) != value["requests_used"]:
        raise ValueError("REQUEST_IDENTITY_INVALID")
    if any(not isinstance(item, str) or not IDENTITY.fullmatch(item) for item in identities):
        raise ValueError("REQUEST_IDENTITY_INVALID")
    if value.get("authority") != LOCKS:
        raise ValueError("STATE_AUTHORITY_INVALID")
    if value.get("pilot_registry_hash") != hashlib.sha256("|".join(PILOTS).encode()).hexdigest():
        raise ValueError("PILOT_REGISTRY_INVALID")
    if value.get("monday_rehearsal_status") != "PASSED_CLOSED_HOLIDAY":
        raise ValueError("REHEARSAL_STATE_INVALID")
    if value.get("controller_date") != "2026-09-08": raise ValueError("CONTROLLER_DATE_INVALID")
    if value.get("last_transition_category") not in {"COLD_START", "SUPERVISOR_STARTED", "CLEAN_SHUTDOWN"}:
        raise ValueError("TRANSITION_CATEGORY_INVALID")
    if value.get("restart_recovery_status") not in {"NOT_REQUIRED", "RESTORED_EXACT_DISABLED_STATE"}:
        raise ValueError("RECOVERY_CATEGORY_INVALID")
    if value.get("error_category") is not None:
        raise ValueError("ERROR_CATEGORY_INVALID")
    _timestamp(value["updated_at"], now)
    if value.get("content_hash") != _hash(value):
        raise ValueError("STATE_HASH_INVALID")
    return value


def validate_state(value: Any, installation: dict[str, Any], *, now: datetime | None = None) -> dict[str, Any]:
    if isinstance(value, dict) and value.get("schema_version") == "iios-tuesday-controller-state-v2":
        from .tuesday_controller_v2 import validate_state_v2
        return validate_state_v2(value, installation, now=now)
    return validate_state_v1(value, installation, now=now)


class ControllerStateStore:
    def __init__(self, root: Path) -> None: self.root = root

    def initialize(self, install: dict[str, Any], state: dict[str, Any]) -> None:
        _directory(self.root, create=True)
        validate_installation(install); validate_state(state, install)
        _atomic(self.root, INSTALL_NAME, install); _atomic(self.root, STATE_NAME, state)

    def _read_json(self, path: Path) -> dict[str, Any]:
        _regular_owner_file(path)
        try: value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("STATE_JSON_INVALID") from exc
        if not isinstance(value, dict): raise ValueError("STATE_JSON_INVALID")
        return value

    def read(self, *, now: datetime | None = None, allow_lock: bool = True, recover: bool = False) -> tuple[dict[str, Any], dict[str, Any]]:
        _directory(self.root, create=False)
        from .tuesday_controller_v2 import LAST_KNOWN_VALID_NAME, V1_ROLLBACK_NAME
        allowed = {INSTALL_NAME, STATE_NAME, LAST_KNOWN_VALID_NAME, V1_ROLLBACK_NAME} | ({LOCK_NAME} if allow_lock else set())
        if {item.name for item in self.root.iterdir()} - allowed:
            raise ValueError("STATE_INVENTORY_INVALID")
        if (self.root / LOCK_NAME).exists(): _regular_owner_file(self.root / LOCK_NAME)
        install = validate_installation(self._read_json(self.root / INSTALL_NAME), now=now)
        try:
            state = validate_state(self._read_json(self.root / STATE_NAME), install, now=now)
        except (OSError, ValueError):
            if not recover or not (self.root / LAST_KNOWN_VALID_NAME).exists():
                raise
            state = validate_state(self._read_json(self.root / LAST_KNOWN_VALID_NAME), install, now=now)
        return install, state

    def write_state(self, state: dict[str, Any], install: dict[str, Any]) -> None:
        validate_state(state, install); _atomic(self.root, STATE_NAME, state)

    def write_installation(self, install: dict[str, Any]) -> None:
        validate_installation(install); _atomic(self.root, INSTALL_NAME, install)

    def acquire(self):
        _directory(self.root, create=False)
        stream = (self.root / LOCK_NAME).open("a+"); os.chmod(stream.fileno(), 0o600)
        try: fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            stream.close(); raise ValueError("DUPLICATE_SUPERVISOR") from None
        return stream


def unavailable_projection(category: str = "CONTROLLER_STATUS_NOT_AVAILABLE", *, state: str = "UNAVAILABLE") -> dict[str, Any]:
    return {
        "schema_version": BROWSER_SCHEMA, "state": state, "installed": False,
        "running": False, "activated": False, "phase": "NOT_INSTALLED",
        "monday_rehearsal_status": "UNAVAILABLE", "requests_today": 0, "credits_today": 0,
        "human_gate": "INSTALLATION_REQUIRED", "restart_recovery": "UNAVAILABLE",
        "integrity": "UNAVAILABLE", "last_update": None, "next_action": "PREPARE_DISABLED_INSTALLATION",
        "authority_locked": True, "error_category": category,
        "controller_generation_sequence": None, "controller_read_timestamp": None,
    }


class ControllerStatusReader:
    MAX_COHERENT_READ_ATTEMPTS = 3

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or (Path.home() / "Library" / "Application Support" / "IIOS" / "TuesdayController")

    def _state_bytes(self) -> bytes:
        path = self.root / STATE_NAME
        _regular_owner_file(path)
        data = path.read_bytes()
        if len(data) > MAX_BYTES:
            raise ValueError("PAYLOAD_TOO_LARGE")
        return data

    def _coherent(self) -> tuple[dict[str, Any], dict[str, Any], tuple[str, int, str, str, str]]:
        from .tuesday_controller_v2 import LAST_KNOWN_VALID_NAME, STATE_SCHEMA_V2, _receipt_hash
        store = ControllerStateStore(self.root)
        for _ in range(self.MAX_COHERENT_READ_ATTEMPTS):
            before = self._state_bytes()
            install, state = store.read()
            if state.get("schema_version") == STATE_SCHEMA_V2:
                lkv = store._read_json(self.root / LAST_KNOWN_VALID_NAME)
                pointer = state.get("last_known_valid")
                lkv_is_current = (
                    lkv.get("schema_version") == state.get("schema_version")
                    and lkv.get("sequence") == state.get("sequence")
                    and lkv.get("content_hash") == state.get("content_hash")
                )
                lkv_is_predecessor = (
                    isinstance(pointer, dict)
                    and pointer.get("schema_version") == lkv.get("schema_version")
                    and pointer.get("sequence") == lkv.get("sequence")
                    and pointer.get("content_hash") == lkv.get("content_hash")
                )
                if (
                    not (lkv_is_current or lkv_is_predecessor)
                    or lkv.get("content_hash") != _hash(lkv)
                    or lkv.get("installation_identity") != state.get("installation_identity")
                ):
                    continue
            after = self._state_bytes()
            if before != after:
                continue
            receipts = state.get("rehearsal_receipts", [])
            receipt_ids = [
                str(item.get("canonical_content_hash") or _receipt_hash(item))
                for item in receipts if isinstance(item, dict)
            ]
            receipt_identity = hashlib.sha256(_canonical({"receipts": receipt_ids})).hexdigest()
            identity = (
                str(state["schema_version"]), int(state["sequence"]), str(state["content_hash"]),
                receipt_identity, str(install["installation_identity"]),
            )
            return install, state, identity
        raise ValueError("CONTROLLER_GENERATION_INCOHERENT")

    def cache_identity(self) -> tuple[str, int, str, str, str] | None:
        if not self.root.exists():
            return ("NOT_INSTALLED", 0, "", "", "")
        try:
            return self._coherent()[2]
        except (OSError, ValueError):
            return None

    def read(self) -> dict[str, Any]:
        if not self.root.exists():
            return unavailable_projection("CONTROLLER_NOT_INSTALLED", state="NOT_INSTALLED")
        try:
            install, state, _ = self._coherent()
            installed = install["installed"]
            lock_path = self.root / LOCK_NAME
            lock_owned = False
            if lock_path.exists():
                stream = lock_path.open("r+")
                try:
                    try: fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    except BlockingIOError: lock_owned = True
                    else: fcntl.flock(stream, fcntl.LOCK_UN)
                finally: stream.close()
            running = state["running"] and install["process_running"] and lock_owned
            if state.get("schema_version") == "iios-tuesday-controller-state-v2":
                from .tuesday_controller_v2 import browser_projection_v2
                return browser_projection_v2(state, running=running) | {
                    "controller_generation_sequence": state["sequence"],
                    "controller_read_timestamp": datetime.now(timezone.utc).isoformat(),
                }
            return {
                "schema_version": BROWSER_SCHEMA, "state": "INSTALLED_BUT_DISABLED" if installed else "NOT_INSTALLED",
                "installed": installed, "running": running, "activated": False,
                "phase": state["phase"] if installed else "NOT_INSTALLED",
                "monday_rehearsal_status": state["monday_rehearsal_status"],
                "requests_today": state["requests_used"], "credits_today": state["credits_used"],
                "human_gate": "AWAITING_TUESDAY_OWNER_AUTHORIZATION" if installed else "INSTALLATION_REQUIRED",
                "restart_recovery": state["restart_recovery_status"], "integrity": "VALID",
                "last_update": state["updated_at"],
                "next_action": "TUESDAY_OWNER_AUTHORIZATION" if installed else "PREPARE_DISABLED_INSTALLATION",
                "authority_locked": True, "error_category": None,
                "controller_generation_sequence": state["sequence"],
                "controller_read_timestamp": datetime.now(timezone.utc).isoformat(),
            }
        except (OSError, ValueError): return unavailable_projection("CONTROLLER_STATUS_FAILED_CLOSED", state="FAILED_CLOSED")


@dataclass
class DisabledSupervisor:
    store: ControllerStateStore
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)
    wait_seconds: float = 30.0

    def run(self) -> int:
        lock = self.store.acquire(); stopped = threading.Event()
        def stop(*_args: Any) -> None:
            stopped.set()
        signal.signal(signal.SIGTERM, stop); signal.signal(signal.SIGINT, stop)
        try:
            install, prior = self.store.read(recover=True)
            if not install["installed"] or install["controller_activated"]:
                raise ValueError("INSTALLATION_NOT_DISABLED")
            prior_install = install
            if prior.get("schema_version") == "iios-tuesday-controller-state-v2":
                from .tuesday_controller_v2 import LAST_KNOWN_VALID_NAME
                _atomic(self.store.root, LAST_KNOWN_VALID_NAME, prior)
            now = self.clock().astimezone(timezone.utc).isoformat()
            install = installation_manifest(install["installation_identity"], installed=True,
                                            registered=True, running=True, generated_at=now)
            self.store.write_installation(install)
            if prior.get("schema_version") == "iios-tuesday-controller-state-v2":
                from .tuesday_controller_v2 import recovered_v2
                running = recovered_v2(prior, prior_install, install, running=True, timestamp=now)
            else:
                running = disabled_state(install["installation_identity"], installed=True, running=True,
                                         updated_at=now, prior=prior, transition="SUPERVISOR_STARTED")
            self.store.write_state(running, install)
            while not stopped.wait(max(0.25, min(self.wait_seconds, 60.0))): pass
            final_install = installation_manifest(install["installation_identity"], installed=True,
                                                  registered=True, running=False,
                                                  generated_at=self.clock().astimezone(timezone.utc).isoformat())
            if running.get("schema_version") == "iios-tuesday-controller-state-v2":
                from .tuesday_controller_v2 import LAST_KNOWN_VALID_NAME
                _atomic(self.store.root, LAST_KNOWN_VALID_NAME, running)
            self.store.write_installation(final_install)
            if running.get("schema_version") == "iios-tuesday-controller-state-v2":
                from .tuesday_controller_v2 import recovered_v2
                final = recovered_v2(running, install, final_install, running=False,
                                     timestamp=self.clock().astimezone(timezone.utc).isoformat())
            else:
                final = disabled_state(install["installation_identity"], installed=True, running=False,
                                       updated_at=self.clock().astimezone(timezone.utc).isoformat(),
                                       prior=running, transition="CLEAN_SHUTDOWN")
            self.store.write_state(final, final_install)
            return 0
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN); lock.close()
