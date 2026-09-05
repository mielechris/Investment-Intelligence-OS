from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, time, timezone
from typing import Any
from zoneinfo import ZoneInfo

SCHEMA_VERSION = "iios-multi-product-research-floor-v1"
PASSPORT_SCHEMA = "iios-cross-asset-opportunity-passport-v1"
OBSERVATION_SCHEMA = "iios-professional-method-observation-v1"
SLEEVE_SCHEMA = "iios-parallel-research-sleeve-v1"
FIXTURE_LABEL = "FIXTURE / NON-LIVE / RESEARCH ONLY"
AUTHORITY = {
    "provider": False,
    "credential": False,
    "automatic_promotion": False,
    "paper_order": False,
    "broker": False,
    "ledger_write": False,
    "live_execution": False,
}
TRUTH_STATES = frozenset({"CURRENT", "STALE", "INCOMPLETE", "UNAVAILABLE", "FAILED_CLOSED", "RESEARCH_ONLY_UNPRICEABLE"})


def _timestamp(value: Any) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        raise ValueError("TIMESTAMP_INVALID") from None
    if parsed.tzinfo is None:
        raise ValueError("TIMESTAMP_INVALID")
    return parsed.astimezone(timezone.utc)


def _hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()


FAMILY_REQUIREMENTS: dict[str, tuple[str, ...]] = {
    "EQUITY_ETF": ("instrument_id", "exchange", "observed_at", "price_basis", "volume", "liquidity", "corporate_action_basis", "market_session", "source_category", "provenance_hash", "benchmark", "spread_bps", "slippage_bps"),
    "TREASURY": ("instrument_id", "security_type", "issue_date", "maturity_date", "coupon", "price_basis", "yield", "yield_convention", "duration", "convexity", "accrued_interest_basis", "settlement_convention", "run_classification", "liquidity", "observed_at", "provenance_hash"),
    "CREDIT": ("instrument_id", "issuer", "maturity_date", "coupon", "price_basis", "yield", "yield_convention", "duration", "credit_quality", "callable_status", "security_type", "quote_basis", "liquidity", "tax_treatment_basis", "observed_at", "provenance_hash"),
    "OPTION": ("instrument_id", "underlying_id", "expiration", "strike", "option_type", "exercise_style", "multiplier", "bid", "ask", "mark", "open_interest", "volume", "implied_volatility", "delta", "gamma", "theta", "vega", "assignment_risk", "early_exercise", "maximum_modeled_loss", "break_even", "spread_bps", "fees", "slippage_bps", "observed_at", "underlying_observed_at", "provenance_hash"),
    "COMMODITY": ("instrument_id", "underlying_id", "exposure_classification", "contract_month", "multiplier", "tick_value", "settlement_basis", "expiry", "roll_policy", "term_structure", "carry_state", "proxy_tracking_basis", "liquidity", "observed_at", "licensing_status", "provenance_hash"),
    "FX": ("instrument_id", "currency_pair", "base_currency", "quote_currency", "exposure_classification", "observed_at", "bid", "ask", "session", "liquidity", "carry_basis", "rollover_basis", "proxy_tracking_basis", "provenance_hash"),
    "CRYPTO": ("instrument_id", "asset_id", "venue_reference", "exposure_classification", "calendar_policy", "observed_at", "price_basis", "liquidity", "custody_warning", "structural_risk_warning", "weekend_policy", "proxy_tracking_basis", "provenance_hash"),
    "INCOME": ("instrument_id", "distribution_yield_basis", "duration_rate_sensitivity", "liquidity", "call_redemption_terms", "expense_ratio", "premium_discount_basis", "credit_issuer_exposure", "observed_at", "provenance_hash"),
}


@dataclass(frozen=True)
class ProductDefinition:
    product_id: str
    display_name: str
    department: str
    family: str
    exposure_classification: str
    market_venue: str
    timezone: str
    calendar: str
    required_source_categories: tuple[str, ...]
    required_pricing_fields: tuple[str, ...]
    freshness_seconds: int
    liquidity_fields: tuple[str, ...]
    transaction_cost_fields: tuple[str, ...]
    risk_fields: tuple[str, ...]
    eligibility_rules: tuple[str, ...]
    benchmark: str
    paper_mark_frequency: str
    invalidation_requirements: tuple[str, ...]
    prohibited_assumptions: tuple[str, ...]
    licensing_status: str = "REVIEW_REQUIRED"
    operational_status: str = "NOT_ACTIVATED"
    permitted_research_modes: tuple[str, ...] = ("FIXTURE", "AUTHENTIC_READ_ONLY")


