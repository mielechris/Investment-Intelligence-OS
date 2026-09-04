from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Protocol


class Capability(str, Enum):
    COMPANY_PROFILE = "COMPANY_PROFILE"
    FINANCIAL_STATEMENTS = "FINANCIAL_STATEMENTS"
    FUNDAMENTAL_RATIOS = "FUNDAMENTAL_RATIOS"
    HISTORICAL_PRICES = "HISTORICAL_PRICES"
    ANALYST_ESTIMATES = "ANALYST_ESTIMATES"
    EARNINGS_CALENDAR = "EARNINGS_CALENDAR"
    COMPANY_NEWS_METADATA = "COMPANY_NEWS_METADATA"
    FOREX_REFERENCE = "FOREX_REFERENCE"
    CRYPTO_REFERENCE = "CRYPTO_REFERENCE"
    COMMODITY_DATA = "COMMODITY_DATA"


DATUM_KINDS = {"FACT", "ESTIMATE", "OPINION", "PREDICTION", "DERIVED_METRIC", "TECHNICAL_OBSERVATION"}
FRESHNESS_STATES = {"CURRENT", "STALE", "UNKNOWN", "UNAVAILABLE"}
RIGHTS_STATES = {"APPROVED_INTERNAL_USE", "RIGHTS_REVIEW_REQUIRED", "LICENSE_REVIEW_REQUIRED", "PROHIBITED"}
VERIFICATION_STATES = {"UNVERIFIED", "PRIMARY_SOURCE_REQUIRED", "PRIMARY_SOURCE_VERIFIED"}
FAILURES = {"PROVIDER_UNAVAILABLE", "PROVIDER_DISABLED", "CREDENTIAL_UNAVAILABLE", "LICENSE_NOT_APPROVED",
    "INVALID_SCHEMA", "RESPONSE_TOO_LARGE", "TIMEOUT", "RETRY_EXHAUSTED", "RATE_LIMITED",
    "POINT_IN_TIME_INVALID", "CAPABILITY_UNAVAILABLE", "PARTIAL_PROVIDER_OUTAGE"}
AUTHORITY = {"credential_exposure": False, "broker_connectivity": False, "ledger_write": False,
    "paper_order_creation": False, "live_execution": False, "automatic_threshold_changes": False,
    "automatic_weight_changes": False, "judgment_bank_auto_write": False, "provider_activation": False}


