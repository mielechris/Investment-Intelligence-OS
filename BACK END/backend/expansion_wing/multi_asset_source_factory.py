from __future__ import annotations

import hashlib
import json
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from .multi_product_research import FAMILY_REQUIREMENTS, PRODUCTS

SCHEMA_VERSION = "iios-multi-asset-source-envelope-v1"
CONTROL_VERSION = "iios-provider-source-control-v1"
ENTITLEMENT_VERSION = "iios-provider-entitlement-registry-v1"
TRUTH = {"CURRENT", "DELAYED", "STALE", "INCOMPLETE", "UNAVAILABLE", "FAILED_CLOSED", "PROXY_ONLY",
         "RESEARCH_ONLY_UNPRICEABLE"}
APPROVAL = {"UNAPPROVED", "OWNER_APPROVED", "PROHIBITED"}
FAILURES = {"NONE", "ENTITLEMENT_UNAPPROVED", "REDISTRIBUTION_PROHIBITED", "SCHEMA_INVALID",
            "FUTURE_EVIDENCE", "DUPLICATE_IDENTITY", "PRIVATE_FIELD_REJECTED", "RESPONSE_TOO_LARGE",
            "BUDGET_EXHAUSTED", "PROVIDER_DISABLED", "TIMEOUT", "RIGHTS_REVIEW_REQUIRED",
            "SOURCE_UNAVAILABLE", "EVIDENCE_INCOMPLETE"}
AUTHORITY = {"provider": False, "credential": False, "browser_request": False, "budget_change": False,
             "candidate_promotion": False, "paper_order": False, "broker": False, "ledger_write": False,
             "live_execution": False}
PROVIDERS = ("FINANCIAL_DATASETS", "FMP", "SEC_EDGAR", "ISSUER_OFFICIAL", "KOYFIN_MANUAL",
             "MARKET_VISION", "SANITIZED_IIOS")
MANUAL_PROVIDERS = {"KOYFIN_MANUAL", "MARKET_VISION"}
PRIVATE_KEYS = {"credential", "api_key", "token", "headers", "source_body", "prompt", "model_response",
                "transcript", "private_path", "raw_error"}


def _time(value: str, category: str = "TIMESTAMP_INVALID") -> datetime:
    try: result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError): raise ValueError(category) from None
    if result.tzinfo is None: raise ValueError(category)
    return result.astimezone(timezone.utc)


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=True).encode("ascii")).hexdigest()


@dataclass(frozen=True)
class ProviderEntitlement:
    provider: str; account_tier: str | None; evidence_date: str | None
    internal_use: bool | None; browser_display: bool | None; redistribution: bool | None
    realtime: bool | None; delayed: bool | None; historical: bool | None
    attribution: str | None; retention: str | None; request_cost: int | None
    rate_limit_per_minute: int | None; product_coverage: tuple[str, ...]
    credential_selector: str | None; approval_state: str
    owner_approval_id: str | None = None; owner_approval_time: str | None = None

    def validate(self) -> None:
        if self.provider not in PROVIDERS or self.approval_state not in APPROVAL:
            raise ValueError("ENTITLEMENT_SCHEMA_INVALID")
        if self.evidence_date is not None: _time(self.evidence_date)
        if self.owner_approval_time is not None: _time(self.owner_approval_time)
        if self.approval_state == "OWNER_APPROVED":
            required = (self.account_tier, self.evidence_date, self.internal_use, self.browser_display,
                self.redistribution, self.realtime, self.delayed, self.historical, self.attribution,
                self.retention, self.request_cost, self.rate_limit_per_minute, self.owner_approval_id,
                self.owner_approval_time)
            if any(value is None for value in required) or self.internal_use is not True:
                raise ValueError("ENTITLEMENT_INCOMPLETE")
        if self.provider in MANUAL_PROVIDERS and self.credential_selector is not None:
            raise ValueError("MANUAL_SOURCE_AUTOMATION_PROHIBITED")

    @property
    def permits_request(self) -> bool:
        try: self.validate()
        except ValueError: return False
        return self.approval_state == "OWNER_APPROVED" and self.internal_use is True and self.request_cost is not None


class EntitlementRegistry:
    def __init__(self, records: tuple[ProviderEntitlement, ...]) -> None:
        if {record.provider for record in records} != set(PROVIDERS) or len(records) != len(PROVIDERS):
            raise ValueError("ENTITLEMENT_INVENTORY_INVALID")
        for record in records: record.validate()
        self._records = {record.provider: record for record in records}

    def require(self, provider: str, *, display: bool = False) -> ProviderEntitlement:
        record = self._records.get(provider)
        if record is None or not record.permits_request: raise PermissionError("ENTITLEMENT_UNAPPROVED")
        if display and record.browser_display is not True: raise PermissionError("REDISTRIBUTION_PROHIBITED")
        return record

    def browser_safe(self) -> tuple[dict[str, Any], ...]:
        return tuple({"provider": item.provider, "approval_state": item.approval_state,
            "internal_use": item.internal_use is True, "browser_display": item.browser_display is True,
            "product_count": len(item.product_coverage), "request_cost_known": item.request_cost is not None}
            for item in self._records.values())


