from __future__ import annotations

import json
import hashlib
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from .provider_enrichment import Capability, EnrichedDatum, ProviderResult, canonical_hash

FMP_HOST = "financialmodelingprep.com"
FMP_BASE_URL = "https://financialmodelingprep.com"
FMP_KEYCHAIN_SERVICE = "com.iios.expansion-wing.fmp"
FMP_KEYCHAIN_ACCOUNT = "fmp-api-key"
MAX_RESPONSE_BYTES = 2_000_000
COVERAGE_STATUS_CATEGORIES = {"SUCCESS", "CLIENT_ERROR", "RATE_LIMITED", "SERVER_ERROR", "UNAVAILABLE"}
COVERAGE_FRESHNESS = {"CURRENT", "STALE", "UNKNOWN", "UNAVAILABLE"}
CAPABILITY_FIELDS = {
    Capability.COMPANY_PROFILE: ({"symbol", "companyName", "cik", "isin", "cusip", "exchange", "industry", "sector", "timestamp"}, {"symbol", "companyName", "timestamp"}, "FACT"),
    Capability.FINANCIAL_STATEMENTS: ({"symbol", "date", "acceptedDate", "period", "revenue", "netIncome", "totalAssets", "totalDebt"}, {"symbol", "date", "acceptedDate"}, "FACT"),
    Capability.FUNDAMENTAL_RATIOS: ({"symbol", "date", "priceEarningsRatio", "priceToBookRatio", "debtEquityRatio", "returnOnEquity"}, {"symbol", "date"}, "DERIVED_METRIC"),
    Capability.HISTORICAL_PRICES: ({"symbol", "date", "open", "high", "low", "close", "volume"}, {"symbol", "date", "close"}, "FACT"),
    Capability.ANALYST_ESTIMATES: ({"symbol", "date", "estimatedRevenueAvg", "estimatedEpsAvg", "updatedAt"}, {"symbol", "date", "updatedAt"}, "ESTIMATE"),
    Capability.EARNINGS_CALENDAR: ({"symbol", "date", "epsEstimated", "revenueEstimated", "updatedAt"}, {"symbol", "date"}, "ESTIMATE"),
    Capability.COMPANY_NEWS_METADATA: ({"symbol", "publishedDate", "title", "site", "url"}, {"symbol", "publishedDate", "title"}, "FACT"),
    Capability.FOREX_REFERENCE: ({"symbol", "date", "price", "timestamp"}, {"symbol", "price", "timestamp"}, "FACT"),
    Capability.CRYPTO_REFERENCE: ({"symbol", "date", "price", "timestamp"}, {"symbol", "price", "timestamp"}, "FACT"),
}


@dataclass(frozen=True)
class FMPPolicy:
    enabled: bool = False
    credential_present: bool = False
    credential_source: str = "NONE"
    credential_service: str = FMP_KEYCHAIN_SERVICE
    credential_account: str = FMP_KEYCHAIN_ACCOUNT
    license_approved: bool = False
    endpoint_approved: bool = False
    timeout_seconds: float = 5.0
    max_response_bytes: int = MAX_RESPONSE_BYTES
    max_redirects: int = 1
    max_retries: int = 1
    backoff_seconds: float = 0.05
    requests_per_minute: int = 10
    cache_seconds: int = 300
    stale_after_seconds: int = 86_400
    max_batch_symbols: int = 50
    unknown_field_policy: str = "IGNORE"

    def validate(self) -> None:
        if not (0 < self.timeout_seconds <= 10 and 0 < self.max_response_bytes <= MAX_RESPONSE_BYTES and
                0 <= self.max_redirects <= 1 and 0 <= self.max_retries <= 2 and 0 <= self.backoff_seconds <= 1 and
                1 <= self.requests_per_minute <= 60 and 1 <= self.cache_seconds <= 3600 and
                60 <= self.stale_after_seconds <= 604_800 and
                1 <= self.max_batch_symbols <= 100 and self.unknown_field_policy in {"IGNORE", "REJECT"}):
            raise ValueError("FMP_POLICY_INVALID")
        if self.credential_present and (self.credential_source != "MACOS_SECURITY_FRAMEWORK_KEYCHAIN" or
                self.credential_service != FMP_KEYCHAIN_SERVICE or self.credential_account != FMP_KEYCHAIN_ACCOUNT):
            raise ValueError("FMP_KEYCHAIN_SELECTOR_REQUIRED")


@dataclass(frozen=True)
class FixtureHTTPResponse:
    status: int
    host: str
    redirect_count: int
    body: bytes


Transport = Callable[[str, tuple[str, ...], Capability, float], FixtureHTTPResponse]


