"""Fail-closed provider readiness for unattended Tuesday Stage A.

Importing this module and evaluating readiness performs no network, Keychain,
controller, policy, paper, ledger, or projection I/O.
"""
from __future__ import annotations

import hashlib
import json
import stat
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol

from .financial_datasets import API_HOST, AUTH_HEADER, KEYCHAIN_ACCOUNT, KEYCHAIN_SERVICE
from .unattended_tuesday import DAILY_CEILING, STAGE_A_MAXIMUM
from .tuesday_whole_factory import PILOT_BY_PRODUCT

COST_SCHEMA = "iios-provider-endpoint-cost-contract-v1"
BROWSER_SCHEMA = "iios-provider-stage-a-readiness-browser-v1"
PROVIDER = "FINANCIAL_DATASETS"
PROVIDER_CONTRACT = "fd-stage-a-standard-v1"
PRICING_OBSERVATION_IDENTITY = "financial-datasets-pricing-2026-09-08-v1"
PRICING_OBSERVED_AT = "2026-09-08T01:25:49+00:00"
PRICING_EXPIRES_AT = "2026-09-09T01:25:49+00:00"
MAX_COST_EVIDENCE_AGE_SECONDS = 86_400
REQUIRED_SESSION_COVERAGE_UTC = "2026-09-08T20:05:00+00:00"
READINESS_ROOT = Path.home()/"Library/Application Support/IIOS/UnattendedTuesdayReadiness"
COST_CONTRACT_NAME = "provider-cost-contract.json"
CREDENTIAL_STATUS_NAME = "credential-presence.json"
READINESS_INVENTORY = frozenset({COST_CONTRACT_NAME, CREDENTIAL_STATUS_NAME})
PRIOR_SESSION_DATE = "2026-09-04"
SOURCE_CONTROLLED_SESSIONS = ("2026-09-01", "2026-09-02", "2026-09-03", "2026-09-04", "2026-09-08")
RATE_LIMIT_PER_MINUTE = 10
MAX_RESPONSE_BYTES = 1_048_576
CONNECT_TIMEOUT_SECONDS = 5
READ_TIMEOUT_SECONDS = 10
OFFICIAL_SOURCES = frozenset({
    "https://www.financialdatasets.ai/pricing",
    "https://docs.financialdatasets.ai/api/prices/snapshot",
    "https://docs.financialdatasets.ai/api/prices/historical",
    "https://docs.financialdatasets.ai/api/company/facts/ticker",
})
ENDPOINT_PATHS = {
    "MARKET_SNAPSHOT": "/prices/snapshot",
    "HISTORICAL_OHLCV": "/prices",
    "COMPANY_FACTS": "/company/facts",
}
INSTRUMENT_CLASSES = {
    "MU": "LISTED_COMMON_STOCK", "SPY": "EQUITY_ETF", "XLK": "EQUITY_ETF",
    "VNQ": "REIT_ETF", "TLT": "BOND_ETF", "GLD": "COMMODITY_TRUST",
    "UUP": "CURRENCY_ETF", "IBIT": "CRYPTO_ETF", "PFF": "PREFERRED_ETF",
    "BIL": "TREASURY_BILL_ETF",
}


def _hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256((encoded + "\n").encode("ascii")).hexdigest()


def _utc(value: str) -> datetime:
    if not isinstance(value, str) or not value.endswith(("Z", "+00:00")):
        raise ValueError("COST_CONTRACT_TIMESTAMP_INVALID")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo != timezone.utc:
        raise ValueError("COST_CONTRACT_TIMESTAMP_INVALID")
    return parsed


def prior_market_session(session_date: str) -> str:
    eligible = [value for value in SOURCE_CONTROLLED_SESSIONS if value < session_date]
    if not eligible:
        raise ValueError("PRIOR_SESSION_UNAVAILABLE")
    return eligible[-1]