@dataclass(frozen=True)
class SourceEnvelope:
    provider: str; instrument_id: str; asset_family: str; venue: str
    observation_time: str; effective_time: str; retrieval_time: str; market_session: str
    price_basis: str; adjustment_basis: str; liquidity_state: str; provenance_hash: str
    license_state: str; credit_cost: int; freshness: str; completeness: str
    proxy_basis: str; failure_category: str; evidence: tuple[tuple[str, Any], ...]

    def validate(self, entitlement: ProviderEntitlement, *, now: datetime, seen: set[str] | None = None) -> None:
        if self.provider != entitlement.provider or not entitlement.permits_request:
            raise PermissionError("ENTITLEMENT_UNAPPROVED")
        if self.asset_family not in FAMILY_REQUIREMENTS or self.freshness not in TRUTH or self.failure_category not in FAILURES:
            raise ValueError("SCHEMA_INVALID")
        observed, effective, retrieved = map(_time, (self.observation_time, self.effective_time, self.retrieval_time))
        if observed > retrieved or effective > retrieved or retrieved > now.astimezone(timezone.utc):
            raise ValueError("FUTURE_EVIDENCE")
        if not self.instrument_id or not self.venue or not self.market_session:
            raise ValueError("SCHEMA_INVALID")
        if not all(isinstance(item, tuple) and len(item) == 2 for item in self.evidence):
            raise ValueError("SCHEMA_INVALID")
        fields = dict(self.evidence)
        if set(fields) & PRIVATE_KEYS or any(isinstance(value, (dict, list, bytes)) for value in fields.values()):
            raise ValueError("PRIVATE_FIELD_REJECTED")
        required = set(FAMILY_REQUIREMENTS[self.asset_family])
        if not required <= set(fields): raise ValueError("EVIDENCE_INCOMPLETE")
        if not all(value is None or isinstance(value, (str, int, float, bool)) for value in fields.values()):
            raise ValueError("SCHEMA_INVALID")
        if not isinstance(self.provenance_hash, str) or len(self.provenance_hash) != 64:
            raise ValueError("SCHEMA_INVALID")
        identity = canonical_hash((self.provider, self.instrument_id, self.effective_time, self.provenance_hash))
        if seen is not None:
            if identity in seen: raise ValueError("DUPLICATE_IDENTITY")
            seen.add(identity)

    def browser_safe(self, entitlement: ProviderEntitlement) -> dict[str, Any]:
        display = entitlement.browser_display is True
        return {"provider": self.provider, "instrument_id": self.instrument_id if display else "WITHHELD_BY_LICENSE",
            "asset_family": self.asset_family, "freshness": self.freshness, "completeness": self.completeness,
            "proxy_basis": self.proxy_basis, "failure_category": self.failure_category,
            "values_displayed": False, "authority": AUTHORITY.copy()}


@dataclass(frozen=True)
class RequestPolicy:
    enabled: bool = False; daily_credits: int = 0; cycle_credits: int = 0
    requests_per_minute: int = 1; timeout_seconds: float = 5.0; retry_limit: int = 0
    response_size_limit: int = 1_000_000

    def validate(self) -> None:
        if self.retry_limit != 0 or not 0 < self.timeout_seconds <= 10 or not 1 <= self.requests_per_minute <= 10:
            raise ValueError("REQUEST_POLICY_INVALID")
        if not 0 <= self.cycle_credits <= self.daily_credits <= 1_000 or not 1 <= self.response_size_limit <= 2_000_000:
            raise ValueError("REQUEST_POLICY_INVALID")


class RequestGovernor:
    def __init__(self, policy: RequestPolicy) -> None:
        policy.validate(); self.policy = policy; self._lock = threading.Lock(); self._inflight: set[str] = set()
        self.used_daily = 0; self.used_cycle = 0

    def authorize(self, provider: str, cost: int, *, browser: bool = False) -> None:
        with self._lock:
            if browser: raise PermissionError("BROWSER_REQUEST_PROHIBITED")
            if not self.policy.enabled: raise PermissionError("PROVIDER_DISABLED")
            if provider in self._inflight: raise RuntimeError("SINGLE_FLIGHT_ACTIVE")
            if cost <= 0 or self.used_daily + cost > self.policy.daily_credits or self.used_cycle + cost > self.policy.cycle_credits:
                raise RuntimeError("BUDGET_EXHAUSTED")
            self._inflight.add(provider); self.used_daily += cost; self.used_cycle += cost

    def finish(self, provider: str) -> None:
        with self._lock: self._inflight.discard(provider)


