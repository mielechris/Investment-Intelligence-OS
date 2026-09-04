from __future__ import annotations

import hashlib
import ipaddress
import json
import re
import socket
import ssl
import threading
import time
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Protocol
from urllib.parse import quote, urlencode, urlparse

from .keychain_adapter import KeychainAdapter

PROVIDER_ID = "FINANCIAL_DATASETS"
PROVIDER_NAME = "Financial Datasets"
API_ORIGIN = "https://api.financialdatasets.ai"
API_HOST = "api.financialdatasets.ai"
AUTH_HEADER = "X-API-KEY"
KEYCHAIN_SERVICE = "com.iios.expansion-wing.financial-datasets"
KEYCHAIN_ACCOUNT = "financial-datasets-api-key"
FMP_SERVICE = "com.iios.expansion-wing.fmp"
FMP_ACCOUNT = "fmp-api-key"
CREDENTIAL_MIN_BYTES = 16
CREDENTIAL_MAX_BYTES = 256
_PLACEHOLDER_CREDENTIALS = frozenset({b"your_api_key_here", b"test", b"example", b"changeme", b"api-key"})
SCHEMA_VERSION = "iios-financial-datasets-v1"
CAPABILITY_STATES = {"SUPPORTED", "PREMIUM_SUPPORTED", "CONTRACT_ONLY", "UNAVAILABLE", "LICENSE_REVIEW_REQUIRED"}
LICENSE_STATES = {"REVIEWED_INTERNAL_USE", "LICENSE_REVIEW_REQUIRED", "REDISTRIBUTION_PROHIBITED",
    "TERMS_CHANGED", "ACCESS_TERMINATED"}
DATA_CLASSES = {"PRIMARY_SOURCE_FACT", "PROVIDER_NORMALIZED_FACT", "DERIVED_METRIC", "ANALYST_ESTIMATE",
    "COMPANY_GUIDANCE", "NEWS_METADATA", "PRESS_RELEASE_METADATA", "INSIDER_DISCLOSURE",
    "INSTITUTIONAL_HOLDING", "TECHNICAL_OBSERVATION", "UNVERIFIED_PROVIDER_VALUE"}
TERMINAL_STATUS = {"AUTHENTICATION_FAILED", "CREDIT_REJECTED", "LICENSE_REJECTED", "SCHEMA_REJECTED",
    "ENTITLEMENT_FAILED", "REDIRECT_REJECTED", "RESPONSE_TOO_LARGE", "EMPTY_RESPONSE",
    "METRIC_CALLBACK_FAILED", "TLS_FAILED", "DNS_FAILED", "ACCOUNTING_UNCERTAIN"}
FIXED_FAILURES = TERMINAL_STATUS | {"DISABLED", "CREDENTIAL_NOT_PROVISIONED", "CREDENTIAL_INVALID",
    "KEYCHAIN_UNAVAILABLE", "KEY_RECORD_MISSING", "KEY_RECORD_INACCESSIBLE_OR_AMBIGUOUS", "INVALID_KEYCHAIN_QUERY",
    "ENDPOINT_NOT_ALLOWED", "BATCH_LIMIT", "UNKNOWN_ENDPOINT_COST", "BALANCE_UNKNOWN",
    "CREDIT_EXHAUSTED", "RATE_LIMITED", "TIMEOUT", "RETRY_EXHAUSTED", "PROVIDER_UNAVAILABLE",
    "POINT_IN_TIME_REJECTED", "PARTIAL_OUTAGE", "TCP_FAILED", "TLS_TRUST_NOT_CONFIGURED",
    "TLS_TRUST_UNSAFE", "TLS_TRUST_HASH_MISMATCH", "TLS_CERTIFICATE_VERIFICATION_FAILED",
    "TLS_PROTOCOL_FAILED", "TLS_HOSTNAME_FAILED", "TLS_TIMEOUT", "PROXY_CONTEXT_REJECTED"}
TRUST_FAILURES = {"NOT_CONFIGURED": "TLS_TRUST_NOT_CONFIGURED", "BUNDLE_MISSING": "TLS_TRUST_NOT_CONFIGURED",
    "BUNDLE_UNSAFE": "TLS_TRUST_UNSAFE", "BUNDLE_HASH_MISMATCH": "TLS_TRUST_HASH_MISMATCH",
    "BUNDLE_INVALID": "TLS_TRUST_UNSAFE", "TLS_VERIFICATION_FAILED": "TLS_CERTIFICATE_VERIFICATION_FAILED",
    "CONTEXT_RESTRICTED": "PROXY_CONTEXT_REJECTED"}
AUTHORITY = {"broker": False, "order": False, "position": False, "fill": False, "ledger_write": False,
    "paper_position_proposal": False, "threshold_change": False, "credential_management": False,
    "service_control": False, "deployment": False, "live_execution": False, "provider_activation": False}


