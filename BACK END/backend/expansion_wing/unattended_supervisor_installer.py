"""Verified, fail-closed installation boundary for the unattended supervisor.

Operational mode has fixed owner-local destinations.  Isolated roots are accepted
only by the Python API used by deterministic tests; they are never CLI options.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import plistlib
import shutil
import stat
import subprocess
import tempfile
import urllib.request
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Callable

from .provider_readiness import installed_readiness_projection, operational_cost_binding
from .unattended_tuesday_service import SUPERVISOR_LOCK_NAME

SCHEMA = "iios-unattended-supervisor-installation-v1"
ROLLBACK_SCHEMA = "iios-unattended-supervisor-rollback-v1"
INSTALLER_VERSION = "superbatch-28h-v1"
LABEL = "com.iios.expansion-wing-unattended-tuesday"
BRANCH = "feature/iios-expansion-wing-dual-book-machinery"
ENTRYPOINT = "expansion_wing.unattended_tuesday_service"
STATE_ROOT_IDENTITY = "IIOS_UNATTENDED_TUESDAY"
PLIST_IDENTITY = "com.iios.expansion-wing-unattended-tuesday.plist"
MAX_FILES = 10
MAX_FILE_BYTES = 1_048_576
ARTIFACT_NAMES = (
    "expansion_wing/provider_readiness.py",
    "expansion_wing/provider_readiness_service.py",
    "expansion_wing/unattended_tuesday.py",
    "expansion_wing/unattended_tuesday_service.py",
    "expansion_wing/operational_market_executor.py",
    "expansion_wing/operational_market_executor_installer.py",
    "expansion_wing/operational_market_executor_service.py",
    "expansion_wing/september_9_canonical_plan.py",
    PLIST_IDENTITY,
)
LEGACY_ARTIFACT_NAMES = ARTIFACT_NAMES[:4] + (PLIST_IDENTITY,)
PRE_RECOVERY_COMMIT = "ef09d94c99ed4943dd623a8636c9148dc1c9dddc"
PRE_RECOVERY_ARTIFACT_NAMES = tuple(name for name in ARTIFACT_NAMES if name != "expansion_wing/september_9_canonical_plan.py")
MIGRATION_SCHEMA = "iios-unattended-supervisor-layout-migration-v1"
MIGRATION_ROLLBACK_SCHEMA = "iios-unattended-supervisor-layout-rollback-v1"
MIGRATION_JOURNAL = ".layout-migration.json"
INSTALL_ROOT = Path.home()/"Library/Application Support/IIOS/UnattendedTuesdaySupervisor"
INSTALLED_ARTIFACTS = INSTALL_ROOT/"installed-artifacts"
CANDIDATE_ROOT = Path.home()/"Library/Application Support/IIOS/UnattendedTuesdaySupervisorCandidate"
MANIFEST_NAME = "installation-manifest.json"
LOCK_NAME = "installation.lock"
ROLLBACK_PARENT = Path.home()/"Library/Application Support/IIOS/Rollback"
ROLLBACK_ROOT = ROLLBACK_PARENT/"UnattendedTuesdaySupervisor28H"
MUSEUM_IDENTITY_ROOT = Path.home()/"Library/Application Support/IIOS/Museum5176"
MUSEUM_IDENTITY_MANIFEST = MUSEUM_IDENTITY_ROOT/"installation-manifest.json"
POLICY_ROOT = Path.home()/"Library/Application Support/IIOS/UnattendedTuesday"
LAUNCH_PLIST = Path.home()/"Library/LaunchAgents"/PLIST_IDENTITY
SOURCE_ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = SOURCE_ROOT/"BACK END/backend"
PLIST_TEMPLATE = SOURCE_ROOT/"config/com.iios.expansion-wing-unattended-tuesday.plist.template"


def _canonical(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)+"\n").encode("ascii")


def _hash_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _hash(value: Any) -> str:
    return _hash_bytes(_canonical(value))


def _commit(value: str) -> bool:
    return isinstance(value, str) and len(value) == 40 and all(c in "0123456789abcdef" for c in value)


def _safe_relative(value: str) -> bool:
    path = PurePosixPath(value)
    return bool(value) and not path.is_absolute() and ".." not in path.parts and str(path) == value


def _file_record(path: Path, relative: str) -> dict[str, Any]:
    info = path.lstat()
    if path.is_symlink() or not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
        raise ValueError("CANDIDATE_INVENTORY_INVALID")
    if info.st_size > MAX_FILE_BYTES:
        raise ValueError("CANDIDATE_INVENTORY_INVALID")
    return {"relative_path": relative, "file_type": "REGULAR", "size": info.st_size,
            "mode": stat.S_IMODE(info.st_mode), "sha256": _hash_bytes(path.read_bytes())}


def inventory(root: Path, expected: tuple[str, ...] = ARTIFACT_NAMES) -> list[dict[str, Any]]:
    info = root.lstat()
    if root.is_symlink() or not stat.S_ISDIR(info.st_mode) or info.st_uid!=os.getuid() or stat.S_IMODE(info.st_mode)!=0o700:
        raise ValueError("CANDIDATE_INVENTORY_INVALID")
    actual = []
    for path in root.rglob("*"):
        if path.is_dir() and not path.is_symlink():
            continue
        actual.append(path.relative_to(root).as_posix())
    allowed=set(expected)|({MANIFEST_NAME} if (root/MANIFEST_NAME).exists() else set())
    if set(actual) != allowed or len(actual) > MAX_FILES:
        raise ValueError("CANDIDATE_INVENTORY_INVALID")
    return [_file_record(root/name, name) for name in sorted(expected)]


def build_candidate(destination: Path, *, source_commit: str, source_root: Path = SOURCE_ROOT,
                    python: str = "/Library/Frameworks/Python.framework/Versions/3.14/bin/python3",
                    log_path: str | None = None,ledger_path: str | None = None) -> str:
    if not _commit(source_commit) or destination.exists():
        raise ValueError("SOURCE_COMMIT_MISMATCH" if not _commit(source_commit) else "CANDIDATE_INVENTORY_INVALID")
    destination.mkdir(mode=0o700, parents=False)
    (destination/"expansion_wing").mkdir(mode=0o700)
    for name in ARTIFACT_NAMES[:-1]:
        source = source_root/"BACK END/backend"/name
        target = destination/name
        if source.is_symlink() or not source.is_file():
            raise ValueError("CANDIDATE_INVENTORY_INVALID")
        target.write_bytes(source.read_bytes()); os.chmod(target, 0o600)
    configured_ledger=ledger_path or os.environ.get("IIOS_DB_PATH")
    if (not configured_ledger or not Path(configured_ledger).is_absolute()
            or source_root.resolve() in Path(configured_ledger).resolve().parents):
        raise ValueError("LEDGER_PATH_CONTRACT_INVALID")
    template = source_root/"config/com.iios.expansion-wing-unattended-tuesday.plist.template"
    if "/GitHub/" in python or "/GitHub/" in str(source_root):
        raise ValueError("IMMUTABLE_RUNTIME_REQUIRED")
    raw = template.read_text().replace("__IMMUTABLE_PYTHON__", python).replace("__IMMUTABLE_RELEASE__", str(source_root))
    raw = raw.replace("__OWNER_ONLY_LOG__", log_path or str(Path.home()/"Library/Logs/IIOS/UnattendedTuesday/unattended.log"))
    raw = raw.replace("__OPERATIONAL_LEDGER_PATH__",configured_ledger)
    plistlib.loads(raw.encode("utf-8"))
    (destination/PLIST_IDENTITY).write_text(raw); os.chmod(destination/PLIST_IDENTITY, 0o600)
    inventory(destination)
    return "CANDIDATE_VALID"


def make_manifest(candidate: Path, *, source_commit: str, installed_at: datetime) -> dict[str, Any]:
    if not _commit(source_commit) or installed_at.tzinfo != timezone.utc or installed_at > datetime.now(timezone.utc):
        raise ValueError("MANIFEST_INVALID")
    files = inventory(candidate)
    body = {"schema": SCHEMA, "installed_source_commit": source_commit,
            "installation_timestamp": installed_at.isoformat(), "service_label": LABEL,
            "state_root_identity": STATE_ROOT_IDENTITY, "executable_module_entrypoint": ENTRYPOINT,
            "plist_identity": PLIST_IDENTITY, "artifact_inventory": files,
            "canonical_inventory_identity": _hash(files), "installer_version": INSTALLER_VERSION,
            "immutable": True}
    return body | {"canonical_manifest_content_hash": _hash(body)}


def validate_manifest(value: Any, candidate: Path | None = None, *, expected_commit: str | None = None,
                      now: datetime | None = None) -> dict[str, Any]:
    keys = {"schema","installed_source_commit","installation_timestamp","service_label","state_root_identity",
            "executable_module_entrypoint","plist_identity","artifact_inventory","canonical_inventory_identity",
            "installer_version","immutable","canonical_manifest_content_hash"}
    if not isinstance(value, dict) or set(value) != keys or value.get("schema") != SCHEMA:
        raise ValueError("MANIFEST_INVALID")
    body = {k:value[k] for k in value if k != "canonical_manifest_content_hash"}
    if value["canonical_manifest_content_hash"] != _hash(body): raise ValueError("MANIFEST_INVALID")
    if not _commit(value["installed_source_commit"]) or (expected_commit and value["installed_source_commit"] != expected_commit):
        raise ValueError("SOURCE_COMMIT_MISMATCH")
    if (value["service_label"],value["state_root_identity"],value["executable_module_entrypoint"],value["plist_identity"],
            value["installer_version"],value["immutable"]) != (LABEL,STATE_ROOT_IDENTITY,ENTRYPOINT,PLIST_IDENTITY,INSTALLER_VERSION,True):
        raise ValueError("MANIFEST_INVALID")
    try: stamp=datetime.fromisoformat(value["installation_timestamp"])
    except (TypeError,ValueError): raise ValueError("MANIFEST_INVALID")
    if stamp.tzinfo != timezone.utc or stamp > (now or datetime.now(timezone.utc)): raise ValueError("MANIFEST_INVALID")
    rows=value["artifact_inventory"]
    if not isinstance(rows,list) or len(rows)!=len(ARTIFACT_NAMES): raise ValueError("MANIFEST_INVALID")
    paths=[row.get("relative_path") for row in rows if isinstance(row,dict)]
    if paths != sorted(ARTIFACT_NAMES) or len(set(paths)) != len(paths) or not all(_safe_relative(x) for x in paths):
        raise ValueError("MANIFEST_INVALID")
    if any(set(row)!={"relative_path","file_type","size","mode","sha256"} or row["file_type"]!="REGULAR"
           or row["mode"]!=0o600 or isinstance(row["size"],bool) or not isinstance(row["size"],int)
           or row["size"]<0 or row["size"]>MAX_FILE_BYTES or not isinstance(row["sha256"],str)
           or len(row["sha256"])!=64 for row in rows): raise ValueError("MANIFEST_INVALID")
    if value["canonical_inventory_identity"] != _hash(rows): raise ValueError("MANIFEST_INVALID")
    if candidate is not None and rows != inventory(candidate): raise ValueError("INSTALLED_INVENTORY_INVALID")
    return value


def validate_legacy_manifest(value: Any, candidate: Path, *, expected_commit: str) -> dict[str, Any]:
    """Accept only the one reviewed five-artifact predecessor of this installer."""
    keys = {"schema","installed_source_commit","installation_timestamp","service_label","state_root_identity",
            "executable_module_entrypoint","plist_identity","artifact_inventory","canonical_inventory_identity",
            "installer_version","immutable","canonical_manifest_content_hash"}
    if not isinstance(value, dict) or set(value) != keys or value.get("schema") != SCHEMA:
        raise ValueError("LEGACY_MANIFEST_INVALID")
    body = {key:value[key] for key in value if key != "canonical_manifest_content_hash"}
    if value["canonical_manifest_content_hash"] != _hash(body): raise ValueError("LEGACY_MANIFEST_INVALID")
    fixed = (value.get("service_label"), value.get("state_root_identity"),
             value.get("executable_module_entrypoint"), value.get("plist_identity"),
             value.get("installer_version"), value.get("immutable"))
    if fixed != (LABEL, STATE_ROOT_IDENTITY, ENTRYPOINT, PLIST_IDENTITY, INSTALLER_VERSION, True):
        raise ValueError("LEGACY_MANIFEST_INVALID")
    if value.get("installed_source_commit") != expected_commit or not _commit(expected_commit):
        raise ValueError("SOURCE_COMMIT_MISMATCH")
    try: stamp = datetime.fromisoformat(value["installation_timestamp"])
    except (TypeError, ValueError): raise ValueError("LEGACY_MANIFEST_INVALID")
    if stamp.tzinfo != timezone.utc or stamp > datetime.now(timezone.utc): raise ValueError("LEGACY_MANIFEST_INVALID")
    rows = value.get("artifact_inventory")
    paths=[row.get("relative_path") for row in rows if isinstance(row,dict)] if isinstance(rows,list) else []
    reviewed_predecessor = PRE_RECOVERY_ARTIFACT_NAMES if expected_commit==PRE_RECOVERY_COMMIT else LEGACY_ARTIFACT_NAMES
    if paths != sorted(reviewed_predecessor):
        raise ValueError("LEGACY_LAYOUT_UNRECOGNIZED")
    if value.get("canonical_inventory_identity") != _hash(rows): raise ValueError("LEGACY_MANIFEST_INVALID")
    if rows != inventory(candidate, reviewed_predecessor): raise ValueError("LEGACY_INVENTORY_INVALID")
    return value


def _tree_records(root: Path) -> list[dict[str, Any]]:
    root_info = root.lstat()
    if root.is_symlink() or not stat.S_ISDIR(root_info.st_mode) or root_info.st_uid != os.getuid():
        raise ValueError("MIGRATION_INVENTORY_INVALID")
    rows=[]
    for path in sorted(root.rglob("*")):
        info=path.lstat()
        relative=path.relative_to(root).as_posix()
        if path.is_symlink() or info.st_uid != os.getuid(): raise ValueError("MIGRATION_INVENTORY_INVALID")
        if stat.S_ISDIR(info.st_mode):
            if stat.S_IMODE(info.st_mode)!=0o700: raise ValueError("MIGRATION_PERMISSIONS_INVALID")
            continue
        if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode)!=0o600:
            raise ValueError("MIGRATION_PERMISSIONS_INVALID")
        rows.append(_file_record(path,relative))
    return rows


def _fsync_directory(path: Path) -> None:
    descriptor=os.open(path,os.O_RDONLY)
    try: os.fsync(descriptor)
    finally: os.close(descriptor)


def _copy_exact_tree(source: Path, destination: Path) -> None:
    if destination.exists(): raise ValueError("MIGRATION_TARGET_EXISTS")
    destination.mkdir(mode=0o700,parents=False)
    for path in sorted(source.rglob("*")):
        relative=path.relative_to(source); info=path.lstat(); target=destination/relative
        if path.is_symlink() or info.st_uid!=os.getuid(): raise ValueError("MIGRATION_INVENTORY_INVALID")
        if stat.S_ISDIR(info.st_mode): target.mkdir(mode=0o700)
        elif stat.S_ISREG(info.st_mode) and stat.S_IMODE(info.st_mode)==0o600:
            target.parent.mkdir(mode=0o700,parents=True,exist_ok=True); target.write_bytes(path.read_bytes()); os.chmod(target,0o600)
        else: raise ValueError("MIGRATION_PERMISSIONS_INVALID")
    _fsync_directory(destination)


def _validated_plist(path: Path,*,require_ledger:bool=True) -> bytes:
    raw=_read_owner_file(path)
    value=plistlib.loads(raw)
    arguments=value.get("ProgramArguments")
    expected_keys={"Label","ProgramArguments","WorkingDirectory","EnvironmentVariables","RunAtLoad",
                   "KeepAlive","ProcessType","StandardOutPath","StandardErrorPath","ThrottleInterval"}
    working=value.get("WorkingDirectory"); environment=value.get("EnvironmentVariables")
    if (not isinstance(value,dict) or set(value)!=expected_keys or value.get("Label") != LABEL or not isinstance(arguments,list)
            or arguments[1:] != ["-m",ENTRYPOINT,"--operational-supervisor"]
            or not isinstance(arguments[0],str) or not arguments[0].endswith("python3")):
        raise ValueError("PLIST_INVALID")
    expected_environment={"PYTHONPATH":working}
    if require_ledger:
        ledger=str(environment.get("IIOS_DB_PATH","")) if isinstance(environment,dict) else ""
        if (not Path(ledger).is_absolute() or Path(working) in Path(ledger).parents
                or environment.get("PYTHONDONTWRITEBYTECODE")!="1"):
            raise ValueError("LEDGER_PATH_CONTRACT_INVALID")
        expected_environment|={"IIOS_DB_PATH":ledger,"PYTHONDONTWRITEBYTECODE":"1"}
    if (not isinstance(working,str) or environment!=expected_environment
            or value.get("RunAtLoad") is not True or value.get("KeepAlive")!={"SuccessfulExit":False}
            or value.get("ProcessType")!="Background" or value.get("ThrottleInterval")!=60
            or not isinstance(value.get("StandardOutPath"),str)
            or value.get("StandardErrorPath")!=value.get("StandardOutPath")):
        raise ValueError("PLIST_INVALID")
    return raw


def _validated_existing_plist(path: Path) -> bytes:
    """Accept a reviewed legacy plist or the ledger-bound replacement, never a hybrid."""
    try:
        return _validated_plist(path, require_ledger=True)
    except ValueError as error:
        if str(error) != "LEDGER_PATH_CONTRACT_INVALID":
            raise
        return _validated_plist(path, require_ledger=False)


def _migration_document(*, legacy_commit:str, target_commit:str, phase:str,
                        legacy_manifest_hash:str, target_manifest_hash:str|None) -> dict[str,Any]:
    body={"schema":MIGRATION_SCHEMA,"legacy_source_commit":legacy_commit,"target_source_commit":target_commit,
          "phase":phase,"legacy_manifest_hash":legacy_manifest_hash,"target_manifest_hash":target_manifest_hash,
          "generation_selection_performed":False,"operational_authorization":False,"immutable":True}
    return body|{"content_hash":_hash(body)}


def _write_journal(root:Path, **values:Any)->None:
    _atomic(root/MIGRATION_JOURNAL,_canonical(_migration_document(**values)))


def _validate_migration_backup(backup:Path)->dict[str,Any]:
    _validate_owner_root(backup)
    raw=_read_owner_file(backup/"rollback-receipt.json"); value=json.loads(raw)
    body={key:value[key] for key in value if key!="content_hash"}
    if (value.get("schema")!=MIGRATION_ROLLBACK_SCHEMA or value.get("content_hash")!=_hash(body)
            or set(body)!={"schema","legacy_source_commit","target_source_commit","inventory","immutable"}):
        raise ValueError("ROLLBACK_INVALID")
    if value["inventory"]!=_tree_records(backup/"legacy-installation"): raise ValueError("ROLLBACK_INVALID")
    return value


def create_legacy_migration_backup(*, install_root:Path, launch_plist:Path, backup:Path,
                                   legacy_commit:str, target_commit:str)->dict[str,Any]:
    if backup.exists(): raise ValueError("ROLLBACK_ALREADY_EXISTS")
    artifacts=install_root/"installed-artifacts"; manifest=install_root/MANIFEST_NAME
    value=json.loads(_read_owner_file(manifest)); validate_legacy_manifest(value,artifacts,expected_commit=legacy_commit)
    plist_raw=_validated_plist(launch_plist,require_ledger=False)
    if plist_raw!=(artifacts/PLIST_IDENTITY).read_bytes(): raise ValueError("PLIST_INVALID")
    building=backup.parent/(backup.name+".building")
    if building.exists(): shutil.rmtree(building)
    building.mkdir(mode=0o700,parents=False); saved=building/"legacy-installation"; saved.mkdir(mode=0o700)
    _copy_exact_tree(artifacts,saved/"installed-artifacts")
    _atomic(saved/MANIFEST_NAME,_read_owner_file(manifest)); _atomic(saved/"launch-agent.plist",plist_raw)
    inventory_rows=_tree_records(saved)
    body={"schema":MIGRATION_ROLLBACK_SCHEMA,"legacy_source_commit":legacy_commit,
          "target_source_commit":target_commit,"inventory":inventory_rows,"immutable":True}
    _atomic(building/"rollback-receipt.json",_canonical(body|{"content_hash":_hash(body)}))
    _validate_migration_backup(building)
    os.replace(building,backup); _fsync_directory(backup.parent)
    return _validate_migration_backup(backup)


def rehearse_legacy_restoration(backup:Path)->str:
    _validate_migration_backup(backup)
    with tempfile.TemporaryDirectory() as raw:
        restored=Path(raw)/"restored"; restored.mkdir(mode=0o700)
        _copy_exact_tree(backup/"legacy-installation",restored/"legacy-installation")
        if _tree_records(restored/"legacy-installation") != _tree_records(backup/"legacy-installation"):
            raise ValueError("ROLLBACK_INVALID")
    return "LEGACY_RESTORATION_REHEARSED"


def _restore_legacy_from_backup(*, install_root:Path, launch_plist:Path, backup:Path)->None:
    receipt=_validate_migration_backup(backup); saved=backup/"legacy-installation"
    replacement=install_root.parent/(install_root.name+".legacy-restore")
    if replacement.exists(): shutil.rmtree(replacement)
    replacement.mkdir(mode=0o700); _copy_exact_tree(saved/"installed-artifacts",replacement/"installed-artifacts")
    _atomic(replacement/MANIFEST_NAME,(saved/MANIFEST_NAME).read_bytes())
    current=install_root.parent/(install_root.name+".failed-target")
    if current.exists(): shutil.rmtree(current)
    os.replace(install_root,current); os.replace(replacement,install_root); _fsync_directory(install_root.parent)
    _atomic(launch_plist,(saved/"launch-agent.plist").read_bytes())
    value=json.loads((install_root/MANIFEST_NAME).read_text())
    validate_legacy_manifest(value,install_root/"installed-artifacts",expected_commit=receipt["legacy_source_commit"])
    if _tree_records(saved)!=_tree_records(backup/"legacy-installation"): raise ValueError("ROLLBACK_INVALID")
    for residual in (current,install_root.parent/(install_root.name+".legacy-artifacts-hold"),
                     install_root.parent/(install_root.name+".eight-artifact-stage")):
        if residual.exists(): shutil.rmtree(residual)
    _fsync_directory(install_root.parent)


def migrate_legacy_layout(*, source_root:Path, install_root:Path, launch_plist:Path, backup:Path,
                          legacy_commit:str, target_commit:str, installed_at:datetime,
                          protected_state_root:Path|None=None, interrupt_at:str|None=None,
                          post_select_validator:Callable[[Path],None]|None=None,
                          service_stopped:bool=False,ledger_path:str|None=None)->str:
    """Migrate a stopped supervisor's reviewed five-file layout; never selects a market generation."""
    if not service_stopped: raise ValueError("SERVICE_TEARDOWN_REQUIRED")
    state_before=_tree_records(protected_state_root) if protected_state_root and protected_state_root.exists() else []
    manifest_path=install_root/MANIFEST_NAME; artifacts=install_root/"installed-artifacts"
    if manifest_path.exists():
        current=json.loads(_read_owner_file(manifest_path))
        try:
            validate_manifest(current,artifacts,expected_commit=target_commit)
            if backup.exists(): _validate_migration_backup(backup)
            if state_before!=( _tree_records(protected_state_root) if protected_state_root and protected_state_root.exists() else []):
                raise ValueError("PROTECTED_STATE_CHANGED")
            for residual in (install_root.parent/(install_root.name+".legacy-artifacts-hold"),
                             install_root.parent/(install_root.name+".eight-artifact-stage")):
                if residual.exists(): shutil.rmtree(residual)
            if (install_root/MIGRATION_JOURNAL).exists(): (install_root/MIGRATION_JOURNAL).unlink()
            return "SUPERVISOR_LAYOUT_ALREADY_CURRENT"
        except ValueError as exc:
            if str(exc)=="PROTECTED_STATE_CHANGED": raise
    legacy=json.loads(_read_owner_file(manifest_path)); validate_legacy_manifest(legacy,artifacts,expected_commit=legacy_commit)
    if backup.exists():
        receipt=_validate_migration_backup(backup)
        if (receipt["legacy_source_commit"],receipt["target_source_commit"])!=(legacy_commit,target_commit):
            raise ValueError("ROLLBACK_INVALID")
    else:
        create_legacy_migration_backup(install_root=install_root,launch_plist=launch_plist,backup=backup,
                                       legacy_commit=legacy_commit,target_commit=target_commit)
    if interrupt_at=="backup": raise RuntimeError("SIMULATED_INTERRUPTION")
    rehearse_legacy_restoration(backup)
    stage=install_root.parent/(install_root.name+".eight-artifact-stage")
    if stage.exists(): shutil.rmtree(stage)
    legacy_plist=plistlib.loads(_validated_plist(launch_plist,require_ledger=False))
    build_candidate(stage,source_commit=target_commit,source_root=source_root,
                    python=legacy_plist["ProgramArguments"][0],
                    log_path=legacy_plist.get("StandardOutPath"),ledger_path=ledger_path)
    target=write_manifest(stage,source_commit=target_commit,installed_at=installed_at)
    validate_candidate(stage,expected_commit=target_commit)
    (stage/MANIFEST_NAME).unlink(); _fsync_directory(stage)
    if interrupt_at=="staging": raise RuntimeError("SIMULATED_INTERRUPTION")
    _write_journal(install_root,legacy_commit=legacy_commit,target_commit=target_commit,phase="STAGED",
                   legacy_manifest_hash=legacy["canonical_manifest_content_hash"],target_manifest_hash=target["canonical_manifest_content_hash"])
    if interrupt_at=="before_selection": raise RuntimeError("SIMULATED_INTERRUPTION")
    hold=install_root.parent/(install_root.name+".legacy-artifacts-hold")
    if hold.exists(): raise ValueError("MIGRATION_TARGET_EXISTS")
    try:
        os.replace(artifacts,hold); os.replace(stage,artifacts); _fsync_directory(install_root.parent)
        _atomic(manifest_path,_canonical(target)); _atomic(launch_plist,(artifacts/PLIST_IDENTITY).read_bytes())
        _write_journal(install_root,legacy_commit=legacy_commit,target_commit=target_commit,phase="SELECTED",
                       legacy_manifest_hash=legacy["canonical_manifest_content_hash"],target_manifest_hash=target["canonical_manifest_content_hash"])
        if interrupt_at=="after_selection": raise RuntimeError("SIMULATED_INTERRUPTION")
        validate_installed_root(expected_commit=target_commit,root=install_root)
        if post_select_validator: post_select_validator(install_root)
        state_after=_tree_records(protected_state_root) if protected_state_root and protected_state_root.exists() else []
        if state_before!=state_after: raise ValueError("PROTECTED_STATE_CHANGED")
    except Exception:
        if install_root.exists():
            _restore_legacy_from_backup(install_root=install_root,launch_plist=launch_plist,backup=backup)
        elif hold.exists():
            os.replace(hold,artifacts); _fsync_directory(install_root.parent)
        raise
    if hold.exists(): shutil.rmtree(hold)
    (install_root/MIGRATION_JOURNAL).unlink(); _fsync_directory(install_root)
    return "SUPERVISOR_LAYOUT_MIGRATED_DISABLED"