def professional_evidence(*, source: str, attributed: bool, rights_approved: bool,
                          corroborated: bool, timestamp: str) -> dict[str, Any]:
    if source not in {"KOYFIN", "MARKET_VISION", "JESSE_INTERVIEW", "FINANCIAL_ADVISER",
                      "PUBLIC_MANAGER", "ISSUER", "SEC"}: raise ValueError("SOURCE_UNAVAILABLE")
    _time(timestamp)
    approved = attributed and rights_approved and corroborated
    return {"source": source, "state": "REPORTED" if approved else "RIGHTS_REVIEW_REQUIRED",
        "disclosure_delay": "UNKNOWN", "conflict_state": "REVIEW_REQUIRED",
        "candidate_creation": False, "candidate_promotion": False, "authority": AUTHORITY.copy()}


def product_source_matrix(envelopes: tuple[SourceEnvelope, ...] = ()) -> tuple[dict[str, Any], ...]:
    by_family: dict[str, list[SourceEnvelope]] = {}
    for envelope in envelopes: by_family.setdefault(envelope.asset_family, []).append(envelope)
    result = []
    for product in PRODUCTS:
        sources = by_family.get(product.family, [])
        state = "UNAVAILABLE"
        if sources:
            current = [source for source in sources if source.freshness == "CURRENT" and source.completeness == "COMPLETE"]
            state = "PROXY_ONLY" if product.exposure_classification in {"PROXY", "REFERENCE"} else "PAPER_TEST_READY" if current else "INCOMPLETE"
        if product.family == "OPTION" and not sources: state = "RESEARCH_ONLY_UNPRICEABLE"
        result.append({"product_id": product.product_id, "family": product.family, "source_state": state,
            "source": sources[0].provider if sources else "UNAVAILABLE", "blocker": "NONE" if state == "PAPER_TEST_READY" else state,
            "synthetic_account_base": 10_000, "operational_paper_fund": False})
    return tuple(result)


def modeled_observation(envelope: SourceEnvelope, entitlement: ProviderEntitlement, *, now: datetime,
                        size_hypothesis: str, invalidation: str, holding_period: str) -> dict[str, Any]:
    envelope.validate(entitlement, now=now)
    eligible = envelope.freshness == "CURRENT" and envelope.completeness == "COMPLETE"
    return {"state": "MODELED_OBSERVATION" if eligible else "BLOCKED", "instrument_id": envelope.instrument_id,
        "entry_basis": envelope.price_basis, "spread": dict(envelope.evidence).get("spread_bps"),
        "slippage": dict(envelope.evidence).get("slippage_bps"), "fees": dict(envelope.evidence).get("fees"),
        "size_hypothesis": size_hypothesis, "invalidation": invalidation, "holding_period": holding_period,
        "marks": (), "exit": None, "outcome": None, "excursions": None, "drawdown": None,
        "benchmark": dict(envelope.evidence).get("benchmark"), "sample_size": 0, "calibration": "UNAVAILABLE",
        "operational_paper_fund": False, "authority": AUTHORITY.copy()}


def control_room_projection(registry: EntitlementRegistry, envelopes: tuple[SourceEnvelope, ...] = (),
                            *, now: str) -> dict[str, Any]:
    _time(now); matrix = product_source_matrix(envelopes)
    return {"schema_version": CONTROL_VERSION, "generated_at": now,
        "providers": registry.browser_safe(), "product_sources": matrix,
        "requests": 0, "credits": 0, "last_observation": None,
        "next_scheduled_check": "NOT_SCHEDULED", "activation_state": "NOT_ACTIVATED",
        "rollback_state": "NOT_REQUIRED", "authority": AUTHORITY.copy()}


def rehearsal_scenarios() -> tuple[str, ...]:
    return ("SOURCE_CURRENT", "SOURCE_DELAYED", "SOURCE_UNAVAILABLE", "RIGHTS_FAILURE",
        "CREDIT_EXHAUSTION", "STALE_EVIDENCE", "FUTURE_EVIDENCE", "PROXY_ONLY",
        "OPTIONS_UNPRICEABLE", "BONDS_INCOMPLETE", "PROVIDER_FAILURE", "RECOVERY",
        "ZERO_CANDIDATE", "VALID_CANDIDATE", "CANDIDATE_LINEAGE_FAILURE", "SYNTHETIC_OBSERVATION",
        "NO_OPERATIONAL_PAPER_ACTIVITY")