class FDCapability(str, Enum):
    COMPANY_FACTS = "COMPANY_FACTS"
    INCOME_STATEMENTS = "INCOME_STATEMENTS"
    BALANCE_SHEETS = "BALANCE_SHEETS"
    CASH_FLOW_STATEMENTS = "CASH_FLOW_STATEMENTS"
    COMBINED_FINANCIAL_STATEMENTS = "COMBINED_FINANCIAL_STATEMENTS"
    FINANCIAL_METRICS = "FINANCIAL_METRICS"
    HISTORICAL_STOCK_PRICES = "HISTORICAL_STOCK_PRICES"
    REAL_TIME_PRICE_SNAPSHOT = "REAL_TIME_PRICE_SNAPSHOT"
    SEC_FILING_METADATA = "SEC_FILING_METADATA"
    SEC_FILING_ITEM_METADATA = "SEC_FILING_ITEM_METADATA"
    EARNINGS = "EARNINGS"
    PRESS_RELEASE_METADATA = "PRESS_RELEASE_METADATA"
    COMPANY_NEWS_METADATA = "COMPANY_NEWS_METADATA"
    INSIDER_TRANSACTIONS = "INSIDER_TRANSACTIONS"
    INSTITUTIONAL_OWNERSHIP = "INSTITUTIONAL_OWNERSHIP"
    SEGMENTED_FINANCIAL_STATEMENTS = "SEGMENTED_FINANCIAL_STATEMENTS"
    OPERATING_KPIS = "OPERATING_KPIS"
    FORWARD_GUIDANCE = "FORWARD_GUIDANCE"
    NON_GAAP_METRICS = "NON_GAAP_METRICS"
    CENTRAL_BANK_INTEREST_RATES = "CENTRAL_BANK_INTEREST_RATES"


@dataclass(frozen=True)
class EndpointSpec:
    capability: FDCapability
    state: str
    path: str | None
    credit_class: str | None
    data_classification: str
    required_fields: frozenset[str]
    allowed_fields: frozenset[str]
    maximum_freshness_seconds: int

    @property
    def credit_cost(self) -> int | None:
        return {"STANDARD": 1, "PREMIUM": 8}.get(self.credit_class or "")


def _spec(capability: FDCapability, state: str, path: str | None, credit: str | None, classification: str,
          required: tuple[str, ...], allowed: tuple[str, ...], freshness: int = 86_400) -> EndpointSpec:
    return EndpointSpec(capability, state, path, credit, classification, frozenset(required),
        frozenset(allowed), freshness)


ENDPOINTS = {
    FDCapability.COMPANY_FACTS: _spec(FDCapability.COMPANY_FACTS, "SUPPORTED", "/company/facts", "STANDARD",
        "PROVIDER_NORMALIZED_FACT", ("ticker", "name", "updated_at"),
        ("ticker", "name", "cik", "industry", "sector", "market_cap", "updated_at")),
    FDCapability.INCOME_STATEMENTS: _spec(FDCapability.INCOME_STATEMENTS, "SUPPORTED", "/financials/income-statements/", "STANDARD",
        "PROVIDER_NORMALIZED_FACT", ("ticker", "report_period", "filing_date"),
        ("ticker", "report_period", "filing_date", "revenue", "net_income")),
    FDCapability.BALANCE_SHEETS: _spec(FDCapability.BALANCE_SHEETS, "SUPPORTED", "/financials/balance-sheets/", "STANDARD",
        "PROVIDER_NORMALIZED_FACT", ("ticker", "report_period", "filing_date"),
        ("ticker", "report_period", "filing_date", "total_assets", "total_debt")),
    FDCapability.CASH_FLOW_STATEMENTS: _spec(FDCapability.CASH_FLOW_STATEMENTS, "SUPPORTED", "/financials/cash-flow-statements/", "STANDARD",
        "PROVIDER_NORMALIZED_FACT", ("ticker", "report_period", "filing_date"),
        ("ticker", "report_period", "filing_date", "operating_cash_flow", "capital_expenditure")),
    FDCapability.COMBINED_FINANCIAL_STATEMENTS: _spec(FDCapability.COMBINED_FINANCIAL_STATEMENTS, "SUPPORTED", "/financials/", "STANDARD",
        "PROVIDER_NORMALIZED_FACT", ("ticker", "report_period", "filing_date"),
        ("ticker", "report_period", "filing_date", "income_statement", "balance_sheet", "cash_flow_statement")),
    FDCapability.FINANCIAL_METRICS: _spec(FDCapability.FINANCIAL_METRICS, "SUPPORTED", "/financial-metrics/", "STANDARD",
        "DERIVED_METRIC", ("ticker", "report_period", "updated_at"),
        ("ticker", "report_period", "updated_at", "price_to_earnings", "return_on_equity")),
    FDCapability.HISTORICAL_STOCK_PRICES: _spec(FDCapability.HISTORICAL_STOCK_PRICES, "SUPPORTED", "/prices/", "STANDARD",
        "TECHNICAL_OBSERVATION", ("ticker", "time", "close"), ("ticker", "time", "open", "high", "low", "close", "volume"), 900),
    FDCapability.REAL_TIME_PRICE_SNAPSHOT: _spec(FDCapability.REAL_TIME_PRICE_SNAPSHOT, "SUPPORTED", "/prices/snapshot/", "STANDARD",
        "TECHNICAL_OBSERVATION", ("ticker", "time", "price"), ("ticker", "time", "price"), 120),
    FDCapability.SEC_FILING_METADATA: _spec(FDCapability.SEC_FILING_METADATA, "SUPPORTED", "/filings/", "STANDARD",
        "PRIMARY_SOURCE_FACT", ("ticker", "filing_date", "accession_number"),
        ("ticker", "filing_date", "report_period", "filing_type", "accession_number", "source_url")),
    FDCapability.SEC_FILING_ITEM_METADATA: _spec(FDCapability.SEC_FILING_ITEM_METADATA, "CONTRACT_ONLY", None, None,
        "PRIMARY_SOURCE_FACT", (), ()),
    FDCapability.EARNINGS: _spec(FDCapability.EARNINGS, "SUPPORTED", "/earnings/", "STANDARD", "ANALYST_ESTIMATE",
        ("ticker", "report_period", "updated_at"), ("ticker", "report_period", "updated_at", "eps_estimate", "eps_actual")),
    FDCapability.PRESS_RELEASE_METADATA: _spec(FDCapability.PRESS_RELEASE_METADATA, "LICENSE_REVIEW_REQUIRED", None, None,
        "PRESS_RELEASE_METADATA", (), ()),
    FDCapability.COMPANY_NEWS_METADATA: _spec(FDCapability.COMPANY_NEWS_METADATA, "LICENSE_REVIEW_REQUIRED", None, None,
        "NEWS_METADATA", (), ()),
    FDCapability.INSIDER_TRANSACTIONS: _spec(FDCapability.INSIDER_TRANSACTIONS, "LICENSE_REVIEW_REQUIRED", None, None,
        "INSIDER_DISCLOSURE", (), ()),
    FDCapability.INSTITUTIONAL_OWNERSHIP: _spec(FDCapability.INSTITUTIONAL_OWNERSHIP, "LICENSE_REVIEW_REQUIRED", None, None,
        "INSTITUTIONAL_HOLDING", (), ()),
    FDCapability.SEGMENTED_FINANCIAL_STATEMENTS: _spec(FDCapability.SEGMENTED_FINANCIAL_STATEMENTS, "PREMIUM_SUPPORTED", "/financials/segmented/", "PREMIUM",
        "PROVIDER_NORMALIZED_FACT", ("ticker", "report_period", "updated_at"), ("ticker", "report_period", "updated_at", "segments")),
    FDCapability.OPERATING_KPIS: _spec(FDCapability.OPERATING_KPIS, "PREMIUM_SUPPORTED", "/company/kpis/", "PREMIUM",
        "UNVERIFIED_PROVIDER_VALUE", ("ticker", "report_period", "updated_at"), ("ticker", "report_period", "updated_at", "kpis")),
    FDCapability.FORWARD_GUIDANCE: _spec(FDCapability.FORWARD_GUIDANCE, "PREMIUM_SUPPORTED", "/company/guidance/", "PREMIUM",
        "COMPANY_GUIDANCE", ("ticker", "published_at"), ("ticker", "published_at", "guidance")),
    FDCapability.NON_GAAP_METRICS: _spec(FDCapability.NON_GAAP_METRICS, "PREMIUM_SUPPORTED", "/financials/non-gaap/", "PREMIUM",
        "UNVERIFIED_PROVIDER_VALUE", ("ticker", "report_period", "updated_at"), ("ticker", "report_period", "updated_at", "metrics")),
    FDCapability.CENTRAL_BANK_INTEREST_RATES: _spec(FDCapability.CENTRAL_BANK_INTEREST_RATES, "CONTRACT_ONLY", None, None,
        "PRIMARY_SOURCE_FACT", (), ()),
}


