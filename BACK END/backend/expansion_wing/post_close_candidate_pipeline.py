from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .candidate_flow_acceptance import AcceptanceResult

SCHEMA_VERSION = "iios-post-close-candidate-pipeline-v1"
AUTHORITY = {
    "automatic_case_promotion": False,
    "committee_reliance": False,
    "paper_order": False,
    "ledger_write": False,
    "broker": False,
    "live_execution": False,
}


def _time(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        raise ValueError("SESSION_TIME_INVALID") from None
    if parsed.tzinfo is None:
        raise ValueError("SESSION_TIME_INVALID")
    return parsed


def _hash(value: dict[str, Any]) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class ClosingSessionEvidence:
    session_date: str
    market_timezone: str
    final_snapshot_at: str
    expected_snapshot_count: int
    observed_snapshot_count: int
    provider_error_count: int
    universe_count: int
    complete: bool
    evidence_hash: str

    def validate(self) -> None:
        fields = {
            "session_date": self.session_date,
            "market_timezone": self.market_timezone,
            "final_snapshot_at": self.final_snapshot_at,
            "expected_snapshot_count": self.expected_snapshot_count,
            "observed_snapshot_count": self.observed_snapshot_count,
            "provider_error_count": self.provider_error_count,
            "universe_count": self.universe_count,
            "complete": self.complete,
        }
        if (
            not re.fullmatch(r"\d{4}-\d{2}-\d{2}", self.session_date)
            or self.market_timezone != "America/New_York"
            or _time(self.final_snapshot_at).date().isoformat() != self.session_date
            or not 1 <= self.expected_snapshot_count <= 200
            or self.observed_snapshot_count != self.expected_snapshot_count
            or self.provider_error_count != 0
            or not 1 <= self.universe_count <= 2_000
            or self.complete is not True
            or not re.fullmatch(r"[0-9a-f]{64}", self.evidence_hash)
            or _hash(fields) != self.evidence_hash
        ):
            raise ValueError("CLOSING_SESSION_INCOMPLETE")


@dataclass(frozen=True)
class PrimarySourceAttestation:
    candidate_id: str
    ticker: str
    source_class: str
    source_host: str
    document_date: str
    content_hash: str
    rights_approved: bool
    human_approved: bool

    def validate(self) -> None:
        if (
            not re.fullmatch(r"candidate_[0-9a-f]{16}", self.candidate_id)
            or not re.fullmatch(r"[A-Z][A-Z0-9.-]{0,9}", self.ticker)
            or self.source_class not in {"SEC_FILING", "ISSUER_RELEASE"}
            or not re.fullmatch(r"[a-z0-9.-]{1,253}", self.source_host)
            or ".." in self.source_host
            or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", self.document_date)
            or not re.fullmatch(r"[0-9a-f]{64}", self.content_hash)
            or self.rights_approved is not True
            or self.human_approved is not True
        ):
            raise ValueError("PRIMARY_SOURCE_ATTESTATION_INVALID")


@dataclass(frozen=True)
class PostCloseResult:
    state: str
    session_date: str | None
    enriched_candidate_count: int
    verified_candidate_count: int
    governed_case_count: int
    failure_category: str | None

    def browser_safe(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "state": self.state,
            "session_date": self.session_date,
            "enriched_candidate_count": self.enriched_candidate_count,
            "verified_candidate_count": self.verified_candidate_count,
            "governed_case_count": self.governed_case_count,
            "failure_category": self.failure_category,
            "authority": AUTHORITY.copy(),
        }


def finalize_post_close(
    closing: ClosingSessionEvidence,
    acceptance: AcceptanceResult,
    attestations: tuple[PrimarySourceAttestation, ...],
    *,
    explicitly_authorized: bool = False,
) -> PostCloseResult:
    if not explicitly_authorized:
        return PostCloseResult("NOT_ACTIVATED", None, 0, 0, 0, "AUTHORIZATION_REQUIRED")
    try:
        closing.validate()
    except ValueError:
        return PostCloseResult("STOPPED_FAIL_CLOSED", closing.session_date, 0, 0, 0,
                               "CLOSING_SESSION_INCOMPLETE")
    if acceptance.state != "COMPLETE" or not 1 <= len(acceptance.review_items) <= 5:
        return PostCloseResult("STOPPED_FAIL_CLOSED", closing.session_date, 0, 0, 0,
                               "CANDIDATE_ACCEPTANCE_REQUIRED")
    by_candidate = {item.candidate_id: item for item in acceptance.review_items}
    verified: set[str] = set()
    try:
        for item in attestations:
            item.validate()
            review = by_candidate.get(item.candidate_id)
            if review is None or review.ticker != item.ticker or item.candidate_id in verified:
                raise ValueError("PRIMARY_SOURCE_ATTESTATION_INVALID")
            verified.add(item.candidate_id)
    except ValueError:
        return PostCloseResult("STOPPED_FAIL_CLOSED", closing.session_date,
                               len(acceptance.review_items), 0, 0,
                               "PRIMARY_SOURCE_ATTESTATION_INVALID")
    if verified != set(by_candidate):
        return PostCloseResult("AWAITING_PRIMARY_SOURCES", closing.session_date,
                               len(by_candidate), len(verified), 0,
                               "PRIMARY_SOURCE_REVIEW_INCOMPLETE")
    return PostCloseResult("READY_FOR_GOVERNED_CASE_DRAFT", closing.session_date,
                           len(by_candidate), len(verified), len(verified), None)
