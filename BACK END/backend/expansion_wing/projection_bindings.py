from __future__ import annotations

import json
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .projection_source_registry import source_registry

BINDING_SCHEMA = "iios-projection-operational-bindings-v1"
BINDING_MANIFEST = Path(__file__).with_name("projection_bindings.json")
OPERATIONAL_ROOTS = {
    "TELEMETRY": Path.home() / "Library" / "Application Support" / "IIOS" / "telemetry",
    "MARKET_VALIDATION": Path.home() / "Library" / "Application Support" / "IIOS" / "market-validation",
    "MARKET_VALIDATION_BROWSER": Path.home() / "Library" / "Application Support" / "IIOS" / "market-validation" / "browser",
    "PUBLISHER_SOURCES": Path.home() / "Library" / "Application Support" / "IIOS" / "ExpansionWingPublisherSources",
}
PROHIBITED_FIELDS = frozenset({"credentials", "headers", "provider_body", "raw_log", "raw_error", "private_9i",
                               "session_results", "prompt", "model_response", "source_path", "ledger_contents"})


@dataclass(frozen=True)
class Binding:
    source_identifier: str
    logical_root: str
    filename: str
    source_schema: str
    adapter_identity: str
    adapter_version: str
    required: bool
    freshness_seconds: int
    failure_behavior: str
    maximum_bytes: int
    expected_mode: int
    expected_owner: str
    symlink_policy: str
    allowed_projected_fields: tuple[str, ...]
    availability_envelope_allowed: bool

    def path(self, roots: dict[str, Path]) -> Path:
        return roots[self.logical_root] / self.filename


def load_binding_manifest(*, manifest: Path | None = None, test_mode: bool = False) -> dict[str, Binding]:
    if manifest is not None and not test_mode:
        raise RuntimeError("OPERATIONAL_BINDING_OVERRIDE_REJECTED")
    path = manifest if test_mode and manifest is not None else BINDING_MANIFEST
    value = json.loads(path.read_bytes())
    if (not isinstance(value, dict) or set(value) != {"schema_version", "runtime_root_policy", "sources", "prohibited_fields"} or
            value["schema_version"] != BINDING_SCHEMA or value["runtime_root_policy"] != "FIXED_REVIEWED_IIOS_ROOTS_ONLY" or
            set(value["prohibited_fields"]) != PROHIBITED_FIELDS or not isinstance(value["sources"], list)):
        raise RuntimeError("BINDING_MANIFEST_INVALID")
    contracts = source_registry()
    result: dict[str, Binding] = {}
    fields = {"source_identifier", "logical_root", "filename", "source_schema", "adapter_identity", "adapter_version",
              "required", "freshness_seconds", "failure_behavior", "maximum_bytes", "expected_mode",
              "expected_owner", "symlink_policy", "allowed_projected_fields", "availability_envelope_allowed"}
    for row in value["sources"]:
        if not isinstance(row, dict) or set(row) != fields:
            raise RuntimeError("BINDING_MANIFEST_INVALID")
        name = row["source_identifier"]
        if (name in result or name not in contracts or row["logical_root"] not in OPERATIONAL_ROOTS or
                not re.fullmatch(r"[a-z0-9_]+\.json", str(row["filename"])) or
                row["required"] != contracts[name].required or row["freshness_seconds"] != contracts[name].freshness_seconds or
                row["failure_behavior"] != contracts[name].failure_behavior or
                row["expected_owner"] != "CURRENT_USER" or row["symlink_policy"] != "REJECT" or
                set(row["allowed_projected_fields"]) != contracts[name].allowed_projected_fields or
                row["maximum_bytes"] < 1024 or row["maximum_bytes"] > 262_144 or
                row["expected_mode"] not in {"0600", "0644"}):
            raise RuntimeError("BINDING_MANIFEST_INVALID")
        result[name] = Binding(**{**row, "expected_mode": int(row["expected_mode"], 8),
                                  "allowed_projected_fields": tuple(row["allowed_projected_fields"])})
    if set(result) != set(contracts):
        raise RuntimeError("BINDING_INVENTORY_INVALID")
    return result


@dataclass(frozen=True)
class SourceArtifact:
    value: dict[str, Any]
    encoded: bytes
    content_hash: str


def read_bound_artifacts(bindings: dict[str, Binding], *, roots: dict[str, Path] | None = None,
                         test_mode: bool = False, expected_uid: int | None = None) -> dict[str, SourceArtifact | None]:
    if roots is not None and not test_mode:
        raise RuntimeError("OPERATIONAL_ROOT_OVERRIDE_REJECTED")
    selected = roots if test_mode and roots is not None else OPERATIONAL_ROOTS
    if set(selected) != set(OPERATIONAL_ROOTS):
        raise RuntimeError("BINDING_ROOT_INVENTORY_INVALID")
    uid = os.getuid() if expected_uid is None else expected_uid
    cache: dict[Path, SourceArtifact | None] = {}
    output: dict[str, SourceArtifact | None] = {}
    for name, binding in bindings.items():
        path = binding.path(selected)
        if path in cache:
            output[name] = cache[path]
            continue
        try:
            root_info, info = path.parent.lstat(), path.lstat()
        except FileNotFoundError:
            cache[path] = None
            output[name] = None
            continue
        if (not stat.S_ISDIR(root_info.st_mode) or stat.S_ISLNK(root_info.st_mode) or root_info.st_uid != uid or
                not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode) or info.st_uid != uid or
                stat.S_IMODE(info.st_mode) != binding.expected_mode or info.st_size > binding.maximum_bytes):
            raise RuntimeError("BOUND_SOURCE_UNSAFE")
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        try:
            raw = os.read(fd, binding.maximum_bytes + 1)
        finally:
            os.close(fd)
        if len(raw) > binding.maximum_bytes:
            raise RuntimeError("BOUND_SOURCE_OVERSIZED")
        try:
            parsed = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise RuntimeError("BOUND_SOURCE_SCHEMA_INVALID") from None
        if not isinstance(parsed, dict):
            raise RuntimeError("BOUND_SOURCE_SCHEMA_INVALID")
        import hashlib
        artifact = SourceArtifact(parsed, raw, hashlib.sha256(raw).hexdigest())
        cache[path] = artifact
        output[name] = artifact
    return output
