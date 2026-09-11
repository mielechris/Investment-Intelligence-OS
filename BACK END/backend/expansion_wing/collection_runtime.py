"""Fresh collection installation: independently pinned byte inventory, never ledger probes."""
from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import sys
from pathlib import Path, PurePosixPath

from .collection_plan import SESSION, SPEC_SHA256, canonical, digest, pin
from .collection_session import exclusive, read_bytes, safe_directory

LABEL = "com.iios.financial-datasets-collection-20260911"
MODULES = ("__init__.py", "models.py", "collection_plan.py", "collection_session.py",
           "collection_runtime.py", "collection_service.py", "collection_transport.py",
           "financial_datasets.py", "financial_datasets_tls.py", "keychain_adapter.py")
FILES = tuple("expansion_wing/" + name for name in MODULES) + ("cacert.pem",)
DIRECTORIES = ("release", "inputs", "state", "raw", "receipts", "logs", "rollback")


def manifest_document(path, expected, root, source_commit):
    data = read_bytes(path)
    if hashlib.sha256(data).hexdigest() != pin(expected):
        raise ValueError("RELEASE_PIN_MISMATCH")
    doc = json.loads(data)
    if (doc.get("schema") != "fd-collection-release-v1" or doc.get("session") != SESSION
            or doc.get("spec_sha256") != SPEC_SHA256 or doc.get("installed_root") != str(root)
            or doc.get("source_commit") != source_commit or not re.fullmatch(r"[0-9a-f]{40}", source_commit)
            or doc.get("label") != LABEL or set(doc.get("files", {})) != set(FILES)):
        raise ValueError("RELEASE_IDENTITY_INVALID")
    for path, record in doc["files"].items():
        parsed = PurePosixPath(path)
        if parsed.is_absolute() or ".." in parsed.parts or str(parsed) != path:
            raise ValueError("UNSAFE_RELEASE_PATH")
        pin(record["sha256"])
        if type(record["size"]) is not int or record["size"] <= 0:
            raise ValueError("RELEASE_SIZE_INVALID")
    runtime = doc["runtime"]
    executable = Path(runtime["executable"])
    # Explicit runtime path only. No executable discovery or invoking a toolchain.
    if not executable.is_absolute() or executable.resolve(strict=True) != executable:
        raise ValueError("RUNTIME_PATH_INVALID")
    if Path(sys.executable).resolve() != executable:
        raise ValueError("RUNTIME_INTERPRETER_MISMATCH")
    if hashlib.sha256(read_bytes(executable, allow_root_owner=True)).hexdigest() != pin(runtime["sha256"]):
        raise ValueError("RUNTIME_HASH_INVALID")
    if runtime["version"] != platform.python_version() or runtime["architecture"] != platform.machine():
        raise ValueError("RUNTIME_VERSION_INVALID")
    if Path(sys.executable).resolve() != executable:
        raise ValueError("RUNTIME_INTERPRETER_MISMATCH")
    source_inventory = {"source_commit": source_commit,
                        "files": {name: doc["files"][name] for name in FILES if name != "cacert.pem"}}
    if digest(source_inventory) != pin(doc["source_inventory_sha256"]):
        raise ValueError("SOURCE_INVENTORY_BINDING_INVALID")
    if source_commit in ("455d31752a0fc73c73625f5757d0f4e87683a6ed", "52ae1028088afe269ae41ebff9719f748297e83b"):
        raise ValueError("UNREPAIRED_SOURCE_COMMIT")
    return doc, data


def inventory(directory, manifest):
    directory = Path(directory)
    if directory.resolve(strict=True) != directory:
        raise ValueError("RELEASE_ROOT_INVALID")
    actual = set()
    for path in directory.rglob("*"):
        if path.is_symlink():
            raise ValueError("RELEASE_SYMLINK")
        if path.is_file():
            actual.add(path.relative_to(directory).as_posix())
        elif path.relative_to(directory).as_posix() != "expansion_wing":
            raise ValueError("UNEXPECTED_RELEASE_DIRECTORY")
    if actual != set(FILES):
        raise ValueError("RELEASE_MEMBERSHIP_INVALID")
    for name, record in manifest["files"].items():
        data = read_bytes(directory / name)
        if len(data) != record["size"] or hashlib.sha256(data).hexdigest() != record["sha256"]:
            raise ValueError("RELEASE_BYTES_INVALID")


