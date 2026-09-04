from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

SCHEMA_VERSION = "iios-multi-asset-research-factory-v1"
ASSET_CLASSES = {
    "US_EQUITY", "EQUITY_ETF", "TREASURY_RATES", "BOND_PROXY", "COMMODITY_PROXY",
    "FX_PROXY", "CRYPTO_REFERENCE", "LISTED_OPTION", "INTRADAY", "RELATIVE_VALUE",
}
DIRECTIONS = {"LONG", "SHORT", "RELATIVE_VALUE", "OBSERVATION_ONLY"}
GOVERNANCE = {"RESEARCH_ONLY", "INCOMPLETE", "PRIMARY_REVIEW_REQUIRED", "PAPER_ELIGIBLE"}
RIGHTS = {"PUBLIC_OFFICIAL", "LICENSED_APPROVED", "RIGHTS_REVIEW_REQUIRED"}
FRESHNESS = {"CURRENT", "STALE", "INCOMPLETE", "UNAVAILABLE"}
COMPLETENESS = {"COMPLETE", "INCOMPLETE"}
PRIMARY_STATES = {"VERIFIED", "PENDING", "UNAVAILABLE"}
PROFESSIONAL_SOURCE_TYPES = {"SEC_13F", "FORM_ADV", "PUBLIC_LETTER", "PUBLIC_INTERVIEW",
    "PODCAST", "CONFERENCE", "FUND_ETF_HOLDINGS", "PUBLIC_MODEL_PORTFOLIO",
    "SEC_FILING", "EARNINGS_MATERIAL", "MARKET_VISION", "KOYFIN_MANUAL_IMPORT",
    "LICENSED_PROVIDER_RESEARCH"}
SOURCE_TYPES = {"IIOS_SCANNER", "PROFESSIONAL_OBSERVATION", "HISTORICAL_PATTERN"}
AUTHORITY = {
    "automatic_promotion": False, "committee_override": False, "risk_override": False,
    "paper_order": False, "ledger_write": False, "broker": False, "live_execution": False,
}


def _time(value: str) -> datetime:
    try: parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError): raise ValueError("TIMESTAMP_INVALID") from None
    if parsed.tzinfo is None: raise ValueError("TIMESTAMP_INVALID")
    return parsed.astimezone(timezone.utc)


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=True).encode("ascii")).hexdigest()


@dataclass(frozen=True)
class CommonOpportunityPassport:
    opportunity_id: str
    source_timestamp: str
    effective_timestamp: str
    asset_class: str
    instrument_type: str
    instrument_id: str
    direction: str
    strategy_family: str
    time_horizon: str
    catalyst: str
    thesis: str
    counter_thesis: str
    expected_return_range: tuple[float, float]
    maximum_modeled_loss: float
    liquidity_classification: str
    volatility_classification: str
    correlation_cluster: str
    invalidation_conditions: tuple[str, ...]
    evidence_freshness: str
    evidence_completeness: str
    primary_source_verification_state: str
    professional_research_observations: tuple[str, ...]
    scanner_observations: tuple[str, ...]
    historical_analog_results: tuple[str, ...]
    confidence: float
    governance_status: str
    authority: dict[str, bool] = field(default_factory=lambda: AUTHORITY.copy())

    def validate(self, *, now: datetime | None = None) -> None:
        expected = now or datetime.now(timezone.utc)
        source, effective = _time(self.source_timestamp), _time(self.effective_timestamp)
        if source > effective or effective > expected.astimezone(timezone.utc): raise ValueError("LOOK_AHEAD_REJECTED")
        if (not re.fullmatch(r"opp_[0-9a-f]{20}", self.opportunity_id) or self.asset_class not in ASSET_CLASSES or
                not re.fullmatch(r"[A-Z0-9][A-Z0-9._:/-]{0,79}", self.instrument_id) or
                self.direction not in DIRECTIONS or self.governance_status not in GOVERNANCE or
                not self.instrument_type or not self.strategy_family or not self.time_horizon or
                not self.catalyst or not self.thesis or not self.counter_thesis or
                len(self.expected_return_range) != 2 or self.expected_return_range[0] > self.expected_return_range[1] or
                self.maximum_modeled_loss < 0 or self.maximum_modeled_loss > 1 or
                not self.invalidation_conditions or not 0 <= self.confidence <= 1 or
                self.evidence_freshness not in FRESHNESS or self.evidence_completeness not in COMPLETENESS or
                self.primary_source_verification_state not in PRIMARY_STATES or
                self.authority != AUTHORITY or any(self.authority.values())):
            raise ValueError("OPPORTUNITY_PASSPORT_INVALID")
        if self.governance_status == "PAPER_ELIGIBLE" and self.primary_source_verification_state != "VERIFIED":
            raise ValueError("PRIMARY_SOURCE_REQUIRED")

    def browser_safe(self) -> dict[str, Any]:
        self.validate()
        value = asdict(self)
        value["professional_research_observation_count"] = len(value.pop("professional_research_observations"))
        value["scanner_observation_count"] = len(value.pop("scanner_observations"))
        value["historical_analog_count"] = len(value.pop("historical_analog_results"))
        value.pop("thesis"); value.pop("counter_thesis"); value.pop("catalyst"); value.pop("invalidation_conditions")
        return value


