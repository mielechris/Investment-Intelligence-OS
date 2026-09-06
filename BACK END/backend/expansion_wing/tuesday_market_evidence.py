from __future__ import annotations

import hashlib
import json
import statistics
from dataclasses import field
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

from .multi_product_research import PRODUCTS

SCHEMA_VERSION = "iios-tuesday-market-evidence-v1"
DERIVATION_VERSION = "iios-market-derivations-v1"
COST_MODEL_VERSION = "iios-paper-cost-assumption-v1"
CONTROLLER_VERSION = "iios-tuesday-observation-controller-v1"
FORWARD_MODE = "FORWARD_ONLY_UNADJUSTED_OBSERVATION"
AUTHORITY = {"provider": False, "credential": False, "broker": False, "ledger_write": False,
             "paper_order": False, "live_execution": False, "automatic_promotion": False}

PILOT_INSTRUMENTS = (
    ("MU", "NASDAQ:MU", "us_large_cap_equities", "COMMON_STOCK"),
    ("SPY", "ARCX:SPY", "broad_factor_etfs", "ETF"),
    ("XLK", "ARCX:XLK", "sector_thematic_etfs", "ETF"),
    ("VNQ", "ARCX:VNQ", "reits_listed_real_estate", "ETF"),
    ("TLT", "NASDAQ:TLT", "treasury_etf_duration_proxies", "ETF"),
    ("GLD", "ARCX:GLD", "commodity_etf_etc_proxies", "ETF"),
    ("UUP", "ARCX:UUP", "currency_etfs_fx_proxies", "ETF"),
    ("IBIT", "NASDAQ:IBIT", "crypto_etfs_listed_proxies", "ETF"),
    ("PFF", "NASDAQ:PFF", "preferred_income_securities", "ETF"),
    ("BIL", "ARCX:BIL", "money_market_ultra_short", "ETF"),
)

METHOD_ADJUSTMENT_REQUIREMENTS = {
    "MEAN_REVERSION": "ADJUSTED_HISTORY_REQUIRED",
    "HISTORICAL_MOMENTUM": "ADJUSTED_HISTORY_REQUIRED",
    "TREND_FOLLOWING": "ADJUSTED_HISTORY_REQUIRED",
    "PAIRS_RELATIVE_VALUE_HISTORY": "ADJUSTED_HISTORY_REQUIRED",
    "BACKTESTED_VOLATILITY": "ADJUSTED_HISTORY_REQUIRED",
    "HISTORICAL_DRAWDOWN": "ADJUSTED_HISTORY_REQUIRED",
    "HISTORICAL_TOTAL_RETURN": "ADJUSTED_HISTORY_REQUIRED",
    "HISTORICAL_CALIBRATION": "ADJUSTED_HISTORY_REQUIRED",
    "LONG_HORIZON_FUNDAMENTAL": "FORWARD_POTENTIALLY_ELIGIBLE",
    "EVENT_DRIVEN": "FORWARD_POTENTIALLY_ELIGIBLE",
    "CATALYST_NEWS_REACTION": "FORWARD_POTENTIALLY_ELIGIBLE",
    "POLICY_MACRO_REGIME": "FORWARD_POTENTIALLY_ELIGIBLE",
    "PROFESSIONAL_METHOD": "FORWARD_WITH_INDEPENDENT_CORROBORATION",
    "FORWARD_PRICE_TRACKING": "FORWARD_POTENTIALLY_ELIGIBLE",
}


def method_adjustment_decision(method: str, *, adjustment_state: str,
                               independent_corroboration: bool = False) -> dict[str, Any]:
    requirement = METHOD_ADJUSTMENT_REQUIREMENTS.get(method)
    if requirement is None:
        return {"eligible": False, "reason": "METHOD_NOT_GOVERNED"}
    if requirement == "ADJUSTED_HISTORY_REQUIRED" and adjustment_state == "UNSPECIFIED":
        return {"eligible": False, "reason": "ADJUSTMENT_BASIS_UNSPECIFIED"}
    if requirement == "FORWARD_WITH_INDEPENDENT_CORROBORATION" and not independent_corroboration:
        return {"eligible": False, "reason": "INDEPENDENT_CORROBORATION_REQUIRED"}
    return {"eligible": True, "reason": None, "mode": FORWARD_MODE}


