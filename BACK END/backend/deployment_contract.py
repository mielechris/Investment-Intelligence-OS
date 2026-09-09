"""Fail-closed contracts for immutable IIOS production deployment.

This module deliberately has no installation side effects at import time.  The
ledger permission transition is an explicit owner operation and is exercised
against an isolated copy before it may be used during a permanent promotion.
"""
from __future__ import annotations

import hashlib
import json
import os
import plistlib
import re
import sqlite3
import stat
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

ACTIVE_RELEASE_SCHEMA = "iios-active-immutable-release-v3"
RUNTIME_MANIFEST_SCHEMA = "iios-immutable-python-runtime-v1"
LEDGER_MIGRATION_SCHEMA = "iios-ledger-permission-migration-v1"
PYTHON_VERSION = "3.14.7"
HEX40 = re.compile(r"[0-9a-f]{40}")
HEX64 = re.compile(r"[0-9a-f]{64}")


def canonical(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode("ascii")


def digest(value: Any) -> str:
    clean = dict(value) if isinstance(value, dict) else value
    if isinstance(clean, dict):
        clean.pop("content_hash", None)
    return hashlib.sha256(canonical(clean)).hexdigest()


def file_hash(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def _owner_regular(path: Path, *, mode: int | None = None) -> os.stat_result:
    info = path.lstat()
    if path.is_symlink() or not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
        raise RuntimeError("DEPLOYMENT_FILE_UNSAFE")
    if mode is not None and stat.S_IMODE(info.st_mode) != mode:
        raise RuntimeError("DEPLOYMENT_FILE_MODE_INVALID")
    return info


def _sqlite_integrity(path: Path) -> str:
    connection = sqlite3.connect(f"file:{path}?mode=ro&immutable=1", uri=True, timeout=2)
    try:
        result = connection.execute("PRAGMA quick_check").fetchone()
    finally:
        connection.close()
    if result != ("ok",):
        raise RuntimeError("LEDGER_INTEGRITY_INVALID")
    return "ok"


@dataclass(frozen=True)
class LedgerIdentity:
    path: str
    owner_uid: int
    group_gid: int
    device: int
    inode: int
    size: int
    mode: int
    sha256: str
    sqlite_integrity: str

    def as_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


def inspect_ledger(path: Path, *, expected_path: Path, expected_uid: int,
                   expected_gid: int, expected_mode: int, expected_sha256: str) -> LedgerIdentity:
    if path != expected_path or not path.is_absolute() or any((Path(str(path) + suffix)).exists() for suffix in ("-wal", "-shm", "-journal")):
        raise RuntimeError("LEDGER_IDENTITY_INVALID")
    info = _owner_regular(path)
    observed = LedgerIdentity(str(path), info.st_uid, info.st_gid, info.st_dev, info.st_ino,
                              info.st_size, stat.S_IMODE(info.st_mode), file_hash(path), _sqlite_integrity(path))
    if (observed.owner_uid != expected_uid or observed.group_gid != expected_gid
            or observed.mode != expected_mode or observed.sha256 != expected_sha256):
        raise RuntimeError("LEDGER_IDENTITY_INVALID")
    return observed


def migrate_ledger_mode(*, path: Path, expected_path: Path, expected_uid: int,
                        expected_gid: int, expected_sha256: str,
                        from_mode: int = 0o644, to_mode: int = 0o600) -> dict[str, Any]:
    before = inspect_ledger(path, expected_path=expected_path, expected_uid=expected_uid,
                            expected_gid=expected_gid, expected_mode=from_mode,
                            expected_sha256=expected_sha256)
    os.chmod(path, to_mode)
    try:
        after = inspect_ledger(path, expected_path=expected_path, expected_uid=expected_uid,
                               expected_gid=expected_gid, expected_mode=to_mode,
                               expected_sha256=expected_sha256)
        if ((before.device, before.inode, before.size, before.sha256, before.sqlite_integrity)
                != (after.device, after.inode, after.size, after.sha256, after.sqlite_integrity)):
            raise RuntimeError("LEDGER_CONTENT_CHANGED")
    except Exception:
        os.chmod(path, from_mode)
        raise
    body = {"schema": LEDGER_MIGRATION_SCHEMA, "path": str(path),
            "device": before.device, "inode": before.inode, "owner_uid": before.owner_uid,
            "group_gid": before.group_gid, "size": before.size, "sha256": before.sha256,
            "sqlite_integrity": "ok", "original_mode": from_mode, "resulting_mode": to_mode,
            "rollback_disposition": "RESTORE_MODE_0644_ONLY_AFTER_HASH_AND_INODE_REVALIDATION"}
    return body | {"content_hash": digest(body)}


def restore_ledger_mode(*, path: Path, receipt: dict[str, Any]) -> str:
    if receipt.get("schema") != LEDGER_MIGRATION_SCHEMA or receipt.get("content_hash") != digest(receipt):
        raise RuntimeError("LEDGER_MIGRATION_RECEIPT_INVALID")
    before = inspect_ledger(path, expected_path=Path(receipt["path"]), expected_uid=receipt["owner_uid"],
                            expected_gid=receipt["group_gid"], expected_mode=receipt["resulting_mode"],
                            expected_sha256=receipt["sha256"])
    if (before.device, before.inode, before.size) != (receipt["device"], receipt["inode"], receipt["size"]):
        raise RuntimeError("LEDGER_IDENTITY_INVALID")
    os.chmod(path, receipt["original_mode"])
    inspect_ledger(path, expected_path=path, expected_uid=receipt["owner_uid"],
                   expected_gid=receipt["group_gid"], expected_mode=receipt["original_mode"],
                   expected_sha256=receipt["sha256"])
    return "LEDGER_MODE_ROLLED_BACK"


def inventory_tree(root: Path) -> list[dict[str, Any]]:
    if not root.is_absolute() or root.is_symlink() or not root.is_dir() or root.stat().st_uid != os.getuid():
        raise RuntimeError("RUNTIME_ROOT_INVALID")
    rows: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        info = path.lstat()
        if path.is_symlink() or info.st_uid != os.getuid() or not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)):
            raise RuntimeError("RUNTIME_INVENTORY_INVALID")
        mode = stat.S_IMODE(info.st_mode)
        if mode & 0o222:
            raise RuntimeError("RUNTIME_WRITABLE")
        if path.is_file():
            rows.append({"path": relative, "size": info.st_size, "mode": mode, "sha256": file_hash(path)})
    return rows