@dataclass(frozen=True)
class LaneDefinition:
    lane_id: str
    asset_class: str
    label: str
    direct_instrument: bool
    proxy_basis: str | None
    research_only: bool
    required_fields: tuple[str, ...]


LANES = (
    LaneDefinition("us_equities", "US_EQUITY", "US equities", True, None, False, ("price", "liquidity")),
    LaneDefinition("equity_etfs", "EQUITY_ETF", "Equity ETFs", True, None, False, ("price", "spread", "holdings_date")),
    LaneDefinition("treasury_rates", "TREASURY_RATES", "Treasury/rates", False, "LIQUID_TREASURY_ETF", True, ("maturity", "duration", "yield_convention", "credit_quality", "callable_status", "proxy_basis")),
    LaneDefinition("bond_proxies", "BOND_PROXY", "IG/HY bond proxies", False, "LIQUID_BOND_ETF", True, ("maturity", "duration", "yield_convention", "credit_quality", "callable_status", "proxy_basis")),
    LaneDefinition("commodity_proxies", "COMMODITY_PROXY", "Commodity proxies", False, "LIQUID_COMMODITY_ETF", True, ("proxy_basis", "roll_effect")),
    LaneDefinition("fx_proxies", "FX_PROXY", "Foreign-exchange proxies", False, "LIQUID_CURRENCY_ETF", True, ("proxy_basis", "session")),
    LaneDefinition("crypto_reference", "CRYPTO_REFERENCE", "Crypto reference assets", False, "REFERENCE_PRICE_ONLY", True, ("venue_set", "timestamp")),
    LaneDefinition("listed_options", "LISTED_OPTION", "Listed-options research", True, None, True, ("contract_id", "underlying", "expiration", "strike", "option_type", "multiplier", "bid", "ask", "implied_volatility", "greeks_state", "assignment_risk", "maximum_loss")),
    LaneDefinition("intraday", "INTRADAY", "Intraday/day-trading research", True, None, True, ("market_session", "observed_at", "latency_ms", "spread", "liquidity", "market_hours_state")),
    LaneDefinition("relative_value", "RELATIVE_VALUE", "Relative-value/cross-asset", False, "EXPLICIT_LEG_IDENTITIES", True, ("legs", "hedge_ratio", "correlation_window")),
)


def lane_registry() -> tuple[LaneDefinition, ...]: return LANES


def classify_lane_proposal(lane_id: str, fields: dict[str, Any], *, market_open: bool = True) -> dict[str, Any]:
    lane = next((item for item in LANES if item.lane_id == lane_id), None)
    if lane is None: return {"state": "FAILED_CLOSED", "reason": "UNSUPPORTED_ASSET_CLASS"}
    missing = tuple(key for key in lane.required_fields if fields.get(key) in (None, "", ()))
    if lane_id == "intraday" and not market_open: return {"state": "INCOMPLETE", "reason": "MARKET_CLOSED"}
    if missing:
        reason = "RESEARCH_ONLY_UNPRICEABLE" if lane_id == "listed_options" else "REQUIRED_INSTRUMENT_FIELDS_MISSING"
        return {"state": "INCOMPLETE", "reason": reason, "missing_fields": missing}
    return {"state": "RESEARCH_ONLY" if lane.research_only else "PRIMARY_REVIEW_REQUIRED",
        "reason": "PROXY_NOT_UNDERLYING" if lane.proxy_basis else None, "proxy_basis": lane.proxy_basis}