_PRODUCT_ROWS = (
    ("us_large_cap_equities", "U.S. Large-Cap Equities", "Multi-Product Trading Floor", "EQUITY_ETF", "DIRECT", "NYSE_NASDAQ", "America/New_York", "US_EQUITY", "SP500"),
    ("us_mid_cap_equities", "U.S. Mid-Cap Equities", "Multi-Product Trading Floor", "EQUITY_ETF", "DIRECT", "NYSE_NASDAQ", "America/New_York", "US_EQUITY", "SP400"),
    ("us_small_cap_equities", "U.S. Small-Cap Equities", "Multi-Product Trading Floor", "EQUITY_ETF", "DIRECT", "NYSE_NASDAQ", "America/New_York", "US_EQUITY", "RUSSELL2000"),
    ("international_developed_equities", "International Developed Equities", "Multi-Product Trading Floor", "EQUITY_ETF", "DIRECT", "MULTI_VENUE", "UTC", "LOCAL_EQUITY", "MSCI_EAFE"),
    ("emerging_market_equities", "Emerging-Market Equities", "Multi-Product Trading Floor", "EQUITY_ETF", "DIRECT", "MULTI_VENUE", "UTC", "LOCAL_EQUITY", "MSCI_EM"),
    ("sector_thematic_etfs", "Sector and Thematic ETFs", "Multi-Product Trading Floor", "EQUITY_ETF", "DIRECT", "NYSE_NASDAQ", "America/New_York", "US_EQUITY", "SP500"),
    ("broad_factor_etfs", "Broad-Market and Factor ETFs", "Multi-Product Trading Floor", "EQUITY_ETF", "DIRECT", "NYSE_NASDAQ", "America/New_York", "US_EQUITY", "SP500"),
    ("treasury_bills_cash", "U.S. Treasury Bills and Cash Equivalents", "Rates and Credit Vault", "TREASURY", "DIRECT", "US_TREASURY", "America/New_York", "US_BOND", "UST_BILL_INDEX"),
    ("treasury_notes_bonds", "U.S. Treasury Notes and Bonds", "Rates and Credit Vault", "TREASURY", "DIRECT", "US_TREASURY", "America/New_York", "US_BOND", "UST_AGGREGATE"),
    ("treasury_etf_duration_proxies", "Treasury ETFs and Duration Proxies", "Rates and Credit Vault", "EQUITY_ETF", "PROXY", "NYSE_NASDAQ", "America/New_York", "US_EQUITY", "UST_AGGREGATE"),
    ("investment_grade_corporate_bonds", "Investment-Grade Corporate Bonds", "Rates and Credit Vault", "CREDIT", "DIRECT", "US_BOND", "America/New_York", "US_BOND", "US_IG_INDEX"),
    ("high_yield_corporate_bonds", "High-Yield Corporate Bonds", "Rates and Credit Vault", "CREDIT", "DIRECT", "US_BOND", "America/New_York", "US_BOND", "US_HY_INDEX"),
    ("municipal_bonds_etfs", "Municipal Bonds and Municipal ETFs", "Rates and Credit Vault", "CREDIT", "DIRECT_OR_PROXY", "US_MUNICIPAL", "America/New_York", "US_BOND", "MUNI_INDEX"),
    ("listed_equity_etf_options", "Listed Equity and ETF Options", "Options Strategy Room", "OPTION", "DERIVATIVE", "US_OPTIONS", "America/New_York", "US_OPTIONS", "UNDERLYING_TOTAL_RETURN"),
    ("index_options", "Index Options", "Options Strategy Room", "OPTION", "DERIVATIVE", "US_OPTIONS", "America/New_York", "US_OPTIONS", "UNDERLYING_INDEX"),
    ("commodity_etf_etc_proxies", "Commodity ETFs and ETC Proxies", "Commodities and Currency Dock", "COMMODITY", "PROXY", "LISTED_PROXY", "America/New_York", "US_EQUITY", "COMMODITY_SPOT_REFERENCE"),
    ("commodity_futures_references", "Commodity Futures References", "Commodities and Currency Dock", "COMMODITY", "REFERENCE", "FUTURES_REFERENCE", "America/Chicago", "FUTURES", "COMMODITY_CONTINUOUS_REFERENCE"),
    ("fx_spot_references", "Foreign-Exchange Spot References", "Commodities and Currency Dock", "FX", "REFERENCE", "FX_REFERENCE", "UTC", "FX_WEEKLY", "CASH_RATE_DIFFERENTIAL"),
    ("currency_etfs_fx_proxies", "Currency ETFs and FX Proxies", "Commodities and Currency Dock", "FX", "PROXY", "NYSE_NASDAQ", "America/New_York", "US_EQUITY", "FX_SPOT_REFERENCE"),
    ("crypto_spot_references", "Crypto Spot References", "Digital Assets Night Desk", "CRYPTO", "REFERENCE", "CRYPTO_REFERENCE", "UTC", "CRYPTO_24_7", "CONSOLIDATED_SPOT_REFERENCE"),
    ("crypto_etfs_listed_proxies", "Crypto ETFs and Listed Proxies", "Digital Assets Night Desk", "CRYPTO", "PROXY", "NYSE_NASDAQ", "America/New_York", "US_EQUITY", "CRYPTO_SPOT_REFERENCE"),
    ("reits_listed_real_estate", "REITs and Listed Real-Estate Securities", "Real Assets and Income Office", "INCOME", "DIRECT", "NYSE_NASDAQ", "America/New_York", "US_EQUITY", "REIT_INDEX"),
    ("preferred_income_securities", "Preferred Stock and Income Securities", "Real Assets and Income Office", "INCOME", "DIRECT", "US_LISTED_INCOME", "America/New_York", "US_EQUITY", "PREFERRED_INDEX"),
    ("money_market_ultra_short", "Money-Market and Ultra-Short-Duration Products", "Real Assets and Income Office", "INCOME", "DIRECT_OR_PROXY", "US_CASH_MARKET", "America/New_York", "US_BOND", "T_BILL_RATE"),
)


