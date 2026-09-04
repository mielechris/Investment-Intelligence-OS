from __future__ import annotations

import hashlib
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

EXTENSIONS = {"wav": "audio/wav", "mp3": "audio/mpeg", "m4a": "audio/mp4", "mp4": "video/mp4",
    "mov": "video/quicktime", "txt": "text/plain", "md": "text/markdown"}
EXECUTABLE_MAGIC = (b"MZ", b"\x7fELF", b"\xcf\xfa\xed\xfe", b"\xfe\xed\xfa\xcf")
ARCHIVE_MAGIC = (b"PK\x03\x04", b"Rar!", b"7z\xbc\xaf\x27\x1c", b"\x1f\x8b")


class MalwareScanner(Protocol):
    def scan(self, payload: bytes) -> str: ...


class InactiveScanner:
    def scan(self, _payload: bytes) -> str: return "NOT_CONFIGURED"


@dataclass(frozen=True)
class QuarantinePolicy:
    max_bytes: int = 25_000_000
    max_duration_seconds: float = 7_200


def _mime(payload: bytes, extension: str) -> str | None:
    if extension == "wav" and payload[:4] == b"RIFF" and payload[8:12] == b"WAVE": return "audio/wav"
    if extension == "mp3" and (payload[:3] == b"ID3" or payload[:2] in (b"\xff\xfb", b"\xff\xf3")): return "audio/mpeg"
    if extension in {"m4a", "mp4", "mov"} and len(payload) >= 12 and payload[4:8] == b"ftyp": return EXTENSIONS[extension]
    if extension in {"txt", "md"}:
        try: payload.decode("utf-8")
        except UnicodeDecodeError: return None
        if b"\0" not in payload: return EXTENSIONS[extension]
    return None


def stage(root: Path, filename: str, payload: bytes, *, duration_seconds: float, scanner: MalwareScanner,
          policy: QuarantinePolicy = QuarantinePolicy()) -> dict:
    if Path(filename).name != filename or filename in {".", ".."}: raise ValueError("TRAVERSAL_NAME_REJECTED")
    extension = Path(filename).suffix.casefold().lstrip(".")
    if extension not in EXTENSIONS: raise ValueError("EXTENSION_REJECTED")
    if not payload or len(payload) > policy.max_bytes: raise ValueError("PAYLOAD_LIMIT")
    if duration_seconds < 0 or duration_seconds > policy.max_duration_seconds: raise ValueError("DURATION_LIMIT")
    if any(payload.startswith(magic) for magic in EXECUTABLE_MAGIC + ARCHIVE_MAGIC): raise ValueError("EXECUTABLE_OR_ARCHIVE_REJECTED")
    if any(magic in payload[1:] for magic in EXECUTABLE_MAGIC + ARCHIVE_MAGIC): raise ValueError("POLYGLOT_REJECTED")
    detected = _mime(payload, extension)
    if detected != EXTENSIONS[extension]: raise ValueError("MIME_MISMATCH")
    scan = scanner.scan(payload)
    if scan not in {"CLEAN", "NOT_CONFIGURED", "MALWARE_DETECTED", "ERROR"}: scan = "ERROR"
    if scan != "CLEAN": return {"status": "REJECTED", "reason": f"SCANNER_{scan}", "stored": False}
    root.mkdir(parents=True, exist_ok=True, mode=0o700); root.chmod(0o700)
    digest = hashlib.sha256(payload).hexdigest(); target = root / f"{digest}.{extension}"
    if target.is_symlink(): raise ValueError("SYMLINK_REJECTED")
    descriptor, temporary = tempfile.mkstemp(prefix=".quarantine-", dir=root)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as handle: handle.write(payload); handle.flush(); os.fsync(handle.fileno())
        os.replace(temporary, target); target.chmod(0o600)
    except Exception:
        try: os.unlink(temporary)
        except FileNotFoundError: pass
        raise
    return {"status": "QUARANTINED", "mime": detected, "size_bytes": len(payload), "duration_seconds": duration_seconds,
            "content_hash": digest, "scanner_status": "CLEAN", "executed": False, "path_exposed": False}
