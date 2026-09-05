from __future__ import annotations

from dataclasses import dataclass

OBSERVATION_CADENCE_SECONDS = 60
SESSION_STATES = {"MARKET_CLOSED_WEEKEND", "MARKET_CLOSED_HOLIDAY", "PRE_MARKET", "REGULAR_SESSION",
                  "POST_MARKET", "UNKNOWN"}


@dataclass(frozen=True)
class PublicationDecision:
    publish: bool
    category: str
    scanner_allowed: bool = False
    provider_allowed: bool = False
    repair_allowed: bool = False


def publication_decision(*, previous_semantic_hash: str | None, semantic_hash: str,
                         previous_session: str | None, session: str,
                         previous_freshness: str | None, freshness: str,
                         failure_state: bool = False) -> PublicationDecision:
    if session not in SESSION_STATES or freshness not in {"CURRENT", "STALE", "UNAVAILABLE", "FAILED_CLOSED"}:
        return PublicationDecision(False, "POLICY_INPUT_INVALID")
    if previous_semantic_hash is None:
        return PublicationDecision(True, "INITIAL_AUTHENTIC_STATE")
    if failure_state and previous_semantic_hash != semantic_hash:
        return PublicationDecision(True, "SANITIZED_FAILURE_REPLACEMENT")
    if previous_session != session:
        return PublicationDecision(True, "MARKET_SESSION_TRANSITION")
    if previous_freshness != freshness:
        return PublicationDecision(True, "FRESHNESS_BOUNDARY_CROSSED")
    if previous_semantic_hash != semantic_hash:
        return PublicationDecision(True, "APPROVED_SOURCE_STATE_CHANGED")
    return PublicationDecision(False, "SEMANTIC_INPUT_UNCHANGED")
