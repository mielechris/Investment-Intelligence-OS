"""Owner-operated, read-only L7/L8 SQLite snapshot kit.

This command is deliberately separate from the Codex workflow.  It accepts
only a hash-bound, owner-created source configuration and the exact consent
sentence below.  The capture child is the reviewed Seatbelt helper; no direct
SQLite copy, network, credential, provider, model, broker, or ledger-write
capability exists in this module.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import subprocess
import sys

BACKEND = Path(__file__).resolve().parents[1] / "BACK END/backend"
sys.path.insert(0, str(BACKEND))
from truth_spine_contract import canonical, digest, seal, utc, verified  # noqa: E402
from truth_spine_sqlite_capture import launch_capture  # noqa: E402
import truth_spine_sqlite_capture as capture_helper  # noqa: E402


SCHEMA = "iios-owner-ledger-snapshot-v1"
CONFIG_SCHEMA = "iios-owner-ledger-source-config-v1"
OUTPUT_ROOT = Path("/private/tmp/iios-northstar-owner-snapshots-sb37")
CONFIRMATION = (
    "I authorize read-only capture of my canonical IIOS L7 and L8 ledgers into "
    "the isolated owner snapshot root. I do not authorize source modification."
)
SOURCE_KINDS = {"L7", "L8"}
UTC_SUFFIX = re.compile(r"(?:Z|[+-]00:00)$")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def alias_path(path: Path, sources: dict[Path, str], output: Path) -> str:
    resolved = path.resolve()
    if resolved == output.resolve() or resolved.is_relative_to(output.resolve()):
        return "{OUTPUT}" + ("/" + resolved.relative_to(output.resolve()).as_posix()
                               if resolved != output.resolve() else "")
    for source, alias in sources.items():
        if resolved == source:
            return "{" + alias + "}"
    return "{PRIVATE_PATH}"


def owner_regular(path: Path, *, mode: int | None = None) -> bytes:
    if not path.is_absolute() or path != path.resolve() or any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError("OWNER_SOURCE_PATH_INVALID")
    info = path.lstat()
    if info.st_uid != os.getuid() or not stat.S_ISREG(info.st_mode):
        raise ValueError("OWNER_SOURCE_TYPE_OR_OWNER_INVALID")
    if mode is not None and stat.S_IMODE(info.st_mode) != mode:
        raise ValueError("OWNER_SOURCE_MODE_INVALID")
    return path.read_bytes()


def atomic_write(path: Path, payload: bytes, mode: int = 0o600) -> None:
    if path.exists() or path.is_symlink():
        raise ValueError("OWNER_OUTPUT_ALREADY_EXISTS")
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if stat.S_IMODE(path.parent.stat().st_mode) != 0o700:
        raise ValueError("OWNER_OUTPUT_DIRECTORY_MODE_INVALID")
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, mode)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        # fd is owned by fdopen after successful construction.
        pass
    dfd = os.open(path.parent, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        os.fsync(dfd)
    finally:
        os.close(dfd)


def load_config(config: Path) -> tuple[dict, dict[Path, str]]:
    raw = owner_regular(config, mode=0o600)
    try:
        record = verified(json.loads(raw))
    except (ValueError, json.JSONDecodeError):
        raise ValueError("OWNER_SOURCE_CONFIG_INVALID") from None
    if record.get("schema") != CONFIG_SCHEMA or set(record) != {"schema", "sources", "content_hash"}:
        raise ValueError("OWNER_SOURCE_CONFIG_INVALID")
    rows = record.get("sources")
    if not isinstance(rows, list) or len(rows) != 2 or {r.get("kind") for r in rows} != SOURCE_KINDS:
        raise ValueError("OWNER_SOURCE_CONFIG_INVALID")
    resolved: dict[Path, str] = {}
    for row in rows:
        if set(row) != {"kind", "alias", "path", "sha256", "size"}:
            raise ValueError("OWNER_SOURCE_CONFIG_INVALID")
        if row["alias"] not in {"L7", "L8"} or not re.fullmatch(r"[0-9a-f]{64}", row["sha256"]):
            raise ValueError("OWNER_SOURCE_CONFIG_INVALID")
        path = Path(row["path"])
        if not path.is_absolute() or any(part.lower() in {"credentials", "keychains"} for part in path.parts):
            raise ValueError("OWNER_SOURCE_PATH_INVALID")
        data = owner_regular(path)
        if len(data) != row["size"] or sha(path) != row["sha256"]:
            raise ValueError("OWNER_SOURCE_IDENTITY_MISMATCH")
        if path in resolved or row["alias"] in resolved.values():
            raise ValueError("OWNER_SOURCE_IDENTITY_DUPLICATE")
        resolved[path] = row["alias"]
    return record, resolved


def snapshot_metadata(path: Path) -> dict:
    """Read only aggregate metadata; no ledger rows or payloads leave SQLite."""
    db = sqlite3.connect(path.as_uri() + "?mode=ro&immutable=1", uri=True)
    try:
        quick = db.execute("PRAGMA quick_check").fetchall()
        integrity = db.execute("PRAGMA integrity_check").fetchall()
        foreign = db.execute("PRAGMA foreign_key_check").fetchall()
        if quick != [("ok",)] or integrity != [("ok",)] or foreign:
            raise ValueError("OWNER_SNAPSHOT_INTEGRITY_INVALID")
        schema = db.execute("SELECT type,name,tbl_name,sql FROM sqlite_schema ORDER BY type,name").fetchall()
        table_rows = db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
        total = 0
        timestamps: list[datetime] = []
        for (table,) in table_rows:
            quoted = '"' + table.replace('"', '""') + '"'
            count = db.execute(f"SELECT count(*) FROM {quoted}").fetchone()[0]
            total += int(count)
            columns = db.execute(f"PRAGMA table_info({quoted})").fetchall()
            for _, name, *_ in columns:
                if not (name.lower().endswith(("_at", "_time", "timestamp")) or name.lower() in {"created", "updated"}):
                    continue
                col = '"' + name.replace('"', '""') + '"'
                value = db.execute(f"SELECT max({col}) FROM {quoted}").fetchone()[0]
                if not isinstance(value, str) or not UTC_SUFFIX.search(value):
                    continue
                try:
                    timestamps.append(utc(value))
                except ValueError:
                    continue
        high = max(timestamps).isoformat().replace("+00:00", "Z") if timestamps else None
        return {"schema_sha256": hashlib.sha256(canonical(schema)).hexdigest(),
                "table_count": len(table_rows), "row_count": total,
                "high_watermark_utc": high, "quick_check": "ok",
                "integrity_check": "ok", "foreign_key_violations": 0}
    finally:
        db.close()


def capture(source: Path, output: Path, evidence: Path, sources: dict[Path, str]) -> dict:
    receipt = launch_capture(source, output, evidence_root=evidence, timeout=120)
    snapshot = output / "snapshot.db"
    metadata = snapshot_metadata(snapshot)
    job = json.loads((output / "job.json").read_bytes())
    return {"alias": sources[source], "snapshot": "{OUTPUT}/" + sources[source].lower() + "/snapshot.db",
            "snapshot_sha256": receipt["snapshot_sha256"], "snapshot_bytes": receipt["bytes"],
            "capture_job": receipt["job"], "helper_sha256": job["helper_sha256"],
            "profile_sha256": job["profile_sha256"], **metadata}


def run(source_root: Path, config: Path, *, confirmation: str,
        expected_commit: str | None = None, helper_sha256: str | None = None) -> dict:
    if confirmation != CONFIRMATION:
        raise PermissionError("OWNER_CONFIRMATION_REQUIRED")
    source_root = source_root.resolve()
    if not source_root.is_dir() or source_root.is_symlink():
        raise ValueError("OWNER_SOURCE_CHECKOUT_INVALID")
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=source_root, text=True).strip()
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("OWNER_SOURCE_COMMIT_INVALID")
    if expected_commit is None or not re.fullmatch(r"[0-9a-f]{40}", expected_commit) or commit != expected_commit:
        raise ValueError("OWNER_SOURCE_COMMIT_PIN_MISMATCH")
    helper = Path(capture_helper.__file__).resolve()
    if helper_sha256 is None or not re.fullmatch(r"[0-9a-f]{64}", helper_sha256) or sha(helper) != helper_sha256:
        raise ValueError("OWNER_HELPER_PIN_MISMATCH")
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=source_root, text=True):
        raise ValueError("OWNER_SOURCE_CHECKOUT_DIRTY")
    config_record, sources = load_config(config)
    if OUTPUT_ROOT.exists() or OUTPUT_ROOT.is_symlink():
        raise ValueError("OWNER_OUTPUT_ROOT_MUST_BE_ABSENT")
    output = OUTPUT_ROOT.resolve()
    output.mkdir(mode=0o700)
    evidence = output / "incidents"
    evidence.mkdir(mode=0o700)
    captures = {}
    try:
        for path in sorted(sources, key=lambda p: sources[p]):
            destination = output / sources[path].lower()
            captures[sources[path]] = capture(path, destination, evidence, sources)
        high = [captures[x]["high_watermark_utc"] for x in ("L7", "L8")]
        if any(value is None for value in high):
            raise ValueError("OWNER_HIGH_WATERMARK_UNAVAILABLE")
        watermark = min(high)
        manifest = seal({"schema": SCHEMA, "source_commit": commit,
                         "config_sha256": sha(config), "config_identity": config_record["content_hash"],
                         "sources": [{"alias": sources[p], "source_identity": "{" + sources[p] + "}",
                                      "bytes": p.stat().st_size, "sha256": sha(p)} for p in sorted(sources, key=lambda p: sources[p])],
                         "captures": captures, "common_reconciliation_watermark_utc": watermark,
                         "authority": {"read_only": True, "provider": False, "credential": False,
                                       "broker": False, "paper": False, "ledger_write": False},
                         "output_root": "{OUTPUT}", "completion": "OWNER_REVIEW_REQUIRED"})
        atomic_write(output / "manifest.json", canonical(manifest))
        receipt = seal({"schema": "iios-owner-ledger-snapshot-receipt-v1",
                        "status": "VERIFIED", "manifest_hash": manifest["content_hash"],
                        "manifest_sha256": sha(output / "manifest.json"),
                        "source_commit": commit, "common_reconciliation_watermark_utc": watermark,
                        "sources": [{"alias": sources[p], "snapshot_sha256": captures[sources[p]]["snapshot_sha256"]}
                                    for p in sorted(sources, key=lambda p: sources[p])],
                        "rows": "NOT_CAPTURED_OR_REPORTED", "credentials": 0, "providers": 0,
                        "output_root": "{OUTPUT}"})
        atomic_write(output / "completion-receipt.json", canonical(receipt))
        return {"status": receipt["status"], "output": "{OUTPUT}",
                "receipt_sha256": sha(output / "completion-receipt.json"),
                "manifest_hash": manifest["content_hash"], "source_commit": commit,
                "watermark": watermark, "credential_accesses": 0, "provider_requests": 0}
    except BaseException as error:
        failure = seal({"schema": "iios-owner-ledger-snapshot-failure-v1", "status": "FAILED_CLOSED",
                        "category": type(error).__name__, "source_commit": commit,
                        "output_root": "{OUTPUT}", "captures_started": sorted(captures),
                        "credentials": 0, "providers": 0})
        if not (output / "failure.json").exists():
            atomic_write(output / "failure.json", canonical(failure))
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description="Owner-only read-only IIOS L7/L8 capture")
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--helper-sha256", required=True)
    parser.add_argument("--confirm", required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.source_root, args.config, confirmation=args.confirm,
                         expected_commit=args.expected_commit, helper_sha256=args.helper_sha256), sort_keys=True))


if __name__ == "__main__":
    main()
