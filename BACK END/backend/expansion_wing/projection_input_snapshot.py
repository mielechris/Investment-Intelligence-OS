from __future__ import annotations

import hashlib
import json
import os
import stat
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .projection_bindings import Binding, read_bound_artifacts
from .projection_source_adapters import adapt_source
from .projection_source_registry import MAX_SOURCE_BYTES, source_registry, validate_envelope

INPUT_ROOT_NAME = "ExpansionWingPublisherInputs"
INPUT_MANIFEST = "envelope-manifest.json"
INPUT_SCHEMA = "iios-projection-envelope-snapshot-v1"
MAX_MANIFEST_BYTES = 32_768


def operational_input_root() -> Path:
    return Path.home() / "Library" / "Application Support" / "IIOS" / INPUT_ROOT_NAME


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def _atomic(root: Path, name: str, encoded: bytes) -> None:
    fd, temporary = tempfile.mkstemp(prefix=f".{name}.", dir=root)
    path = Path(temporary)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(encoded); stream.flush(); os.fsync(stream.fileno())
        os.replace(path, root / name)
        directory_fd = os.open(root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try: os.fsync(directory_fd)
        finally: os.close(directory_fd)
    except Exception:
        try: os.close(fd)
        except OSError: pass
        try: path.unlink()
        except OSError: pass
        raise RuntimeError("ENVELOPE_PUBLICATION_FAILED") from None


def _safe_root(root: Path, *, expected_uid: int, create: bool = False) -> None:
    if create and not root.exists(): root.mkdir(mode=0o700)
    info = root.lstat()
    if (not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode) or info.st_uid != expected_uid or
            stat.S_IMODE(info.st_mode) != 0o700):
        raise RuntimeError("ENVELOPE_ROOT_UNSAFE")


@dataclass(frozen=True)
class SnapshotResult:
    changed: bool
    changed_envelopes: int
    semantic_hash: str
    state: str


class EnvelopeSnapshotBuilder:
    def __init__(self, root: Path, bindings: dict[str, Binding], *, roots: dict[str, Path] | None = None,
                 test_mode: bool = False, before_manifest: Callable[[], None] | None = None) -> None:
        if root != operational_input_root() and not test_mode:
            raise RuntimeError("OPERATIONAL_INPUT_ROOT_OVERRIDE_REJECTED")
        self.root, self.bindings, self.roots = root, bindings, roots
        self.test_mode, self.before_manifest = test_mode, before_manifest
        self.uid = os.getuid()

    def build(self, *, now: datetime) -> tuple[dict[str, dict[str, Any]], SnapshotResult]:
        if now.tzinfo is None: raise RuntimeError("ENVELOPE_CLOCK_INVALID")
        artifacts = read_bound_artifacts(self.bindings, roots=self.roots, test_mode=self.test_mode)
        envelopes = {name: adapt_source(name, self.bindings[name], artifacts[name]) for name in self.bindings}
        contracts = source_registry()
        for name, envelope in envelopes.items(): validate_envelope(envelope, contracts[name], now=now)
        encoded = {f"{name}.json": _canonical(value) for name, value in envelopes.items()}
        hashes = {name[:-5]: hashlib.sha256(value).hexdigest() for name, value in encoded.items()}
        semantic = hashlib.sha256(_canonical(hashes)).hexdigest()
        expected = set(encoded) | {INPUT_MANIFEST}
        if self.root.exists():
            _safe_root(self.root, expected_uid=self.uid)
            names = {p.name for p in self.root.iterdir()}
            if names and names != expected and not (INPUT_MANIFEST not in names and names < expected):
                raise RuntimeError("ENVELOPE_INVENTORY_UNSAFE")
        else:
            parent = self.root.parent; parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            self.root.mkdir(mode=0o700)
        old_manifest: dict[str, Any] | None = None
        manifest_path = self.root / INPUT_MANIFEST
        if manifest_path.exists():
            try: old_manifest = json.loads(manifest_path.read_bytes())
            except Exception: raise RuntimeError("ENVELOPE_MANIFEST_INVALID") from None
            manifest_fields={"schema_version","semantic_hash","inventory","envelope_hashes","adapter_versions","source_hashes"}
            if (not isinstance(old_manifest,dict) or set(old_manifest)!=manifest_fields or
                    old_manifest.get("schema_version")!=INPUT_SCHEMA or old_manifest.get("inventory")!=sorted(expected) or
                    set(old_manifest.get("envelope_hashes",{}))!=set(envelopes)):
                raise RuntimeError("ENVELOPE_MANIFEST_INVALID")
            for name,digest in old_manifest["envelope_hashes"].items():
                path=self.root/f"{name}.json"; info=path.lstat()
                if (not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode) or info.st_uid!=self.uid or
                        stat.S_IMODE(info.st_mode)!=0o600 or hashlib.sha256(path.read_bytes()).hexdigest()!=digest):
                    raise RuntimeError("ENVELOPE_MANIFEST_INVALID")
            if old_manifest.get("semantic_hash") == semantic:
                return envelopes, SnapshotResult(False, 0, semantic, "UNCHANGED")
        changed = 0
        for name, value in encoded.items():
            path = self.root / name
            if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest() != hashlib.sha256(value).hexdigest():
                _atomic(self.root, name, value); changed += 1
        manifest = {"schema_version": INPUT_SCHEMA, "semantic_hash": semantic,
            "inventory": sorted(expected), "envelope_hashes": hashes,
            "adapter_versions": {name: self.bindings[name].adapter_version for name in sorted(self.bindings)},
            "source_hashes": {name: envelopes[name]["source_content_hash"] for name in sorted(envelopes)}}
        if self.before_manifest: self.before_manifest()
        _atomic(self.root, INPUT_MANIFEST, _canonical(manifest))
        return envelopes, SnapshotResult(True, changed, semantic, "PUBLISHED")