def forward_eligibility(evidence: dict[str, Any], *, thesis_evidence: bool, invalidation: bool,
                        candidate_id: str | None, committee_approved: bool, risk_approved: bool,
                        corporate_action_state: str = "CLEAR") -> dict[str, Any]:
    requirements = {
        "ENTITLEMENT": evidence.get("license") == "INTERNAL_PRIVATE_RESEARCH",
        "CURRENT_SNAPSHOT": evidence.get("freshness") == "CURRENT" and evidence.get("observed", {}).get("snapshot_available") is True,
        "IDENTITY": isinstance(evidence.get("instrument"), dict) and bool(evidence["instrument"].get("instrument_id")),
        "TIMESTAMPS": bool(evidence.get("observed", {}).get("provider_timestamp") and evidence.get("observed", {}).get("retrieved_at")),
        "MARKET_SESSION": evidence.get("market_session") == "REGULAR",
        "CURRENT_PRICE": evidence.get("observed", {}).get("price_available") is True,
        "LIQUIDITY_PROXY": evidence.get("liquidity_proxy_state") == "DAILY_VOLUME_PROXY_AVAILABLE",
        "COST_MODEL": evidence.get("paper_cost_assumption", {}).get("classification") == "PAPER_COST_ASSUMPTION_NOT_MARKET_QUOTE",
        "BENCHMARK": bool(evidence.get("benchmark")), "THESIS": thesis_evidence, "INVALIDATION": invalidation,
        "IMMUTABLE_CANDIDATE": bool(candidate_id), "RESEARCH": evidence.get("research_eligible") is True,
        "COMMITTEE": committee_approved, "RISK": risk_approved, "CORPORATE_ACTION": corporate_action_state == "CLEAR",
        "AUTHORITY_LOCK": evidence.get("authority") == AUTHORITY,
    }
    failed = [name for name, passed in requirements.items() if not passed]
    return {"mode": FORWARD_MODE, "synthetic_paper_eligible": not failed,
        "operational_paper_eligible": False, "failed_requirements": failed,
        "historical_return_claim": False, "total_return_claim": False, "authority": AUTHORITY.copy()}


def prospective_mark(state: dict[str, Any], *, timestamp: str, source_hash: str,
                     corporate_action: str = "NONE") -> dict[str, Any]:
    if corporate_action not in {"NONE", "SPLIT", "DIVIDEND", "MERGER", "TICKER_CHANGE", "UNRECONCILED"}:
        raise ValueError("CORPORATE_ACTION_STATE_INVALID")
    if corporate_action != "NONE":
        return {"state": "SUSPENDED", "outcome": "INCOMPLETE_CORPORATE_ACTION", "marks": tuple(state.get("marks", ())),
            "retroactive_rewrite": False, "normalization_event_required": True, "authority": AUTHORITY.copy()}
    _time(timestamp)
    previous = tuple(state.get("marks", ()))
    if previous and _time(timestamp) <= _time(previous[-1]["timestamp"]):
        raise ValueError("PROSPECTIVE_MARK_ORDER_INVALID")
    return {"state": "OBSERVING", "outcome": None,
        "marks": previous + ({"timestamp": timestamp, "source_hash": source_hash},),
        "retroactive_rewrite": False, "normalization_event_required": False, "authority": AUTHORITY.copy()}


PHASES = ("PREMARKET_LOCKED", "OPENING_EVIDENCE_COLLECTION", "HUMAN_CANDIDATE_REVIEW",
          "FORWARD_OBSERVATION_ACTIVE", "INTRADAY_MARK", "CLOSING_MARK", "POST_CLOSE_AUDIT",
          "FAILED_CLOSED")
