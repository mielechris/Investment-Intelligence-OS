from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Protocol


SCHEMA_VERSION = "iios-listed-security-evidence-v1"
PROJECTION_VERSION = "iios-listed-security-browser-v1"
PROVIDER_PRIORITY = ("FINANCIAL_DATASETS", "FMP", "SANITIZED_IIOS", "SEC_ISSUER")
LICENSE_STATES = {"LICENSE_REVIEW_REQUIRED", "INTERNAL_USE_APPROVED", "DISPLAY_APPROVED", "PROHIBITED"}
FRESHNESS_STATES = {"CURRENT", "STALE", "UNAVAILABLE"}
SESSION_STATES = {"PREMARKET", "REGULAR", "AFTER_HOURS", "CLOSED", "UNKNOWN"}
PRICE_BASES = {"RAW", "ADJUSTED", "UNAVAILABLE"}
AUTHORITY = {
    "provider": False, "credential": False, "broker": False, "ledger_write": False,
    "paper_order": False, "live_execution": False, "automatic_promotion": False,
}
PRODUCTS = (
    "US_LARGE_CAP_EQUITIES", "US_MID_CAP_EQUITIES", "US_SMALL_CAP_EQUITIES",
    "INTERNATIONAL_EQUITIES", "EMERGING_MARKET_EQUITIES", "SECTOR_THEMATIC_ETFS",
    "BROAD_FACTOR_ETFS", "REITS_LISTED_REAL_ESTATE", "TREASURY_ETFS",
    "PREFERRED_STOCKS_HYBRID_INCOME", "CRYPTO_ETFS_LISTED_PROXIES",
    "CURRENCY_ETFS_FX_PROXIES", "COMMODITY_ETFS_LISTED_PROXIES", "ULTRA_SHORT_LISTED_PRODUCTS",
)
PRODUCT_STATES = {"PAPER_TEST_READY", "DELAYED_DATA", "RESEARCH_ONLY", "PROXY_ONLY", "INCOMPLETE",
                  "UNAVAILABLE", "FAILED_CLOSED"}
_ALLOWED_FIELDS = {
    "schema_version", "provider", "provider_tier", "license_state", "instrument_id", "ticker",
    "exchange", "security_type", "currency", "observation_timestamp", "effective_timestamp", "provider_timestamp",
    "retrieved_at", "freshness_state", "session_state", "price_basis", "adjustment_state",
    "price_available", "volume_available", "liquidity_state", "spread_slippage_state", "source_hash", "credit_cost",
    "primary_source_verification_required", "products", "research_eligible", "paper_eligible",
    "authority",
}