def _product(row: tuple[str, ...]) -> ProductDefinition:
    product_id, display, department, family, classification, venue, tz, calendar, benchmark = row
    requirements = FAMILY_REQUIREMENTS[family]
    pricing = tuple(field for field in requirements if field in {"price_basis", "bid", "ask", "mark", "yield", "coupon", "strike", "implied_volatility", "distribution_yield_basis", "settlement_basis"})
    return ProductDefinition(product_id, display, department, family, classification, venue, tz, calendar,
        ("AUTHORIZED_MARKET_EVIDENCE", "PRIMARY_VERIFICATION"), pricing, 60 if family in {"OPTION", "FX", "CRYPTO"} else 900,
        tuple(field for field in requirements if field in {"volume", "liquidity", "open_interest"}),
        tuple(field for field in requirements if field in {"spread_bps", "fees", "slippage_bps", "expense_ratio", "rollover_basis"}),
        ("maximum_modeled_loss", "liquidity", "invalidation"),
        ("COMPLETE_PRODUCT_EVIDENCE", "CURRENT_FOR_SESSION", "HUMAN_REVIEW"), benchmark,
        "INTRADAY" if family in {"OPTION", "FX", "CRYPTO"} else "DAILY",
        ("explicit_condition", "time_horizon"),
        ("NO_PROXY_EQUIVALENCE", "NO_MISSING_VALUE_INFERENCE", "NO_AUTOMATIC_PROMOTION"))


PRODUCTS = tuple(_product(row) for row in _PRODUCT_ROWS)


@dataclass(frozen=True)
class MethodDefinition:
    method_id: str
    display_name: str
    department: str
    eligibility_rules: tuple[str, ...] = ("POINT_IN_TIME", "TRANSACTION_COSTS", "OUT_OF_SAMPLE", "HUMAN_REVIEW")
    operational_status: str = "NOT_ACTIVATED"
    automatic_promotion: bool = False


