from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .multi_asset_projection import AUTHORITY, LANES, build_projection
from .projection_cadence import OBSERVATION_CADENCE_SECONDS, PublicationDecision, publication_decision
from .projection_runtime import ROLLBACK_NAME, ProjectionStore
from .projection_source_registry import SourceContract, content_hash, source_registry, timestamp, validate_envelope

PUBLISHER_LABEL = "com.iios.expansion-wing-projection-publisher"
PUBLISHER_SCHEMA = "iios-governed-projection-publisher-v1"
_CANDIDATE_FIELDS = {"candidate_id", "instrument_id", "asset_lane", "originating_scanner", "discovered_at",
                     "source_cycle_id", "completeness", "missing_fields", "verification_state",
                     "promotion_state", "blocked_reason"}
_LANE_FIELDS = {"state", "freshness", "candidate_count", "research_eligible", "paper_eligible",
                "missing_evidence", "instrument_basis", "session_evidence", "last_trustworthy_timestamp"}
_PROJECTED_LANE_FIELDS = _LANE_FIELDS - {"session_evidence", "last_trustworthy_timestamp"}


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def _combined_hash(receipts: dict[str, dict[str, Any]]) -> str:
    return hashlib.sha256(_canonical({name: receipt["immutable_hash"] for name, receipt in sorted(receipts.items())})).hexdigest()


def _freshness(receipts: dict[str, dict[str, Any]], session: str) -> str:
    required = source_registry()
    if any(name not in receipts for name, contract in required.items() if contract.required):
        return "UNAVAILABLE"
    if session in {"MARKET_CLOSED_WEEKEND", "MARKET_CLOSED_HOLIDAY", "PRE_MARKET"}:
        return "STALE"
    if session == "UNKNOWN":
        return "UNAVAILABLE"
    return "CURRENT" if all(receipts[name]["fresh"] for name, contract in required.items() if contract.required) else "STALE"


def _unavailable_lanes(raw: dict[str, Any] | None, state: str) -> dict[str, dict[str, Any]]:
    raw = raw or {}
    return {name: {"state": state, "freshness": state, "candidate_count": None,
        "research_eligible": False, "paper_eligible": False,
        "missing_evidence": "EVIDENCE_NOT_CURRENT" if state == "STALE" else "LANE_EVIDENCE_UNAVAILABLE",
        "instrument_basis": (raw.get(name) or {}).get("instrument_basis") or
            ("REFERENCE_ONLY" if name == "crypto_reference" else
             "EXPLICIT_PROXY" if name in {"treasury_rates", "bond_proxies", "commodity_proxies", "fx_proxies", "relative_value"}
             else "DIRECT")} for name in sorted(LANES)}


@dataclass(frozen=True)
class EvaluationResult:
    state: str
    decision: str
    changed: bool
    sequence: int | None
    projection_sha256: str | None
    semantic_hash: str | None
    evaluated_at: str | None = None
    source_generated_at: str | None = None
    evidence_effective_at: str | None = None
    market_session_date: str | None = None

    def browser_safe(self) -> dict[str, Any]:
        return {"schema_version": PUBLISHER_SCHEMA, "state": self.state, "decision": self.decision,
                "changed": self.changed, "sequence": self.sequence, "projection_sha256": self.projection_sha256,
                "semantic_hash": self.semantic_hash, "observation_cadence_seconds": OBSERVATION_CADENCE_SECONDS,
                "evaluated_at": self.evaluated_at, "source_generated_at": self.source_generated_at,
                "evidence_effective_at": self.evidence_effective_at,
                "market_session_date": self.market_session_date,
                "provider_requests": 0, "keychain_access": False, "broker_access": False, "ledger_writes": 0,
                "paper_orders": 0, "authority": AUTHORITY.copy()}


@dataclass(frozen=True)
class EvaluationTimes:
    """Separates in-memory validation clocks from the timestamp persisted on publication."""
    observation_time: datetime
    prior_projection_generated_at: datetime | None
    newest_source_generated_at: datetime
    newest_evidence_effective_at: datetime
    comparison_projection_generated_at: datetime
    publication_projection_generated_at: datetime
    freshness_evaluated_at: datetime

    @classmethod
    def resolve(cls, receipts: dict[str, dict[str, Any]], *, observation_time: datetime,
                prior_projection_generated_at: str | None) -> "EvaluationTimes":
        observation = observation_time.astimezone(timezone.utc)
        source = max(receipt["generated_at"] for receipt in receipts.values())
        effective = max(receipt["effective_at"] for receipt in receipts.values())
        prior = timestamp(prior_projection_generated_at) if prior_projection_generated_at is not None else None
        comparison = max(value for value in (observation, source, effective, prior) if value is not None)
        return cls(observation, prior, source, effective, comparison, observation, observation)


