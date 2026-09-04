from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

LAYERS = ("original", "notes", "claims", "browser")
BROWSER_ALLOWLIST = {"schema_version", "generated_at", "truth_state", "real_source_count", "fixture_source_count",
    "rights_review_count", "approved_source_count", "claims_pending_review_count", "reason"}
BROWSER_REASONS = {"NO_APPROVED_SOURCES", "SOURCE_REVIEW_PENDING", "ARCHIVE_UNAVAILABLE"}


@dataclass(frozen=True)
class RetentionPolicy:
    retention_days: int
    deletion_requires_human_approval: bool = True
    audit_manifest_required: bool = True

    def validate(self) -> None:
        if self.retention_days < 1 or not self.deletion_requires_human_approval or not self.audit_manifest_required:
            raise ValueError("RETENTION_POLICY_INVALID")


class SecureArchive:
    def __init__(self, root: Path, retention: RetentionPolicy) -> None:
        retention.validate(); self.root = root; self.retention = retention
        root.mkdir(parents=True, exist_ok=True, mode=0o700); root.chmod(0o700)
        for layer in LAYERS:
            path = root / layer; path.mkdir(exist_ok=True, mode=0o700); path.chmod(0o700)

    def _atomic(self, path: Path, payload: bytes) -> None:
        fd, temporary = tempfile.mkstemp(prefix=".pending-", dir=path.parent)
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "wb") as handle:
                handle.write(payload); handle.flush(); os.fsync(handle.fileno())
            os.replace(temporary, path); path.chmod(0o600)
        except Exception:
            try: os.close(fd)
            except OSError: pass
            try: os.unlink(temporary)
            except FileNotFoundError: pass
            raise

    def store(self, layer: str, payload: bytes, *, expected_hash: str | None = None) -> dict[str, Any]:
        if layer not in LAYERS: raise ValueError("ARCHIVE_LAYER_INVALID")
        digest = hashlib.sha256(payload).hexdigest()
        if expected_hash is not None and expected_hash != digest: raise ValueError("IMMUTABLE_HASH_MISMATCH")
        path = self.root / layer / f"{digest}.bin"
        if path.exists() and path.read_bytes() != payload: raise RuntimeError("CONTENT_ADDRESS_COLLISION")
        if not path.exists(): self._atomic(path, payload)
        return {"content_hash": digest, "layer": layer, "size_bytes": len(payload), "stored": True}

    def publish_browser(self, projection: dict[str, Any]) -> dict[str, Any]:
        if set(projection) - BROWSER_ALLOWLIST: raise ValueError("UNSAFE_BROWSER_FIELD")
        if projection.get("schema_version") != "investor-archive-browser-v1": raise ValueError("BROWSER_SCHEMA_INVALID")
        if projection.get("truth_state") not in {"CURRENT", "INCOMPLETE", "UNAVAILABLE"}:
            raise ValueError("BROWSER_TRUTH_INVALID")
        count_keys = BROWSER_ALLOWLIST & {key for key in BROWSER_ALLOWLIST if key.endswith("_count")}
        if any(key in projection and (not isinstance(projection[key], int) or isinstance(projection[key], bool) or
                                      projection[key] < 0) for key in count_keys):
            raise ValueError("BROWSER_COUNT_INVALID")
        if "reason" in projection and projection["reason"] not in BROWSER_REASONS:
            raise ValueError("BROWSER_REASON_INVALID")
        if not isinstance(projection.get("generated_at"), str) or len(projection["generated_at"]) > 40:
            raise ValueError("BROWSER_TIME_INVALID")
        encoded = json.dumps(projection, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
        if b"/Users/" in encoded or b"transcript" in encoded or b"hidden_reasoning" in encoded:
            raise ValueError("PRIVATE_BROWSER_VALUE")
        return self.store("browser", encoded)

    def manifest_entry(self, *, action: str, content_hash: str, actor: str, occurred_at: str) -> dict[str, str | bool]:
        if action not in {"STORED", "RETAINED", "DELETION_APPROVED", "DELETED"} or not actor:
            raise ValueError("AUDIT_EVENT_INVALID")
        return {"action": action, "content_hash": content_hash, "actor": actor, "occurred_at": occurred_at,
                "human_approval_required": action.startswith("DELETION")}