def dependency_inventory(root: Path) -> list[dict[str, str]]:
    rows = []
    for metadata in sorted(root.rglob("*.dist-info/METADATA")):
        name = version = None
        for line in metadata.read_text(errors="strict").splitlines():
            if line.startswith("Name: ") and name is None: name = line[6:]
            if line.startswith("Version: ") and version is None: version = line[9:]
            if name and version: break
        if not name or not version: raise RuntimeError("RUNTIME_DEPENDENCIES_INVALID")
        rows.append({"name": name, "version": version,
                     "metadata_path": metadata.relative_to(root).as_posix(), "metadata_sha256": file_hash(metadata)})
    return rows


def validate_runtime_manifest(root: Path, manifest: dict[str, Any], *, expected_release_commit: str) -> dict[str, Any]:
    required = {"schema", "runtime_id", "release_commit", "runtime_root", "interpreter",
                "interpreter_sha256", "python_version", "dependency_inventory",
                "file_inventory", "platform_dependencies", "content_hash"}
    if set(manifest) != required or manifest.get("schema") != RUNTIME_MANIFEST_SCHEMA or manifest.get("content_hash") != digest(manifest):
        raise RuntimeError("RUNTIME_MANIFEST_INVALID")
    if manifest.get("release_commit") != expected_release_commit or not HEX40.fullmatch(expected_release_commit):
        raise RuntimeError("RUNTIME_RELEASE_MISMATCH")
    if Path(manifest.get("runtime_root", "")) != root or not root.is_absolute():
        raise RuntimeError("RUNTIME_ROOT_INVALID")
    interpreter = Path(manifest.get("interpreter", ""))
    if interpreter.is_symlink() or root not in interpreter.parents:
        raise RuntimeError("RUNTIME_INTERPRETER_INVALID")
    info = _owner_regular(interpreter)
    if info.st_mode & 0o222 or file_hash(interpreter) != manifest.get("interpreter_sha256"):
        raise RuntimeError("RUNTIME_INTERPRETER_INVALID")
    version = subprocess.run((str(interpreter), "--version"), check=True, capture_output=True, text=True, timeout=5).stdout.strip()
    if version != f"Python {PYTHON_VERSION}" or manifest.get("python_version") != PYTHON_VERSION:
        raise RuntimeError("RUNTIME_VERSION_INVALID")
    observed = inventory_tree(root)
    manifest_name = "runtime-manifest.json"
    observed_without_manifest = [row for row in observed if row["path"] != manifest_name]
    if manifest.get("file_inventory") != observed_without_manifest:
        raise RuntimeError("RUNTIME_INVENTORY_INVALID")
    if manifest.get("dependency_inventory") != dependency_inventory(root) or not manifest["dependency_inventory"]:
        raise RuntimeError("RUNTIME_DEPENDENCIES_INVALID")
    for dependency in manifest.get("platform_dependencies", []):
        path = Path(dependency.get("path", ""))
        if not path.is_absolute() or "/GitHub/" in str(path) or not path.is_file() or path.is_symlink():
            raise RuntimeError("RUNTIME_PLATFORM_DEPENDENCY_INVALID")
        if file_hash(path) != dependency.get("sha256"):
            raise RuntimeError("RUNTIME_PLATFORM_DEPENDENCY_INVALID")
    return manifest