@dataclass(frozen=True)
class EndpointCost:
    evidence_category: str
    endpoint_identity: str
    confirmed_cost_credits: int
    source_url: str
    observed_at: str
    expires_at: str
    rate_limit_per_minute: int = RATE_LIMIT_PER_MINUTE
    pricing_observation_identity: str = PRICING_OBSERVATION_IDENTITY

    def document(self) -> dict[str, Any]:
        value = {
            "schema": COST_SCHEMA, "provider_identity": PROVIDER,
            "provider_contract_version": PROVIDER_CONTRACT,
            "pricing_observation_identity": self.pricing_observation_identity,
            "evidence_category": self.evidence_category,
            "endpoint_identity": self.endpoint_identity,
            "cost_unit": "INTEGER_REQUEST_CREDIT",
            "confirmed_cost_per_request": self.confirmed_cost_credits,
            "source_url_identity": self.source_url,
            "documentation_observed_at": self.observed_at,
            "expiration_revalidation_time": self.expires_at,
            "rate_limit_class": f"MAX_{self.rate_limit_per_minute}_PER_MINUTE",
            "ambiguity_treatment": "RESERVE_AND_FINALIZE_CONSERVATIVELY",
        }
        return value | {"canonical_content_hash": _hash(value)}

    def validate(self, now: datetime) -> str:
        if now.tzinfo != timezone.utc:
            return "COST_CONTRACT_EXPIRED"
        if (self.endpoint_identity not in ENDPOINT_PATHS or self.source_url != "https://www.financialdatasets.ai/pricing"
                or self.pricing_observation_identity != PRICING_OBSERVATION_IDENTITY):
            return "ENDPOINT_COST_UNKNOWN"
        if isinstance(self.confirmed_cost_credits, bool) or not isinstance(self.confirmed_cost_credits, int) or self.confirmed_cost_credits < 1:
            return "ENDPOINT_COST_UNKNOWN"
        if self.rate_limit_per_minute != RATE_LIMIT_PER_MINUTE:
            return "RATE_LIMIT_BLOCKED"
        try:
            observed, expires = _utc(self.observed_at), _utc(self.expires_at)
        except (TypeError, ValueError):
            return "ENDPOINT_COST_UNKNOWN"
        if (expires <= observed or (expires-observed).total_seconds() > MAX_COST_EVIDENCE_AGE_SECONDS
                or expires < _utc(REQUIRED_SESSION_COVERAGE_UTC) or now < observed or now > expires):
            return "COST_CONTRACT_EXPIRED"
        return "VALID"


def reviewed_cost_contracts() -> dict[str, EndpointCost]:
    """Source-reviewed, account-neutral contracts for only the three fixed paths."""
    pricing = "https://www.financialdatasets.ai/pricing"
    return {
        endpoint: EndpointCost(
            evidence_category=endpoint,
            endpoint_identity=endpoint,
            confirmed_cost_credits=1,
            source_url=pricing,
            observed_at=PRICING_OBSERVED_AT,
            expires_at=PRICING_EXPIRES_AT,
        )
        for endpoint in ENDPOINT_PATHS
    }


class CredentialPresenceProbe(Protocol):
    def exists(self, *, service: str, account: str) -> bool | None: ...


class FixedCredentialBoundary:
    """Presence-only boundary; deliberately provides no secret retrieval API."""
    __slots__ = ("_probe",)
    service = KEYCHAIN_SERVICE
    account = KEYCHAIN_ACCOUNT

    def __init__(self, probe: CredentialPresenceProbe) -> None:
        self._probe = probe

    def status(self) -> str:
        try: result = self._probe.exists(service=self.service, account=self.account)
        except PermissionError: return "ACCESS_DENIED"
        return "AVAILABLE" if result is True else "UNAVAILABLE" if result is False else "AMBIGUOUS"


def cost_contract_document() -> dict[str, Any]:
    contracts=reviewed_cost_contracts()
    value={"schema":COST_SCHEMA,"provider_identity":PROVIDER,"pricing_change_invalidation":True,
        "browser_refresh":False,"provider_execution_refresh":False,"planned_request_count":50,
        "worst_case_credits":50,"stage_a_maximum":STAGE_A_MAXIMUM,"daily_hard_ceiling":DAILY_CEILING,
        "contracts":[contracts[key].document() for key in sorted(contracts)]}
    return value|{"document_hash":_hash(value)}


def validate_cost_contract_document(value:Any,*,now:datetime)->dict[str,Any]:
    expected=cost_contract_document()
    if value != expected: raise ValueError("COST_CONTRACT_HASH_INVALID")
    if any(contract.validate(now)!="VALID" for contract in reviewed_cost_contracts().values()):
        raise ValueError("COST_CONTRACT_EXPIRED")
    return value