def _atomic(path: Path, data: bytes, mode: int = 0o600) -> None:
    fd, raw = tempfile.mkstemp(prefix=".install-", dir=path.parent)
    try:
        os.write(fd,data); os.fchmod(fd,mode); os.fsync(fd); os.close(fd); fd=-1
        os.replace(raw,path)
        parent=os.open(path.parent,os.O_RDONLY)
        try: os.fsync(parent)
        finally: os.close(parent)
    finally:
        if fd >= 0: os.close(fd)
        if os.path.exists(raw): os.unlink(raw)


def _copy_tree(source: Path, destination: Path) -> None:
    if destination.exists(): raise ValueError("FAILED_CLOSED")
    destination.mkdir(mode=0o700,parents=False)
    for row in inventory(source):
        target=destination/row["relative_path"]; target.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
        target.write_bytes((source/row["relative_path"]).read_bytes()); os.chmod(target,row["mode"])
    directory=os.open(destination,os.O_RDONLY)
    try: os.fsync(directory)
    finally: os.close(directory)


def write_manifest(candidate: Path, *, source_commit: str, installed_at: datetime) -> dict[str, Any]:
    value=make_manifest(candidate,source_commit=source_commit,installed_at=installed_at)
    _atomic(candidate/MANIFEST_NAME,_canonical(value)); return value


