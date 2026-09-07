"""Fixture-first Tuesday whole-factory commissioning contracts.

This module deliberately has no filesystem, network, credential, broker, or ledger
adapter.  It prepares a future owner-authorized plan without changing the installed
disabled controller.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Iterable

from .multi_product_research import METHODS, PRODUCTS
from .tuesday_controller import AUTHORITY

SCHEMA_VERSION = "iios-tuesday-whole-factory-v1"
MIGRATION_SCHEMA = "iios-tuesday-staged-budget-v2"
DAILY_CEILING = 200
STAGE_LIMITS = {"A": 100, "B": 50, "C": 50}
PER_INSTRUMENT_LIMIT = 10
PER_ENDPOINT_LIMIT = 100
DECISIONS = (
    "APPROVE_FOR_COMMITTEE_REVIEW", "DEFER_FOR_MORE_EVIDENCE", "REJECT",
    "SOURCE_NOT_ELIGIBLE", "IDENTITY_NOT_AUTHENTICATED",
)
LOCKED_AUTHORITY = {
    "provider": False, "credential": False, "automatic_promotion": False,
    "synthetic_observation": False, "paper_order": False, "broker": False,
    "ledger_write": False, "live_execution": False, "browser_control": False,
}

PILOT_BY_PRODUCT = {
    "us_large_cap_equities": ("MU", "DIRECT_COMMON_STOCK"),
    "broad_factor_etfs": ("SPY", "LISTED_ETF"),
    "sector_thematic_etfs": ("XLK", "LISTED_ETF"),
    "reits_listed_real_estate": ("VNQ", "LISTED_REIT_PROXY"),
    "treasury_etf_duration_proxies": ("TLT", "LISTED_TREASURY_DURATION_PROXY"),
    "commodity_etf_etc_proxies": ("GLD", "LISTED_COMMODITY_PROXY"),
    "currency_etfs_fx_proxies": ("UUP", "LISTED_CURRENCY_PROXY"),
    "crypto_etfs_listed_proxies": ("IBIT", "LISTED_CRYPTO_PROXY"),
    "preferred_income_securities": ("PFF", "LISTED_PREFERRED_INCOME_PROXY"),
    "money_market_ultra_short": ("BIL", "LISTED_ULTRA_SHORT_PROXY"),
}
PENDING_PRODUCTS = frozenset({
    "us_mid_cap_equities", "us_small_cap_equities",
    "international_developed_equities", "emerging_market_equities",
})
STRUCTURAL_PRODUCTS = frozenset({p.product_id for p in PRODUCTS}) - set(PILOT_BY_PRODUCT) - PENDING_PRODUCTS


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def product_test_matrix() -> tuple[dict[str, Any], ...]:
    rows = []
    for product in PRODUCTS:
        if product.product_id in PILOT_BY_PRODUCT:
            instrument, interpretation = PILOT_BY_PRODUCT[product.product_id]
            mode, source, entitlement = "LIVE_EVIDENCE_ELIGIBLE", "FINANCIAL_DATASETS", "PRECHECK_REQUIRED"
            outcome, blocker, ceiling = "BOUNDED_EVIDENCE_IF_AUTHORIZED", "STAGE_A_NOT_RELEASED", 10
        elif product.product_id in PENDING_PRODUCTS:
            instrument, interpretation = None, "IDENTITY_PENDING"
            mode, source, entitlement = "LIVE_EVIDENCE_PENDING_IDENTITY", "APPROVED_PROVIDER", "UNVERIFIED"
            outcome, blocker, ceiling = "AWAITING_SUPPORTED_IDENTITY", "OWNER_INSTRUMENT_APPROVAL_REQUIRED", 0
        else:
            instrument, interpretation = None, product.exposure_classification
            mode, source, entitlement = "STRUCTURAL_FAIL_CLOSED", "SPECIALIZED_SOURCE_NOT_ACTIVATED", "NOT_ACTIVATED"
            outcome, blocker, ceiling = "STRUCTURAL_VALIDATION_ONLY", "SPECIALIZED_LIVE_SOURCE_REQUIRED", 0
        rows.append({
            "product_id": product.product_id, "display_name": product.display_name,
            "tuesday_participation": True,
            "test_mode": mode, "instrument": instrument, "interpretation": interpretation,
            "source": source, "entitlement_state": entitlement,
            "evidence_requirements": product.eligibility_rules,
            "method_eligibility": "REQUIRES_CURRENT_COMPLETE_EVIDENCE",
            "synthetic_sleeve": {"starting_basis": 10_000, "pooled": False,
                                 "deployable_capital": False, "positions": 0, "trades": 0,
                                 "performance": None},
            "expected_request_ceiling": ceiling, "expected_outcome": outcome,
            "blocker": blocker, "next_activation_requirement": blocker,
            "authority": LOCKED_AUTHORITY.copy(),
        })
    return tuple(rows)


def method_product_matrix() -> tuple[dict[str, Any], ...]:
    products = product_test_matrix()
    rows = []
    for method in METHODS:
        for product in products:
            historical = method.method_id in {"mean_reversion", "trend_following", "relative_value", "pairs_trading", "long_horizon_fundamental"}
            reason = "ADJUSTMENT_TREATMENT_UNSPECIFIED" if historical else (
                product["blocker"] if product["test_mode"] != "LIVE_EVIDENCE_ELIGIBLE" else "CURRENT_EVIDENCE_AND_HUMAN_REVIEW_REQUIRED")
            rows.append({
                "method_id": method.method_id, "product_id": product["product_id"],
                "eligible": False, "evidence_requirements": method.required_evidence,
                "adjustment_requirement": "EXPLICIT" if historical else "PRODUCT_SPECIFIC",
                "minimum_sample": method.minimum_sample_size, "liquidity_requirement": method.liquidity_requirements,
                "cost_model": method.cost_model, "benchmark": method.benchmark,
                "holding_period": method.holding_period_range, "invalidation": method.invalidation_rules,
                "risk_requirements": method.risk_measure, "outcome_requirements": "WALK_FORWARD_OUT_OF_SAMPLE",
                "reason_blocked": reason, "result": None, "automatic_promotion": False,
            })
    return tuple(rows)


@dataclass
class StagedCreditGovernor:
    releases: dict[str, int] = field(default_factory=lambda: {k: 0 for k in STAGE_LIMITS})
    used: dict[str, int] = field(default_factory=lambda: {k: 0 for k in STAGE_LIMITS})
    reserved: dict[str, int] = field(default_factory=lambda: {k: 0 for k in STAGE_LIMITS})
    request_ids: set[str] = field(default_factory=set)
    release_receipts: list[dict[str, Any]] = field(default_factory=list)

    def release(self, stage: str, amount: int, *, owner: str, timestamp: str, reason: str) -> str:
        if stage not in STAGE_LIMITS or isinstance(amount, bool) or not 0 < amount <= STAGE_LIMITS[stage]:
            return "STAGE_RELEASE_REJECTED"
        if self.releases[stage] or not all((owner, timestamp, reason)):
            return "STAGE_RELEASE_REJECTED"
        if stage == "B" and not self.releases["A"] or stage == "C" and not self.releases["B"]:
            return "PRIOR_STAGE_REVIEW_REQUIRED"
        self.releases[stage] = amount
        self.release_receipts.append({"stage": stage, "amount": amount, "owner": owner,
                                      "timestamp": timestamp, "reason": reason, "immutable": True})
        return "RELEASED"

    def reserve(self, stage: str, request_id: str, cost: int) -> str:
        if stage not in STAGE_LIMITS or not request_id or request_id in self.request_ids:
            return "DUPLICATE_OR_INVALID_REQUEST"
        if isinstance(cost, bool) or not isinstance(cost, int) or cost <= 0:
            return "UNKNOWN_ENDPOINT_COST"
        if self.used[stage] + self.reserved[stage] + cost > self.releases[stage]:
            return "STAGE_BUDGET_EXHAUSTED"
        if sum(self.used.values()) + sum(self.reserved.values()) + cost > DAILY_CEILING:
            return "DAILY_CEILING_EXCEEDED"
        self.request_ids.add(request_id); self.reserved[stage] += cost
        return "RESERVED"

    def settle(self, stage: str, cost: int, outcome: str) -> str:
        if outcome not in {"CONFIRMED", "AMBIGUOUS", "FAILED"} or self.reserved.get(stage, 0) < cost:
            return "SETTLEMENT_REJECTED"
        self.reserved[stage] -= cost
        if outcome in {"CONFIRMED", "AMBIGUOUS"}: self.used[stage] += cost
        return outcome

    def report(self) -> dict[str, Any]:
        return {"daily_ceiling": DAILY_CEILING, "stage_limits": STAGE_LIMITS.copy(),
                "released": self.releases.copy(), "used": self.used.copy(), "reserved": self.reserved.copy(),
                "remaining": sum(self.releases.values()) - sum(self.used.values()) - sum(self.reserved.values()),
                "auto_release": False, "auto_reload": False, "automatic_retries": False,
                "browser_invocation": False, "authority": LOCKED_AUTHORITY.copy()}


REQUEST_FIELDS = frozenset({"stage", "product_room", "instrument", "endpoint", "purpose", "estimated_cost",
                            "request_identity", "earliest", "latest", "prerequisites", "cache_policy",
                            "retry_policy", "failure_behavior", "sanitized_fields", "browser_invocation"})


def compile_request_plan(rows: Iterable[dict[str, Any]], releases: dict[str, int]) -> dict[str, Any]:
    products = {p["product_id"]: p for p in product_test_matrix()}; seen = set(); totals = {k: 0 for k in STAGE_LIMITS}; output = []
    instrument_totals: dict[str, int] = {}; endpoint_totals: dict[str, int] = {}
    for raw in rows:
        if not isinstance(raw, dict) or set(raw) != REQUEST_FIELDS: raise ValueError("REQUEST_SCHEMA_INVALID")
        stage, product_id, request_id, cost = raw["stage"], raw["product_room"], raw["request_identity"], raw["estimated_cost"]
        if stage not in STAGE_LIMITS or product_id not in products or products[product_id]["test_mode"] != "LIVE_EVIDENCE_ELIGIBLE": raise ValueError("UNSUPPORTED_PRODUCT")
        if not isinstance(cost, int) or isinstance(cost, bool) or cost <= 0: raise ValueError("UNKNOWN_ENDPOINT_COST")
        if request_id in seen: raise ValueError("DUPLICATE_REQUEST_IDENTITY")
        if raw["retry_policy"] != "NO_RETRY" or raw["browser_invocation"] is not False: raise ValueError("UNSAFE_INVOCATION")
        if not raw["earliest"] or not raw["latest"] or "ENTITLEMENT" not in raw["prerequisites"]: raise ValueError("SESSION_OR_ENTITLEMENT_MISSING")
        if raw["instrument"] != products[product_id]["instrument"]: raise ValueError("INSTRUMENT_IDENTITY_INVALID")
        instrument_totals[raw["instrument"]] = instrument_totals.get(raw["instrument"], 0) + cost
        endpoint_totals[raw["endpoint"]] = endpoint_totals.get(raw["endpoint"], 0) + cost
        if instrument_totals[raw["instrument"]] > PER_INSTRUMENT_LIMIT: raise ValueError("PER_INSTRUMENT_LIMIT_EXCEEDED")
        if endpoint_totals[raw["endpoint"]] > PER_ENDPOINT_LIMIT: raise ValueError("PER_ENDPOINT_LIMIT_EXCEEDED")
        seen.add(request_id); totals[stage] += cost; output.append(dict(raw))
    if sum(totals.values()) > DAILY_CEILING or any(totals[s] > min(STAGE_LIMITS[s], releases.get(s, 0)) for s in totals): raise ValueError("BUDGET_EXCEEDED")
    return {"schema_version": "iios-tuesday-request-plan-v1", "requests": tuple(output), "totals": totals,
            "total": sum(totals.values()), "instrument_totals": instrument_totals,
            "endpoint_totals": endpoint_totals, "hash": _digest(output), "authority": LOCKED_AUTHORITY.copy()}


def core_request_plan() -> tuple[dict[str, Any], ...]:
    rows = []
    operations = (
        ("MARKET_SNAPSHOT", "OPENING_EVIDENCE", "2026-09-08T13:00:00Z", "2026-09-08T15:00:00Z"),
        ("HISTORICAL_OHLCV", "POINT_IN_TIME_HISTORY", "2026-09-08T13:00:00Z", "2026-09-08T15:00:00Z"),
        ("COMPANY_FACTS", "CURRENT_FUNDAMENTALS", "2026-09-08T13:00:00Z", "2026-09-08T17:00:00Z"),
        ("MARKET_SNAPSHOT", "INTRADAY_MARK", "2026-09-08T16:00:00Z", "2026-09-08T18:30:00Z"),
        ("MARKET_SNAPSHOT", "CLOSING_MARK", "2026-09-08T20:00:00Z", "2026-09-08T21:00:00Z"),
    )
    for index, (product, (instrument, _)) in enumerate(PILOT_BY_PRODUCT.items(), 1):
        for operation, (endpoint, purpose, earliest, latest) in enumerate(operations, 1):
            rows.append({"stage": "A", "product_room": product, "instrument": instrument,
                         "endpoint": endpoint, "purpose": purpose, "estimated_cost": 1,
                         "request_identity": f"tuesday-a-{index:02d}-{operation:02d}-{instrument.lower()}",
                         "earliest": earliest, "latest": latest,
                         "prerequisites": ("ENTITLEMENT", "OWNER_RELEASE", "REGULAR_SESSION"),
                         "cache_policy": "CONTENT_HASH_ZERO_CREDIT_REPEAT", "retry_policy": "NO_RETRY",
                         "failure_behavior": "FAIL_CLOSED", "sanitized_fields": ("identity", "timestamp", "hash"),
                         "browser_invocation": False})
    return tuple(rows)


def fixture_rehearsal(scenarios: Iterable[str]) -> dict[str, Any]:
    safe = {"ALL_24_ROOMS", "VALID_PRODUCT_EVIDENCE", "STAGE_A_RELEASE", "STAGE_B_RELEASE",
            "STAGE_C_RELEASE", "CACHE_REUSE", "HUMAN_APPROVE", "HUMAN_DEFER", "HUMAN_REJECT",
            "RESTART_RECOVERY", "POST_CLOSE_ACCOUNTING"}
    rows = []
    for scenario in scenarios:
        rows.append({"scenario": scenario, "result": "REHEARSAL_ONLY" if scenario in safe else "FAILED_CLOSED",
                     "provider_requests": 0, "credits": 0, "keychain_access": 0,
                     "operational_mutation": False, "automatic_promotion": False,
                     "authority": LOCKED_AUTHORITY.copy()})
    return {"schema_version": "iios-tuesday-whole-factory-rehearsal-v1", "results": tuple(rows),
            "scenario_count": len(rows), "hash": _digest(rows)}


def scanner_status(*, universe_size: int | None = None) -> dict[str, Any]:
    return {"schema_version": "iios-tuesday-scanner-status-v1", "universe_size": universe_size,
            "scan_state": "OBSERVATION_ONLY", "authenticated_opportunity_count": 0,
            "lineage_complete_count": 0, "awaiting_evidence_count": None, "candidate_count": 0,
            "promoted_count": 0, "rejected_count": 0, "current_blockers": ("CURRENT_SCAN_EVIDENCE_REQUIRED",),
            "last_governed_scan_category": "NOT_OBSERVED_IN_REHEARSAL", "last_governed_scan_timestamp": None,
            "provider_credits_used_by_scanning": 0, "browser_triggered_scans": 0,
            "aggregate_counts_create_identities": False, "automatic_promotion": False,
            "authority": LOCKED_AUTHORITY.copy()}


def migrate_disabled_v1(state: dict[str, Any]) -> dict[str, Any]:
    required = {"schema_version", "activated", "phase", "sequence", "global_credit_ceiling", "requests_used", "credits_used", "request_identities", "authority"}
    if not required <= set(state) or state["activated"] is not False or state["phase"] != "TUESDAY_PREMARKET_LOCKED" or state["global_credit_ceiling"] != 30:
        raise ValueError("INCOMPATIBLE_CONTROLLER_STATE")
    if state["requests_used"] != len(state["request_identities"]) or len(set(state["request_identities"])) != len(state["request_identities"]):
        raise ValueError("AMBIGUOUS_CONTROLLER_STATE")
    if any(state["authority"].values()): raise ValueError("UNSAFE_AUTHORITY")
    value = {"schema_version": MIGRATION_SCHEMA, "source_schema": state["schema_version"],
             "activated": False, "phase": state["phase"], "sequence": state["sequence"] + 1,
             "daily_ceiling": DAILY_CEILING, "released": {k: 0 for k in STAGE_LIMITS},
             "requests_used": state["requests_used"], "credits_used": state["credits_used"],
             "request_identities": list(state["request_identities"]), "authority": LOCKED_AUTHORITY.copy(),
             "migration": "ISOLATED_FIXTURE_ONLY"}
    value["content_hash"] = _digest(value)
    return value


def candidate_decision(decision: str, *, current_evidence: bool, immutable_identity: bool,
                       human_actor: bool) -> dict[str, Any]:
    if decision not in DECISIONS or not human_actor: raise ValueError("HUMAN_DECISION_REQUIRED")
    approved = decision == "APPROVE_FOR_COMMITTEE_REVIEW" and current_evidence and immutable_identity
    return {"decision": decision, "committee_eligible": approved, "automatic_promotion": False,
            "synthetic_observation_eligible": False, "authority": LOCKED_AUTHORITY.copy()}


def post_close_report() -> dict[str, Any]:
    return {"schema_version": "iios-tuesday-whole-factory-post-close-v1", "universe_scanned": None,
            "opportunities_discovered": None, "lineage_complete_opportunities": None,
            "candidate_decisions": (), "product_room_participation": (), "requests_by_stage": {},
            "credits_by_stage": {}, "cache_hits": 0, "ambiguous_reservations": 0,
            "committee_decisions": (), "skeptic_decisions": (), "risk_decisions": (),
            "synthetic_observations": (), "structural_results": (), "corporate_action_suspensions": (),
            "operational_paper_activity": {"positions": 0, "transactions": 0, "orders": 0, "fills": 0},
            "errors": (), "unavailable_fields": ("CURRENT_TUESDAY_EVIDENCE",),
            "next_evidence_requirements": ("OWNER_STAGE_A_AUTHORIZATION",),
            "method_success": None, "profitability": None, "execution_quality": None,
            "authority": LOCKED_AUTHORITY.copy()}


def browser_projection() -> dict[str, Any]:
    products = product_test_matrix(); methods = method_product_matrix(); governor = StagedCreditGovernor().report()
    return {"schema_version": SCHEMA_VERSION, "mode": "FIXTURE_NON_LIVE_REHEARSAL",
            "controller": {"installed": True, "running": True, "activated": False,
                           "phase": "TUESDAY_PREMARKET_LOCKED", "operational_allowance": 0},
            "products": products, "product_counts": {"total": 24, "participating": 24, "pilots": 10, "pending_identity": 4, "structural": 10, "operational_trading": 0},
            "methods": {"total": 16, "matrix_rows": len(methods), "eligible": 0, "results": None},
            "scanner": scanner_status(), "credit_governor": governor,
            "candidate_workflow": DECISIONS, "request_plan": {"stage_a_rows": len(core_request_plan()), "planned_cost": 50},
            "post_close": post_close_report(),
            "paper": {"operational_nav": 10_000, "operational_cash": 10_000,
                      "positions": 0, "transactions": 0, "orders": 0, "fills": 0},
            "authority": LOCKED_AUTHORITY.copy()}