def installed_readiness_projection(*,root:Path=READINESS_ROOT,now:datetime|None=None,policy_installed:bool=False)->dict[str,Any]:
    """Read fixed owner-only metadata only; never reads Keychain or network."""
    current=datetime.now(timezone.utc) if now is None else now
    try:
        info=root.lstat()
        if root.is_symlink() or not stat.S_ISDIR(info.st_mode) or stat.S_IMODE(info.st_mode)!=0o700: raise ValueError("READINESS_ROOT_INVALID")
        if {item.name for item in root.iterdir()}!=READINESS_INVENTORY: raise ValueError("READINESS_INVENTORY_INVALID")
        docs={}
        for name in READINESS_INVENTORY:
            path=root/name; item=path.lstat()
            if path.is_symlink() or not stat.S_ISREG(item.st_mode) or stat.S_IMODE(item.st_mode)!=0o600: raise ValueError("READINESS_FILE_INVALID")
            docs[name]=json.loads(path.read_text())
        validate_cost_contract_document(docs[COST_CONTRACT_NAME],now=current)
        credential=docs[CREDENTIAL_STATUS_NAME]
        if set(credential)!={"schema","status","checked_at"} or credential.get("schema")!="iios-credential-presence-v1" or credential.get("status") not in {"AVAILABLE","UNAVAILABLE","AMBIGUOUS","ACCESS_DENIED"}: raise ValueError("CREDENTIAL_METADATA_INVALID")
        class StoredProbe:
            def exists(self,**kwargs):
                del kwargs
                return True if credential["status"]=="AVAILABLE" else False if credential["status"]=="UNAVAILABLE" else None
        projection=evaluate_readiness(reviewed_cost_contracts(),FixedCredentialBoundary(StoredProbe()),now=current)
        projection.update({"commissioning_state":"AUTHORIZED_WAITING" if policy_installed and projection["failure_category"]=="PROVIDER_READY" else "READY_FOR_OWNER_POLICY_AUTHORIZATION" if projection["failure_category"]=="PROVIDER_READY" else "FAILED_CLOSED","unattended_service_state":"INSTALLED_DISABLED","one_day_policy_state":"AUTHORIZED_WAITING" if policy_installed else "NOT_AUTHORIZED"})
        return projection
    except (OSError,ValueError,json.JSONDecodeError):
        return {"schema_version":BROWSER_SCHEMA,"provider_state":"FAILED_CLOSED","commissioning_state":"UNAVAILABLE","unattended_service_state":"UNAVAILABLE","one_day_policy_state":"NOT_AUTHORIZED","authority_locked":True,"network_enabled":False}


def revised_request_plan() -> tuple[dict[str, Any], ...]:
    """The reviewed 50-row provider plan; changing any field changes its identity."""
    windows = (
        ("OPENING_SESSION", "MARKET_SNAPSHOT", "06:30", "07:00", None),
        ("POINT_IN_TIME_OHLCV", "HISTORICAL_OHLCV", "06:30", "08:00", "2026-09-04/2026-09-08"),
        ("APPLICABLE_FACTS", "APPLICABLE", "07:00", "10:00", None),
        ("INTRADAY_MARK", "MARKET_SNAPSHOT", "09:30", "10:30", None),
        ("CLOSING_MARK", "MARKET_SNAPSHOT", "12:55", "13:05", None),
    )
    result = []
    for room, (instrument, _description) in PILOT_BY_PRODUCT.items():
        for category, endpoint, earliest, latest, date_window in windows:
            resolved_endpoint = endpoint
            resolved_category = category
            resolved_window = date_window
            if endpoint == "APPLICABLE":
                if instrument == "MU":
                    resolved_endpoint = "COMPANY_FACTS"
                else:
                    resolved_endpoint = "HISTORICAL_OHLCV"
                    resolved_category = "PRIOR_SESSION_BASELINE"
                    prior = prior_market_session("2026-09-08")
                    resolved_window = f"{prior}/{prior}"
            identity_payload = {
                "provider": PROVIDER, "provider_contract": PROVIDER_CONTRACT,
                "instrument": instrument, "endpoint": resolved_endpoint,
                "evidence_category": resolved_category, "earliest": earliest,
                "latest": latest, "date_window": resolved_window,
            }
            result.append(identity_payload | {
                "product_room": room, "confirmed_cost": 1, "retry": False,
                "request_identity": "stage-a-" + _hash(identity_payload),
            })
    return tuple(result)


def revised_plan_identity() -> str:
    return _hash({"schema": "iios-stage-a-provider-plan-v2", "requests": revised_request_plan()})