_TRANSITIONS = {
    "PREMARKET_LOCKED": {"OPENING_EVIDENCE_COLLECTION"},
    "OPENING_EVIDENCE_COLLECTION": {"HUMAN_CANDIDATE_REVIEW"},
    "HUMAN_CANDIDATE_REVIEW": {"FORWARD_OBSERVATION_ACTIVE"},
    "FORWARD_OBSERVATION_ACTIVE": {"INTRADAY_MARK"}, "INTRADAY_MARK": {"CLOSING_MARK"},
    "CLOSING_MARK": {"POST_CLOSE_AUDIT"}, "POST_CLOSE_AUDIT": set(), "FAILED_CLOSED": set(),
}


@dataclass
class TuesdayController:
    enabled: bool = False
    phase: str = "PREMARKET_LOCKED"
    consumed_by_instrument: dict[str, int] = field(default_factory=dict)
    observation_ids: set[str] = field(default_factory=set)
    marks: tuple[dict[str, Any], ...] = ()
    lock_owner: str | None = None

    def readiness(self) -> dict[str, Any]:
        return {"enabled": self.enabled, "phase": self.phase, "fixed_instruments": tuple(x[0] for x in PILOT_INSTRUMENTS),
            "maximum_credits": 30, "maximum_per_instrument": 3, "no_retry": True, "redirects": False,
            "timeout_seconds": 10, "maximum_response_bytes": 1_000_000, "single_flight": True,
            "owner_only_state": True, "append_only": True, "raw_response_retention": False,
            "browser_provider_values": False, "graceful_recovery": True, "authority": AUTHORITY.copy()}

    def transition(self, target: str, *, human_candidate_review: bool = False, valid_input: bool = True) -> str:
        if target not in PHASES or not valid_input or target not in _TRANSITIONS[self.phase]:
            self.phase = "FAILED_CLOSED"; return self.phase
        if target == "FORWARD_OBSERVATION_ACTIVE" and not human_candidate_review:
            self.phase = "FAILED_CLOSED"; return self.phase
        self.phase = target; return self.phase

    def reserve(self, ticker: str, observation_id: str, *, owner_authorized: bool, entitlement: bool,
                session_open: bool) -> str:
        if not self.enabled or not owner_authorized or not entitlement or not session_open:
            return "CREDENTIAL_ACCESS_PROHIBITED"
        governed = {row[0] for row in PILOT_INSTRUMENTS}
        used = sum(self.consumed_by_instrument.values())
        if ticker not in governed or observation_id in self.observation_ids or used >= 30 or self.consumed_by_instrument.get(ticker, 0) >= 3:
            self.phase = "FAILED_CLOSED"; return "BUDGET_IDENTITY_OR_DUPLICATE_REJECTED"
        self.observation_ids.add(observation_id); self.consumed_by_instrument[ticker] = self.consumed_by_instrument.get(ticker, 0) + 1
        return "RESERVED"


def synthetic_forward_receipt(*, observation_id: str, instrument_id: str, product_id: str,
                              thesis_id: str, benchmark: str, timestamp: str, modeled_cost_bps: float,
                              synthetic_quantity: float, invalidation: str, committee_receipt: str,
                              risk_receipt: str, corporate_action_state: str,
                              evidence_lineage: tuple[str, ...]) -> dict[str, Any]:
    if (not all(isinstance(x, str) and x for x in (observation_id, instrument_id, product_id, thesis_id,
            benchmark, invalidation, committee_receipt, risk_receipt)) or corporate_action_state != "CLEAR"
            or not evidence_lineage or modeled_cost_bps < 0 or synthetic_quantity <= 0):
        raise ValueError("SYNTHETIC_OBSERVATION_CONTRACT_INVALID")
    _time(timestamp)
    return {"schema_version": "iios-synthetic-forward-observation-v1", "classification": "SYNTHETIC_PAPER_RESEARCH",
        "observation_id": observation_id, "instrument_id": instrument_id, "product_id": product_id,
        "thesis_id": thesis_id, "benchmark": benchmark, "timestamp": timestamp,
        "modeled_cost_bps": modeled_cost_bps, "synthetic_quantity": synthetic_quantity,
        "invalidation": invalidation, "committee_receipt": committee_receipt, "risk_receipt": risk_receipt,
        "corporate_action_state": corporate_action_state, "evidence_lineage": evidence_lineage,
        "operational_position": False, "order": False, "fill": False, "transaction": False,
        "ledger_write": False, "recommendation": False, "authority": AUTHORITY.copy()}