@dataclass(frozen=True)
class ProfessionalObservation:
    observation_id: str
    professional_id: str
    source_type: str
    publication_timestamp: str
    observation_timestamp: str
    asset_class: str
    themes: tuple[str, ...]
    stated_thesis: str
    observed_positioning: str
    valuation_framework: str
    catalyst: str
    horizon: str
    risks: tuple[str, ...]
    invalidation: tuple[str, ...]
    conviction: str
    words_positioning_agreement: str
    primary_evidence_reference: str
    rights_status: str
    outcome_state: str = "UNRESOLVED"
    later_accuracy_score: float | None = None

    def validate(self, *, now: datetime | None = None) -> None:
        publication, observed = _time(self.publication_timestamp), _time(self.observation_timestamp)
        if publication > observed or observed > (now or datetime.now(timezone.utc)).astimezone(timezone.utc):
            raise ValueError("LOOK_AHEAD_REJECTED")
        if (not re.fullmatch(r"pro_[0-9a-f]{16}", self.observation_id) or not self.professional_id or
                self.asset_class not in ASSET_CLASSES or self.rights_status not in RIGHTS or
                self.source_type not in PROFESSIONAL_SOURCE_TYPES or not self.themes or not self.stated_thesis or not self.risks or
                not self.invalidation or not self.primary_evidence_reference or
                (self.later_accuracy_score is not None and not 0 <= self.later_accuracy_score <= 1)):
            raise ValueError("PROFESSIONAL_OBSERVATION_INVALID")

    @property
    def disclosure_delay_seconds(self) -> int:
        return int((_time(self.observation_timestamp) - _time(self.publication_timestamp)).total_seconds())

    def research_question(self) -> dict[str, Any]:
        self.validate()
        return {"observation_id": self.observation_id, "professional_id": self.professional_id,
            "asset_class": self.asset_class, "disclosure_delay_seconds": self.disclosure_delay_seconds,
            "state": "ATTRIBUTED_HYPOTHESIS", "primary_review_required": True, "authority": AUTHORITY.copy()}


def professional_source_registry() -> tuple[dict[str, Any], ...]:
    return (
        {"source_type":"SEC_13F","rights":"PUBLIC_OFFICIAL","disclosure_delay_required":True},
        {"source_type":"FORM_ADV","rights":"PUBLIC_OFFICIAL","disclosure_delay_required":True},
        {"source_type":"PUBLIC_LETTER","rights":"RIGHTS_REVIEW_REQUIRED","disclosure_delay_required":True},
        {"source_type":"PUBLIC_INTERVIEW","rights":"RIGHTS_REVIEW_REQUIRED","disclosure_delay_required":True},
        {"source_type":"FUND_ETF_HOLDINGS","rights":"RIGHTS_REVIEW_REQUIRED","disclosure_delay_required":True},
        {"source_type":"MARKET_VISION","rights":"RIGHTS_REVIEW_REQUIRED","trust":"SECONDARY_DOMAIN_EXPERT"},
        {"source_type":"KOYFIN_MANUAL_IMPORT","rights":"LICENSED_APPROVED","human_cockpit_only":True},
    )


def build_scoreboard(observations: tuple[ProfessionalObservation, ...], *, minimum_sample: int = 20) -> dict[str, Any]:
    for item in observations: item.validate()
    resolved = [x for x in observations if x.later_accuracy_score is not None]
    scores = [float(x.later_accuracy_score) for x in resolved]
    return {"observations_evaluated":len(resolved), "unresolved_observations":len(observations)-len(resolved),
        "hit_rate":sum(x >= .5 for x in scores)/len(scores) if scores else None,
        "return_distribution":"UNAVAILABLE", "drawdown_distribution":"UNAVAILABLE",
        "calibration":sum(scores)/len(scores) if scores else None,
        "average_disclosure_delay_seconds":sum(x.disclosure_delay_seconds for x in observations)//len(observations) if observations else None,
        "evidence_completeness":"INCOMPLETE" if any(x.rights_status=="RIGHTS_REVIEW_REQUIRED" for x in observations) else "COMPLETE",
        "regime_dependence":"UNRESOLVED", "sample_size_warning":len(resolved)<minimum_sample,
        "survivorship_bias_warning":True, "look_ahead_permitted":False,
        "investment_endorsement":False}