def validate_service_plists(plists: Iterable[Path], *, release_root: Path, runtime_root: Path,
                            ledger_path: Path, interpreter: Path) -> dict[str, str]:
    expected_labels = {"com.iios.backend8002", "com.iios.v7living-truth-sidecar",
                       "com.iios.expansion-wing-projection-publisher",
                       "com.iios.expansion-wing-unattended-tuesday"}
    hashes: dict[str, str] = {}
    for path in plists:
        value = plistlib.loads(path.read_bytes())
        label = value.get("Label")
        environment = value.get("EnvironmentVariables", {})
        arguments = value.get("ProgramArguments", [])
        paths = [str(value.get("WorkingDirectory", "")), str(environment.get("PYTHONPATH", "")), *map(str, arguments)]
        absolute_paths = [item for item in paths if item.startswith("/")]
        permitted_roots = (str(release_root), str(runtime_root))
        if (label not in expected_labels or arguments[:1] != [str(interpreter)]
                or environment.get("IIOS_DB_PATH") != str(ledger_path)
                or environment.get("PYTHONPATH") != str(release_root / "source/BACK END/backend")
                or not all(item == str(ledger_path) or "/GitHub/" not in item for item in paths)
                or any(item != str(ledger_path) and not item.startswith(permitted_roots) for item in absolute_paths)):
            raise RuntimeError("SERVICE_DEPLOYMENT_INVALID")
        hashes[label] = file_hash(path)
    if set(hashes) != expected_labels:
        raise RuntimeError("SERVICE_DEPLOYMENT_INVALID")
    return hashes