def validate_origin(url: str, *, expected_path: str | None = None) -> str:
    parsed = urlparse(url)
    try: ipaddress.ip_address(parsed.hostname or "")
    except ValueError: pass
    else: raise ValueError("ENDPOINT_NOT_ALLOWED")
    path = parsed.path
    segments = path.split("/")
    if (parsed.scheme != "https" or parsed.hostname != API_HOST or parsed.port not in (None, 443) or
            parsed.username or parsed.password or parsed.query or parsed.fragment or "%" in path or
            "//" in path or any(segment in {".", ".."} for segment in segments) or
            (expected_path is not None and path != expected_path)):
        raise ValueError("ENDPOINT_NOT_ALLOWED")
    return path


def canonical_request_target(capability: FDCapability, ticker: str) -> str:
    spec = ENDPOINTS.get(capability)
    if (not spec or not spec.path or not re.fullmatch(r"[A-Z][A-Z0-9.-]{0,9}", ticker)):
        raise ValueError("ENDPOINT_NOT_ALLOWED")
    validate_origin(f"{API_ORIGIN}{spec.path}", expected_path=spec.path)
    query = urlencode((("ticker", ticker),), quote_via=quote, safe="")
    return f"{API_ORIGIN}{spec.path}?{query}"


class CredentialProvider(Protocol):
    def retrieve(self) -> bytes: ...


class SecurityFrameworkCredentialProvider:
    def __init__(self, adapter: KeychainAdapter) -> None:
        if adapter.service != KEYCHAIN_SERVICE.encode("ascii"):
            raise ValueError("FINANCIAL_DATASETS_SELECTOR_REQUIRED")
        self.adapter = adapter

    def retrieve(self) -> bytes:
        try:
            value = self.adapter.retrieve_opaque(KEYCHAIN_ACCOUNT, minimum_bytes=CREDENTIAL_MIN_BYTES,
                maximum_bytes=CREDENTIAL_MAX_BYTES)
        except RuntimeError as exc:
            category = str(exc)
            if category in {"KEY_RECORD_MISSING", "KEY_RECORD_INACCESSIBLE_OR_AMBIGUOUS", "INVALID_KEYCHAIN_QUERY"}:
                raise RuntimeError(category) from None
            raise RuntimeError("KEYCHAIN_UNAVAILABLE") from None
        return validate_credential(value)