def monday_rehearsal() -> dict[str, Any]:
    return {"schema_version": "iios-superbatch24-monday-rehearsal-v1", "date": "2026-09-07",
        "market_state": "CLOSED_HOLIDAY", "controller": "DISABLED", "provider_requests": 0,
        "credits_consumed": 0, "keychain_access": False, "candidates_created": 0,
        "synthetic_positions": 0, "operational_positions": 0, "orders": 0, "fills": 0,
        "transactions": 0, "ledger_entries": 0, "pilot_rooms": 10, "unavailable_rooms": 14,
        "historical_methods": "ADJUSTMENT_BASIS_UNSPECIFIED", "next_phase": "TUESDAY_PREMARKET_PREPARATION",
        "browser_provider_invocation": False, "projection_sequence_mutation": False,
        "authority": AUTHORITY.copy()}


def post_close_report(*, instrument_accounting: dict[str, dict[str, int]]) -> dict[str, Any]:
    unknown = set(instrument_accounting) - {row[0] for row in PILOT_INSTRUMENTS}
    if unknown or any(not isinstance(value, dict) or set(value) != {"requests", "credits"}
                      or value["requests"] < 0 or value["credits"] < 0 for value in instrument_accounting.values()):
        raise ValueError("POST_CLOSE_ACCOUNTING_INVALID")
    return {"schema_version": "iios-tuesday-post-close-report-v1", "instrument_accounting": instrument_accounting,
        "current_evidence_count": 0, "human_candidates": [], "accepted_observations": [],
        "rejected_observations": [], "committee_decisions": [], "risk_decisions": [],
        "synthetic_sleeve_nav": None, "synthetic_sleeve_cash": None, "modeled_costs": [],
        "corporate_action_suspensions": [], "unresolved_blockers": ["CURRENT_TUESDAY_EVIDENCE_REQUIRED"],
        "sample_state": "INSUFFICIENT_SAMPLE", "drawdown": None, "calibration": None, "outcomes": None,
        "operational_paper_mutated": False, "protected_services_mutated": False, "profitability_claim": False,
        "authority": AUTHORITY.copy()}


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=True).encode("ascii")).hexdigest()


def _time(value: str) -> datetime:
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        raise ValueError("TIMESTAMP_INVALID") from None
    if result.tzinfo is None:
        raise ValueError("TIMESTAMP_INVALID")
    return result.astimezone(timezone.utc)


@dataclass(frozen=True)
class DerivedValue:
    name: str
    value: float | None
    formula_version: str
    input_timestamps: tuple[str, ...]
    input_hashes: tuple[str, ...]
    lookback: str
    units: str
    missing_input_behavior: str
    effective_timestamp: str | None


@dataclass(frozen=True)
class PaperCostAssumption:
    product_id: str
    version: str
    observed_spread_bps: float | None
    estimated_spread_bps: float | None
    slippage_bps: float
    commission_fee_bps: float
    total_modeled_cost_bps: float
    classification: str = "PAPER_COST_ASSUMPTION_NOT_MARKET_QUOTE"
    actual_bid_ask_available: bool = False