def operational_cost_binding(*, root: Path = READINESS_ROOT, now: datetime | None = None) -> dict[str, Any]:
    """Validate the fixed installed cost document and its exact 50-row plan."""
    current = datetime.now(timezone.utc) if now is None else now
    projection = installed_readiness_projection(root=root, now=current)
    if projection.get("provider_state") != "READY":
        raise ValueError("OPERATIONAL_COST_BINDING_UNAVAILABLE")
    expected = {
        "request_plan_identity": revised_plan_identity(),
        "planned_identity_count": 50,
        "supported_costed_identity_count": 50,
        "blocked_identity_count": 0,
        "exact_planned_cost_credits": 50,
        "worst_case_cost_credits": 50,
        "stage_a_authorized_allowance_credits": 50,
        "stage_a_maximum_credits": STAGE_A_MAXIMUM,
        "daily_hard_ceiling_credits": DAILY_CEILING,
    }
    document = json.loads((root / COST_CONTRACT_NAME).read_text())
    validate_cost_contract_document(document, now=current)
    return expected | {"cost_contract_hash": document["document_hash"]}


def classify_identity(row: Mapping[str, Any]) -> str:
    instrument, endpoint = row.get("instrument"), row.get("endpoint")
    if instrument not in INSTRUMENT_CLASSES:
        return "PROVIDER_IDENTITY_AMBIGUOUS"
    if row.get("provider_contract") != PROVIDER_CONTRACT:
        return "PROVIDER_IDENTITY_AMBIGUOUS"
    if endpoint in {"MARKET_SNAPSHOT", "HISTORICAL_OHLCV"}:
        return "SUPPORTED_AND_COSTED"
    if endpoint == "COMPANY_FACTS" and instrument == "MU":
        return "SUPPORTED_AND_COSTED"
    if endpoint == "INSTRUMENT_PROFILE":
        return "UNSUPPORTED_FOR_INSTRUMENT"
    return "ENDPOINT_COST_UNKNOWN"


def evaluate_readiness(contracts: Mapping[str, EndpointCost], credential: FixedCredentialBoundary, *, now: datetime, policy_identity: str = "tuesday-2026-09-08-stage-a") -> dict[str, Any]:
    """Return sanitized scalar/count truth without spending or writes."""
    del policy_identity  # retained for a stable public call signature; plan v2 is fixed
    rows = revised_request_plan()
    states = tuple(classify_identity(row) for row in rows)
    unsupported = states.count("UNSUPPORTED_FOR_INSTRUMENT")
    ambiguous = states.count("PROVIDER_IDENTITY_AMBIGUOUS")
    unresolved = sum(state != "SUPPORTED_AND_COSTED" for state in states)
    failure = "PROVIDER_IDENTITY_AMBIGUOUS" if ambiguous else "REQUEST_PLAN_INVALID" if unsupported else None
    costs: dict[str, int] = {}
    contract_states = []
    for endpoint in sorted({row["endpoint"] for row, state in zip(rows, states) if state == "SUPPORTED_AND_COSTED"}):
        contract = contracts.get(endpoint)
        state = "ENDPOINT_COST_UNKNOWN" if contract is None else contract.validate(now)
        contract_states.append(state)
        if state == "VALID" and contract is not None:
            costs[endpoint] = contract.confirmed_cost_credits
        elif failure is None:
            failure = state
    worst_case = None
    if not unresolved and contract_states and all(state == "VALID" for state in contract_states):
        worst_case = sum(costs[row["endpoint"]] for row in rows)
        if worst_case > STAGE_A_MAXIMUM or worst_case > DAILY_CEILING:
            failure = failure or "BUDGET_INSUFFICIENT"
    credential_state = credential.status()
    if credential_state != "AVAILABLE" and failure is None:
        failure = {"UNAVAILABLE":"CREDENTIAL_NOT_AVAILABLE","AMBIGUOUS":"CREDENTIAL_AMBIGUOUS","ACCESS_DENIED":"CREDENTIAL_ACCESS_DENIED"}.get(credential_state,"CREDENTIAL_AMBIGUOUS")
    category = failure or "PROVIDER_READY"
    return {
        "schema_version": BROWSER_SCHEMA,
        "provider_state": "READY" if category == "PROVIDER_READY" else "FAILED_CLOSED",
        "provider_identity": PROVIDER,
        "request_plan_state": "VALID" if unresolved == 0 else "INVALID",
        "cost_contract_state": "VALID" if contract_states and all(x == "VALID" for x in contract_states) else "UNAVAILABLE",
        "credential_presence_state": credential_state,
        "supported_costed_identity_count": len(rows) - unresolved,
        "unsupported_identity_count": unsupported,
        "ambiguous_identity_count": ambiguous,
        "planned_identity_count": len(rows),
        "worst_case_stage_a_credits": worst_case,
        "stage_a_authorized_allowance_credits": 50,
        "stage_a_maximum": STAGE_A_MAXIMUM,
        "stage_a_safety_margin": None if worst_case is None else STAGE_A_MAXIMUM - worst_case,
        "daily_hard_ceiling": DAILY_CEILING,
        "stage_b_state": "LOCKED",
        "stage_c_state": "LOCKED",
        "stage_a_released_credits": 0,
        "failure_category": category,
        "network_enabled": False,
        "authority_locked": True,
        "cost_contract_binding": "VALID" if category == "PROVIDER_READY" else "UNAVAILABLE",
    }