def validate_candidate(candidate: Path, *, expected_commit: str) -> str:
    raw=(candidate/MANIFEST_NAME).read_bytes(); manifest=json.loads(raw)
    if raw != _canonical(manifest): raise ValueError("MANIFEST_INVALID")
    validate_manifest(manifest,candidate,expected_commit=expected_commit)
    return "CANDIDATE_VALID"


def validate_installed_root(*, expected_commit: str, root: Path = INSTALL_ROOT) -> str:
    info=root.lstat()
    if root.is_symlink() or not stat.S_ISDIR(info.st_mode) or stat.S_IMODE(info.st_mode)!=0o700 or info.st_uid!=os.getuid():
        raise ValueError("INSTALLED_INVENTORY_INVALID")
    manifest_path=root/MANIFEST_NAME; item=manifest_path.lstat()
    if manifest_path.is_symlink() or not stat.S_ISREG(item.st_mode) or stat.S_IMODE(item.st_mode)!=0o600 or item.st_uid!=os.getuid():
        raise ValueError("MANIFEST_INVALID")
    value=json.loads(manifest_path.read_text())
    validate_manifest(value,root/"installed-artifacts",expected_commit=expected_commit)
    return "INSTALLED_VALID"


def museum_identity_document(source_commit:str,inventory_identity:str)->dict[str,Any]:
    if not _commit(source_commit) or not isinstance(inventory_identity,str) or len(inventory_identity)!=64:
        raise ValueError("MANIFEST_INVALID")
    body={"schema":"iios-museum-5176-installation-v1","installed_source_commit":source_commit,
          "bundle_inventory_identity":inventory_identity,"immutable":True}
    return body|{"canonical_content_hash":_hash(body)}


