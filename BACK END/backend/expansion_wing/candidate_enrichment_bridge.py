from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from .financial_datasets import FDCapability, FDResult, GovernedRecord

SCHEMA_VERSION = "iios-candidate-enrichment-bridge-v1"
SCANNER_ID = "EXISTING_IIOS_519_SYMBOL_SCANNER"
ALLOWED_MISSING_FIELDS = frozenset({"company_profile", "identifiers"})
AUTHORITY = {"provider_activation": False, "continuous_scan": False, "automatic_promotion": False,
    "committee_reliance": False, "judgment_write": False, "pattern_submission": False,
    "paper_order": False, "ledger_write": False, "broker": False, "live_execution": False}


class CompanyFactsProvider(Protocol):
    credits: Any
    def fetch(self, capability: FDCapability, tickers: tuple[str, ...]) -> FDResult: ...


def _time(value: str) -> datetime:
    try: parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError): raise ValueError("CANDIDATE_TIME_INVALID") from None
    if parsed.tzinfo is None: raise ValueError("CANDIDATE_TIME_INVALID")
    return parsed


@dataclass(frozen=True)
class ScannerCandidate:
    candidate_id: str
    ticker: str
    discovered_at: str
    originating_scanner: str
    missing_fields: tuple[str, ...]

    def validate(self) -> None:
        if (not re.fullmatch(r"candidate_[0-9a-f]{16}", self.candidate_id) or
                not re.fullmatch(r"[A-Z][A-Z0-9.-]{0,9}", self.ticker) or
                self.originating_scanner != SCANNER_ID or not self.missing_fields or
                not set(self.missing_fields) <= ALLOWED_MISSING_FIELDS):
            raise ValueError("CANDIDATE_CONTRACT_INVALID")
        _time(self.discovered_at)


@dataclass(frozen=True)
class CandidateEvidence:
    candidate_id: str
    ticker: str
    normalized_hash: str
    provider_timestamp_state: str
    freshness: str
    verification_state: str
    record: GovernedRecord

    def validate(self) -> None:
        self.record.validate()
        if (self.record.ticker != self.ticker or self.record.normalized_content_hash != self.normalized_hash or
                self.provider_timestamp_state != "UNAVAILABLE" or self.freshness != "UNKNOWN" or
                self.verification_state != "PRIMARY_SOURCE_REQUIRED"):
            raise ValueError("EVIDENCE_CONTRACT_INVALID")


@dataclass(frozen=True)
class BridgeResult:
    state: str
    evidence: tuple[CandidateEvidence, ...]
    candidate_count: int
    unique_ticker_count: int
    provider_request_count: int
    cache_hit_count: int
    starting_conservative_credits: int
    ending_conservative_credits: int
    new_conservative_credits: int
    primary_review_queue_count: int
    failure_category: str | None = None

    def browser_safe(self) -> dict[str, Any]:
        value = {"schema_version": SCHEMA_VERSION, "state": self.state,
            "candidate_count": self.candidate_count, "unique_ticker_count": self.unique_ticker_count,
            "provider_request_count": self.provider_request_count, "cache_hit_count": self.cache_hit_count,
            "starting_conservative_credits": self.starting_conservative_credits,
            "ending_conservative_credits": self.ending_conservative_credits,
            "new_conservative_credits": self.new_conservative_credits,
            "primary_review_queue_count": self.primary_review_queue_count,
            "failure_category": self.failure_category, "authority": AUTHORITY.copy()}
        validate_browser_projection(value)
        return value


@dataclass(frozen=True)
class BridgePolicy:
    enabled: bool = False
    max_candidates: int = 5
    max_new_credits: int = 5

    def validate(self) -> None:
        if not 1 <= self.max_candidates <= 5 or not 1 <= self.max_new_credits <= 5:
            raise ValueError("BRIDGE_POLICY_INVALID")