def validate_credential(value: bytes | str) -> bytes:
    if isinstance(value, str):
        try: encoded = value.encode("ascii", errors="strict")
        except UnicodeEncodeError: raise RuntimeError("CREDENTIAL_INVALID") from None
    elif isinstance(value, bytes): encoded = value
    else: raise RuntimeError("CREDENTIAL_INVALID")
    if (not CREDENTIAL_MIN_BYTES <= len(encoded) <= CREDENTIAL_MAX_BYTES or
            any(byte < 0x21 or byte > 0x7E for byte in encoded) or
            encoded.lower() in _PLACEHOLDER_CREDENTIALS):
        raise RuntimeError("CREDENTIAL_INVALID")
    return encoded


@dataclass(frozen=True)
class FDPolicy:
    enabled: bool = False
    license_state: str = "REVIEWED_INTERNAL_USE"
    provider_balance: int | None = None
    total_ceiling: int = 1_000
    daily_ceiling: int = 100
    monthly_ceiling: int = 1_000
    requests_per_minute: int = 10
    batch_limit: int = 50
    timeout_seconds: float = 5.0
    response_timeout_seconds: float = 10.0
    response_size_limit: int = 2_000_000
    redirect_limit: int = 1
    retry_limit: int = 0
    cache_seconds: int = 300
    auto_reload: bool = False

    def validate(self) -> None:
        if self.license_state not in LICENSE_STATES: raise ValueError("LICENSE_STATE_INVALID")
        if self.auto_reload: raise ValueError("AUTO_RELOAD_PROHIBITED")
        if (self.total_ceiling <= 0 or self.total_ceiling > 1_000 or self.daily_ceiling <= 0 or
                self.monthly_ceiling <= 0 or self.daily_ceiling > self.total_ceiling or
                self.monthly_ceiling > self.total_ceiling or not 1 <= self.requests_per_minute <= 10 or
                not 1 <= self.batch_limit <= 50 or not 0 < self.timeout_seconds <= 10 or
                not 0 < self.response_timeout_seconds <= 20 or not 0 < self.response_size_limit <= 2_000_000 or
                not 0 <= self.redirect_limit <= 1 or self.retry_limit != 0 or not 1 <= self.cache_seconds <= 300):
            raise ValueError("POLICY_INVALID")


class CreditLedger:
    def __init__(self, policy: FDPolicy, *, prior_ambiguous_credits: int = 0) -> None:
        policy.validate()
        if not 0 <= prior_ambiguous_credits <= policy.total_ceiling: raise ValueError("ACCOUNTING_INVALID")
        self.policy = policy; self._lock = threading.Lock(); self.confirmed_consumed = 0
        self.ambiguous_reserved = prior_ambiguous_credits; self._pending: dict[int, int] = {}; self._sequence = 0
        self.daily = 0; self.monthly = 0

    @property
    def consumed(self) -> int:
        return self.confirmed_consumed + self.ambiguous_reserved + sum(self._pending.values())

    def reserve(self, cost: int | None) -> tuple[int, dict[str, int]]:
        with self._lock:
            if cost not in {1, 8}: raise RuntimeError("UNKNOWN_ENDPOINT_COST")
            if self.policy.provider_balance is None: raise RuntimeError("BALANCE_UNKNOWN")
            remaining = min(self.policy.provider_balance, self.policy.total_ceiling) - self.consumed
            if cost > remaining or self.daily + cost > self.policy.daily_ceiling or self.monthly + cost > self.policy.monthly_ceiling:
                raise RuntimeError("CREDIT_EXHAUSTED")
            self._sequence += 1; token = self._sequence; self._pending[token] = cost
            self.daily += cost; self.monthly += cost
            return token, self.snapshot()

    def release_before_transport(self, token: int) -> dict[str, int]:
        with self._lock:
            cost = self._pending.pop(token); self.daily -= cost; self.monthly -= cost
            return self.snapshot()

    def confirm_response(self, token: int) -> dict[str, int]:
        with self._lock:
            self.confirmed_consumed += self._pending.pop(token)
            return self.snapshot()

    def mark_ambiguous(self, token: int) -> dict[str, int]:
        with self._lock:
            self.ambiguous_reserved += self._pending.pop(token)
            return self.snapshot()

    def snapshot(self) -> dict[str, int]:
        used = self.confirmed_consumed + self.ambiguous_reserved + sum(self._pending.values())
        return {"consumed": used, "confirmed": self.confirmed_consumed, "ambiguous": self.ambiguous_reserved,
            "remaining": min(self.policy.provider_balance or 0, self.policy.total_ceiling) - used}

    def authorize_attempt(self, cost: int | None) -> dict[str, int]:
        token, _ = self.reserve(cost)
        return self.confirm_response(token)


@dataclass(frozen=True)
class FDResponse:
    status: int
    final_url: str
    redirects: tuple[str, ...]
    body: bytes
    latency_ms: float | None = None


@dataclass(frozen=True)
class AttemptRecord:
    provider_id: str; capability: str; canonical_endpoint_id: str; symbol: str
    projected_credit_cost: int; attempt_sequence_number: int; request_started: bool
    response_observed: bool; terminal_status_category: str; latency_ms: float | None
    response_size_bytes: int | None; cache_state: str; retry_count: int; accounting_state: str
    lifecycle_state: str

    def sanitized(self) -> dict[str, Any]: return asdict(self)


Transport = Callable[[str, dict[str, bytes], tuple[str, ...], float, float], FDResponse]


