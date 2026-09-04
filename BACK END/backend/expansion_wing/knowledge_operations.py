from __future__ import annotations

import json
import os
import stat
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA = "expansion-wing-knowledge-operations-v1"
STATUS = {"READY", "AVAILABLE_EMPTY", "NOT_ACTIVATED", "AWAITING_APPROVED_SOURCE", "DISABLED", "UNAVAILABLE"}
SECURITY_FIELDS = {"schema_version", "algorithm", "key_id", "plaintext_retained", "review_service_enabled"}
COUNT_FIELDS = ("source_count", "note_count", "claim_count", "rights_review_queue_count",
    "transcript_review_queue_count", "contradiction_queue_count", "judgment_queue_count", "pattern_queue_count")


def _owned(path: Path, *, mode: int, uid: int) -> bool:
    try:
        value = path.lstat()
        return not stat.S_ISLNK(value.st_mode) and stat.S_IMODE(value.st_mode) == mode and value.st_uid == uid
    except OSError:
        return False


def _bounded_manifest(path: Path, uid: int) -> dict[str, Any] | None:
    try:
        if not _owned(path, mode=0o600, uid=uid) or path.stat().st_size > 2_000:
            return None
        value = json.loads(path.read_text(encoding="ascii"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    if (not isinstance(value, dict) or set(value) != SECURITY_FIELDS or
            value.get("schema_version") != "expansion-wing-security-manifest-v1" or
            value.get("algorithm") != "AES-256-GCM" or value.get("key_id") != "archive-key-v1" or
            value.get("plaintext_retained") is not False or value.get("review_service_enabled") is not False):
        return None
    return value


def _encrypted_count(root: Path, layer: str, uid: int) -> int | None:
    directory = root / layer
    if not directory.exists(): return 0
    if not _owned(directory, mode=0o700, uid=uid): return None
    try: entries = list(directory.iterdir())
    except OSError: return None
    if any(not entry.is_file() or entry.is_symlink() or entry.suffix != ".enc" or
           not _owned(entry, mode=0o600, uid=uid) for entry in entries): return None
    return len(entries)


def knowledge_operations_projection(security_root: Path, archive_root: Path, *, expected_uid: int | None = None,
                                    review_service_installed: bool = False) -> dict[str, Any]:
    uid = os.getuid() if expected_uid is None else expected_uid
    counts = {field: 0 for field in COUNT_FIELDS}
    unavailable = {"schema_version": SCHEMA, "generated_at": datetime.now(timezone.utc).isoformat(),
        "operational_encryption": "UNAVAILABLE", "keychain": "UNAVAILABLE", "backup_recovery": "UNAVAILABLE",
        "owner_reviewer": "UNAVAILABLE", "review_service": "DISABLED", "archive": "UNAVAILABLE",
        "public_source_intake": "NOT_ACTIVATED", "transcription": "NOT_ACTIVATED", **counts,
        "private_data_exposed": False, "authority_granted": False}
    if review_service_installed: return unavailable
    if not (_owned(security_root, mode=0o700, uid=uid) and _owned(archive_root, mode=0o700, uid=uid)):
        return unavailable
    manifest = _bounded_manifest(archive_root / "manifests" / "security.json", uid)
    if manifest is None: return unavailable
    source_count = _encrypted_count(archive_root, "original", uid)
    note_count = _encrypted_count(archive_root, "notes", uid)
    claim_count = _encrypted_count(archive_root, "claims", uid)
    if None in (source_count, note_count, claim_count): return unavailable
    canary = archive_root / "records" / "synthetic-canary.enc"
    owner = archive_root / "reviewers" / "owner-admin.enc"
    backup_manifest = archive_root / "manifests" / "backup.json"
    result = {**unavailable, "operational_encryption": "READY", "keychain": "READY",
        "backup_recovery": "READY" if _owned(backup_manifest, mode=0o600, uid=uid) else "UNAVAILABLE",
        "owner_reviewer": "READY" if _owned(owner, mode=0o600, uid=uid) else "UNAVAILABLE",
        "archive": "AVAILABLE_EMPTY" if source_count + note_count + claim_count == 0 else "READY",
        "public_source_intake": "AWAITING_APPROVED_SOURCE", "source_count": source_count,
        "note_count": note_count, "claim_count": claim_count}
    if not _owned(canary, mode=0o600, uid=uid): result["operational_encryption"] = "UNAVAILABLE"
    if any(result[key] not in STATUS for key in ("operational_encryption", "keychain", "backup_recovery",
            "owner_reviewer", "review_service", "archive", "public_source_intake", "transcription")):
        raise RuntimeError("KNOWLEDGE_PROJECTION_INVALID")
    return result


def validate_browser_projection(value: dict[str, Any]) -> None:
    allowed = {"schema_version", "generated_at", "operational_encryption", "keychain", "backup_recovery",
        "owner_reviewer", "review_service", "archive", "public_source_intake", "transcription",
        *COUNT_FIELDS, "private_data_exposed", "authority_granted"}
    if set(value) != allowed or value.get("schema_version") != SCHEMA:
        raise ValueError("KNOWLEDGE_PROJECTION_FIELDS_INVALID")
    if any(not isinstance(value[field], int) or isinstance(value[field], bool) or value[field] < 0 for field in COUNT_FIELDS):
        raise ValueError("KNOWLEDGE_PROJECTION_COUNT_INVALID")
    if value["private_data_exposed"] is not False or value["authority_granted"] is not False:
        raise ValueError("KNOWLEDGE_PROJECTION_AUTHORITY_INVALID")