def render_service_plists(*, source_root: Path, destination: Path, release_root: Path,
                          runtime_root: Path, ledger_path: Path, log_root: Path) -> dict[str, str]:
    if (any("/GitHub/" in str(path) for path in (release_root, runtime_root))
            or release_root == runtime_root or not all(path.is_absolute() for path in (release_root, runtime_root, ledger_path, log_root))):
        raise RuntimeError("SERVICE_DEPLOYMENT_INVALID")
    interpreter = runtime_root / "bin/python3.14"
    replacements = {"__IMMUTABLE_PYTHON__": str(interpreter), "__IMMUTABLE_RELEASE__": str(release_root),
                    "__OPERATIONAL_LEDGER_PATH__": str(ledger_path),
                    "__OWNER_ONLY_LOG__": str(log_root / "UnattendedTuesday/unattended.log"),
                    "__OWNER_ONLY_BACKEND_OUT__": str(log_root / "backend8002.out.log"),
                    "__OWNER_ONLY_BACKEND_ERR__": str(log_root / "backend8002.err.log"),
                    "__OWNER_ONLY_MUSEUM_OUT__": str(log_root / "v7living-truth-sidecar.out.log"),
                    "__OWNER_ONLY_MUSEUM_ERR__": str(log_root / "v7living-truth-sidecar.err.log")}
    names = ("com.iios.backend8002.plist", "com.iios.v7living-truth-sidecar.plist",
             "com.iios.expansion-wing-projection-publisher.plist",
             "com.iios.expansion-wing-unattended-tuesday.plist")
    destination.mkdir(mode=0o700, parents=True, exist_ok=False)
    for name in names:
        template = source_root / "config" / f"{name}.template"
        raw = template.read_text()
        for marker, value in replacements.items(): raw = raw.replace(marker, value)
        if "__" in raw: raise RuntimeError("SERVICE_DEPLOYMENT_INVALID")
        plistlib.loads(raw.encode())
        target = destination / name; target.write_text(raw); target.chmod(0o600)
    return validate_service_plists((destination/name for name in names), release_root=release_root,
                                   runtime_root=runtime_root, ledger_path=ledger_path, interpreter=interpreter)


def validate_active_release(path: Path, *, configured_ledger: str | None = None) -> dict[str, Any]:
    _owner_regular(path, mode=0o600)
    value = json.loads(path.read_bytes())
    required = {"schema", "release_id", "git_commit", "release_manifest_sha256", "release_root",
                "runtime_id", "runtime_root", "runtime_manifest_sha256", "operational_ledger_path",
                "ledger_path_contract_hash", "ledger_migration_contract_hash", "content_hash"}
    if set(value) != required or value.get("schema") != ACTIVE_RELEASE_SCHEMA or value.get("content_hash") != digest(value):
        raise RuntimeError("EXPECTED_RELEASE_UNAVAILABLE")
    release_root = Path(value["release_root"]); runtime_root = Path(value["runtime_root"]); ledger = Path(value["operational_ledger_path"])
    if (not HEX40.fullmatch(value["git_commit"]) or not release_root.is_absolute() or not runtime_root.is_absolute()
            or not ledger.is_absolute() or release_root in ledger.parents or runtime_root in ledger.parents
            or configured_ledger is not None and configured_ledger != str(ledger)):
        raise RuntimeError("EXPECTED_RELEASE_UNAVAILABLE")
    for root, name, expected in ((release_root, "release-manifest.json", value["release_manifest_sha256"]),
                                 (runtime_root, "runtime-manifest.json", value["runtime_manifest_sha256"])):
        target = root / name
        if target.is_symlink() or not target.is_file() or file_hash(target) != expected:
            raise RuntimeError("EXPECTED_RELEASE_UNAVAILABLE")
    runtime_manifest = json.loads((runtime_root / "runtime-manifest.json").read_bytes())
    validate_runtime_manifest(runtime_root, runtime_manifest, expected_release_commit=value["git_commit"])
    binding = {"release_id": value["release_id"], "git_commit": value["git_commit"],
               "release_root": str(release_root), "runtime_id": value["runtime_id"],
               "runtime_root": str(runtime_root), "operational_ledger_path": str(ledger)}
    if value["ledger_path_contract_hash"] != hashlib.sha256(canonical(binding)).hexdigest():
        raise RuntimeError("EXPECTED_RELEASE_UNAVAILABLE")
    return value