@dataclass(frozen=True)
class GovernedRecord:
    provider_id: str; capability: str; ticker: str; requested_at: str
    provider_publication_timestamp: str | None; filing_report_period: str | None
    source_accession_or_url: str | None; freshness: str; normalized_content_hash: str
    schema_version: str; data_classification: str; verification_state: str
    credit_cost: int; cache_state: str; fields: tuple[tuple[str, Any], ...]

    def validate(self) -> None:
        if (self.provider_id != PROVIDER_ID or self.capability not in {x.value for x in FDCapability} or
                self.data_classification not in DATA_CLASSES or self.verification_state not in {
                    "PRIMARY_SOURCE_REQUIRED", "PRIMARY_SOURCE_VERIFIED"}):
            raise ValueError("PROVENANCE_INVALID")
        requested = _time(self.requested_at)
        if self.provider_publication_timestamp:
            if _time(self.provider_publication_timestamp) > requested: raise ValueError("POINT_IN_TIME_REJECTED")
        if not re.fullmatch(r"[0-9a-f]{64}", self.normalized_content_hash): raise ValueError("HASH_INVALID")


@dataclass(frozen=True)
class FDResult:
    state: str; capability: str; records: tuple[GovernedRecord, ...] = (); failure: str | None = None
    projected_credit_cost: int = 0; consumed_credits: int = 0; remaining_credits: int | None = None
    cache_hit: bool = False; request_timestamp: str | None = None; response_status_category: str = "NOT_REQUESTED"
    ignored_field_count: int = 0
    attempts: tuple[AttemptRecord, ...] = ()

    def safe_accounting(self) -> dict[str, Any]:
        return {"provider_state": self.state, "capability_requested": self.capability,
            "credit_classification": "PREMIUM" if self.projected_credit_cost == 8 else "STANDARD",
            "projected_credit_cost": self.projected_credit_cost, "consumed_credit_count": self.consumed_credits,
            "remaining_authorized_credit_count": self.remaining_credits, "cache_hit": self.cache_hit,
            "request_timestamp": self.request_timestamp, "response_status_category": self.response_status_category,
            "failure_category": self.failure, "attempts": tuple(item.sanitized() for item in self.attempts),
            "authority": AUTHORITY.copy()}


def _time(value: str) -> datetime:
    try: parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError): raise ValueError("TIME_INVALID") from None
    if parsed.tzinfo is None: raise ValueError("TIME_INVALID")
    return parsed