class GovernedProjectionPublisher:
    def __init__(self, root: Path, *, contracts: dict[str, SourceContract] | None = None,
                 before_commit: Callable[[], None] | None = None) -> None:
        self.store = ProjectionStore(root)
        self.contracts = contracts or source_registry()
        self.before_commit = before_commit

    def _receipts(self, envelopes: dict[str, Any], now: datetime) -> dict[str, dict[str, Any]]:
        unknown = set(envelopes) - set(self.contracts)
        if unknown:
            raise ValueError("UNREGISTERED_SOURCE_REJECTED")
        receipts: dict[str, dict[str, Any]] = {}
        for name, contract in self.contracts.items():
            if name not in envelopes:
                if contract.required:
                    raise ValueError("REQUIRED_SOURCE_UNAVAILABLE")
                continue
            receipts[name] = validate_envelope(envelopes[name], contract, now=now)
        return receipts

    def _projection(self, receipts: dict[str, dict[str, Any]], *, now: datetime,
                    generated_at: str) -> dict[str, Any]:
        payload = lambda name: receipts[name]["payload"] if name in receipts else None
        authority = payload("authority_locks")
        if authority != AUTHORITY or any(authority.values()):
            raise ValueError("PUBLISHER_AUTHORITY_FAIL_CLOSED")
        paper = payload("paper_fund")
        if (paper.get("nav") != 10_000 or paper.get("cash") != 10_000 or
                any(paper.get(key) != 0 for key in ("positions", "transactions", "orders", "fills"))):
            raise ValueError("PAPER_TRUTH_MISMATCH")
        session_payload = payload("market_session")
        session = session_payload["state"]
        freshness = _freshness(receipts, session)
        radar = payload("radar_cycle")
        lineage = payload("candidate_lineage")
        candidates: list[dict[str, Any]] = []
        conveyor_state = "FAILED_CLOSED" if radar.get("state") == "FAILED_CLOSED" else "UNAVAILABLE"
        if (freshness == "CURRENT" and radar.get("state") in {"AVAILABLE", "AVAILABLE_EMPTY"} and
                radar.get("cycle_complete") is True and isinstance(lineage, dict) and
                lineage.get("state") in {"AVAILABLE", "AVAILABLE_EMPTY"} and
                lineage.get("cycle_id") == radar.get("cycle_id") and
                lineage.get("source_artifact_hash") == radar.get("source_artifact_hash")):
            rows = lineage.get("candidates")
            if not isinstance(rows, list) or len(rows) > 5:
                raise ValueError("CANDIDATE_BOUND_INVALID")
            if any(not isinstance(row, dict) or set(row) != _CANDIDATE_FIELDS for row in rows):
                raise ValueError("CANDIDATE_SCHEMA_INVALID")
            if len({row["candidate_id"] for row in rows}) != len(rows):
                raise ValueError("CANDIDATE_DUPLICATE")
            if any(row["source_cycle_id"] != radar["cycle_id"] for row in rows):
                raise ValueError("CANDIDATE_LINEAGE_INVALID")
            candidates = rows
            conveyor_state = "AVAILABLE" if rows else "AVAILABLE_EMPTY"
        raw_lanes = (payload("lane_evidence") or {}).get("lanes")
        if freshness != "CURRENT":
            lanes = _unavailable_lanes(raw_lanes if isinstance(raw_lanes, dict) else None, "STALE")
        else:
            if (not isinstance(raw_lanes, dict) or set(raw_lanes) != LANES or
                    any(not isinstance(lane, dict) or set(lane) != _LANE_FIELDS for lane in raw_lanes.values())):
                raise ValueError("LANE_EVIDENCE_INVALID")
            lanes = {name: {key: value for key, value in lane.items() if key in _PROJECTED_LANE_FIELDS}
                     for name, lane in raw_lanes.items()}
            lanes = {name: {**lane, "paper_eligible": False} for name, lane in lanes.items()}
        professional = payload("professional_research")
        professional_view = {"state": "UNAVAILABLE", "observation_count": None,
            "primary_verification_state": "UNAVAILABLE", "agreement_state": "UNAVAILABLE",
            "sample_warning": True, "endorsement": False}
        if freshness == "CURRENT" and isinstance(professional, dict):
            professional_view.update({"state": professional["state"],
                "observation_count": professional["observation_count"],
                "primary_verification_state": professional["primary_verification_state"],
                "agreement_state": professional["agreement_state"]})
        sleeves = payload("research_sleeves") or {}
        provider = payload("provider_credit") or {}
        combined = _combined_hash(receipts)
        source_generated = max(receipt["generated_at"] for receipt in receipts.values()).isoformat()
        return build_projection(source_generated_at=source_generated, source_cycle_id=radar.get("cycle_id"),
            projection_generated_at=generated_at, evidence_freshness_state=freshness,
            market_session_state=session, lane_states=lanes,
            candidate_conveyor={"state": conveyor_state, "candidates": candidates},
            professional_observatory=professional_view,
            scoreboard={"state": "UNAVAILABLE", "sample_size": None, "unresolved_observations": None,
                "hit_rate": None, "calibration": None, "return_distribution_state": "UNAVAILABLE",
                "drawdown_distribution_state": "UNAVAILABLE", "sample_warning": True,
                "survivorship_warning": True},
            paper_research_sleeves={"state": sleeves.get("state", "UNAVAILABLE"),
                "sleeve_count": sleeves.get("sleeve_count"), "operational_position_count": 0,
                "authoritative_cash": paper["cash"], "paper_authority": False, "broker_authority": False},
            provider={"state": provider.get("state", "UNAVAILABLE"),
                "confirmed_credits": provider.get("confirmed_credits"),
                "ambiguous_credits": provider.get("ambiguous_credits"),
                "remaining_ceiling": provider.get("remaining_ceiling"), "outbound_requests": 0},
            queue={"state": "UNAVAILABLE", "depth": None}, authoritative_paper_nav=paper["nav"],
            last_trustworthy_hash=combined, enabled=True, validation_clock=now)

    def evaluate(self, envelopes: dict[str, Any], *, now: datetime) -> EvaluationResult:
        if now.tzinfo is None:
            return EvaluationResult("FAILED_CLOSED", "CLOCK_INVALID", False, None, None, None)
        try:
            receipts = self._receipts(envelopes, now)
            existing = manifest = None
            try:
                existing, manifest = self.store.read(now=now)
            except RuntimeError:
                names = {item.name for item in self.store.root.iterdir()} if self.store.root.exists() else set()
                if names != {ROLLBACK_NAME}:
                    raise
            times = EvaluationTimes.resolve(receipts, observation_time=now,
                prior_projection_generated_at=existing["projection_generated_at"] if existing else None)
            proposed_for_compare = self._projection(receipts, now=times.freshness_evaluated_at,
                generated_at=times.comparison_projection_generated_at.isoformat())
            semantic = proposed_for_compare["last_trustworthy_hash"]
            prior_semantic = existing.get("last_trustworthy_hash") if existing else None
            decision: PublicationDecision = publication_decision(previous_semantic_hash=prior_semantic,
                semantic_hash=semantic, previous_session=existing.get("market_session_state") if existing else None,
                session=proposed_for_compare["market_session_state"],
                previous_freshness=existing.get("evidence_freshness_state") if existing else None,
                freshness=proposed_for_compare["evidence_freshness_state"],
                failure_state=proposed_for_compare["candidate_conveyor"]["state"] == "FAILED_CLOSED")
            if not decision.publish:
                return EvaluationResult("UNCHANGED", decision.category, False, manifest["sequence"],
                    manifest["projection_sha256"], semantic, now.isoformat(),
                    times.newest_source_generated_at.isoformat(), times.newest_evidence_effective_at.isoformat(),
                    receipts["market_session"]["payload"]["session_date"])
            projection = self._projection(receipts, now=times.freshness_evaluated_at,
                generated_at=times.publication_projection_generated_at.isoformat())
            if self.before_commit:
                self.before_commit()
            published = self.store.publish(projection, now=now)
            return EvaluationResult("PUBLISHED", decision.category, published.changed, published.sequence,
                published.projection_sha256, semantic, now.isoformat(),
                times.newest_source_generated_at.isoformat(), times.newest_evidence_effective_at.isoformat(),
                receipts["market_session"]["payload"]["session_date"])
        except (ValueError, RuntimeError):
            return EvaluationResult("FAILED_CLOSED", "SANITIZED_SOURCE_REJECTION", False, None, None, None)


def publisher_health(result: EvaluationResult) -> dict[str, Any]:
    return result.browser_safe()


if __name__ == "__main__":
    from .projection_publisher_service import main
    raise SystemExit(main())