def _time(value: str, category: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        raise ValueError(category) from None
    if parsed.tzinfo is None:
        raise ValueError(category)
    return parsed.astimezone(timezone.utc)


@dataclass(frozen=True)
class LicenseDecision:
    provider: str
    account_tier: str | None
    internal_use: bool | None
    browser_display: bool | None
    redistribution: bool | None
    realtime_entitled: bool | None
    historical_entitled: bool | None
    attribution_required: bool | None
    request_cost_known: bool

    def gate(self) -> str:
        if self.provider not in PROVIDER_PRIORITY:
            return "PROVIDER_NOT_APPROVED"
        if self.account_tier is None:
            return "ACCOUNT_TIER_UNVERIFIED"
        values = (self.internal_use, self.browser_display, self.redistribution,
                  self.realtime_entitled, self.historical_entitled, self.attribution_required)
        if any(value is None for value in values) or not self.request_cost_known:
            return "LICENSE_TERMS_INCOMPLETE"
        if not self.internal_use:
            return "LICENSE_PROHIBITED"
        return "LICENSE_APPROVED"


@dataclass(frozen=True)
class ListedSecurityEvidence:
    schema_version: str
    provider: str
    provider_tier: str
    license_state: str
    instrument_id: str
    ticker: str
    exchange: str
    security_type: str
    currency: str
    observation_timestamp: str
    effective_timestamp: str
    provider_timestamp: str | None
    retrieved_at: str
    freshness_state: str
    session_state: str
    price_basis: str
    adjustment_state: str
    price_available: bool
    volume_available: bool
    liquidity_state: str
    spread_slippage_state: str
    source_hash: str
    credit_cost: int
    primary_source_verification_required: bool
    products: tuple[str, ...]
    research_eligible: bool
    paper_eligible: bool
    authority: dict[str, bool]

    def validate(self) -> None:
        if set(asdict(self)) != _ALLOWED_FIELDS or self.schema_version != SCHEMA_VERSION:
            raise ValueError("EVIDENCE_SCHEMA_INVALID")
        if self.provider not in PROVIDER_PRIORITY or self.license_state not in LICENSE_STATES:
            raise ValueError("EVIDENCE_PROVENANCE_INVALID")
        if self.instrument_id != "NASDAQ:MU" or self.ticker != "MU" or self.exchange != "NASDAQ":
            raise ValueError("INSTRUMENT_IDENTITY_INVALID")
        if self.security_type != "COMMON_STOCK" or self.currency != "USD":
            raise ValueError("INSTRUMENT_CLASS_INVALID")
        observed = _time(self.observation_timestamp, "OBSERVATION_TIMESTAMP_INVALID")
        effective = _time(self.effective_timestamp, "EFFECTIVE_TIMESTAMP_INVALID")
        retrieved = _time(self.retrieved_at, "RETRIEVAL_TIMESTAMP_INVALID")
        if observed > retrieved or effective > retrieved:
            raise ValueError("POINT_IN_TIME_INVALID")
        if self.provider_timestamp is not None:
            published = _time(self.provider_timestamp, "PROVIDER_TIMESTAMP_INVALID")
            if published > retrieved:
                raise ValueError("POINT_IN_TIME_INVALID")
        if self.freshness_state not in FRESHNESS_STATES or self.session_state not in SESSION_STATES:
            raise ValueError("TRUTH_STATE_INVALID")
        if self.price_basis not in PRICE_BASES or self.adjustment_state not in {"ADJUSTED", "UNADJUSTED", "UNKNOWN"}:
            raise ValueError("PRICE_CONTRACT_INVALID")
        if self.liquidity_state not in {"OBSERVED", "UNAVAILABLE"}:
            raise ValueError("LIQUIDITY_CONTRACT_INVALID")
        if self.spread_slippage_state not in {"OBSERVED", "HYPOTHESIS_ONLY", "UNAVAILABLE"}:
            raise ValueError("SPREAD_SLIPPAGE_CONTRACT_INVALID")
        if not re.fullmatch(r"[0-9a-f]{64}", self.source_hash) or not 0 <= self.credit_cost <= 8:
            raise ValueError("SOURCE_ACCOUNTING_INVALID")
        if not self.products or any(product not in PRODUCTS for product in self.products):
            raise ValueError("PRODUCT_CLASSIFICATION_INVALID")
        if (self.license_state != "DISPLAY_APPROVED" and self.research_eligible) or self.paper_eligible:
            raise ValueError("ELIGIBILITY_INVALID")
        if self.primary_source_verification_required is not True or self.authority != AUTHORITY:
            raise ValueError("AUTHORITY_INVALID")

    def browser_safe(self) -> dict[str, Any]:
        self.validate()
        return {
            "schema_version": PROJECTION_VERSION,
            "source_state": "AVAILABLE" if self.license_state == "DISPLAY_APPROVED" else "NOT_ACTIVATED",
            "license_state": self.license_state,
            "instrument_id": self.instrument_id,
            "freshness_state": self.freshness_state,
            "session_state": self.session_state,
            "price_available": self.price_available,
            "volume_available": self.volume_available,
            "liquidity_state": self.liquidity_state,
            "spread_slippage_state": self.spread_slippage_state,
            "product_count": len(self.products),
            "product_readiness": product_classifications(self),
            "research_eligible": self.research_eligible,
            "paper_eligible": False,
            "primary_source_verification_required": True,
            "authority": AUTHORITY.copy(),
        }


class FixtureTransport(Protocol):
    def fetch(self, ticker: str) -> dict[str, Any]: ...


class ListedSecurityAdapter:
    """Fixture-first adapter. Network and credential access are deliberately absent."""

    def __init__(self, transport: FixtureTransport, license_decision: LicenseDecision) -> None:
        self.transport = transport
        self.license_decision = license_decision

    def fetch_mu(self, *, now: datetime) -> ListedSecurityEvidence:
        if self.license_decision.gate() != "LICENSE_APPROVED":
            raise PermissionError(self.license_decision.gate())
        payload = self.transport.fetch("MU")
        return parse_mu_fixture(payload, now=now, license_decision=self.license_decision)


def parse_mu_fixture(payload: dict[str, Any], *, now: datetime,
                     license_decision: LicenseDecision) -> ListedSecurityEvidence:
    allowed = {"ticker", "exchange", "security_type", "currency", "observed_at", "effective_at", "provider_timestamp",
               "session", "price_basis", "adjustment", "price", "volume", "liquidity"}
    required = allowed - {"provider_timestamp", "price", "volume"}
    if not isinstance(payload, dict) or not required <= set(payload) or len(set(payload) - allowed) > 16:
        raise ValueError("PROVIDER_SCHEMA_INVALID")
    if any(isinstance(value, (dict, list)) for value in payload.values()):
        raise ValueError("PROVIDER_SCHEMA_INVALID")
    if payload.get("ticker") != "MU" or payload.get("exchange") != "NASDAQ":
        raise ValueError("INSTRUMENT_IDENTITY_INVALID")
    observed = _time(payload["observed_at"], "OBSERVATION_TIMESTAMP_INVALID")
    age = (now.astimezone(timezone.utc) - observed).total_seconds()
    freshness = "CURRENT" if 0 <= age <= 900 else "STALE" if age > 900 else "UNAVAILABLE"
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    products = ("US_LARGE_CAP_EQUITIES", "SECTOR_THEMATIC_ETFS", "BROAD_FACTOR_ETFS")
    evidence = ListedSecurityEvidence(
        SCHEMA_VERSION, license_decision.provider, license_decision.account_tier or "UNVERIFIED",
        "DISPLAY_APPROVED" if license_decision.browser_display else "INTERNAL_USE_APPROVED",
        "NASDAQ:MU", "MU", "NASDAQ", payload["security_type"], payload["currency"],
        payload["observed_at"], payload["effective_at"], payload.get("provider_timestamp"), now.isoformat(), freshness,
        payload["session"], payload["price_basis"], payload["adjustment"], payload.get("price") is not None,
        payload.get("volume") is not None, payload["liquidity"], "UNAVAILABLE", hashlib.sha256(canonical).hexdigest(),
        1, True, products, bool(license_decision.browser_display and freshness == "CURRENT"), False,
        AUTHORITY.copy(),
    )
    evidence.validate()
    return evidence


def unavailable_projection(reason: str = "ACCOUNT_TIER_UNVERIFIED") -> dict[str, Any]:
    return {"schema_version": PROJECTION_VERSION, "source_state": "NOT_ACTIVATED",
        "license_state": "LICENSE_REVIEW_REQUIRED", "instrument_id": "NASDAQ:MU",
        "freshness_state": "UNAVAILABLE", "session_state": "UNKNOWN", "price_available": False,
        "volume_available": False, "liquidity_state": "UNAVAILABLE", "product_count": 0,
        "spread_slippage_state": "UNAVAILABLE", "product_readiness": product_classifications(None),
        "research_eligible": False, "paper_eligible": False,
        "primary_source_verification_required": True, "failure_category": reason,
        "authority": AUTHORITY.copy()}


def product_classifications(evidence: ListedSecurityEvidence | None) -> dict[str, str]:
    """A common-stock observation cannot activate proxy or unrelated asset-product rooms."""
    values = {product: "UNAVAILABLE" for product in PRODUCTS}
    if evidence is None:
        return values
    direct = {"US_LARGE_CAP_EQUITIES", "SECTOR_THEMATIC_ETFS", "BROAD_FACTOR_ETFS"}
    for product in direct:
        values[product] = ("PAPER_TEST_READY" if evidence.freshness_state == "CURRENT" and
                           evidence.license_state == "DISPLAY_APPROVED" else "DELAYED_DATA" if
                           evidence.freshness_state == "STALE" else "RESEARCH_ONLY")
    for product in ("TREASURY_ETFS", "COMMODITY_ETFS_LISTED_PROXIES", "CURRENCY_ETFS_FX_PROXIES",
                    "CRYPTO_ETFS_LISTED_PROXIES"):
        if product in values:
            values[product] = "PROXY_ONLY"
    return values