def paper_cost_assumption(product_id: str, *, estimated_spread_bps: float | None = None,
                          slippage_bps: float = 10.0, fee_bps: float = 1.0) -> PaperCostAssumption:
    if product_id not in {item.product_id for item in PRODUCTS}:
        raise ValueError("PRODUCT_NOT_GOVERNED")
    if any(isinstance(x, bool) or not isinstance(x, (int, float)) or x < 0
           for x in (slippage_bps, fee_bps)):
        raise ValueError("COST_ASSUMPTION_INVALID")
    spread = 15.0 if estimated_spread_bps is None else estimated_spread_bps
    if isinstance(spread, bool) or not isinstance(spread, (int, float)) or spread < 0:
        raise ValueError("COST_ASSUMPTION_INVALID")
    return PaperCostAssumption(product_id, COST_MODEL_VERSION, None, float(spread),
        float(slippage_bps), float(fee_bps), float(spread + slippage_bps + fee_bps))


def derive_liquidity(rows: list[dict[str, Any]], *, lookback: int = 20) -> dict[str, DerivedValue]:
    selected = rows[-lookback:]
    if not selected or any(not isinstance(row, dict) or not isinstance(row.get("volume"), (int, float))
                           or isinstance(row.get("volume"), bool) or row["volume"] < 0
                           or not isinstance(row.get("close"), (int, float)) or isinstance(row.get("close"), bool)
                           or row["close"] < 0 or not isinstance(row.get("time"), str) for row in selected):
        unavailable = DerivedValue("UNAVAILABLE", None, DERIVATION_VERSION, (), (), f"{lookback}_OBSERVATIONS",
            "UNAVAILABLE", "RETURN_UNAVAILABLE", None)
        return {"median_daily_volume": unavailable, "median_daily_dollar_volume": unavailable,
                "close_to_close_volatility": unavailable}
    timestamps = tuple(row["time"] for row in selected)
    for timestamp in timestamps:
        _time(timestamp)
    hashes = tuple(_hash(row) for row in selected)
    effective = max(timestamps, key=_time)
    common = dict(formula_version=DERIVATION_VERSION, input_timestamps=timestamps, input_hashes=hashes,
                  lookback=f"{len(selected)}_OBSERVATIONS", missing_input_behavior="RETURN_UNAVAILABLE",
                  effective_timestamp=effective)
    closes = [float(row["close"]) for row in selected]
    returns = [(closes[index] / closes[index - 1]) - 1 for index in range(1, len(closes)) if closes[index - 1] > 0]
    volatility = statistics.stdev(returns) if len(returns) >= 2 else None
    return {
        "median_daily_volume": DerivedValue("MEDIAN_DAILY_VOLUME", float(statistics.median(row["volume"] for row in selected)), units="SHARES", **common),
        "median_daily_dollar_volume": DerivedValue("MEDIAN_DAILY_DOLLAR_VOLUME", float(statistics.median(row["volume"] * row["close"] for row in selected)), units="USD", **common),
        "close_to_close_volatility": DerivedValue("SAMPLE_STANDARD_DEVIATION_CLOSE_TO_CLOSE_RETURNS", volatility,
            units="DECIMAL_RETURN", **common),
    }


def adjustment_contract(documented_basis: str | None) -> dict[str, Any]:
    mapping = {"RAW": "RAW", "SPLIT_ADJUSTED": "SPLIT_ADJUSTED", "DIVIDEND_ADJUSTED": "DIVIDEND_ADJUSTED",
               "FULLY_ADJUSTED": "FULLY_ADJUSTED"}
    state = mapping.get(documented_basis or "", "UNSPECIFIED")
    return {"adjustment_state": state, "adjusted_history_available": state != "UNSPECIFIED",
            "adjusted_history_method_eligible": state != "UNSPECIFIED", "missing_behavior": "UNAVAILABLE"}


