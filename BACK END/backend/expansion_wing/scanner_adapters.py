from __future__ import annotations

from dataclasses import dataclass

OUTCOMES = {"CLEAN", "MALWARE_DETECTED", "UNAVAILABLE", "STALE_SIGNATURES", "TIMEOUT", "ERROR", "AMBIGUOUS"}


@dataclass(frozen=True)
class ScannerResult:
    outcome: str
    scanner_name: str
    scanner_version: str
    signature_age_hours: float
    elapsed_seconds: float
    file_size: int


@dataclass(frozen=True)
class ScannerPolicy:
    max_signature_age_hours: float = 24
    timeout_seconds: float = 30
    max_file_bytes: int = 25_000_000


def accept_scan(result: ScannerResult, policy: ScannerPolicy = ScannerPolicy()) -> str:
    if result.outcome not in OUTCOMES or not result.scanner_name or not result.scanner_version: return "REJECTED_AMBIGUOUS"
    if result.file_size < 0 or result.file_size > policy.max_file_bytes: return "REJECTED_FILE_SIZE"
    if result.elapsed_seconds < 0 or result.elapsed_seconds > policy.timeout_seconds: return "REJECTED_TIMEOUT"
    if result.signature_age_hours < 0 or result.signature_age_hours > policy.max_signature_age_hours: return "REJECTED_STALE_SIGNATURES"
    return "ACCEPTED_CLEAN" if result.outcome == "CLEAN" else f"REJECTED_{result.outcome}"