_METHOD_ROWS = (
    ("intraday_momentum", "Intraday Momentum", "Intraday Operations Desk"),
    ("opening_range_breakout", "Opening-Range/Breakout Research", "Intraday Operations Desk"),
    ("mean_reversion", "Mean Reversion", "Research Laboratory"),
    ("event_driven", "Event-Driven", "Research Laboratory"),
    ("catalyst_news_reaction", "Catalyst/News Reaction", "Research Laboratory"),
    ("trend_following", "Trend Following", "Research Laboratory"),
    ("relative_value", "Relative Value", "Relative-Value Workshop"),
    ("pairs_trading", "Pairs Trading", "Relative-Value Workshop"),
    ("yield_curve_duration", "Yield-Curve and Duration", "Rates and Credit Vault"),
    ("credit_spread", "Credit Spread", "Rates and Credit Vault"),
    ("volatility_options_structure", "Volatility and Options Structure", "Options Strategy Room"),
    ("income_cash_management", "Income/Cash Management", "Real Assets and Income Office"),
    ("tactical_asset_allocation", "Tactical Asset Allocation", "Cross-Asset Committee Chamber"),
    ("long_horizon_fundamental", "Long-Horizon Fundamental", "Multi-Product Trading Floor"),
    ("policy_macro_regime", "Policy/Macro Regime", "Cross-Asset Committee Chamber"),
    ("professional_method_replication", "Professional-Method Replication Research", "Professional Strategy Observatory"),
)
METHODS = tuple(MethodDefinition(*row) for row in _METHOD_ROWS)


def product_registry() -> tuple[ProductDefinition, ...]:
    return PRODUCTS


def method_registry() -> tuple[MethodDefinition, ...]:
    return METHODS


def validate_product_evidence(product_id: str, evidence: dict[str, Any], *, now: datetime | None = None) -> dict[str, Any]:
    product = next((item for item in PRODUCTS if item.product_id == product_id), None)
    if product is None or not isinstance(evidence, dict):
        return {"state": "FAILED_CLOSED", "reason": "PRODUCT_OR_EVIDENCE_INVALID", "authority": AUTHORITY.copy()}
    required = FAMILY_REQUIREMENTS[product.family]
    missing = tuple(field for field in required if evidence.get(field) in (None, "", (), []))
    if missing:
        state = "RESEARCH_ONLY_UNPRICEABLE" if product.family == "OPTION" else "INCOMPLETE"
        return {"state": state, "reason": "REQUIRED_FIELDS_MISSING", "missing_fields": missing, "authority": AUTHORITY.copy()}
    try:
        observed = _timestamp(evidence["observed_at"])
        clock = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        if observed > clock:
            raise ValueError("FUTURE_EVIDENCE")
        age = (clock - observed).total_seconds()
    except ValueError:
        return {"state": "FAILED_CLOSED", "reason": "EVIDENCE_TIMESTAMP_INVALID", "authority": AUTHORITY.copy()}
    if product.family == "OPTION":
        try:
            underlying = _timestamp(evidence["underlying_observed_at"])
        except ValueError:
            return {"state": "RESEARCH_ONLY_UNPRICEABLE", "reason": "UNSYNCHRONIZED_QUOTES", "authority": AUTHORITY.copy()}
        numeric = ("bid", "ask", "mark", "strike", "multiplier", "implied_volatility", "delta", "gamma", "theta", "vega", "maximum_modeled_loss")
        if any(isinstance(evidence[x], bool) or not isinstance(evidence[x], (int, float)) for x in numeric):
            return {"state": "RESEARCH_ONLY_UNPRICEABLE", "reason": "OPTION_NUMERIC_FIELD_INVALID", "authority": AUTHORITY.copy()}
        if evidence["bid"] < 0 or evidence["ask"] < evidence["bid"] or evidence["maximum_modeled_loss"] < 0:
            return {"state": "RESEARCH_ONLY_UNPRICEABLE", "reason": "OPTION_LOSS_OR_QUOTE_INVALID", "authority": AUTHORITY.copy()}
        if abs((observed - underlying).total_seconds()) > 5:
            return {"state": "RESEARCH_ONLY_UNPRICEABLE", "reason": "UNSYNCHRONIZED_QUOTES", "authority": AUTHORITY.copy()}
    if product.family == "CREDIT" and evidence.get("callable_status") == "CALLABLE" and not evidence.get("call_redemption_terms"):
        return {"state": "INCOMPLETE", "reason": "CALL_TERMS_REQUIRED", "authority": AUTHORITY.copy()}
    if product.family == "COMMODITY" and product.exposure_classification == "REFERENCE" and evidence.get("roll_policy") == "UNKNOWN":
        return {"state": "INCOMPLETE", "reason": "FUTURES_EXPIRY_ROLL_REQUIRED", "authority": AUTHORITY.copy()}
    state = "CURRENT" if age <= product.freshness_seconds else "STALE"
    return {"state": state, "reason": None if state == "CURRENT" else "PRICE_STALE", "evidence_hash": _hash(evidence),
        "research_eligible": state == "CURRENT", "paper_eligible": False, "authority": AUTHORITY.copy()}