@dataclass
class FixtureAccounting:
    """Deterministic non-network reservation model used only by tests/rehearsals."""
    transmitted: set[str]
    charged: dict[str, int]
    cached: set[str]
    released_allowance: int = 0

    @classmethod
    def empty(cls) -> "FixtureAccounting":
        return cls(set(), {}, set(), 0)

    def release(self, credits: int) -> None:
        if credits != STAGE_A_MAXIMUM or self.released_allowance:
            raise ValueError("ALLOWANCE_RELEASE_REJECTED")
        self.released_allowance = credits

    def execute(self, identity: str, outcome: str) -> str:
        if identity in self.cached:
            return "CACHE_HIT_ZERO_INCREMENTAL_COST"
        if identity in self.transmitted:
            raise ValueError("DUPLICATE_REQUEST_REJECTED")
        if outcome == "PRE_TRANSMISSION_REJECTED":
            return outcome
        if self.released_allowance < 1:
            raise ValueError("BUDGET_INSUFFICIENT")
        self.transmitted.add(identity)
        self.charged[identity] = 1
        self.released_allowance -= 1
        if outcome == "CONFIRMED":
            self.cached.add(identity)
            return "CONFIRMED"
        if outcome == "AMBIGUOUS":
            return "AMBIGUOUS_CHARGED_ONCE_NO_RETRY"
        raise ValueError("OUTCOME_INVALID")

    def close(self) -> None:
        self.released_allowance = 0


class StubTransport(Protocol):
    def send(self, *, host: str, path: str, headers: Mapping[str, bytes], timeout: tuple[int, int]) -> tuple[int, str, bytes]: ...


def bounded_stub_request(*, endpoint: str, credential_supplier: Callable[[], bytes], transport: StubTransport) -> dict[str, Any]:
    """Least-authority test seam. Production enablement is intentionally absent."""
    if endpoint not in ENDPOINT_PATHS:
        raise ValueError("ENDPOINT_NOT_ALLOWED")
    secret = credential_supplier()
    if not isinstance(secret, bytes) or not 16 <= len(secret) <= 256 or any(byte < 0x21 or byte > 0x7E for byte in secret):
        raise ValueError("CREDENTIAL_INVALID")
    try:
        status, content_type, body = transport.send(host=API_HOST, path=ENDPOINT_PATHS[endpoint], headers={AUTH_HEADER: secret}, timeout=(CONNECT_TIMEOUT_SECONDS, READ_TIMEOUT_SECONDS))
        if len(body) > MAX_RESPONSE_BYTES:
            raise ValueError("RESPONSE_BOUNDS_EXCEEDED")
        if content_type.split(";", 1)[0].strip().lower() != "application/json":
            raise ValueError("CONTENT_TYPE_REJECTED")
        if status != 200:
            raise ValueError("PROVIDER_RESPONSE_REJECTED")
        parsed = json.loads(body)
        if not isinstance(parsed, dict):
            raise ValueError("PROVIDER_SCHEMA_REJECTED")
        return {"status_category": "HTTP_2XX", "response_bytes": len(body), "content_hash": _hash(parsed)}
    except TimeoutError as exc:
        raise ValueError("AMBIGUOUS_CHARGE_NO_RETRY") from exc
    finally:
        secret = b""