def validate_museum_identity(value:Any)->str:
    if not isinstance(value,dict) or set(value)!={"schema","installed_source_commit","bundle_inventory_identity","immutable","canonical_content_hash"}:
        raise ValueError("MANIFEST_INVALID")
    body={k:value[k] for k in value if k!="canonical_content_hash"}
    if value!=museum_identity_document(value.get("installed_source_commit"),value.get("bundle_inventory_identity")) or value["canonical_content_hash"]!=_hash(body):
        raise ValueError("MANIFEST_INVALID")
    return value["installed_source_commit"]


def _read_owner_file(path:Path)->bytes:
    stat=path.lstat()
    if path.is_symlink() or not path.is_file() or stat.st_uid!=os.getuid() or stat.st_mode&0o777!=0o600:
        raise ValueError("MANIFEST_INVALID")
    return path.read_bytes()


def _validate_owner_root(path:Path)->None:
    stat=path.lstat()
    if path.is_symlink() or not path.is_dir() or stat.st_uid!=os.getuid() or stat.st_mode&0o777!=0o700:
        raise ValueError("MANIFEST_INVALID")


def supervisor_browser_projection(*,supervisor_root:Path=INSTALL_ROOT,museum_manifest:Path=MUSEUM_IDENTITY_MANIFEST,
                                  service_probe:Callable[[],dict[str,Any]]|None=None,clock:Callable[[],datetime]|None=None)->dict[str,Any]:
    unavailable={"schema_version":"iios-unattended-supervisor-browser-v1","provenance":"UNAVAILABLE",
        "supervisor_installed":None,"supervisor_running":None,"manifest_status":"UNAVAILABLE","inventory_status":"UNAVAILABLE",
        "commit_binding":"UNAVAILABLE","service_ownership":"UNAVAILABLE","lock_ownership":"UNAVAILABLE",
        "listener_count":None,"child_count":None,"coherent_read_timestamp":None,"generation_identity":None,
        "readiness_classification":"UNAVAILABLE"}
    if not supervisor_root.exists():
        return unavailable|{"provenance":"SUPERVISOR_NOT_INSTALLED","supervisor_installed":False,
                            "supervisor_running":False,"readiness_classification":"SUPERVISOR_NOT_INSTALLED"}
    try:
        _validate_owner_root(supervisor_root)
        _validate_owner_root(museum_manifest.parent)
        for _attempt in range(3):
            first=_read_owner_file(supervisor_root/MANIFEST_NAME)
            museum_first=_read_owner_file(museum_manifest)
            manifest=json.loads(first); validate_manifest(manifest,supervisor_root/"installed-artifacts")
            museum=json.loads(museum_first); museum_commit=validate_museum_identity(museum)
            service=(service_probe or _service_probe)()
            second=_read_owner_file(supervisor_root/MANIFEST_NAME); museum_second=_read_owner_file(museum_manifest)
            if first!=second or museum_first!=museum_second: continue
            if service!={"running":True,"supervisor_count":1,"lock_owned":True,"listeners":0,"children":0}: raise ValueError("FAILED_CLOSED")
            commit=manifest["installed_source_commit"]; now=(clock or (lambda:datetime.now(timezone.utc)))()
            generation=_hash({"supervisor_manifest":manifest["canonical_manifest_content_hash"],"museum":museum["canonical_content_hash"],"service":service})[:16]
            return {"schema_version":"iios-unattended-supervisor-browser-v1","provenance":"AUTHENTIC_OPERATIONAL_SUPERVISOR_INSTALLATION",
                "supervisor_installed":True,"supervisor_running":True,"manifest_status":"VALID","inventory_status":"VALID",
                "commit_binding":"MATCH" if commit==museum_commit else "MISMATCH","service_ownership":"LAUNCHD","lock_ownership":"VALID",
                "listener_count":0,"child_count":0,"coherent_read_timestamp":now.isoformat(),"generation_identity":generation,
                "readiness_classification":"READY_FOR_OWNER_POLICY_AUTHORIZATION"}
        raise ValueError("FAILED_CLOSED")
    except (OSError,ValueError,json.JSONDecodeError,KeyError): return unavailable