class FinancialDatasetsAdapter:
    name = PROVIDER_ID

    def __init__(self, policy: FDPolicy = FDPolicy(), *, credentials: CredentialProvider | None = None,
                 transport: Transport | None = None, clock: Callable[[], float] = time.monotonic,
                 utcnow: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
                 prior_ambiguous_credits: int = 0,
                 metric_recorder: Callable[[AttemptRecord], None] | None = None) -> None:
        policy.validate(); self.policy = policy; self.credentials = credentials; self.transport = transport
        self.clock = clock; self.utcnow = utcnow
        self.credits = CreditLedger(policy, prior_ambiguous_credits=prior_ambiguous_credits)
        self.metric_recorder = metric_recorder; self.attempt_records: list[AttemptRecord] = []
        self._cache: dict[tuple[str, tuple[str, ...]], tuple[float, FDResult]] = {}
        self._condition = threading.Condition(); self._inflight: set[tuple[str, tuple[str, ...]]] = set()
        self._request_times: list[float] = []; self.transport_calls = 0

    def capabilities(self) -> dict[str, str]: return {key.value: value.state for key, value in ENDPOINTS.items()}

    def fetch(self, capability: FDCapability, tickers: tuple[str, ...]) -> FDResult:
        spec = ENDPOINTS.get(capability)
        cost = spec.credit_cost if spec else None
        if not self.policy.enabled: return self._fail(capability, "DISABLED", cost)
        if self.policy.license_state != "REVIEWED_INTERNAL_USE": return self._fail(capability, "LICENSE_REJECTED", cost)
        if not spec or spec.path is None: return self._fail(capability, "ENDPOINT_NOT_ALLOWED", cost)
        if cost is None: return self._fail(capability, "UNKNOWN_ENDPOINT_COST", cost)
        if (not tickers or len(tickers) > self.policy.batch_limit or len(set(tickers)) != len(tickers) or
                any(not re.fullmatch(r"[A-Z][A-Z0-9.-]{0,9}", ticker) for ticker in tickers)):
            return self._fail(capability, "BATCH_LIMIT", cost)
        if self.policy.provider_balance is None: return self._fail(capability, "BALANCE_UNKNOWN", cost)
        key = (capability.value, tickers)
        with self._condition:
            cached = self._cache.get(key)
            if cached and self.clock() - cached[0] <= self.policy.cache_seconds:
                prior = cached[1]
                attempt = self._cache_attempt(capability, tickers, "HIT")
                return FDResult(prior.state, prior.capability, prior.records, projected_credit_cost=cost,
                    consumed_credits=self.credits.consumed, remaining_credits=self._remaining(), cache_hit=True,
                    request_timestamp=prior.request_timestamp, response_status_category="CACHE_HIT",
                    ignored_field_count=prior.ignored_field_count, attempts=(attempt,))
            while key in self._inflight:
                self._condition.wait(timeout=self.policy.response_timeout_seconds)
                cached = self._cache.get(key)
                if cached:
                    prior = cached[1]
                    attempt = self._cache_attempt(capability, tickers, "SINGLE_FLIGHT")
                    return FDResult(prior.state, prior.capability, prior.records, projected_credit_cost=cost,
                        consumed_credits=self.credits.consumed, remaining_credits=self._remaining(), cache_hit=True,
                        request_timestamp=prior.request_timestamp, response_status_category="SINGLE_FLIGHT_CACHE",
                        ignored_field_count=prior.ignored_field_count, attempts=(attempt,))
                if key in self._inflight: return self._fail(capability, "TIMEOUT", cost)
            self._inflight.add(key)
        try:
            result = self._request(spec, tickers)
            if result.state == "AVAILABLE":
                with self._condition: self._cache[key] = (self.clock(), result)
            return result
        finally:
            with self._condition: self._inflight.discard(key); self._condition.notify_all()

    def _request(self, spec: EndpointSpec, tickers: tuple[str, ...]) -> FDResult:
        readiness = getattr(self.transport, "trust_readiness", None)
        if callable(readiness):
            try: trust_state = readiness()
            except Exception: return self._fail(spec.capability, "TLS_TRUST_UNSAFE", spec.credit_cost)
            if trust_state != "READY":
                return self._fail(spec.capability, TRUST_FAILURES.get(trust_state, "TLS_TRUST_UNSAFE"), spec.credit_cost)
        now = self.clock(); self._request_times = [value for value in self._request_times if now - value < 60]
        if len(self._request_times) >= self.policy.requests_per_minute: return self._fail(spec.capability, "RATE_LIMITED", spec.credit_cost)
        try: token, accounting = self.credits.reserve(spec.credit_cost)
        except RuntimeError as exc: return self._fail(spec.capability, str(exc), spec.credit_cost)
        requested_at = self.utcnow().isoformat(); symbol = "|".join(tickers)
        attempt = AttemptRecord(PROVIDER_ID, spec.capability.value, spec.capability.value, symbol,
            spec.credit_cost or 0, token, False, False, "PENDING", None, None, "MISS", 0, "RESERVED", "AUTHORIZED")
        try:
            if self.credentials is None or self.transport is None: raise RuntimeError("CREDENTIAL_NOT_PROVISIONED")
            secret = validate_credential(self.credentials.retrieve())
            url = f"{API_ORIGIN}{spec.path}"; validate_origin(url, expected_path=spec.path)
        except RuntimeError as exc:
            accounting = self.credits.release_before_transport(token)
            category = str(exc) if str(exc) in FIXED_FAILURES else "KEYCHAIN_UNAVAILABLE"
            attempt = replace(attempt, terminal_status_category=category,
                accounting_state="RELEASED_BEFORE_TRANSPORT", lifecycle_state="TRANSPORT_FAILED")
            return self._with_attempt(self._fail(spec.capability, category, spec.credit_cost, accounting, requested_at), attempt)
        except Exception:
            accounting = self.credits.release_before_transport(token)
            attempt = replace(attempt, terminal_status_category="PROVIDER_UNAVAILABLE",
                accounting_state="RELEASED_BEFORE_TRANSPORT", lifecycle_state="TRANSPORT_FAILED")
            return self._with_attempt(self._fail(spec.capability, "PROVIDER_UNAVAILABLE", spec.credit_cost, accounting, requested_at), attempt)
        started = self.clock(); self._request_times.append(started); self.transport_calls += 1
        attempt = replace(attempt, request_started=True, lifecycle_state="REQUEST_STARTING")
        try:
            response = self.transport(url, {AUTH_HEADER: secret}, tickers,
                self.policy.timeout_seconds, self.policy.response_timeout_seconds)
        except Exception as exc:
            transport_category = getattr(exc, "category", None)
            if transport_category in FIXED_FAILURES:
                if not getattr(exc, "request_started", True):
                    accounting = self.credits.release_before_transport(token)
                    complete = replace(attempt, request_started=False, terminal_status_category=transport_category,
                        accounting_state="RELEASED_BEFORE_TRANSPORT", lifecycle_state="TRANSPORT_FAILED")
                    return self._with_attempt(self._fail(spec.capability, transport_category, spec.credit_cost,
                        accounting, requested_at), complete)
                lifecycle = {"DNS_FAILED": "DNS_FAILED", "TLS_TIMEOUT": "TIMEOUT",
                    "TLS_CERTIFICATE_VERIFICATION_FAILED": "TLS_FAILED", "TLS_HOSTNAME_FAILED": "TLS_FAILED",
                    "TLS_PROTOCOL_FAILED": "TLS_FAILED"}.get(transport_category, "TRANSPORT_FAILED")
                return self._ambiguous_failure(spec, attempt, token, requested_at,
                    transport_category, lifecycle, started)
            if isinstance(exc, TimeoutError):
                return self._ambiguous_failure(spec, attempt, token, requested_at, "TIMEOUT", "TIMEOUT", started)
            if isinstance(exc, socket.gaierror):
                return self._ambiguous_failure(spec, attempt, token, requested_at, "DNS_FAILED", "DNS_FAILED", started)
            if isinstance(exc, ssl.SSLError):
                return self._ambiguous_failure(spec, attempt, token, requested_at, "TLS_FAILED", "TLS_FAILED", started)
            return self._ambiguous_failure(spec, attempt, token, requested_at,
                "ACCOUNTING_UNCERTAIN", "TRANSPORT_FAILED", started)
        if not isinstance(response, FDResponse):
            return self._ambiguous_failure(spec, attempt, token, requested_at,
                "ACCOUNTING_UNCERTAIN", "TRANSPORT_FAILED", started)
        accounting = self.credits.confirm_response(token)
        latency = response.latency_ms if response.latency_ms is not None else max(0.0, (self.clock() - started) * 1000)
        size = len(response.body) if isinstance(response.body, bytes) else None
        attempt = replace(attempt, response_observed=True, latency_ms=latency, response_size_bytes=size,
            accounting_state="CONFIRMED_CONSUMED", lifecycle_state="RESPONSE_OBSERVED")
        if not isinstance(response.body, bytes) or not response.body:
            return self._terminal_response(spec, attempt, requested_at, accounting, "EMPTY_RESPONSE")
        if len(response.body) > self.policy.response_size_limit:
            return self._terminal_response(spec, attempt, requested_at, accounting, "RESPONSE_TOO_LARGE")
        try:
            if response.redirects or validate_origin(response.final_url, expected_path=spec.path) != spec.path:
                raise ValueError
        except ValueError:
            attempt = replace(attempt, lifecycle_state="REDIRECT_REJECTED")
            return self._terminal_response(spec, attempt, requested_at, accounting, "REDIRECT_REJECTED")
        if response.status == 401: return self._terminal_response(spec, attempt, requested_at, accounting, "AUTHENTICATION_FAILED")
        if response.status == 403: return self._terminal_response(spec, attempt, requested_at, accounting, "ENTITLEMENT_FAILED")
        if response.status == 429: return self._terminal_response(spec, attempt, requested_at, accounting, "RATE_LIMITED")
        if response.status != 200: return self._terminal_response(spec, attempt, requested_at, accounting, "PROVIDER_UNAVAILABLE")
        result = self._normalize(spec, tickers, response.body, requested_at, accounting, self._status(response.status))
        attempt = replace(attempt, terminal_status_category=result.failure or "SUCCESS")
        return self._with_attempt(result, attempt)

    def _ambiguous_failure(self, spec: EndpointSpec, attempt: AttemptRecord, token: int,
                           requested_at: str, category: str, lifecycle: str, started: float) -> FDResult:
        accounting = self.credits.mark_ambiguous(token)
        complete = replace(attempt, terminal_status_category=category,
            latency_ms=max(0.0, (self.clock() - started) * 1000), accounting_state="AMBIGUOUS_RESERVED",
            lifecycle_state=lifecycle)
        return self._with_attempt(self._fail(spec.capability, category, spec.credit_cost, accounting, requested_at), complete)

    def _terminal_response(self, spec: EndpointSpec, attempt: AttemptRecord, requested_at: str,
                           accounting: dict[str, int], category: str) -> FDResult:
        complete = replace(attempt, terminal_status_category=category)
        return self._with_attempt(self._fail(spec.capability, category, spec.credit_cost, accounting, requested_at), complete)

    def _with_attempt(self, result: FDResult, attempt: AttemptRecord) -> FDResult:
        self.attempt_records.append(attempt)
        if self.metric_recorder is not None:
            try: self.metric_recorder(attempt)
            except Exception:
                failed = replace(attempt, terminal_status_category="METRIC_CALLBACK_FAILED")
                self.attempt_records[-1] = failed
                return replace(result, state="UNAVAILABLE", records=(), failure="METRIC_CALLBACK_FAILED",
                    attempts=(failed,))
        return replace(result, attempts=(attempt,))

    def _cache_attempt(self, capability: FDCapability, tickers: tuple[str, ...], state: str) -> AttemptRecord:
        attempt = AttemptRecord(PROVIDER_ID, capability.value, capability.value, "|".join(tickers), 0, 0,
            False, False, "CACHE_HIT", None, None, state, 0, "ZERO_CREDIT", "RESPONSE_OBSERVED")
        self.attempt_records.append(attempt)
        return attempt

    def _normalize(self, spec: EndpointSpec, tickers: tuple[str, ...], body: bytes, requested_at: str,
                   accounting: dict[str, int], category: str) -> FDResult:
        try: payload = json.loads(body)
        except (UnicodeDecodeError, json.JSONDecodeError): return self._fail(spec.capability, "SCHEMA_REJECTED", spec.credit_cost, accounting, requested_at)
        rows = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(rows, list) or len(rows) > len(tickers) * 20:
            return self._fail(spec.capability, "SCHEMA_REJECTED", spec.credit_cost, accounting, requested_at)
        records = []; ignored = 0; digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        requested_dt = _time(requested_at)
        for row in rows:
            if not isinstance(row, dict) or not spec.required_fields <= set(row) or row.get("ticker") not in tickers:
                return self._fail(spec.capability, "SCHEMA_REJECTED", spec.credit_cost, accounting, requested_at)
            ignored += len(set(row) - spec.allowed_fields)
            clean = {key: row[key] for key in sorted(set(row) & spec.allowed_fields)}
            publication = clean.get("updated_at") or clean.get("filing_date") or clean.get("time")
            try:
                published_dt = _time(str(publication)) if publication else None
                if published_dt and published_dt > requested_dt: raise ValueError
            except ValueError:
                return self._fail(spec.capability, "POINT_IN_TIME_REJECTED", spec.credit_cost, accounting, requested_at)
            freshness = "UNKNOWN" if not published_dt else (
                "STALE" if (requested_dt - published_dt).total_seconds() > spec.maximum_freshness_seconds else "CURRENT")
            fields = tuple((key, value) for key, value in clean.items() if key not in {
                "ticker", "updated_at", "filing_date", "time", "report_period", "accession_number", "source_url"})
            record = GovernedRecord(PROVIDER_ID, spec.capability.value, row["ticker"], requested_at,
                str(publication) if publication else None, clean.get("report_period"),
                clean.get("accession_number") or clean.get("source_url"), freshness, digest, SCHEMA_VERSION,
                spec.data_classification, "PRIMARY_SOURCE_REQUIRED", spec.credit_cost or 0, "MISS", fields)
            record.validate(); records.append(record)
        return FDResult("AVAILABLE", spec.capability.value, tuple(records), projected_credit_cost=spec.credit_cost or 0,
            consumed_credits=accounting["consumed"], remaining_credits=accounting["remaining"],
            request_timestamp=requested_at, response_status_category=category, ignored_field_count=ignored)

    def _remaining(self) -> int | None:
        if self.policy.provider_balance is None: return None
        return min(self.policy.provider_balance, self.policy.total_ceiling) - self.credits.consumed

    def _fail(self, capability: FDCapability, failure: str, cost: int | None,
              accounting: dict[str, int] | None = None, requested_at: str | None = None) -> FDResult:
        safe = failure if failure in FIXED_FAILURES else "PROVIDER_UNAVAILABLE"
        return FDResult("UNAVAILABLE", capability.value, failure=safe, projected_credit_cost=cost or 0,
            consumed_credits=(accounting or {}).get("consumed", self.credits.consumed),
            remaining_credits=(accounting or {}).get("remaining", self._remaining()), request_timestamp=requested_at,
            response_status_category="TERMINAL" if safe in TERMINAL_STATUS else "UNAVAILABLE")

    @staticmethod
    def _status(status: int) -> str:
        if status == 200: return "SUCCESS"
        if status in {401, 403}: return "AUTHENTICATION_ERROR"
        if status == 429: return "RATE_LIMIT"
        if 400 <= status < 500: return "CLIENT_ERROR"
        if 500 <= status < 600: return "SERVER_ERROR"
        return "UNAVAILABLE"