def composite_evidence(*, instrument: dict[str, Any], snapshot: dict[str, Any] | None,
                       history: list[dict[str, Any]] | None, adjustment_basis: str | None,
                       observed_at: str, retrieved_at: str, credits: int) -> dict[str, Any]:
    if not isinstance(instrument, dict) or not {"ticker", "instrument_id", "product_id", "security_type"} <= set(instrument):
        raise ValueError("INSTRUMENT_IDENTITY_INVALID")
    if (instrument["ticker"], instrument["instrument_id"], instrument["product_id"], instrument["security_type"]) not in PILOT_INSTRUMENTS:
        raise ValueError("INSTRUMENT_NOT_GOVERNED")
    if credits < 0 or credits > 3 or _time(observed_at) > _time(retrieved_at):
        raise ValueError("ACCOUNTING_OR_POINT_IN_TIME_INVALID")
    adjustment = adjustment_contract(adjustment_basis)
    liquidity = derive_liquidity(history or [])
    cost = paper_cost_assumption(instrument["product_id"])
    current = bool(snapshot) and (_time(retrieved_at) - _time(observed_at)).total_seconds() <= 900
    history_available = bool(history)
    missing = []
    if not snapshot: missing.append("SNAPSHOT")
    if not history_available: missing.append("HISTORICAL_OHLCV")
    if not adjustment["adjusted_history_available"]: missing.append("ADJUSTMENT_BASIS")
    payload = {"schema_version": SCHEMA_VERSION, "instrument": instrument, "observed": {
        "snapshot_available": bool(snapshot), "historical_ohlcv_available": history_available,
        "price_available": bool(snapshot),
        "provider_timestamp": observed_at, "retrieved_at": retrieved_at,
        "adjustment_state": adjustment["adjustment_state"]},
        "derived": {key: asdict(value) for key, value in liquidity.items()}, "paper_cost_assumption": asdict(cost),
        "freshness": "CURRENT" if current else "STALE" if snapshot else "UNAVAILABLE",
        "missing_fields": missing, "credits": credits, "provider": "FINANCIAL_DATASETS",
        "market_session": "REGULAR" if current else "CLOSED_OR_STALE",
        "liquidity_proxy_state": "DAILY_VOLUME_PROXY_AVAILABLE" if history_available else "UNAVAILABLE",
        "liquidity_scope": "DAILY_VOLUME_PROXY_NOT_ORDER_BOOK",
        "license": "INTERNAL_PRIVATE_RESEARCH", "primary_source_verification_required": True,
        "research_eligible": current and history_available,
        "forward_mode": FORWARD_MODE,
        "benchmark": next(item.benchmark for item in PRODUCTS if item.product_id == instrument["product_id"]),
        "adjusted_history_method_eligible": current and history_available and adjustment["adjusted_history_method_eligible"],
        "paper_research_eligible": False, "authority": AUTHORITY.copy()}
    payload["evidence_hash"] = _hash(payload)
    return payload


def controller_plan(*, instruments: int, observations_per_instrument: int, credits_remaining: int,
                    market_day: bool) -> dict[str, Any]:
    expected = instruments * observations_per_instrument
    permitted = market_day and instruments <= len(PILOT_INSTRUMENTS) and observations_per_instrument <= 3 \
        and expected <= 30 and expected <= credits_remaining
    return {"schema_version": CONTROLLER_VERSION, "enabled": False, "activation_state": "DISABLED",
        "single_flight": True, "provider": "FINANCIAL_DATASETS", "fixed_registry": True,
        "cadence": ("OPENING_CURRENT_EVIDENCE", "BOUNDED_INTRADAY_MARK", "CLOSING_POST_MARKET_MARK"),
        "expected_credits": expected, "hard_batch_ceiling": 30, "hard_per_instrument_ceiling": 3,
        "budget_valid": permitted, "market_state": "OPENING_DAY" if market_day else "CLOSED_HOLIDAY",
        "browser_control": False, "service_control": False, "automatic_retry": False,
        "authority": AUTHORITY.copy()}


