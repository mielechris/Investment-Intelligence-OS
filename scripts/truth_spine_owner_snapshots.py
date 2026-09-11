"""Owner-operated, read-only L7/L8 snapshot kit.

Version 3 separates mutable source binding from immutable snapshot identity.
Config-only validation uses metadata only; capture binds the SQLite-consistent
snapshot hash and never treats a live source-file hash as a snapshot identity.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import sqlite3
import stat
import subprocess
import sys
from typing import Any

BACKEND = Path(__file__).resolve().parents[1] / "BACK END/backend"
sys.path.insert(0, str(BACKEND))
from truth_spine_contract import canonical, seal, utc, verified  # noqa: E402
from truth_spine_sqlite_capture import launch_capture  # noqa: E402
import truth_spine_sqlite_capture as capture_helper  # noqa: E402

SCHEMA = "iios-owner-ledger-snapshot-v1"
CONFIG_SCHEMA = "iios-owner-ledger-source-config-v3"
# Attempt 1 is retained failure evidence; attempt 2 must use a fresh root.
OUTPUT_ROOT = Path("/private/tmp/iios-northstar-owner-snapshots-sb37-attempt2")
CONFIRMATION = ("I confirm these are my canonical IIOS L7 and L8 ledgers. I authorize "
                "read-only capture into the isolated owner snapshot root. I do not "
                "authorize source modification.")
CAPTURE_CONFIRMATION = (
    "I authorize read-only logical capture of my canonical IIOS L7 and L8 ledgers. "
    "SQLite may create or update only their exact WAL/SHM coordination files as required to establish a consistent read transaction. "
    "I do not authorize logical records, schemas, journal mode, or main database content to be modified."
)
SOURCE_KINDS = {"L7", "L8"}
SQLITE_COORDINATION_POLICY = {
    "schema": "iios-owner-sqlite-wal-shm-coordination-v1",
    "allowed_suffixes": ["-wal", "-shm"],
    "main_database_writes": False,
    "rollback_journal": False,
    "source_metadata_changes": False,
    "source_rename_unlink": False,
    "outside_destination_writes": False,
}
HISTORICAL_OBSERVATIONS = {
    "L7": [{"observed_utc": "2026-09-10T00:52:05.297458Z", "size": 333561856,
            "sha256": "98397c6172bbd794d62e32ce1e155da9b93e3a07d4cdd0e69a7a4d34e8a22583"}],
    "L8": [{"observed_utc": "2026-09-10T00:52:21.325937Z", "size": 1266163712,
            "sha256": "63ae15e655adb313cda0db896118c571378d98c17c8d7dd9561867c5c6e29978"}],
}
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
COMMIT40 = re.compile(r"[0-9a-f]{40}\Z")
PLACEHOLDER = re.compile(r"(?:<[^>]+>|PLACEHOLDER|OWNER[-_]SUPPLIED|REPLACE[-_]ME)", re.I)
FORBIDDEN_PARTS = {"credentials", "keychain", "keychains", ".git", "node_modules"}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _absolute_regular_metadata(path: Path) -> os.stat_result:
    if not path.is_absolute() or path != path.resolve() or path.is_symlink():
        raise ValueError("OWNER_SOURCE_PATH_INVALID")
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
        raise ValueError("OWNER_SOURCE_TYPE_OR_OWNER_INVALID")
    return info


def owner_regular(path: Path, *, mode: int | None = None) -> bytes:
    """Compatibility helper for the explicit capture path (not config-only)."""
    info = _absolute_regular_metadata(path)
    if mode is not None and stat.S_IMODE(info.st_mode) != mode:
        raise ValueError("OWNER_SOURCE_MODE_INVALID")
    return path.read_bytes()


def _source_path(path_value: Any) -> Path:
    if not isinstance(path_value, str) or PLACEHOLDER.search(path_value):
        raise ValueError("OWNER_SOURCE_PATH_INVALID")
    path = Path(path_value)
    if not path.is_absolute() or path != path.resolve():
        raise ValueError("OWNER_SOURCE_PATH_INVALID")
    if any(part.lower() in FORBIDDEN_PARTS for part in path.parts):
        raise ValueError("OWNER_SOURCE_PATH_INVALID")
    if path == OUTPUT_ROOT or OUTPUT_ROOT in path.parents:
        raise ValueError("OWNER_SOURCE_PATH_INVALID")
    if "iios-truth-spine-3-src" in path.parts:
        raise ValueError("OWNER_SOURCE_PATH_CHECKOUT_BOUND")
    return path


def _source_metadata(row: dict) -> tuple[Path, dict]:
    required = {"role", "path", "device", "inode", "owner_uid", "mode", "file_type",
                "observed_utc", "provenance", "prior_observations", "mutable_source"}
    if set(row) != required or row.get("role") not in {"L7_OPERATIONAL", "L8_HISTORICAL"}:
        raise ValueError("OWNER_SOURCE_CONFIG_INVALID")
    if not all(isinstance(row[key], int) for key in ("device", "inode", "owner_uid", "mode")):
        raise ValueError("OWNER_SOURCE_CONFIG_INVALID")
    if row.get("mutable_source") is not True or row.get("mode") == 0:
        raise ValueError("OWNER_SOURCE_CONFIG_INVALID")
    try:
        utc(row["observed_utc"])
    except (KeyError, TypeError, ValueError):
        raise ValueError("OWNER_SOURCE_CONFIG_TIMESTAMP_INVALID") from None
    provenance = row.get("provenance")
    if (not isinstance(provenance, list) or not provenance or
            any(not isinstance(x, str) or not x for x in provenance)):
        raise ValueError("OWNER_SOURCE_PROVENANCE_MISSING")
    if row.get("file_type") != "regular":
        raise ValueError("OWNER_SOURCE_CONFIG_INVALID")
    prior = row.get("prior_observations")
    if not isinstance(prior, list) or any(
        not isinstance(item, dict) or set(item) != {"observed_utc", "size", "sha256"}
        or not isinstance(item["size"], int) or item["size"] < 0 or not HEX64.fullmatch(str(item["sha256"]))
        for item in prior
    ):
        raise ValueError("OWNER_SOURCE_CONFIG_INVALID")
    for item in prior:
        try: utc(item["observed_utc"])
        except ValueError: raise ValueError("OWNER_SOURCE_CONFIG_TIMESTAMP_INVALID") from None
    path = _source_path(row["path"])
    info = _absolute_regular_metadata(path)
    if (info.st_dev, info.st_ino, info.st_uid, stat.S_IMODE(info.st_mode)) != (
            row["device"], row["inode"], row["owner_uid"], row["mode"]):
        raise ValueError("OWNER_SOURCE_METADATA_MISMATCH")
    return path, row


def _parse_config(config: Path) -> dict:
    info = _absolute_regular_metadata(config)
    if stat.S_IMODE(info.st_mode) != 0o600:
        raise ValueError("OWNER_CONFIG_MODE_INVALID")
    try:
        record = verified(json.loads(config.read_bytes()))
    except (ValueError, json.JSONDecodeError):
        raise ValueError("OWNER_SOURCE_CONFIG_INVALID") from None
    expected = {"schema", "created_utc", "owner_confirmation_hash", "source_commit",
                "helper_sha256", "owner_kit_sha256", "sqlite_coordination", "sources", "content_hash"}
    if record.get("schema") != CONFIG_SCHEMA or set(record) != expected:
        raise ValueError("OWNER_SOURCE_CONFIG_INVALID")
    try:
        utc(record["created_utc"])
    except (KeyError, TypeError, ValueError):
        raise ValueError("OWNER_SOURCE_CONFIG_TIMESTAMP_INVALID") from None
    for key, pattern in (("owner_confirmation_hash", HEX64), ("helper_sha256", HEX64),
                         ("owner_kit_sha256", HEX64), ("source_commit", COMMIT40)):
        if not isinstance(record.get(key), str) or not pattern.fullmatch(record[key]):
            raise ValueError("OWNER_SOURCE_CONFIG_INVALID")
    if record["owner_confirmation_hash"] != hashlib.sha256(CONFIRMATION.encode()).hexdigest():
        raise ValueError("OWNER_CONFIRMATION_HASH_INVALID")
    if record.get("sqlite_coordination") != SQLITE_COORDINATION_POLICY:
        raise ValueError("OWNER_SQLITE_COORDINATION_POLICY_INVALID")
    rows = record.get("sources")
    if (not isinstance(rows, list) or len(rows) != 2 or
            {r.get("role") for r in rows if isinstance(r, dict)} != {"L7_OPERATIONAL", "L8_HISTORICAL"}):
        raise ValueError("OWNER_SOURCE_CONFIG_INVALID")
    return record


def load_config(config: Path, *, content: bool = True) -> tuple[dict, dict[Path, str]]:
    """Load v2 config; ``content=False`` performs metadata checks only."""
    record = _parse_config(config)
    resolved: dict[Path, str] = {}
    for row in record["sources"]:
        path, metadata = _source_metadata(row)
        alias = "L7" if metadata["role"] == "L7_OPERATIONAL" else "L8"
        if path in resolved or alias in resolved.values():
            raise ValueError("OWNER_SOURCE_IDENTITY_DUPLICATE")
        # Mutable sources are allowed to advance; capture revalidates metadata
        # immediately before admission and binds the resulting snapshot hash.
        resolved[path] = alias
    return record, resolved


def validate_config_only(config: Path, *, expected_commit: str, helper_sha256: str,
                         owner_kit_sha256: str) -> dict:
    """Validate config and source metadata without reading source bytes."""
    if not COMMIT40.fullmatch(expected_commit) or not HEX64.fullmatch(helper_sha256) or not HEX64.fullmatch(owner_kit_sha256):
        raise ValueError("OWNER_PIN_INVALID")
    if sha(Path(capture_helper.__file__).resolve()) != helper_sha256 or sha(Path(__file__).resolve()) != owner_kit_sha256:
        raise ValueError("OWNER_PIN_MISMATCH")
    record, sources = load_config(config, content=False)
    if (record["source_commit"] != expected_commit or record["helper_sha256"] != helper_sha256 or
            record["owner_kit_sha256"] != owner_kit_sha256):
        raise ValueError("OWNER_PIN_MISMATCH")
    return {"status": "CONFIG_VALID", "schema": CONFIG_SCHEMA, "source_count": len(sources),
            "source_aliases": sorted(sources.values()), "config_sha256": sha(config),
            "ledger_content_opened": False, "credential_accesses": 0, "provider_requests": 0}


def discover_candidates(metadata_files: list[Path]) -> list[dict]:
    """Discover paths explicitly present in supplied metadata files only."""
    candidates: dict[str, dict] = {}
    for metadata_file in metadata_files:
        try:
            _absolute_regular_metadata(metadata_file)
            raw = metadata_file.read_bytes()
        except (OSError, ValueError):
            continue
        try:
            obj = plistlib.loads(raw) if metadata_file.suffix == ".plist" else json.loads(raw)
            values: list[str] = []
            def collect(value: Any) -> None:
                if isinstance(value, str) and value.startswith("/") and value.lower().endswith(".db"):
                    values.append(value)
                elif isinstance(value, dict):
                    for item in value.values(): collect(item)
                elif isinstance(value, (list, tuple)):
                    for item in value: collect(item)
            collect(obj)
        except (ValueError, json.JSONDecodeError, plistlib.InvalidFileException):
            values = re.findall(r"/[^\n\"']+?\.db", raw.decode("utf-8", "ignore"), re.I)
        for value in values:
            try:
                path = _source_path(value)
                st = _absolute_regular_metadata(path)
            except (OSError, ValueError):
                continue
            key = str(path)
            entry = candidates.setdefault(key, {"path": "{OWNER_SELECTED}", "basename": path.name,
                "size": st.st_size, "device": st.st_dev, "inode": st.st_ino,
                "owner_uid": st.st_uid, "mode": stat.S_IMODE(st.st_mode), "file_type": "regular",
                "evidence_sources": [], "confidence": "HIGH"})
            if metadata_file.name not in entry["evidence_sources"]:
                entry["evidence_sources"].append(metadata_file.name)
    return sorted(candidates.values(), key=lambda item: (item["basename"], item["inode"]))


def build_config(l7: Path, l8: Path, *, source_commit: str, helper_sha256: str,
                 owner_kit_sha256: str, provenance: dict[str, list[str]],
                 prior_observations: dict[str, list[dict]] | None = None) -> dict:
    """Build a sealed v3 config from metadata; never reads source bytes."""
    if not COMMIT40.fullmatch(source_commit) or not HEX64.fullmatch(helper_sha256) or not HEX64.fullmatch(owner_kit_sha256):
        raise ValueError("OWNER_PIN_INVALID")
    rows = []
    for kind, path in (("L7", l7), ("L8", l8)):
        path = _source_path(str(path))
        info = _absolute_regular_metadata(path)
        refs = provenance.get(kind, [])
        if not refs:
            raise ValueError("OWNER_SOURCE_PROVENANCE_MISSING")
        prior = (prior_observations or HISTORICAL_OBSERVATIONS).get(kind, [])
        rows.append({"role": "L7_OPERATIONAL" if kind == "L7" else "L8_HISTORICAL",
                     "path": str(path), "device": info.st_dev, "inode": info.st_ino,
                     "owner_uid": info.st_uid, "mode": stat.S_IMODE(info.st_mode),
                     "file_type": "regular", "observed_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                     "provenance": list(refs), "prior_observations": prior,
                     "mutable_source": True})
    if l7.resolve() == l8.resolve():
        raise ValueError("OWNER_SOURCE_IDENTITY_DUPLICATE")
    return seal({"schema": CONFIG_SCHEMA, "created_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                 "owner_confirmation_hash": hashlib.sha256(CONFIRMATION.encode()).hexdigest(),
                 "source_commit": source_commit, "helper_sha256": helper_sha256,
                 "owner_kit_sha256": owner_kit_sha256,
                 "sqlite_coordination": SQLITE_COORDINATION_POLICY, "sources": rows})


def discover_metadata_files() -> list[Path]:
    """Return only bounded, known IIOS metadata locations (never a home scan)."""
    home = Path.home()
    files = list((home / "Library/LaunchAgents").glob("com.iios.*.plist"))
    releases = home / "Library/Application Support/IIOS/Releases"
    files.extend(releases.glob("*/release-manifest.json"))
    return [p for p in files if p.is_file()]


def owner_workflow(source_root: Path, config: Path, *, expected_commit: str,
                   helper_sha256: str, owner_kit_sha256: str,
                   l7: Path, l8: Path, confirm: str, capture_confirm: str,
                   provenance: dict[str, list[str]]) -> dict:
    """Explicit two-confirmation owner flow; never auto-selects a source."""
    if confirm != CONFIRMATION:
        raise PermissionError("OWNER_CONFIRMATION_REQUIRED")
    if capture_confirm != CAPTURE_CONFIRMATION:
        raise PermissionError("OWNER_CAPTURE_CONFIRMATION_REQUIRED")
    record = build_config(l7, l8, source_commit=expected_commit,
                         helper_sha256=helper_sha256, owner_kit_sha256=owner_kit_sha256,
                         provenance=provenance)
    atomic_write(config, canonical(record))
    validate_config_only(config, expected_commit=expected_commit,
                         helper_sha256=helper_sha256, owner_kit_sha256=owner_kit_sha256)
    return run(source_root, config, confirmation=capture_confirm,
               expected_commit=expected_commit, helper_sha256=helper_sha256,
               owner_kit_sha256=owner_kit_sha256)


def atomic_write(path: Path, payload: bytes, mode: int = 0o600) -> None:
    if path.exists() or path.is_symlink():
        raise ValueError("OWNER_OUTPUT_ALREADY_EXISTS")
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if stat.S_IMODE(path.parent.stat().st_mode) != 0o700:
        raise ValueError("OWNER_OUTPUT_DIRECTORY_MODE_INVALID")
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, mode)
    with os.fdopen(fd, "wb") as stream:
        stream.write(payload); stream.flush(); os.fsync(stream.fileno())
    dfd = os.open(path.parent, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        os.fsync(dfd)
    finally:
        os.close(dfd)


def snapshot_metadata(path: Path) -> dict:
    """Read aggregate metadata only after explicit owner capture consent."""
    db = sqlite3.connect(path.as_uri() + "?mode=ro&immutable=1", uri=True)
    try:
        if (db.execute("PRAGMA quick_check").fetchall() != [("ok",)] or
                db.execute("PRAGMA integrity_check").fetchall() != [("ok",)] or
                db.execute("PRAGMA foreign_key_check").fetchall()):
            raise ValueError("OWNER_SNAPSHOT_INTEGRITY_INVALID")
        schema = db.execute("SELECT type,name,tbl_name,sql FROM sqlite_schema ORDER BY type,name").fetchall()
        tables = db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
        total = 0; stamps: list[datetime] = []
        for (table,) in tables:
            quoted = '"' + table.replace('"', '""') + '"'
            total += int(db.execute(f"SELECT count(*) FROM {quoted}").fetchone()[0])
            for _, name, *_ in db.execute(f"PRAGMA table_info({quoted})").fetchall():
                if not (name.lower().endswith(("_at", "_time", "timestamp")) or name.lower() in {"created", "updated"}):
                    continue
                column = name.replace('"', '""')
                value = db.execute(f'SELECT max("{column}") FROM {quoted}').fetchone()[0]
                if isinstance(value, str):
                    try: stamps.append(utc(value))
                    except ValueError: pass
        high = max(stamps).isoformat().replace("+00:00", "Z") if stamps else None
        return {"schema_sha256": hashlib.sha256(canonical(schema)).hexdigest(), "table_count": len(tables),
                "row_count": total, "high_watermark_utc": high, "quick_check": "ok",
                "integrity_check": "ok", "foreign_key_violations": 0}
    finally:
        db.close()


def capture(source: Path, output: Path, evidence: Path, sources: dict[Path, str]) -> dict:
    before = _absolute_regular_metadata(source)
    role = "L7" if sources[source] == "L7" else "L8"
    receipt = launch_capture(source, output, evidence_root=evidence, timeout=120,
                             source_role=role)
    after = _absolute_regular_metadata(source)
    if (before.st_dev, before.st_ino, before.st_uid, stat.S_IFMT(before.st_mode)) != (after.st_dev, after.st_ino, after.st_uid, stat.S_IFMT(after.st_mode)):
        raise ValueError("OWNER_SOURCE_IDENTITY_CHANGED")
    metadata = snapshot_metadata(output / "snapshot.db")
    job = json.loads((output / "job.json").read_bytes())
    return {"alias": sources[source], "snapshot": "{OUTPUT}/" + sources[source].lower() + "/snapshot.db",
            "snapshot_sha256": receipt["snapshot_sha256"], "snapshot_bytes": receipt["bytes"],
            "capture_job": receipt["job"], "helper_sha256": job["helper_sha256"],
            "profile_sha256": job["profile_sha256"],
            "coordination": receipt.get("coordination", {}),
            "runtime": receipt.get("runtime", {}),
            "source_acquisition": {"role": "L7_OPERATIONAL" if sources[source] == "L7" else "L8_HISTORICAL",
                "device": after.st_dev, "inode": after.st_ino, "owner_uid": after.st_uid,
                "mode": stat.S_IMODE(after.st_mode), "size": after.st_size,
                "captured_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")},
            **metadata}


def run(source_root: Path, config: Path, *, confirmation: str, expected_commit: str | None = None,
        helper_sha256: str | None = None, owner_kit_sha256: str | None = None) -> dict:
    if confirmation != CAPTURE_CONFIRMATION:
        raise PermissionError("OWNER_CONFIRMATION_REQUIRED")
    source_root = source_root.resolve()
    if not source_root.is_dir() or source_root.is_symlink():
        raise ValueError("OWNER_SOURCE_CHECKOUT_INVALID")
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=source_root, text=True).strip()
    if expected_commit is None or not COMMIT40.fullmatch(expected_commit) or commit != expected_commit:
        raise ValueError("OWNER_SOURCE_COMMIT_PIN_MISMATCH")
    helper = Path(capture_helper.__file__).resolve()
    if helper_sha256 is None or not HEX64.fullmatch(helper_sha256) or sha(helper) != helper_sha256:
        raise ValueError("OWNER_HELPER_PIN_MISMATCH")
    if owner_kit_sha256 is None or not HEX64.fullmatch(owner_kit_sha256) or sha(Path(__file__).resolve()) != owner_kit_sha256:
        raise ValueError("OWNER_KIT_PIN_MISMATCH")
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=source_root, text=True):
        raise ValueError("OWNER_SOURCE_CHECKOUT_DIRTY")
    config_record, sources = load_config(config, content=True)
    if (config_record["source_commit"] != commit or config_record["helper_sha256"] != helper_sha256 or
            config_record["owner_kit_sha256"] != owner_kit_sha256):
        raise ValueError("OWNER_CONFIG_PIN_MISMATCH")
    if OUTPUT_ROOT.exists() or OUTPUT_ROOT.is_symlink():
        raise ValueError("OWNER_OUTPUT_ROOT_MUST_BE_ABSENT")
    output = OUTPUT_ROOT.resolve(); output.mkdir(mode=0o700)
    evidence = output / "incidents"; evidence.mkdir(mode=0o700)
    captures: dict[str, dict] = {}
    try:
        for path in sorted(sources, key=lambda p: sources[p]):
            captures[sources[path]] = capture(path, output / sources[path].lower(), evidence, sources)
        high = [captures[x]["high_watermark_utc"] for x in ("L7", "L8")]
        if any(value is None for value in high):
            raise ValueError("OWNER_HIGH_WATERMARK_UNAVAILABLE")
        watermark = min(high)
        manifest = seal({"schema": SCHEMA, "source_commit": commit, "config_sha256": sha(config),
            "config_identity": config_record["content_hash"], "sources": [{"alias": sources[p], "source_identity": "{" + sources[p] + "}", "source_acquisition": captures[sources[p]]["source_acquisition"]} for p in sorted(sources, key=lambda p: sources[p])], "captures": captures, "common_reconciliation_watermark_utc": watermark, "authority": {"read_only": True, "provider": False, "credential": False, "broker": False, "paper": False, "ledger_write": False}, "output_root": "{OUTPUT}", "completion": "OWNER_REVIEW_REQUIRED"})
        atomic_write(output / "manifest.json", canonical(manifest))
        receipt = seal({"schema": "iios-owner-ledger-snapshot-receipt-v1", "status": "VERIFIED", "manifest_hash": manifest["content_hash"], "manifest_sha256": sha(output / "manifest.json"), "source_commit": commit, "common_reconciliation_watermark_utc": watermark, "sources": [{"alias": sources[p], "snapshot_sha256": captures[sources[p]]["snapshot_sha256"]} for p in sorted(sources, key=lambda p: sources[p])], "rows": "NOT_CAPTURED_OR_REPORTED", "credentials": 0, "providers": 0, "output_root": "{OUTPUT}"})
        atomic_write(output / "completion-receipt.json", canonical(receipt))
        return {"status": receipt["status"], "output": "{OUTPUT}", "receipt_sha256": sha(output / "completion-receipt.json"), "manifest_hash": manifest["content_hash"], "source_commit": commit, "watermark": watermark, "credential_accesses": 0, "provider_requests": 0}
    except BaseException as error:
        failure = seal({"schema": "iios-owner-ledger-snapshot-failure-v1", "status": "FAILED_CLOSED", "category": type(error).__name__, "source_commit": commit, "output_root": "{OUTPUT}", "captures_started": sorted(captures), "credentials": 0, "providers": 0})
        if not (output / "failure.json").exists():
            atomic_write(output / "failure.json", canonical(failure))
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description="Owner-only read-only IIOS L7/L8 capture")
    parser.add_argument("--source-root", type=Path)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--helper-sha256", required=True)
    parser.add_argument("--owner-kit-sha256", required=True)
    parser.add_argument("--confirm")
    parser.add_argument("--config-only", action="store_true")
    parser.add_argument("--discover", action="store_true")
    parser.add_argument("--metadata-file", action="append", type=Path, default=[])
    parser.add_argument("--workflow", action="store_true")
    parser.add_argument("--l7-path", type=Path)
    parser.add_argument("--l8-path", type=Path)
    parser.add_argument("--provenance-source", action="append", default=[])
    args = parser.parse_args()
    if args.discover:
        files = args.metadata_file or discover_metadata_files()
        print(json.dumps({"status": "DISCOVERY_ONLY", "candidates": discover_candidates(files),
                          "source_content_opened": False}, sort_keys=True))
        return
    if args.workflow:
        if args.source_root is None:
            parser.error("workflow requires --source-root")
        # Listing is metadata-only; adoption remains explicit through the two paths.
        files = args.metadata_file or discover_metadata_files()
        print(json.dumps({"status": "DISCOVERY_ONLY", "candidates": discover_candidates(files)}, sort_keys=True))
        l7_path = args.l7_path or Path(input("Canonical L7 path (select explicitly): ").strip())
        l8_path = args.l8_path or Path(input("Canonical L8 path (select explicitly): ").strip())
        owner_confirmation = input("Owner confirmation: ")
        capture_confirmation = input("Capture confirmation: ")
        refs = {"L7": list(args.provenance_source), "L8": list(args.provenance_source)}
        result = owner_workflow(args.source_root, args.config, expected_commit=args.expected_commit,
            helper_sha256=args.helper_sha256, owner_kit_sha256=args.owner_kit_sha256,
            l7=l7_path, l8=l8_path, confirm=owner_confirmation,
            capture_confirm=capture_confirmation, provenance=refs)
        print(json.dumps(result, sort_keys=True)); return
    if args.config_only:
        result = validate_config_only(args.config, expected_commit=args.expected_commit, helper_sha256=args.helper_sha256, owner_kit_sha256=args.owner_kit_sha256)
    else:
        if args.source_root is None or args.confirm is None:
            parser.error("capture requires --source-root and --confirm")
        result = run(args.source_root, args.config, confirmation=args.confirm, expected_commit=args.expected_commit, helper_sha256=args.helper_sha256, owner_kit_sha256=args.owner_kit_sha256)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