def build_operational_candidate(expected_commit: str) -> str:
    repository_gate(expected_commit)
    if CANDIDATE_ROOT.exists():
        raise ValueError("CANDIDATE_INVENTORY_INVALID")
    build_candidate(CANDIDATE_ROOT,source_commit=expected_commit,ledger_path=os.environ.get("IIOS_DB_PATH"))
    write_manifest(CANDIDATE_ROOT,source_commit=expected_commit,installed_at=datetime.now(timezone.utc))
    return validate_candidate(CANDIDATE_ROOT,expected_commit=expected_commit)


def plan_install(expected_commit: str) -> str:
    repository_gate(expected_commit); validate_candidate(CANDIDATE_ROOT,expected_commit=expected_commit)
    if POLICY_ROOT.exists() and any(POLICY_ROOT.iterdir()): raise ValueError("FAILED_CLOSED")
    if ROLLBACK_ROOT.exists(): raise ValueError("ROLLBACK_INVALID")
    return "INSTALL_PLAN_READY"


def supervisor_lock_path(root: Path = INSTALL_ROOT) -> Path:
    root_info=root.lstat()
    if root.is_symlink() or not stat.S_ISDIR(root_info.st_mode) or root_info.st_uid!=os.getuid() or stat.S_IMODE(root_info.st_mode)!=0o700:
        raise ValueError("SUPERVISOR_LOCK_ROOT_INVALID")
    path=root/SUPERVISOR_LOCK_NAME
    if path.parent.resolve()!=root.resolve(): raise ValueError("SUPERVISOR_LOCK_PATH_INVALID")
    return path