US_HOLIDAYS = frozenset({"2026-09-07"})


def market_session(product_id: str, observed_at: str) -> dict[str, Any]:
    product = next((item for item in PRODUCTS if item.product_id == product_id), None)
    if product is None:
        return {"state": "FAILED_CLOSED", "reason": "PRODUCT_UNKNOWN"}
    moment = _timestamp(observed_at)
    if product.calendar == "CRYPTO_24_7":
        return {"state": "OPEN_24_7", "calendar": product.calendar, "evidence_required": True}
    if product.calendar == "FX_WEEKLY":
        weekday = moment.weekday()
        return {"state": "CLOSED" if weekday == 5 or (weekday == 6 and moment.hour < 21) else "OPEN_WEEKLY", "calendar": product.calendar, "evidence_required": True}
    local = moment.astimezone(ZoneInfo("America/New_York"))
    date = local.date().isoformat()
    if local.weekday() >= 5:
        state = "CLOSED_WEEKEND"
    elif date in US_HOLIDAYS:
        state = "CLOSED_HOLIDAY"
    elif local.time() < time(9, 30):
        state = "PRE_MARKET"
    elif local.time() < time(16):
        state = "REGULAR_SESSION"
    elif local.time() < time(20):
        state = "POST_MARKET"
    else:
        state = "CLOSED"
    return {"state": state, "calendar": product.calendar, "evidence_required": True}


@dataclass(frozen=True)
class CrossAssetPassport:
    candidate_id: str
    product_id: str
    method_id: str
    instrument_id: str
    underlying_id: str | None
    classification: str
    discovery_timestamp: str
    source_timestamps: tuple[str, ...]
    provenance_hashes: tuple[str, ...]
    market_session_state: str
    thesis: str
    catalyst: str
    opposing_case: str
    historical_analogue: str
    professional_observation_id: str | None
    liquidity: str
    volatility: str
    correlation: str
    spread_bps: float
    fees: float
    slippage_bps: float
    maximum_modeled_loss: float
    sizing_hypothesis: str
    invalidation: str
    holding_period: str
    benchmark: str
    missing_fields: tuple[str, ...] = ()
    research_eligible: bool = False
    paper_eligible: bool = False
    blocked_reason: str = "HUMAN_REVIEW_REQUIRED"
    schema_version: str = PASSPORT_SCHEMA
    authority: dict[str, bool] = field(default_factory=lambda: AUTHORITY.copy())

    def validate(self, *, now: datetime | None = None) -> None:
        product_ids, method_ids = {x.product_id for x in PRODUCTS}, {x.method_id for x in METHODS}
        clock = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        if (self.schema_version != PASSPORT_SCHEMA or not re.fullmatch(r"candidate_[0-9a-f]{20}", self.candidate_id)
                or self.product_id not in product_ids or self.method_id not in method_ids
                or self.classification not in {"DIRECT", "PROXY", "DERIVATIVE", "REFERENCE", "DIRECT_OR_PROXY"}
                or not self.instrument_id or not self.source_timestamps or not self.provenance_hashes
                or any(not re.fullmatch(r"[0-9a-f]{64}", value) for value in self.provenance_hashes)
                or any(_timestamp(value) > clock for value in (self.discovery_timestamp, *self.source_timestamps))
                or min(self.spread_bps, self.fees, self.slippage_bps, self.maximum_modeled_loss) < 0
                or not all((self.thesis, self.catalyst, self.opposing_case, self.historical_analogue,
                            self.liquidity, self.volatility, self.correlation, self.sizing_hypothesis,
                            self.invalidation, self.holding_period, self.benchmark, self.blocked_reason))
                or self.paper_eligible or self.authority != AUTHORITY or any(self.authority.values())):
            raise ValueError("CROSS_ASSET_PASSPORT_INVALID")

    def browser_safe(self, *, now: datetime | None = None) -> dict[str, Any]:
        self.validate(now=now)
        value = asdict(self)
        for field_name in ("thesis", "catalyst", "opposing_case", "historical_analogue", "sizing_hypothesis", "invalidation"):
            value.pop(field_name)
        value["professional_observation_present"] = value.pop("professional_observation_id") is not None
        return value