class FMPAdapter:
    name = "FMP"

    def __init__(self, policy: FMPPolicy = FMPPolicy(), *, transport: Transport | None = None,
                 clock: Callable[[], float] = time.monotonic,
                 utcnow: Callable[[], datetime] = lambda: datetime.now(timezone.utc)) -> None:
        policy.validate(); self.policy = policy; self.transport = transport; self.clock = clock; self.utcnow = utcnow
        self._cache: dict[tuple[tuple[str, ...], Capability, str], tuple[float, ProviderResult]] = {}
        self._condition = threading.Condition(); self._inflight: set[tuple[tuple[str, ...], Capability, str]] = set()
        self._request_times: list[float] = []; self.endpoint_request_count: dict[str, int] = {}

    def capabilities(self) -> frozenset[Capability]:
        return frozenset(CAPABILITY_FIELDS)

    def fetch(self, symbols: tuple[str, ...], capability: Capability, *, point_in_time_cutoff: str) -> ProviderResult:
        blocked = self._preflight(symbols, capability)
        if blocked:
            return ProviderResult(self.name, capability.value, "UNAVAILABLE", failure_category=blocked)
        key = (symbols, capability, point_in_time_cutoff)
        with self._condition:
            cached = self._cache.get(key)
            if cached and self.clock() - cached[0] <= self.policy.cache_seconds:
                value = cached[1]
                return ProviderResult(value.provider, value.capability, value.state, value.data,
                    value.failure_category, 0, True)
            while key in self._inflight:
                self._condition.wait(timeout=self.policy.timeout_seconds)
                cached = self._cache.get(key)
                if cached:
                    value = cached[1]
                    return ProviderResult(value.provider, value.capability, value.state, value.data,
                        value.failure_category, 0, True)
                if key in self._inflight:
                    return ProviderResult(self.name, capability.value, "UNAVAILABLE", failure_category="TIMEOUT")
            self._inflight.add(key)
        try:
            result = self._request(symbols, capability, point_in_time_cutoff)
            if result.state == "CURRENT":
                with self._condition:
                    self._cache[key] = (self.clock(), result)
            return result
        finally:
            with self._condition:
                self._inflight.discard(key); self._condition.notify_all()

    def _preflight(self, symbols: tuple[str, ...], capability: Capability) -> str | None:
        if not self.policy.enabled: return "PROVIDER_DISABLED"
        if not self.policy.credential_present: return "CREDENTIAL_UNAVAILABLE"
        if not self.policy.license_approved or not self.policy.endpoint_approved: return "LICENSE_NOT_APPROVED"
        if capability not in self.capabilities(): return "CAPABILITY_UNAVAILABLE"
        if not symbols or len(symbols) > self.policy.max_batch_symbols: return "INVALID_SCHEMA"
        if self.transport is None: return "PROVIDER_UNAVAILABLE"
        return None

    def _request(self, symbols: tuple[str, ...], capability: Capability, cutoff: str) -> ProviderResult:
        now = self.clock(); self._request_times = [value for value in self._request_times if now - value < 60]
        if len(self._request_times) >= self.policy.requests_per_minute:
            return ProviderResult(self.name, capability.value, "UNAVAILABLE", failure_category="RATE_LIMITED")
        attempts = 0
        while attempts <= self.policy.max_retries:
            attempts += 1; self._request_times.append(self.clock())
            self.endpoint_request_count[capability.value] = self.endpoint_request_count.get(capability.value, 0) + 1
            try:
                response = self.transport(FMP_HOST, symbols, capability, self.policy.timeout_seconds)  # type: ignore[misc]
                if response.host != FMP_HOST or response.redirect_count > self.policy.max_redirects:
                    return ProviderResult(self.name, capability.value, "UNAVAILABLE", failure_category="INVALID_SCHEMA", request_count=attempts)
                if len(response.body) > self.policy.max_response_bytes:
                    return ProviderResult(self.name, capability.value, "UNAVAILABLE", failure_category="RESPONSE_TOO_LARGE", request_count=attempts)
                if response.status == 429:
                    return ProviderResult(self.name, capability.value, "UNAVAILABLE", failure_category="RATE_LIMITED", request_count=attempts)
                if response.status != 200:
                    raise RuntimeError("SANITIZED_PROVIDER_FAILURE")
                return self._decode(response.body, symbols, capability, cutoff, attempts)
            except TimeoutError:
                category = "TIMEOUT"
            except Exception:
                category = "RETRY_EXHAUSTED"
            if attempts <= self.policy.max_retries and self.policy.backoff_seconds:
                time.sleep(self.policy.backoff_seconds)
        return ProviderResult(self.name, capability.value, "UNAVAILABLE", failure_category=category, request_count=attempts)

    def _decode(self, body: bytes, symbols: tuple[str, ...], capability: Capability, cutoff: str,
                attempts: int) -> ProviderResult:
        try:
            rows = json.loads(body)
            if not isinstance(rows, list) or len(rows) > len(symbols) * 20:
                raise ValueError
            allowed, required, kind = CAPABILITY_FIELDS[capability]
            digest = canonical_hash(rows); retrieved_at = self.utcnow(); retrieved = retrieved_at.isoformat()
            data = []
            for row in rows:
                if not isinstance(row, dict) or not required <= set(row) or row.get("symbol") not in symbols:
                    raise ValueError
                if self.policy.unknown_field_policy == "REJECT" and set(row) - allowed:
                    raise ValueError
                clean = {key: value for key, value in row.items() if key in allowed}
                publication = clean.get("updatedAt") or clean.get("acceptedDate") or clean.get("publishedDate") or clean.get("date") or clean.get("timestamp")
                for field, value in clean.items():
                    if field in {"symbol", "updatedAt", "acceptedDate", "publishedDate", "date", "timestamp"}: continue
                    try:
                        published_at = datetime.fromisoformat(str(publication).replace("Z", "+00:00"))
                        if published_at.tzinfo is None: raise ValueError
                    except (AttributeError, ValueError):
                        raise ValueError("POINT_IN_TIME_INVALID") from None
                    freshness = "STALE" if (retrieved_at - published_at).total_seconds() > self.policy.stale_after_seconds else "CURRENT"
                    datum = EnrichedDatum(str(clean["symbol"]), field, value, kind, self.name, capability.value,
                        str(publication), str(publication) if publication else None, retrieved, cutoff, freshness,
                        "APPROVED_INTERNAL_USE", digest, "PRIMARY_SOURCE_REQUIRED")
                    datum.validate(); data.append(datum)
            return ProviderResult(self.name, capability.value, "CURRENT", tuple(data), request_count=attempts)
        except (KeyError, TypeError, ValueError) as exc:
            category = "POINT_IN_TIME_INVALID" if str(exc) == "POINT_IN_TIME_INVALID" else "INVALID_SCHEMA"
            return ProviderResult(self.name, capability.value, "UNAVAILABLE", failure_category=category, request_count=attempts)

    def accounting(self) -> dict[str, object]:
        return {"provider": self.name, "requests_by_capability": dict(self.endpoint_request_count),
            "billable_cost_usd": None, "cost_state": "LICENSE_REVIEW_REQUIRED",
            "credentials_exposed": False, "browser_credentials_exposed": False}


