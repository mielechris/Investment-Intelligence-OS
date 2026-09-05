from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SOURCE_ENVELOPE_SCHEMA = "iios-projection-source-envelope-v1"
MAX_SOURCE_BYTES = 262_144
_ENVELOPE_FIELDS = {"schema_version", "source_identifier", "source_schema", "artifact_identity",
                    "generated_at", "effective_at", "immutable_hash", "payload"}
_PROHIBITED_KEYS = {"credential", "credential_value", "api_key", "authorization", "headers", "provider_body",
                    "raw_log", "raw_error", "private_9i", "session_results", "prompt", "model_response",
                    "source_path", "filesystem_path", "ledger_contents"}
_PROHIBITED_VALUES = re.compile(r"(?:/Users/|/home/|file://|https?://[^ ]+/(?:private|raw))", re.I)


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def content_hash(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def timestamp(value: Any) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        raise ValueError("SOURCE_TIMESTAMP_INVALID") from None
    if parsed.tzinfo is None:
        raise ValueError("SOURCE_TIMESTAMP_INVALID")
    return parsed.astimezone(timezone.utc)


@dataclass(frozen=True)
class SourceContract:
    source_identifier: str
    source_schema: str
    artifact_identity: str
    freshness_seconds: int
    required: bool
    allowed_projected_fields: frozenset[str]
    failure_behavior: str


def source_registry() -> dict[str, SourceContract]:
    definitions = (
        ("factory_health", "iios-factory-health-v1", "FACTORY_HEALTH", 120, True, {"state"}),
        ("market_session", "iios-market-session-v1", "MARKET_SESSION", 120, True,
         {"state", "session_date", "calendar_approved"}),
        ("radar_cycle", "iios-radar-cycle-v1", "RADAR_CYCLE", 900, True,
         {"state", "cycle_id", "cycle_complete", "source_artifact_hash"}),
        ("candidate_lineage", "iios-candidate-lineage-v1", "CANDIDATE_LINEAGE", 900, False,
         {"state", "cycle_id", "source_artifact_hash", "candidates"}),
        ("benchmark_9h", "batch9h-validation-browser-v1", "BENCHMARK_9H", 86_400, False,
         {"state", "session_date", "full_session_complete"}),
        ("shadow_9i", "batch9i-browser-shadow-strategy-v1", "SHADOW_9I", 86_400, False,
         {"state", "source_session", "consumed_naturally", "observational_only"}),
        ("outcomes_9j", "batch9j-browser-outcome-learning-v1", "OUTCOMES_9J", 86_400, False,
         {"state", "source_session", "advanced"}),
        ("professional_research", "iios-professional-observations-v1", "PROFESSIONAL_RESEARCH", 86_400, False,
         {"state", "observation_count", "primary_verification_state", "agreement_state"}),
        ("lane_evidence", "iios-multi-asset-lane-evidence-v1", "LANE_EVIDENCE", 900, True,
         {"state", "session_date", "lanes"}),
        ("research_sleeves", "iios-research-sleeves-v1", "RESEARCH_SLEEVES", 86_400, False,
         {"state", "sleeve_count", "operational_position_count"}),
        ("paper_fund", "paper-portfolio-core-v1", "PAPER_FUND", 900, True,
         {"state", "nav", "cash", "positions", "transactions", "orders", "fills"}),
        ("provider_credit", "iios-provider-credit-sanitized-v1", "PROVIDER_CREDIT", 86_400, False,
         {"state", "confirmed_credits", "ambiguous_credits", "remaining_ceiling"}),
        ("authority_locks", "iios-authority-locks-v1", "AUTHORITY_LOCKS", 120, True,
         {"provider_contact", "credential_access", "automatic_promotion", "paper_order", "ledger_write",
          "broker", "live_execution"}),
    )
    return {row[0]: SourceContract(row[0], row[1], row[2], row[3], row[4], frozenset(row[5]),
                                   "FAIL_CLOSED" if row[4] else "PROJECT_UNAVAILABLE") for row in definitions}


def _private(value: Any) -> bool:
    if isinstance(value, dict):
        return any(str(key).lower() in _PROHIBITED_KEYS or _private(item) for key, item in value.items())
    if isinstance(value, list):
        return any(_private(item) for item in value)
    return isinstance(value, str) and bool(_PROHIBITED_VALUES.search(value))


def validate_envelope(value: Any, contract: SourceContract, *, now: datetime) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != _ENVELOPE_FIELDS:
        raise ValueError("SOURCE_ENVELOPE_INVALID")
    if (value["schema_version"] != SOURCE_ENVELOPE_SCHEMA or
            value["source_identifier"] != contract.source_identifier or
            value["source_schema"] != contract.source_schema or
            value["artifact_identity"] != contract.artifact_identity):
        raise ValueError("SOURCE_IDENTITY_INVALID")
    payload = value["payload"]
    if (not isinstance(payload, dict) or set(payload) != contract.allowed_projected_fields or _private(payload) or
            len(canonical(value)) > MAX_SOURCE_BYTES):
        raise ValueError("SOURCE_PAYLOAD_INVALID")
    generated, effective = timestamp(value["generated_at"]), timestamp(value["effective_at"])
    clock = now.astimezone(timezone.utc)
    if generated > clock or effective > clock or effective > generated:
        raise ValueError("SOURCE_LOOK_AHEAD_REJECTED")
    if value["immutable_hash"] != content_hash(payload):
        raise ValueError("SOURCE_HASH_MISMATCH")
    return {"source_identifier": contract.source_identifier, "generated_at": generated,
            "effective_at": effective, "age_seconds": (clock - effective).total_seconds(),
            "fresh": (clock - effective).total_seconds() <= contract.freshness_seconds,
            "immutable_hash": value["immutable_hash"], "payload": payload}


class RegisteredSourceReader:
    """Reads only source-controlled artifact names below one owner-only root."""

    def __init__(self, root: Path, artifacts: dict[str, str], *, expected_uid: int | None = None) -> None:
        self.root = root
        self.artifacts = artifacts.copy()
        self.expected_uid = os.getuid() if expected_uid is None else expected_uid

    def read(self, source_identifier: str) -> dict[str, Any]:
        if source_identifier not in source_registry() or source_identifier not in self.artifacts:
            raise RuntimeError("SOURCE_NOT_REGISTERED")
        name = self.artifacts[source_identifier]
        if not re.fullmatch(r"[a-z0-9_-]{1,80}\.json", name):
            raise RuntimeError("SOURCE_ARTIFACT_IDENTITY_INVALID")
        root_info = self.root.lstat()
        if (not stat.S_ISDIR(root_info.st_mode) or stat.S_ISLNK(root_info.st_mode) or
                root_info.st_uid != self.expected_uid or stat.S_IMODE(root_info.st_mode) != 0o700):
            raise RuntimeError("SOURCE_ROOT_UNSAFE")
        directory_fd = os.open(self.root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0))
        try:
            try:
                fd = os.open(name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=directory_fd)
            except OSError:
                raise RuntimeError("SOURCE_UNAVAILABLE") from None
            try:
                info = os.fstat(fd)
                if (not stat.S_ISREG(info.st_mode) or info.st_uid != self.expected_uid or
                        stat.S_IMODE(info.st_mode) != 0o600 or info.st_size > MAX_SOURCE_BYTES):
                    raise RuntimeError("SOURCE_ARTIFACT_UNSAFE")
                raw = os.read(fd, MAX_SOURCE_BYTES + 1)
                if len(raw) > MAX_SOURCE_BYTES:
                    raise RuntimeError("SOURCE_ARTIFACT_UNSAFE")
            finally:
                os.close(fd)
        finally:
            os.close(directory_fd)
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise RuntimeError("SOURCE_SCHEMA_INVALID") from None
