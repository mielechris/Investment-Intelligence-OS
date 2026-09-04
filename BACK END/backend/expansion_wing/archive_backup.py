from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone


def backup_manifest(records: dict[str, bytes], *, key_id: str) -> dict:
    if not records or not key_id: raise ValueError("BACKUP_INPUT_REQUIRED")
    entries = {name: hashlib.sha256(payload).hexdigest() for name, payload in sorted(records.items())}
    body = {"schema_version": "encrypted-archive-backup-v1", "key_id": key_id,
        "created_at": datetime.now(timezone.utc).isoformat(), "entries": entries, "encrypted": True}
    body["manifest_hash"] = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return body


def verify_restore(manifest: dict, restored: dict[str, bytes]) -> str:
    entries = manifest.get("entries")
    if not isinstance(entries, dict): return "MANIFEST_INVALID"
    if set(restored) != set(entries): return "PARTIAL_RESTORE"
    if any(hashlib.sha256(restored[name]).hexdigest() != digest for name, digest in entries.items()):
        return "HASH_MISMATCH"
    return "VERIFIED"


def authorize_deletion(content_hash: str, *, reviewer: str, timestamp: str, reason: str,
                       human_authorized: bool) -> dict:
    if not human_authorized: raise PermissionError("DELETION_AUTHORIZATION_REQUIRED")
    if len(content_hash) != 64 or not all((reviewer, timestamp, reason)): raise ValueError("DELETION_AUDIT_REQUIRED")
    return {"content_hash": content_hash, "deleted": True, "private_content_retained": False,
            "tombstone": True, "reviewer": reviewer, "timestamp": timestamp, "reason": reason}


def retention_expired(created_at: str, now: str, retention_days: int) -> bool:
    if retention_days < 1: raise ValueError("RETENTION_INVALID")
    created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    instant = datetime.fromisoformat(now.replace("Z", "+00:00"))
    return (instant - created).total_seconds() >= retention_days * 86_400