class BoundedLiveAcceptanceRunner:
    """No-network-by-default orchestration; a caller must inject an enabled adapter and authorize once."""

    def __init__(self, adapter: FinancialDatasetsAdapter, *, explicitly_authorized: bool = False) -> None:
        self.adapter = adapter; self.explicitly_authorized = explicitly_authorized

    def run(self) -> dict[str, Any]:
        if not self.explicitly_authorized or not self.adapter.policy.enabled:
            return {"status": "NOT_AUTHORIZED", "attempted_requests": 0, "confirmed_requests": 0,
                "ambiguous_requests": 0, "results": (), "authority": AUTHORITY.copy()}
        readiness = getattr(self.adapter.transport, "trust_readiness", None)
        if not callable(readiness) or readiness() != "READY":
            return {"status": "TRUST_NOT_READY", "attempted_requests": 0, "confirmed_requests": 0,
                "ambiguous_requests": 0, "results": (), "accounting": self.adapter.credits.snapshot(),
                "authority": AUTHORITY.copy()}
        results: list[dict[str, Any]] = []
        for symbol in ("MU", "AMD"):
            result = self.adapter.fetch(FDCapability.COMPANY_FACTS, (symbol,))
            results.append(result.safe_accounting())
            if result.state != "AVAILABLE": break
            repeat = self.adapter.fetch(FDCapability.COMPANY_FACTS, (symbol,))
            results.append(repeat.safe_accounting())
        attempts = tuple(item for item in self.adapter.attempt_records if item.projected_credit_cost > 0)
        return {"status": "COMPLETE" if len(results) == 4 else "STOPPED_FAIL_CLOSED",
            "attempted_requests": sum(item.request_started for item in attempts),
            "confirmed_requests": sum(item.response_observed for item in attempts),
            "ambiguous_requests": sum(item.accounting_state == "AMBIGUOUS_RESERVED" for item in attempts),
            "results": tuple(results), "accounting": self.adapter.credits.snapshot(),
            "authority": AUTHORITY.copy()}