def supervisor_lock_state(root: Path = INSTALL_ROOT) -> str:
    path=supervisor_lock_path(root)
    if not path.exists(): return "MISSING"
    info=path.lstat()
    if path.is_symlink() or not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or stat.S_IMODE(info.st_mode)!=0o600:
        raise ValueError("SUPERVISOR_LOCK_MALFORMED")
    handle=open(path,"a+")
    try:
        try: fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError: return "HELD"
        fcntl.flock(handle,fcntl.LOCK_UN); return "STALE_UNLOCKED"
    finally: handle.close()


def _wait_absent(old_pid: int, timeout: int = 30) -> None:
    import time
    for _ in range(timeout):
        label=subprocess.run(["launchctl","print",f"gui/{os.getuid()}/{LABEL}"],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode
        alive=True
        try: os.kill(old_pid,0)
        except ProcessLookupError: alive=False
        lock_state=supervisor_lock_state()
        if label and not alive and lock_state in {"MISSING","STALE_UNLOCKED"}: return
        time.sleep(1)
    raise ValueError("FAILED_CLOSED")

def upgrade_same_layout(*,source_root:Path,install_root:Path,launch_plist:Path,backup:Path,
        source_commit:str,target_commit:str,installed_at:datetime,service_stopped:bool=False,
        post_select_validator:Callable[[Path],None]|None=None,ledger_path:str|None=None)->str:
    """Atomically replace one validated installation with the same artifact layout."""
    if not service_stopped: raise ValueError("SERVICE_TEARDOWN_REQUIRED")
    current=json.loads(_read_owner_file(install_root/MANIFEST_NAME)); validate_manifest(current,install_root/"installed-artifacts",expected_commit=source_commit)
    if tuple(row["relative_path"] for row in current["artifact_inventory"])!=tuple(sorted(ARTIFACT_NAMES)): raise ValueError("SAME_LAYOUT_INVENTORY_INVALID")
    if backup.exists():
        receipt=json.loads(_read_owner_file(backup/"rollback-receipt.json"))
        if receipt.get("source_commit")!=source_commit or receipt.get("target_commit")!=target_commit: raise ValueError("ROLLBACK_INVALID")
    else:
        backup.mkdir(mode=0o700,parents=True); saved=backup/"prior-installation"; _copy_exact_tree(install_root,saved)
        _atomic(backup/"launch-agent.plist",_validated_existing_plist(launch_plist)); rows=_tree_records(saved)
        body={"schema":"iios-unattended-supervisor-same-layout-rollback-v1","source_commit":source_commit,"target_commit":target_commit,"inventory":rows,"plist_sha256":_hash_bytes((backup/"launch-agent.plist").read_bytes()),"immutable":True}
        _atomic(backup/"rollback-receipt.json",_canonical(body|{"content_hash":_hash(body)}))
    with tempfile.TemporaryDirectory() as raw:
        rehearsal=Path(raw)/"restore"; _copy_exact_tree(backup/"prior-installation",rehearsal)
        if _tree_records(rehearsal)!=_tree_records(backup/"prior-installation"): raise ValueError("ROLLBACK_INVALID")
    stage=install_root.parent/(install_root.name+".same-layout-stage")
    hold=install_root.parent/(install_root.name+".same-layout-hold")
    for p in (stage,hold):
        if p.exists(): raise ValueError("SAME_LAYOUT_RESIDUAL_INVALID")
    stage.mkdir(mode=0o700); artifacts=stage/"installed-artifacts"
    prior_plist=plistlib.loads(_validated_existing_plist(launch_plist))
    build_candidate(artifacts,source_commit=target_commit,source_root=source_root,
        python=prior_plist["ProgramArguments"][0],log_path=prior_plist.get("StandardOutPath"),ledger_path=ledger_path)
    target=write_manifest(artifacts,source_commit=target_commit,installed_at=installed_at)
    os.replace(artifacts/MANIFEST_NAME,stage/MANIFEST_NAME); _fsync_directory(stage)
    if set(row["relative_path"] for row in target["artifact_inventory"])!=set(row["relative_path"] for row in current["artifact_inventory"]): raise ValueError("SAME_LAYOUT_INVENTORY_INVALID")
    try:
        os.replace(install_root,hold); os.replace(stage,install_root); _fsync_directory(install_root.parent)
        _atomic(launch_plist,(install_root/"installed-artifacts"/PLIST_IDENTITY).read_bytes())
        validate_installed_root(expected_commit=target_commit,root=install_root)
        if post_select_validator: post_select_validator(install_root)
    except Exception:
        if install_root.exists(): shutil.rmtree(install_root)
        if hold.exists(): os.replace(hold,install_root)
        _atomic(launch_plist,(backup/"launch-agent.plist").read_bytes()); raise
    if hold.exists(): shutil.rmtree(hold)
    return "SUPERVISOR_SAME_LAYOUT_UPGRADED_DISABLED"


def _backup_legacy(old_pid: int) -> None:
    if ROLLBACK_ROOT.exists(): raise ValueError("ROLLBACK_INVALID")
    ROLLBACK_ROOT.mkdir(mode=0o700,parents=False)
    files={"launch-agent.plist":LAUNCH_PLIST,"installation-manifest.json":INSTALL_ROOT/MANIFEST_NAME}
    rows=[]
    for name,source in files.items():
        info=source.lstat()
        if source.is_symlink() or not stat.S_ISREG(info.st_mode): raise ValueError("ROLLBACK_INVALID")
        target=ROLLBACK_ROOT/name; target.write_bytes(source.read_bytes()); os.chmod(target,0o600)
        rows.append(_file_record(target,name))
    body={"schema":ROLLBACK_SCHEMA,"prior_policy_absent":not (POLICY_ROOT/"unattended-policy.json").exists(),"prior_pid":old_pid,
          "prior_manifest_commit":json.loads((ROLLBACK_ROOT/"installation-manifest.json").read_text()).get("installed_commit"),
          "inventory":rows}
    _atomic(ROLLBACK_ROOT/"rollback-manifest.json",_canonical(body|{"content_hash":_hash(body)}))


def reconcile_disabled(expected_commit: str) -> str:
    install_lock=INSTALL_ROOT/LOCK_NAME; handle=open(install_lock,"a+"); os.chmod(install_lock,0o600)
    try:
        try: fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError: raise ValueError("FAILED_CLOSED")
        plan_install(expected_commit)
        printed=subprocess.check_output(["launchctl","print",f"gui/{os.getuid()}/{LABEL}"],text=True)
        marker="pid = "; old_pid=int(next(line.split(marker,1)[1] for line in printed.splitlines() if marker in line).strip())
        _backup_legacy(old_pid)
        subprocess.run(["launchctl","bootout",f"gui/{os.getuid()}/{LABEL}"],check=True)
        _wait_absent(old_pid)
        try:
            staged=INSTALL_ROOT/".installed-artifacts.next"
            if staged.exists(): raise ValueError("FAILED_CLOSED")
            _copy_tree(CANDIDATE_ROOT,staged)
            if INSTALLED_ARTIFACTS.exists(): raise ValueError("FAILED_CLOSED")
            os.replace(staged,INSTALLED_ARTIFACTS)
            manifest=json.loads((CANDIDATE_ROOT/MANIFEST_NAME).read_text())
            _atomic(INSTALL_ROOT/MANIFEST_NAME,_canonical(manifest))
            _atomic(LAUNCH_PLIST,(CANDIDATE_ROOT/PLIST_IDENTITY).read_bytes())
            subprocess.run(["launchctl","bootstrap",f"gui/{os.getuid()}",str(LAUNCH_PLIST)],check=True)
            validate_installed_root(expected_commit=expected_commit)
            return "SUPERVISOR_RECONCILED_DISABLED"
        except Exception:
            restore(expected_commit=None)
            raise ValueError("FAILED_CLOSED")
    finally:
        fcntl.flock(handle,fcntl.LOCK_UN); handle.close()


def _rollback_value() -> dict[str,Any]:
    value=json.loads((ROLLBACK_ROOT/"rollback-manifest.json").read_text())
    body={k:value[k] for k in value if k!="content_hash"}
    if set(value)!={"schema","prior_policy_absent","prior_pid","prior_manifest_commit","inventory","content_hash"} or value["schema"]!=ROLLBACK_SCHEMA or value["content_hash"]!=_hash(body):
        raise ValueError("ROLLBACK_INVALID")
    for row in value["inventory"]:
        if _file_record(ROLLBACK_ROOT/row["relative_path"],row["relative_path"])!=row: raise ValueError("ROLLBACK_INVALID")
    return value


def restore(expected_commit: str | None) -> str:
    del expected_commit
    value=_rollback_value()
    subprocess.run(["launchctl","bootout",f"gui/{os.getuid()}/{LABEL}"],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    _atomic(LAUNCH_PLIST,(ROLLBACK_ROOT/"launch-agent.plist").read_bytes())
    _atomic(INSTALL_ROOT/MANIFEST_NAME,(ROLLBACK_ROOT/"installation-manifest.json").read_bytes())
    if INSTALLED_ARTIFACTS.exists(): shutil.rmtree(INSTALLED_ARTIFACTS)
    if value["prior_policy_absent"] and POLICY_ROOT.exists() and any(POLICY_ROOT.iterdir()): raise ValueError("ROLLBACK_INVALID")
    subprocess.run(["launchctl","bootstrap",f"gui/{os.getuid()}",str(LAUNCH_PLIST)],check=True)
    return "SUPERVISOR_INSTALLED_DISABLED"


def compare(old: Path, new: Path) -> dict[str, list[str]]:
    old_rows={x["relative_path"]:x for x in inventory(old)}
    new_rows={x["relative_path"]:x for x in inventory(new)}
    unchanged=sorted(k for k in old_rows if old_rows[k]["sha256"]==new_rows[k]["sha256"])
    return {"changed":sorted(set(old_rows)-set(unchanged)),"unchanged":unchanged}


def readiness(*, expected_commit: str, install_root: Path = INSTALL_ROOT,
              service_probe: Callable[[],dict[str,Any]], operational_probe: Callable[[],dict[str,Any]]) -> str:
    if (install_root/"installed-artifacts").is_dir():
        validate_installed_root(expected_commit=expected_commit,root=install_root)
    else:
        validate_candidate(install_root,expected_commit=expected_commit)
    service=service_probe(); facts=operational_probe()
    required={"running":True,"supervisor_count":1,"lock_owned":True,"listeners":0,"children":0,
              "policy_present":False,"released_credits":0,"provider_requests":0,"provider_credits":0,
              "controller_valid":True,"monday_rehearsal_valid":True,"authority_locked":True,
              "paper_activity":0,"cost_binding":"VALID","credential_readiness":"AVAILABLE",
              "planned":50,"supported":50,"blocked":0,"exact_cost":50,"allowance":50}
    if service | facts != required: raise ValueError("FAILED_CLOSED")
    return "READY_FOR_OWNER_POLICY_AUTHORIZATION"


def _service_probe() -> dict[str,Any]:
    printed=subprocess.check_output(["launchctl","print",f"gui/{os.getuid()}/{LABEL}"],text=True,stderr=subprocess.DEVNULL)
    pids=[line for line in printed.splitlines() if line.strip().startswith("pid =")]
    if len(pids)!=1: raise ValueError("FAILED_CLOSED")
    pid=int(pids[0].split("=",1)[1])
    children=subprocess.run(["pgrep","-P",str(pid)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0
    listener_run=subprocess.run(["lsof","-nP","-a","-p",str(pid),"-iTCP","-sTCP:LISTEN"],text=True,capture_output=True)
    listeners=listener_run.stdout.splitlines()
    owned=supervisor_lock_state()=="HELD"
    return {"running":"state = running" in printed,"supervisor_count":1,"lock_owned":owned,
            "listeners":max(0,len(listeners)-1),"children":1 if children else 0}


def _operational_probe() -> dict[str,Any]:
    with urllib.request.urlopen("http://127.0.0.1:5176/expansion-wing/snapshot",timeout=5) as response:
        if response.status!=200 or int(response.headers.get("Content-Length","0") or 0)>2_000_000: raise ValueError("FAILED_CLOSED")
        snapshot=json.load(response)
    sections=snapshot["sections"]
    controller=sections["tuesday_controller_status"]["data"]
    ready=sections["provider_stage_a_readiness"]["data"]
    books=sections["books"]["data"]
    authority=sections["authority_lock"]["data"]
    binding=operational_cost_binding()
    return {"policy_present":POLICY_ROOT.exists() and (POLICY_ROOT/"unattended-policy.json").exists(),
            "released_credits":ready["stage_a_released_credits"],"provider_requests":controller["requests_today"],
            "provider_credits":controller["credits_today"],"controller_valid":controller["integrity"]=="VALID" and controller["activated"] is False,
            "monday_rehearsal_valid":controller["authentic_rehearsal_status"]=="PASSED_CLOSED_HOLIDAY",
            "authority_locked":authority["locked"] is True and not any(authority[k] for k in ("broker","credential","ledger_write","live_execution","paper_order","provider")),
            "paper_activity":sum(books[k] for k in ("positions","transactions","orders","fills")),
            "cost_binding":"VALID" if ready["cost_contract_binding"]=="VALID" else "INVALID",
            "credential_readiness":ready["credential_presence_state"],"planned":binding["planned_identity_count"],
            "supported":binding["supported_costed_identity_count"],"blocked":binding["blocked_identity_count"],
            "exact_cost":binding["exact_planned_cost_credits"],"allowance":binding["stage_a_authorized_allowance_credits"]}


def _git(command: list[str]) -> str:
    return subprocess.check_output(["git",*command],cwd=SOURCE_ROOT,text=True,stderr=subprocess.DEVNULL).strip()


def repository_gate(expected: str) -> None:
    if (not _commit(expected) or _git(["branch","--show-current"])!=BRANCH
            or _git(["rev-parse","HEAD"])!=expected or _git(["rev-parse",f"origin/{BRANCH}"])!=expected):
        raise ValueError("SOURCE_COMMIT_MISMATCH")
    if _git(["status","--porcelain=v1"]): raise ValueError("SOURCE_COMMIT_MISMATCH")


def main(argv: list[str] | None = None) -> int:
    parser=argparse.ArgumentParser(); parser.add_argument("--reviewed-operational-mode",action="store_true")
    parser.add_argument("command",choices=("validate-candidate","plan-install","install-disabled","validate-installed","reconcile-disabled","readiness","restore"))
    parser.add_argument("--expected-source-commit",required=True); parser.add_argument("--browser",action="store_true",help=argparse.SUPPRESS)
    args=parser.parse_args(argv)
    try:
        if args.browser or not args.reviewed_operational_mode: raise ValueError("FAILED_CLOSED")
        repository_gate(args.expected_source_commit)
        if args.command=="validate-candidate": result=build_operational_candidate(args.expected_source_commit)
        elif args.command=="plan-install": result=plan_install(args.expected_source_commit)
        elif args.command in {"install-disabled","reconcile-disabled"}: result=reconcile_disabled(args.expected_source_commit)
        elif args.command=="validate-installed": result=validate_installed_root(expected_commit=args.expected_source_commit)
        elif args.command=="restore": result=restore(args.expected_source_commit)
        elif args.command=="readiness":
            result=readiness(expected_commit=args.expected_source_commit,service_probe=_service_probe,operational_probe=_operational_probe)
        else: raise ValueError("FAILED_CLOSED")
        print(json.dumps({"status":result},sort_keys=True)); return 0
    except (OSError,ValueError,subprocess.SubprocessError) as exc:
        category=str(exc) if str(exc) in {"SOURCE_COMMIT_MISMATCH","CANDIDATE_INVENTORY_INVALID","INSTALLED_INVENTORY_INVALID","MANIFEST_INVALID","ROLLBACK_INVALID","FAILED_CLOSED"} else "FAILED_CLOSED"
        print(json.dumps({"status":category},sort_keys=True)); return 5


if __name__=="__main__": raise SystemExit(main())