@dataclass(frozen=True)
class ProfessionalMethodObservation:
    observation_id: str
    professional_id: str
    source_id: str
    publication_timestamp: str
    effective_timestamp: str
    product_ids: tuple[str, ...]
    method_id: str
    stated_thesis: str
    stated_risks: tuple[str, ...]
    public_position_disclosure: str | None
    disclosure_delay_seconds: int
    conflict_disclosure: str
    rights_status: str
    point_in_time_available: bool
    corroboration_state: str
    later_outcome_state: str = "UNRESOLVED"
    schema_version: str = OBSERVATION_SCHEMA

    def validate(self, *, now: datetime | None = None) -> None:
        clock = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        product_ids, method_ids = {x.product_id for x in PRODUCTS}, {x.method_id for x in METHODS}
        publication, effective = _timestamp(self.publication_timestamp), _timestamp(self.effective_timestamp)
        if (self.schema_version != OBSERVATION_SCHEMA or not re.fullmatch(r"observation_[0-9a-f]{16}", self.observation_id)
                or not all((self.professional_id, self.source_id, self.stated_thesis, self.stated_risks, self.conflict_disclosure))
                or not self.product_ids or not set(self.product_ids) <= product_ids or self.method_id not in method_ids
                or publication > effective or effective > clock or self.disclosure_delay_seconds < 0
                or self.rights_status not in {"PUBLIC_OFFICIAL", "LICENSED_APPROVED", "RIGHTS_REVIEW_REQUIRED"}
                or self.corroboration_state not in {"UNAVAILABLE", "UNVERIFIED", "VERIFIED_UNCORROBORATED", "INDEPENDENTLY_CORROBORATED"}):
            raise ValueError("PROFESSIONAL_OBSERVATION_INVALID")

    def classification(self, *, now: datetime | None = None) -> dict[str, Any]:
        self.validate(now=now)
        return {"state": self.corroboration_state, "attributed_hypothesis": True,
            "professional_only_promotion": False, "endorsement": False, "authority": AUTHORITY.copy()}


PRODUCT_ACCOUNTING = {
    "TREASURY": ("accrual_basis", "duration_effect"), "CREDIT": ("accrual_basis", "duration_effect"),
    "OPTION": ("multiplier", "expiration", "assignment_basis"), "COMMODITY": ("multiplier", "margin_hypothesis", "roll_policy"),
    "FX": ("base_quote_basis", "carry_basis"), "CRYPTO": ("calendar_24_7_marks",),
    "EQUITY_ETF": ("dividend_distribution_basis", "expense_tracking_basis"),
    "INCOME": ("distribution_basis", "cash_yield_basis"),
}


@dataclass(frozen=True)
class ParallelResearchSleeve:
    sleeve_id: str
    product_id: str
    method_id: str
    modeled_capital_basis: float
    modeled_entry_time: str
    evidence_at_entry_hash: str
    instrument_id: str
    modeled_price_basis: str
    spread_bps: float
    fees: float
    slippage_bps: float
    size_hypothesis: str
    maximum_modeled_loss: float
    invalidation: str
    exit_rules: str
    holding_period: str
    mark_frequency: str
    benchmark: str
    favorable_excursion: float | None
    adverse_excursion: float | None
    realized_outcome: float | None
    unrealized_outcome: float | None
    drawdown: float | None
    attribution: str
    data_completeness: str
    warnings: tuple[str, ...]
    accounting: dict[str, Any]
    schema_version: str = SLEEVE_SCHEMA