def credential_lifecycle_contract() -> dict[str, object]:
    """Metadata-only contract; never retrieves or accepts a credential value."""
    return {"storage": "MACOS_SECURITY_FRAMEWORK_KEYCHAIN", "adapter": "REVIEWED_SECURITY_FRAMEWORK_ADAPTER",
        "service": FMP_KEYCHAIN_SERVICE, "account": FMP_KEYCHAIN_ACCOUNT,
        "retrieval_scope": "ISOLATED_AUTHORIZED_COVERAGE_TEST_PROCESS_ONLY",
        "persistent": True, "delete_after_test": False, "rotation_authorized": False,
        "revocation_authorized": False, "provisioning_separate_authorization_required": True,
        "provider_contact_separate_authorization_required": True, "secret_exposed": False}


def summarize_license_pending_coverage(*, capability: Capability, response_body: bytes,
        http_status_category: str, latency_ms: int, cache_result: str, accounting_request_count: int,
        freshness: str, failure_category: str | None = None) -> dict[str, object]:
    """Build the only record retainable from a separately authorized license-pending probe."""
    if capability not in CAPABILITY_FIELDS or len(response_body) > MAX_RESPONSE_BYTES:
        raise ValueError("COVERAGE_RESPONSE_INVALID")
    if http_status_category not in COVERAGE_STATUS_CATEGORIES or freshness not in COVERAGE_FRESHNESS:
        raise ValueError("COVERAGE_CATEGORY_INVALID")
    if not isinstance(latency_ms, int) or isinstance(latency_ms, bool) or not 0 <= latency_ms <= 30_000:
        raise ValueError("COVERAGE_LATENCY_INVALID")
    if (cache_result not in {"MISS", "HIT"} or not isinstance(accounting_request_count, int) or
            isinstance(accounting_request_count, bool) or accounting_request_count not in {0, 1}):
        raise ValueError("COVERAGE_ACCOUNTING_INVALID")
    if failure_category is not None and failure_category not in {
            "INVALID_SCHEMA", "RESPONSE_TOO_LARGE", "TIMEOUT", "RETRY_EXHAUSTED", "RATE_LIMITED",
            "POINT_IN_TIME_INVALID", "PROVIDER_UNAVAILABLE"}:
        raise ValueError("COVERAGE_FAILURE_INVALID")
    try:
        payload = json.loads(response_body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        payload = None
    rows = payload if isinstance(payload, list) else [payload]
    field_names = sorted({key for row in rows if isinstance(row, dict) for key in row})
    allowed, required, _kind = CAPABILITY_FIELDS[capability]
    schema_match = bool(rows) and all(isinstance(row, dict) and required <= set(row) for row in rows)
    timestamp_fields = {"timestamp", "date", "acceptedDate", "updatedAt", "publishedDate"}
    return {"endpoint_capability": capability.value, "http_status_category": http_status_category,
        "response_byte_count": len(response_body), "latency_ms": latency_ms,
        "returned_top_level_field_names": tuple(field_names), "schema_match": schema_match,
        "timestamp_availability": bool(timestamp_fields & set(field_names)), "freshness": freshness,
        "content_hash": hashlib.sha256(response_body).hexdigest(), "cache_result": cache_result,
        "accounting_request_count": accounting_request_count, "failure_category": failure_category,
        "response_body_retained": False, "normalized_security_evidence_retained": False,
        "license_state": "LICENSE_REVIEW_REQUIRED"}
