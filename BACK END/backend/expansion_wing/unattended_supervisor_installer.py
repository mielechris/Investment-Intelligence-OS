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
MAX_FILES = 8
MAX_FILE_BYTES = 1_048_576
ARTIFACT_NAMES = (
    "expansion_wing/provider_readiness.py",
    "expansion_wing/provider_readiness_service.py",
    "expansion_wing/unattended_tuesday.py",
    "expansion_wing/unattended_tuesday_service.py",
    PLIST_IDENTITY,
)
INSTALL_ROOT = Path.home()/"Library/Application Support/IIOS/UnattendedTuesdaySupervisor"
INSTALLED_ARTIFACTS = INSTALL_ROOT/"installed-artifacts"
CANDIDATE_ROOT = Path.home()/"Library/Application Support/IIOS/UnattendedTuesdaySupervisorCandidate"
MANIFEST_NAME = "installation-manifest.json"
LOCK_NAME = "installation.lock"
ROLLBACK_PARENT = Path.home()/"Library/Application Support/IIOS/Rollback"
ROLLBACK_ROOT = ROLLBACK_PARENT/"UnattendedTuesdaySupervisor28H"
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
                    log_path: str | None = None) -> str:
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
    template = source_root/"config/com.iios.expansion-wing-unattended-tuesday.plist.template"
    raw = template.read_text().replace("__FIXED_PYTHON__", python).replace("__FIXED_WORKTREE__", str(source_root))
    raw = raw.replace("__OWNER_ONLY_LOG__", log_path or str(Path.home()/"Library/Logs/IIOS/UnattendedTuesday/unattended.log"))
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


def build_operational_candidate(expected_commit: str) -> str:
    repository_gate(expected_commit)
    if CANDIDATE_ROOT.exists():
        raise ValueError("CANDIDATE_INVENTORY_INVALID")
    build_candidate(CANDIDATE_ROOT,source_commit=expected_commit)
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