def synthetic_observation(evidence: dict[str, Any], *, candidate_id: str | None) -> dict[str, Any]:
    eligible = bool(candidate_id and evidence.get("research_eligible") and evidence.get("paper_research_eligible")
                    and not evidence.get("missing_fields"))
    return {"state": "SYNTHETIC_OBSERVATION_ELIGIBLE" if eligible else "BLOCKED",
        "modeled_position": None, "operational_position": False, "order": False, "fill": False,
        "transaction": False, "broker_request": False, "ledger_write": False, "authority": AUTHORITY.copy()}


def product_board(records: list[dict[str, Any]], *, next_observation: str | None) -> list[dict[str, Any]]:
    by_product = {row.get("instrument", {}).get("product_id"): row for row in records if isinstance(row, dict)}
    result = []
    for product in PRODUCTS:
        row = by_product.get(product.product_id)
        result.append({"product_id": product.product_id, "source": "FINANCIAL_DATASETS" if row else "UNAVAILABLE",
            "entitlement": "CREDITS_INTERNAL_USE" if row else "NOT_VERIFIED", "last_observation": row.get("observed", {}).get("provider_timestamp") if row else None,
            "freshness": row.get("freshness") if row else "UNAVAILABLE", "completeness": "COMPLETE" if row and not row.get("missing_fields") else "INCOMPLETE",
            "classification": "PAPER_TEST_READY_FORWARD_ONLY" if row and row.get("forward_eligible") else "RESEARCH_ONLY" if row else "UNAVAILABLE", "credits_used": row.get("credits") if row else None,
            "evidence_fields_available": ["SNAPSHOT"] if row and row.get("observed", {}).get("snapshot_available") else [],
            "missing_fields": row.get("missing_fields") if row else ["AUTHENTICATED_EVIDENCE"],
            "research_eligible": bool(row and row.get("research_eligible")), "paper_research_eligible": False,
            "synthetic_activity": False, "forward_only_paper_research": FORWARD_MODE if row else "UNAVAILABLE",
            "current_snapshot": row.get("freshness") if row else "UNAVAILABLE",
            "historical_adjustment": row.get("observed", {}).get("adjustment_state") if row else "UNAVAILABLE",
            "historical_signal_methods": "BLOCKED" if row and row.get("observed", {}).get("adjustment_state") == "UNSPECIFIED" else "UNAVAILABLE",
            "liquidity_evidence": row.get("liquidity_proxy_state") if row else "UNAVAILABLE", "observed_bid_ask": "UNAVAILABLE",
            "paper_cost": "MODELED_ASSUMPTION" if row else "UNAVAILABLE", "operational_eligibility": False,
            "corporate_action_monitoring": "REQUIRED" if row else "UNAVAILABLE",
            "synthetic_eligibility": bool(row and row.get("forward_eligible")),
            "blocker": None if row and row.get("forward_eligible") else "CURRENT_FORWARD_CONTRACT_REQUIRED",
            "next_scheduled_observation": next_observation, "authority": AUTHORITY.copy()})
    return result


def mu_tuesday_template() -> dict[str, Any]:
    return {"instrument_id": "NASDAQ:MU", "product_room": "U.S. Large-Cap Equities",
        "mode": FORWARD_MODE, "starting_synthetic_sleeve": 10_000,
        "candidate_state": "WAITING_FOR_CURRENT_TUESDAY_EVIDENCE", "thesis_class": "FUNDAMENTAL_DISLOCATION_REBOUND",
        "methods": ["LONG_HORIZON_FUNDAMENTAL", "CATALYST_NEWS_REACTION", "MEAN_REVERSION"],
        "required_evidence": ["CURRENT_COMPOSITE", "PRIMARY_THESIS_EVIDENCE", "LIQUIDITY", "COST_MODEL", "IMMUTABLE_CANDIDATE"],
        "bear_case_required": True, "invalidation_required": True, "holding_period": "HYPOTHESIS_PENDING_REVIEW",
        "benchmark": "SP500", "committee_required": True, "risk_required": True,
        "entry_price": None, "share_count": None, "stop": None, "target": None, "size": None,
        "position": None, "return": None, "recommendation": None,
        "authority": AUTHORITY.copy()}