def primary_source_gate(record: GovernedRecord, *, primary_source_verified: bool, human_approved: bool) -> dict[str, Any]:
    record.validate(); ready = primary_source_verified and human_approved
    return {"status": "READY" if ready else "BLOCKED_PRIMARY_SOURCE_VERIFICATION",
        "judgment_foundry": ready, "pattern_laboratory": ready, "committee_reliance": ready,
        "paper_position_proposal": False, "failure_museum": ready, "automatic_action": False,
        "authority": AUTHORITY.copy()}


def browser_readiness(*, credential_provisioned: bool = False) -> dict[str, Any]:
    return {"schema_version": "iios-financial-datasets-readiness-v1", "adapter": "AVAILABLE",
        "credential": "AVAILABLE" if credential_provisioned else "NOT_PROVISIONED",
        "license": "REVIEWED_INTERNAL_USE", "provider_network": "DISABLED", "credit_ceiling": 1_000,
        "credits_consumed": 0, "auto_reload": False, "continuous_scanning": False,
        "provider_authority_granted": False}


def enrich_shortlist(adapter: FinancialDatasetsAdapter, capabilities: tuple[FDCapability, ...],
                     tickers: tuple[str, ...]) -> dict[str, Any]:
    results = tuple(adapter.fetch(capability, tickers) for capability in capabilities)
    failures = sum(result.state != "AVAILABLE" for result in results)
    return {"state": "UNAVAILABLE" if results and failures == len(results) else "PARTIAL" if failures else "AVAILABLE",
        "results": results, "partial_outage_visible": bool(failures), "cross_provider_substitution": False,
        "discovery_owner": "EXISTING_IIOS_SCANNER", "continuous_scan": False,
        "primary_source_verification_required": True, "authority": AUTHORITY.copy()}