def fuse_candidate(observations: tuple[dict[str, Any], ...]) -> dict[str, Any]:
    valid=[]
    for row in observations:
        if not isinstance(row,dict) or set(row)!={"source_type","source_id","timestamp","signal","correlation_cluster"}:
            return {"state":"FAILED_CLOSED","reason":"OBSERVATION_CONTRACT_INVALID","authority":AUTHORITY.copy()}
        if row["source_type"] not in SOURCE_TYPES or not row["source_id"]: return {"state":"FAILED_CLOSED","reason":"OBSERVATION_CONTRACT_INVALID","authority":AUTHORITY.copy()}
        try: _time(row["timestamp"])
        except ValueError: return {"state":"FAILED_CLOSED","reason":"OBSERVATION_TIMESTAMP_INVALID","authority":AUTHORITY.copy()}
        valid.append(row)
    sources={x["source_type"] for x in valid}; signals={x["signal"] for x in valid}
    duplicates=len(valid)-len({(x["source_type"],x["source_id"]) for x in valid})
    ready={"IIOS_SCANNER","HISTORICAL_PATTERN"} <= sources
    return {"state":"PRIMARY_REVIEW_REQUIRED" if ready else "INCOMPLETE",
        "agreements":max(0,len(valid)-len(signals)), "contradictions":max(0,len(signals)-1),
        "missing_evidence":sorted({"IIOS_SCANNER","HISTORICAL_PATTERN"}-sources),
        "stale_evidence":0, "correlated_duplicates":duplicates,
        "independent_source_count":len({(x["source_type"],x["source_id"]) for x in valid}),
        "confidence_decomposition":{kind:sum(x["source_type"]==kind for x in valid) for kind in sorted(SOURCE_TYPES)},
        "professional_opinion_sufficient":False, "authority":AUTHORITY.copy()}


def browser_projection(*, lane_states: dict[str,str], professional_count: int, scoreboard: dict[str,Any],
                       sleeve_count: int, consolidated_nav: float, candidate_state: str) -> dict[str,Any]:
    expected={x.lane_id for x in LANES}
    states={"AVAILABLE","AVAILABLE_EMPTY","STALE","INCOMPLETE","UNAVAILABLE","FAILED_CLOSED"}
    scoreboard_fields={"observations_evaluated","unresolved_observations","hit_rate","return_distribution",
        "drawdown_distribution","calibration","average_disclosure_delay_seconds","evidence_completeness",
        "regime_dependence","sample_size_warning","survivorship_bias_warning","look_ahead_permitted","investment_endorsement"}
    if set(lane_states)!=expected or any(v not in states for v in lane_states.values()):
        raise ValueError("MULTI_ASSET_PROJECTION_INVALID")
    if (candidate_state not in states or set(scoreboard)!=scoreboard_fields or
            any(not isinstance(x,int) or isinstance(x,bool) or x<0 for x in (professional_count,sleeve_count)) or
            consolidated_nav != 10_000 or scoreboard.get("investment_endorsement") is not False or
            scoreboard.get("look_ahead_permitted") is not False):
        raise ValueError("MULTI_ASSET_PROJECTION_INVALID")
    return {"schema_version":SCHEMA_VERSION,"state":candidate_state,"lane_states":dict(sorted(lane_states.items())),
        "professional_observation_count":professional_count,"scoreboard":scoreboard,
        "paper_sleeve_count":sleeve_count,"consolidated_paper_nav":consolidated_nav,
        "provider_status":"NOT_ACTIVATED","queue_depth":0,"last_successful_cycle":None,
        "failure_reasons":[],"authority":AUTHORITY.copy()}
