from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any


class Availability(StrEnum):
    AVAILABLE = "AVAILABLE"
    CURRENT = "CURRENT"
    STALE = "STALE"
    INCOMPLETE = "INCOMPLETE"
    UNAVAILABLE = "UNAVAILABLE"
    UNKNOWN = "UNKNOWN"


class Book(StrEnum):
    TACTICAL = "TACTICAL"
    STRATEGIC = "STRATEGIC"
    OBSERVATION_ONLY = "OBSERVATION_ONLY"


class Eligibility(StrEnum):
    ELIGIBLE = "ELIGIBLE"
    INELIGIBLE = "INELIGIBLE"
    OBSERVATION_ONLY = "OBSERVATION_ONLY"
    INCOMPLETE = "INCOMPLETE"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class AuthorityBoundary:
    paper_mode: bool = True
    read_only_projection: bool = True
    credential_access: bool = False
    raw_log_access: bool = False
    ledger_write_authority: bool = False
    trading_controls: bool = False
    broker_connectivity: bool = False
    live_execution_authority: bool = False
    automatic_governance_changes: bool = False


@dataclass
class OpportunityPassport:
    passport_id: str
    instrument: str
    asset_class: str
    observed_at: str
    provenance: list[dict[str, Any]]
    discovery_reason: str
    catalyst: str
    expected_horizon: str
    upside_range_pct: tuple[float, float] | None
    downside_range_pct: tuple[float, float] | None
    invalidation: str
    liquidity: dict[str, Any]
    volatility: dict[str, Any]
    correlation: dict[str, Any]
    evidence_freshness: Availability
    confidence: float
    missing_evidence: list[str]
    applicable_book: Book
    eligibility: Eligibility = Eligibility.INCOMPLETE
    gate_reasons: list[str] = field(default_factory=list)
    asset_details: dict[str, Any] = field(default_factory=dict)
    authority: AuthorityBoundary = field(default_factory=AuthorityBoundary)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