class CandidateEnrichmentBridge:
    def __init__(self, provider: CompanyFactsProvider, policy: BridgePolicy = BridgePolicy()) -> None:
        policy.validate(); self.provider = provider; self.policy = policy

    def run(self, candidates: tuple[ScannerCandidate, ...], *, explicitly_authorized: bool = False) -> BridgeResult:
        starting = int(self.provider.credits.consumed)
        if not self.policy.enabled or not explicitly_authorized:
            return self._result("NOT_ACTIVATED", (), candidates, 0, 0, starting, "AUTHORIZATION_REQUIRED")
        if not candidates or len(candidates) > self.policy.max_candidates:
            return self._result("REJECTED", (), candidates, 0, 0, starting, "CANDIDATE_BATCH_INVALID")
        try:
            for candidate in candidates: candidate.validate()
        except ValueError:
            return self._result("REJECTED", (), candidates, 0, 0, starting, "CANDIDATE_CONTRACT_INVALID")
        evidence_by_ticker: dict[str, GovernedRecord] = {}
        requests = cache_hits = 0
        for ticker in dict.fromkeys(item.ticker for item in candidates):
            if int(self.provider.credits.consumed) - starting >= self.policy.max_new_credits:
                return self._result("STOPPED_FAIL_CLOSED", (), candidates, requests, cache_hits, starting,
                    "CREDIT_LIMIT_REACHED")
            result = self.provider.fetch(FDCapability.COMPANY_FACTS, (ticker,))
            requests += sum(item.request_started for item in result.attempts)
            cache_hits += int(result.cache_hit)
            if result.state != "AVAILABLE" or len(result.records) != 1:
                return self._result("STOPPED_FAIL_CLOSED", (), candidates, requests, cache_hits, starting,
                    result.failure or "PROVIDER_RESULT_INVALID")
            evidence_by_ticker[ticker] = result.records[0]
        evidence = tuple(CandidateEvidence(item.candidate_id, item.ticker,
            evidence_by_ticker[item.ticker].normalized_content_hash, "UNAVAILABLE",
            evidence_by_ticker[item.ticker].freshness, evidence_by_ticker[item.ticker].verification_state,
            evidence_by_ticker[item.ticker]) for item in candidates)
        for item in evidence: item.validate()
        return self._result("READY_FOR_PRIMARY_REVIEW", evidence, candidates, requests, cache_hits, starting, None)

    def _result(self, state: str, evidence: tuple[CandidateEvidence, ...], candidates: tuple[ScannerCandidate, ...],
                requests: int, cache_hits: int, starting: int, failure: str | None) -> BridgeResult:
        ending = int(self.provider.credits.consumed)
        return BridgeResult(state, evidence, len(candidates), len({item.ticker for item in candidates}),
            requests, cache_hits, starting, ending, ending - starting, len(evidence), failure)


def downstream_gate(evidence: CandidateEvidence, *, primary_source_verified: bool,
                    human_approved: bool) -> dict[str, Any]:
    evidence.validate(); ready = primary_source_verified and human_approved
    return {"state": "RESEARCH_REVIEWED" if ready else "BLOCKED_PRIMARY_SOURCE_REVIEW",
        "research_agent_context": ready, "committee_reliance": False, "judgment_foundry": False,
        "pattern_laboratory": False, "paper_order": False, "automatic_action": False,
        "authority": AUTHORITY.copy()}


def validate_browser_projection(value: dict[str, Any]) -> None:
    counts = {"candidate_count", "unique_ticker_count", "provider_request_count", "cache_hit_count",
        "starting_conservative_credits", "ending_conservative_credits", "new_conservative_credits",
        "primary_review_queue_count"}
    expected = {"schema_version", "state", "failure_category", "authority", *counts}
    if set(value) != expected or value.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("BRIDGE_PROJECTION_INVALID")
    if any(not isinstance(value.get(key), int) or isinstance(value.get(key), bool) or value[key] < 0 for key in counts):
        raise ValueError("BRIDGE_PROJECTION_INVALID")
    authority = value.get("authority")
    if authority != AUTHORITY or any(authority.values()):
        raise ValueError("BRIDGE_PROJECTION_INVALID")