def _timestamp(value: str, category: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        raise ValueError(category) from None
    if parsed.tzinfo is None:
        raise ValueError(category)
    return parsed


@dataclass(frozen=True)
class EnrichedDatum:
    symbol: str
    field: str
    value: str | int | float | bool | None
    datum_kind: str
    provider: str
    endpoint_capability: str
    observation_timestamp: str
    provider_publication_timestamp: str | None
    retrieval_timestamp: str
    point_in_time_cutoff: str
    freshness: str
    rights_state: str
    response_hash: str
    verification_state: str

    def validate(self) -> None:
        if not self.symbol or not self.field or not self.provider:
            raise ValueError("DATUM_IDENTITY_REQUIRED")
        if self.datum_kind not in DATUM_KINDS:
            raise ValueError("DATUM_KIND_INVALID")
        if self.endpoint_capability not in {item.value for item in Capability}:
            raise ValueError("CAPABILITY_INVALID")
        if self.freshness not in FRESHNESS_STATES or self.rights_state not in RIGHTS_STATES:
            raise ValueError("GOVERNANCE_STATE_INVALID")
        if self.verification_state not in VERIFICATION_STATES:
            raise ValueError("VERIFICATION_STATE_INVALID")
        observed = _timestamp(self.observation_timestamp, "OBSERVATION_TIME_INVALID")
        retrieved = _timestamp(self.retrieval_timestamp, "RETRIEVAL_TIME_INVALID")
        cutoff = _timestamp(self.point_in_time_cutoff, "POINT_IN_TIME_INVALID")
        if self.provider_publication_timestamp is not None:
            published = _timestamp(self.provider_publication_timestamp, "PUBLICATION_TIME_INVALID")
            if published > cutoff:
                raise ValueError("POINT_IN_TIME_INVALID")
        if observed > retrieved or cutoff > retrieved:
            raise ValueError("POINT_IN_TIME_INVALID")
        if not isinstance(self.value, (str, int, float, bool, type(None))):
            raise ValueError("SCALAR_VALUE_REQUIRED")
        if not isinstance(self.response_hash, str) or len(self.response_hash) != 64:
            raise ValueError("RESPONSE_HASH_INVALID")


@dataclass(frozen=True)
class ProviderResult:
    provider: str
    capability: str
    state: str
    data: tuple[EnrichedDatum, ...] = ()
    failure_category: str | None = None
    request_count: int = 0
    cache_hit: bool = False

    def validate(self) -> None:
        if self.state not in {"CURRENT", "PARTIAL", "UNAVAILABLE"}:
            raise ValueError("PROVIDER_STATE_INVALID")
        if self.failure_category is not None and self.failure_category not in FAILURES:
            raise ValueError("FAILURE_CATEGORY_INVALID")
        for datum in self.data:
            datum.validate()

    def browser_safe(self) -> dict[str, Any]:
        self.validate()
        return {"provider": self.provider, "capability": self.capability, "state": self.state,
            "datum_count": len(self.data), "failure_category": self.failure_category,
            "request_count": self.request_count, "cache_hit": self.cache_hit, "authority": AUTHORITY.copy()}


class MarketEnrichmentProvider(Protocol):
    name: str

    def capabilities(self) -> frozenset[Capability]: ...

    def fetch(self, symbols: tuple[str, ...], capability: Capability, *, point_in_time_cutoff: str) -> ProviderResult: ...


MISSING_FIELD_CAPABILITY = {
    "company_profile": Capability.COMPANY_PROFILE,
    "identifiers": Capability.COMPANY_PROFILE,
    "financial_statements": Capability.FINANCIAL_STATEMENTS,
    "fundamental_ratios": Capability.FUNDAMENTAL_RATIOS,
    "historical_prices": Capability.HISTORICAL_PRICES,
    "analyst_estimates": Capability.ANALYST_ESTIMATES,
    "earnings_calendar": Capability.EARNINGS_CALENDAR,
    "company_news_metadata": Capability.COMPANY_NEWS_METADATA,
    "forex_reference": Capability.FOREX_REFERENCE,
    "crypto_reference": Capability.CRYPTO_REFERENCE,
    "commodity_data": Capability.COMMODITY_DATA,
}


class EnrichmentRouter:
    """Routes scanner-discovered candidates; it never discovers symbols or executes actions."""

    def __init__(self, providers: dict[str, MarketEnrichmentProvider]) -> None:
        self.providers = providers

    def required_capabilities(self, missing_fields: tuple[str, ...]) -> tuple[Capability, ...]:
        try:
            return tuple(dict.fromkeys(MISSING_FIELD_CAPABILITY[field] for field in missing_fields))
        except KeyError:
            raise ValueError("UNKNOWN_ENRICHMENT_FIELD") from None

    def enrich(self, symbols: tuple[str, ...], missing_fields: tuple[str, ...], *, provider_name: str,
               originating_scanner: str, point_in_time_cutoff: str) -> dict[str, Any]:
        if originating_scanner != "EXISTING_IIOS_519_SYMBOL_SCANNER":
            raise PermissionError("SCANNER_OWNERSHIP_REQUIRED")
        if not symbols or len(symbols) > 519 or len(set(symbols)) != len(symbols):
            raise ValueError("SCANNER_CANDIDATE_BATCH_INVALID")
        provider = self.providers.get(provider_name)
        if provider is None:
            return self._packet((), "UNAVAILABLE", "PROVIDER_UNAVAILABLE")
        results = []
        for capability in self.required_capabilities(missing_fields):
            if capability not in provider.capabilities():
                results.append(ProviderResult(provider.name, capability.value, "UNAVAILABLE",
                    failure_category="CAPABILITY_UNAVAILABLE"))
            else:
                results.append(provider.fetch(symbols, capability, point_in_time_cutoff=point_in_time_cutoff))
        state = "PARTIAL" if any(item.state == "UNAVAILABLE" for item in results) else "CURRENT"
        failure = "PARTIAL_PROVIDER_OUTAGE" if state == "PARTIAL" else None
        return self._packet(tuple(results), state, failure)

    @staticmethod
    def _packet(results: tuple[ProviderResult, ...], state: str, failure: str | None) -> dict[str, Any]:
        for result in results:
            result.validate()
        return {"state": state, "failure_category": failure, "results": results,
            "primary_source_verification_required_for_material_claims": True,
            "routes": ("RESEARCH_AGENTS", "PATTERN_LAB", "INVESTMENT_COMMITTEE_EVIDENCE_PACKET"),
            "direct_execution_route": False, "authority": AUTHORITY.copy()}


def canonical_hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    return hashlib.sha256(encoded).hexdigest()


def load_watchlist(path: str | Path) -> tuple[dict[str, Any], ...]:
    root = json.loads(Path(path).read_text(encoding="utf-8"))
    if root.get("schema_version") != "iios-research-watchlist-v1" or root.get("inventory_type") != "RESEARCH_NOT_PORTFOLIO":
        raise ValueError("WATCHLIST_SCHEMA_INVALID")
    entries = root.get("entries")
    if not isinstance(entries, list) or {item.get("symbol") for item in entries} != {"MU", "INTC", "AMD", "NVDA", "MSTR"}:
        raise ValueError("WATCHLIST_MEMBERSHIP_INVALID")
    required = {"symbol", "inclusion_reason", "originating_case_or_hypothesis", "research_status", "sector_theme",
        "added_timestamp", "reviewer", "verification_status", "missing_enrichment_fields",
        "paper_eligibility_status", "automatic_execution_authority"}
    for item in entries:
        if set(item) != required or item["automatic_execution_authority"] is not False:
            raise ValueError("WATCHLIST_AUTHORITY_INVALID")
        _timestamp(item["added_timestamp"], "WATCHLIST_TIME_INVALID")
        if item["paper_eligibility_status"] != "NOT_EVALUATED" or item["verification_status"] != "UNVERIFIED":
            raise ValueError("WATCHLIST_GOVERNANCE_INVALID")
    return tuple(entries)


def load_capability_audit(path: str | Path) -> tuple[dict[str, Any], ...]:
    root = json.loads(Path(path).read_text(encoding="utf-8"))
    required_sources = {"EXISTING_IIOS", "FMP_FREE", "FMP_STARTER", "FMP_PREMIUM", "KOYFIN_PLUS",
        "MARKET_VISION", "SEC_ISSUER_FILINGS", "USDA", "EIA", "EPA", "FEDERAL_RESERVE_FRED"}
    records = root.get("sources")
    if root.get("schema_version") != "iios-provider-capability-audit-v1" or not isinstance(records, list):
        raise ValueError("CAPABILITY_AUDIT_SCHEMA_INVALID")
    if {item.get("source") for item in records} != required_sources:
        raise ValueError("CAPABILITY_AUDIT_SOURCE_SET_INVALID")
    fields = {"source", "structured_api", "autonomous_scanning", "coverage", "historical_depth",
        "update_frequency", "point_in_time", "download_limits", "internal_use", "display_redistribution",
        "estimated_monthly_cost_usd", "gaps_filled", "duplicates", "activation"}
    for item in records:
        if set(item) != fields or item["activation"] not in {"ACTIVE_UNCHANGED", "NOT_ACTIVATED"}:
            raise ValueError("CAPABILITY_AUDIT_RECORD_INVALID")
        if item["source"] != "EXISTING_IIOS" and not any(
                marker in str(item[field]) for field in ("autonomous_scanning", "internal_use", "display_redistribution")
                for marker in ("REVIEW_REQUIRED", "NOT_PERMITTED", "PROHIBITED")):
            raise ValueError("CAPABILITY_RIGHTS_GATE_REQUIRED")
    return tuple(records)


def koyfin_manual_import_contract() -> dict[str, Any]:
    return {"role": "HUMAN_RESEARCH_COCKPIT", "manual_note_import": "DISABLED",
        "manual_csv_import": "DISABLED", "authenticated_automation": False, "scraping": False,
        "polling": False, "cookie_access": False, "autonomous_provider": False,
        "activation_gate": "TRIAL_UTILIZATION_AND_LICENSE_REVIEW_REQUIRED", "authority": AUTHORITY.copy()}