def install_disabled(root, payload, manifest_path, expected, source_commit):
    """Future authorized installer; never invoked against a permanent root by source tests."""
    root, payload = Path(root), Path(payload)
    if not root.is_absolute() or root.exists() or root.is_symlink() or root.parent.resolve(strict=True) != root.parent:
        raise ValueError("NEW_CANONICAL_ROOT_REQUIRED")
    manifest, data = manifest_document(manifest_path, expected, root, source_commit)
    inventory(payload, manifest)
    root.mkdir(mode=0o700)
    for name in DIRECTORIES:
        (root / name).mkdir(mode=0o700)
    (root / "release" / "expansion_wing").mkdir(mode=0o700)
    # Copy exact independent pins, verify again after copy and recheck source.
    for name, record in manifest["files"].items():
        before = read_bytes(payload / name)
        if hashlib.sha256(before).hexdigest() != record["sha256"]:
            raise ValueError("SOURCE_CHANGED")
        exclusive(root / "release" / name, before)
        if read_bytes(root / "release" / name) != before or read_bytes(payload / name) != before:
            raise ValueError("COPY_VERIFICATION_FAILED")
    exclusive(root / "release-manifest.json", data)
    info = root.lstat()
    exclusive(root / "state" / "ownership.json", canonical({"device": info.st_dev, "inode": info.st_ino,
                                                           "uid": info.st_uid, "release": expected}))
    inventory(root / "release", manifest)
    return "INSTALLED_DISABLED_ZERO_RELEASED_CREDITS"


def validate_installed(root, expected, source_commit, *, executing=False):
    root = Path(root)
    identity = safe_directory(root)
    if {p.name for p in root.iterdir()} != set(DIRECTORIES) | {"release-manifest.json"}:
        raise ValueError("ROOT_MEMBERSHIP_INVALID")
    for name in DIRECTORIES:
        safe_directory(root / name)
    manifest, _ = manifest_document(root / "release-manifest.json", expected, root, source_commit)
    ownership = json.loads(read_bytes(root / "state" / "ownership.json"))
    if ownership != {"device": identity[0], "inode": identity[1], "uid": os.getuid(), "release": expected}:
        raise ValueError("ROOT_OWNERSHIP_INVALID")
    if {p.name for p in (root / "inputs").iterdir()} not in (set(), {"account.json", "authority.json"}):
        raise ValueError("INPUT_MEMBERSHIP_INVALID")
    if {p.name for p in (root / "state").iterdir()} - {"ownership.json", "session.lock", "supervisor.lock", "disarmed.json"}:
        raise ValueError("STATE_MEMBERSHIP_INVALID")
    inventory(root / "release", manifest)
    if executing:
        if Path(__file__).resolve() != root / "release" / "expansion_wing" / "collection_runtime.py":
            raise ValueError("MUTABLE_CHECKOUT_EXECUTION_REJECTED")
        for module in tuple(sys.modules.values()):
            name = getattr(module, "__name__", "")
            filename = getattr(module, "__file__", None)
            if name.startswith("expansion_wing") and filename:
                p = Path(filename).resolve()
                if not p.is_relative_to(root / "release") or p.relative_to(root / "release").as_posix() not in FILES:
                    raise ValueError("UNPINNED_PACKAGE_IMPORT")
    return manifest


def startup_plist(root, manifest_hash, source_commit, runtime_executable, account_hash, authority_hash):
    """Returns reviewable data; does not install a LaunchAgent or launch a process."""
    import plistlib
    for value in (manifest_hash, account_hash, authority_hash):
        pin(value)
    return plistlib.dumps({"Label": LABEL, "ProgramArguments": [runtime_executable, "-B", "-m",
        "expansion_wing.collection_service", "supervise", "--root", str(root),
        "--release-sha256", manifest_hash, "--source-commit", source_commit,
        "--account-sha256", account_hash, "--authority-sha256", authority_hash],
        "WorkingDirectory": str(Path(root) / "release"), "RunAtLoad": True,
        "KeepAlive": False, "ExitTimeOut": 20,
        "EnvironmentVariables": {"PYTHONDONTWRITEBYTECODE": "1"},
        "StandardOutPath": str(Path(root) / "logs" / "stdout.log"),
        "StandardErrorPath": str(Path(root) / "logs" / "stderr.log")}, sort_keys=True)