class MultiProductPaperLaboratory:
    def __init__(self, *, comparison_capital: float = 10_000.0) -> None:
        if comparison_capital <= 0:
            raise ValueError("COMPARISON_CAPITAL_INVALID")
        self.comparison_capital = comparison_capital
        self._sleeves: dict[str, ParallelResearchSleeve] = {}

    def add(self, sleeve: ParallelResearchSleeve, *, operational_paper: dict[str, Any]) -> dict[str, Any]:
        product = next((item for item in PRODUCTS if item.product_id == sleeve.product_id), None)
        if product is None or sleeve.method_id not in {x.method_id for x in METHODS} or sleeve.schema_version != SLEEVE_SCHEMA:
            return {"state": "FAILED_CLOSED", "reason": "SLEEVE_REGISTRY_INVALID", "authority": AUTHORITY.copy()}
        required = PRODUCT_ACCOUNTING[product.family]
        if (sleeve.modeled_capital_basis != self.comparison_capital or not re.fullmatch(r"sleeve_[0-9a-f]{16}", sleeve.sleeve_id)
                or not re.fullmatch(r"[0-9a-f]{64}", sleeve.evidence_at_entry_hash)
                or any(sleeve.accounting.get(key) in (None, "") for key in required)
                or min(sleeve.spread_bps, sleeve.fees, sleeve.slippage_bps, sleeve.maximum_modeled_loss) < 0
                or not all((sleeve.instrument_id, sleeve.modeled_price_basis, sleeve.size_hypothesis,
                            sleeve.invalidation, sleeve.exit_rules, sleeve.holding_period, sleeve.mark_frequency,
                            sleeve.benchmark, sleeve.attribution, sleeve.data_completeness))):
            return {"state": "INCOMPLETE", "reason": "SLEEVE_ACCOUNTING_INCOMPLETE", "authority": AUTHORITY.copy()}
        if operational_paper != {"nav": 10_000.0, "cash": 10_000.0, "positions": 0, "transactions": 0, "orders": 0, "fills": 0}:
            return {"state": "FAILED_CLOSED", "reason": "OPERATIONAL_PAPER_BOUNDARY_CHANGED", "authority": AUTHORITY.copy()}
        if sleeve.sleeve_id in self._sleeves:
            return {"state": "DUPLICATE", "authority": AUTHORITY.copy()}
        _timestamp(sleeve.modeled_entry_time)
        self._sleeves[sleeve.sleeve_id] = sleeve
        return {"state": "RESEARCH_RECORDED", "operational_position_created": False, "authority": AUTHORITY.copy()}

    def scoreboard(self) -> dict[str, Any]:
        resolved = [item for item in self._sleeves.values() if item.realized_outcome is not None]
        return {"schema_version": SCHEMA_VERSION, "sleeve_count": len(self._sleeves),
            "comparison_capital_each": self.comparison_capital, "operational_paper_nav": 10_000.0,
            "operational_positions_created": 0, "equal_weight_score": None if not resolved else sum(item.realized_outcome or 0 for item in resolved) / len(resolved),
            "risk_normalized_score": None, "resolved_sample_size": len(resolved),
            "unresolved_outcomes": len(self._sleeves) - len(resolved), "sample_size_warning": len(resolved) < 20,
            "disclosure_delay_warning": True, "calibration_limits": "FIXTURE_RESULTS_ARE_NOT_PROFITABILITY",
            "authority": AUTHORITY.copy()}


def browser_registry_projection() -> dict[str, Any]:
    return {"schema_version": SCHEMA_VERSION, "fixture_label": FIXTURE_LABEL,
        "product_count": len(PRODUCTS), "method_count": len(METHODS),
        "products": [{"product_id": item.product_id, "display_name": item.display_name,
            "department": item.department, "family": item.family, "classification": item.exposure_classification,
            "operational_status": item.operational_status, "licensing_status": item.licensing_status} for item in PRODUCTS],
        "methods": [{"method_id": item.method_id, "display_name": item.display_name,
            "department": item.department, "operational_status": item.operational_status} for item in METHODS],
        "authority": AUTHORITY.copy()}
