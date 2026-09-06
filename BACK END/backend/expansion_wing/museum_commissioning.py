from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any

from .multi_product_research import AUTHORITY, METHODS, PRODUCTS

SCHEMA_VERSION = "iios-museum-master-commissioning-v1"
SYNTHETIC_LABEL = "Synthetic comparison basis — not deployable capital."
TRUTH_STATES = frozenset({
    "CURRENT", "AVAILABLE", "AVAILABLE_EMPTY", "STALE", "INCOMPLETE", "UNAVAILABLE",
    "FAILED_CLOSED", "NOT_ACTIVATED", "RESEARCH_ONLY_UNPRICEABLE", "INSUFFICIENT_SAMPLE",
})
SESSION_PHASES = (
    "CLOSED_HOLIDAY", "MARKET_CLOSED", "PRE_MARKET", "REGULAR_SESSION",
    "POST_MARKET", "POST_CLOSE", "FAILED_CLOSED",
)

MODULE_ROWS = (
    ("executive_factory_status", "Factory truth", "SANITIZED_TELEMETRY", "Control Room", "REUSED"),
    ("market_session_calendar", "Market session controller", "APPROVED_CALENDAR", "Control Room", "REUSED"),
    ("protected_service_health", "Factory Watch", "SANITIZED_SERVICE_HEALTH", "Control Room", "CONSOLIDATED"),
    ("factory_operating_cadence", "ReadinessSuperbatch", "FIXED_SCHEDULE_CONTRACT", "Control Room", "CONSOLIDATED"),
    ("pipeline_9a_9b_9e", "Factory telemetry", "SANITIZED_TELEMETRY", "Control Room", "REUSED"),
    ("validation_9h", "MarketValidationStackPanel", "SANITIZED_VALIDATION", "Control Room", "REUSED"),
    ("shadow_9i", "shadow_browser", "BROWSER_SAFE_9I", "Control Room", "REUSED"),
    ("outcomes_9j", "Outcome Learning Theater", "BROWSER_SAFE_9J", "Control Room", "REUSED"),
    ("radar_universe", "QualificationWatch", "SANITIZED_RADAR", "Control Room", "CONSOLIDATED"),
    ("candidate_lineage", "Candidate Conveyor", "IMMUTABLE_LINEAGE", "Control Room", "REUSED"),
    ("external_research", "Data Expansion Factory", "SANITIZED_RESEARCH_STATUS", "Control Room", "CONSOLIDATED"),
    ("candidate_conveyor", "Candidate Conveyor", "CURRENT_LINEAGE_ONLY", "Expansion Wing", "REUSED"),
    ("investment_committee", "OperatingSuperbatch", "HUMAN_DECISION_RECEIPTS", "Control Room", "CONSOLIDATED"),
    ("skeptic_red_team", "ThesisIntegrityCommand", "HUMAN_REVIEW_RECEIPTS", "Control Room", "CONSOLIDATED"),
    ("risk_inspection", "PaperCapitalControlPanel", "RISK_RECEIPTS", "Control Room", "CONSOLIDATED"),
    ("operational_paper", "PaperFundOperationsDock", "SANITIZED_PAPER_READ_MODEL", "Control Room", "REUSED"),
    ("projection_reader", "projection_runtime", "OWNER_ONLY_PROJECTION", "Control Room", "REUSED"),
    ("projection_publisher", "projection_publisher", "SANITIZED_PUBLISHER_STATUS", "Control Room", "REUSED"),
    ("provider_credit", "provider_enrichment", "SANITIZED_ACCOUNTING", "Control Room", "REUSED"),
    ("professional_observatory", "Professional Strategy Observatory", "RIGHTS_GOVERNED_OBSERVATIONS", "Expansion Wing", "REUSED"),
    ("product_readiness", "multi_product_research", "PRODUCT_EVIDENCE_CONTRACT", "Expansion Wing", "REUSED"),
    ("method_readiness", "multi_product_research", "METHOD_EVALUATION_CONTRACT", "Expansion Wing", "REUSED"),
    ("synthetic_sleeves", "paper_research_lab", "RESEARCH_ONLY_LEDGER", "Expansion Wing", "REUSED"),
    ("evidence_warehouse", "knowledge_operations", "BROWSER_SAFE_COUNTS", "Control Room", "CONSOLIDATED"),
    ("sanitized_receipts", "DailyFactoryEpisode", "SANITIZED_RECEIPTS", "Story", "CONSOLIDATED"),
    ("post_close_audit", "post_close_operations", "GOVERNED_RECONCILIATION", "Control Room", "REUSED"),
    ("security_authority", "security_readiness", "SCALAR_SECURITY_MANIFEST", "Control Room", "REUSED"),
    ("blockers_actions", "ReadinessSuperbatch", "FIXED_STATUS_CATEGORIES", "Control Room", "CONSOLIDATED"),
)

CONTROL_ROOM_PANELS = tuple(row[0] for row in MODULE_ROWS)


def module_registry() -> tuple[dict[str, Any], ...]:
    return tuple({
        "module_id": module_id,
        "latest_valid_implementation": implementation,
        "truth_source": source,
        "freshness_contract": "SOURCE_SPECIFIC_FAIL_CLOSED",
        "runtime_availability": "READ_ONLY_WHEN_SANITIZED",
        "museum_destination": destination,
        "disposition": disposition,
        "exclusion_reason": None,
    } for module_id, implementation, source, destination, disposition in MODULE_ROWS)


def _section(snapshot: dict[str, Any], name: str) -> tuple[str, dict[str, Any]]:
    raw = snapshot.get("sections", {}).get(name) if isinstance(snapshot.get("sections"), dict) else None
    if not isinstance(raw, dict):
        return "UNAVAILABLE", {}
    state = raw.get("state") if raw.get("state") in TRUTH_STATES else "UNAVAILABLE"
    data = raw.get("data") if isinstance(raw.get("data"), dict) else {}
    return state, data


def _panel(module_id: str, state: str, *, evidence_timestamp: str | None = None,
           effective_timestamp: str | None = None, freshness: str | None = None,
           provenance: str = "SANITIZED_READ_MODEL", eligibility: bool = False,
           blocker: str | None = None, next_observation: str = "NATURAL_SOURCE_CYCLE",
           scope: str = "UNAVAILABLE", summary: str = "No browser-safe evidence is available.") -> dict[str, Any]:
    return {
        "module_id": module_id, "state": state, "evidence_timestamp": evidence_timestamp,
        "effective_timestamp": effective_timestamp, "freshness": freshness or state,
        "provenance_category": provenance, "eligible": eligibility, "blocker": blocker,
        "next_expected_observation": next_observation, "scope": scope, "summary": summary,
    }


def control_room_projection(snapshot: dict[str, Any] | None) -> dict[str, Any]:
    source = snapshot if isinstance(snapshot, dict) else {}
    mapping = {
        "executive_factory_status": "service_health", "market_session_calendar": "market_session",
        "protected_service_health": "service_health", "factory_operating_cadence": "last_cycle",
        "pipeline_9a_9b_9e": "radar", "validation_9h": "benchmark_9h", "shadow_9i": "shadow_9i",
        "outcomes_9j": "outcomes_9j", "radar_universe": "radar", "candidate_lineage": "candidate_conveyor",
        "external_research": "primary_source_review_queue", "candidate_conveyor": "candidate_conveyor",
        "investment_committee": "committee", "skeptic_red_team": "risk", "risk_inspection": "risk",
        "operational_paper": "books", "projection_reader": "projection_activation",
        "projection_publisher": "projection_activation", "provider_credit": "provider_credit_meter",
        "professional_observatory": "professional_strategy_observatory", "product_readiness": "tuesday_command_center",
        "method_readiness": "method_manager_scoreboard", "synthetic_sleeves": "paper_research_sleeves",
        "evidence_warehouse": "knowledge_operations", "sanitized_receipts": "last_cycle",
        "post_close_audit": "post_close_control", "security_authority": "authority_lock",
        "blockers_actions": "tuesday_command_center",
    }
    panels = []
    for module_id in CONTROL_ROOM_PANELS:
        state, data = _section(source, mapping[module_id])
        evidence_at = data.get("generated_at") or data.get("observed_at") or data.get("last_publication_time")
        scope = "OPERATIONAL_READ_ONLY" if module_id in {"operational_paper", "protected_service_health"} else "RESEARCH_ONLY"
        blocker = None if state in {"CURRENT", "AVAILABLE", "AVAILABLE_EMPTY"} else state
        panels.append(_panel(module_id, state, evidence_timestamp=evidence_at if isinstance(evidence_at, str) else None,
                             effective_timestamp=data.get("effective_at") if isinstance(data.get("effective_at"), str) else None,
                             eligibility=False, blocker=blocker, scope=scope,
                             summary="Sanitized scalar status only; technical evidence remains behind its governed source."))
    return {"schema_version": SCHEMA_VERSION, "panel_count": len(panels), "panels": panels,
            "browser_methods": ("GET", "HEAD"), "publisher_control": False, "authority": AUTHORITY.copy()}


def ambient_scene(*, session_phase: str, evidence_state: str, reduced_motion: bool = False) -> dict[str, Any]:
    if session_phase not in SESSION_PHASES or evidence_state not in TRUTH_STATES:
        return {"state": "FAILED_CLOSED", "motion": "FROZEN", "reason": "AMBIENT_INPUT_INVALID", "evidence_movement": False}
    scene = "HOLIDAY_WATCH" if session_phase == "CLOSED_HOLIDAY" else "POST_CLOSE_CLEANUP" if session_phase == "POST_CLOSE" else "QUIET_EVIDENCE_WATCH"
    if evidence_state == "FAILED_CLOSED": scene = "FAILED_CLOSED_INSPECTION"
    return {"state": "AVAILABLE", "scene": scene, "motion": "STABLE_EQUIVALENT" if reduced_motion else "BOUNDED_AMBIENT",
            "evidence_movement": False, "candidate_implied": False, "trade_implied": False,
            "position_implied": False, "recommendation_implied": False, "profit_implied": False,
            "provider_implied": False, "current_evidence_implied": False,
            "commentary": "The House Is Quiet. Departments remain present while evidence and authority stay unchanged."}


def product_readiness() -> tuple[dict[str, Any], ...]:
    return tuple({**asdict(product), "tested": True, "evidence_available": False, "contract_complete": False,
                  "research_eligible": False, "paper_eligible": False, "candidate_count": None,
                  "blocker": "NOT_ACTIVATED", "outcome_available": False, "state": "NOT_ACTIVATED",
                  "authority": AUTHORITY.copy()} for product in PRODUCTS)


def method_readiness() -> tuple[dict[str, Any], ...]:
    return tuple({**asdict(method), "sizing_hypothesis": None, "exit_rules": None,
                  "ranking_eligible": False, "score": None, "sample_size": 0,
                  "state": "INSUFFICIENT_SAMPLE", "authority": AUTHORITY.copy()} for method in METHODS)


def synthetic_sleeves() -> tuple[dict[str, Any], ...]:
    unresolved = {key: None for key in (
        "method", "modeled_entry_time", "entry_evidence", "modeled_entry_price", "spread", "fees",
        "slippage", "sizing_hypothesis", "invalidation", "exit_rule", "holding_period", "realized_outcome",
        "unrealized_outcome", "favorable_excursion", "adverse_excursion", "drawdown", "volatility",
        "calibration", "attribution", "sample_size",
    )}
    return tuple({"sleeve_id": f"research_{product.product_id}", "product": product.product_id,
                  "synthetic_basis": 10_000.0, "label": SYNTHETIC_LABEL, "pooled": False,
                  "operational_capital": False, "mark_frequency": product.paper_mark_frequency,
                  "benchmark": product.benchmark, **unresolved, "authority": AUTHORITY.copy()}
                 for product in PRODUCTS)


def professional_readiness() -> tuple[dict[str, Any], ...]:
    rows = (
        ("KOYFIN", "UNAVAILABLE", "LICENSE_REQUIRED"),
        ("MARKET_VISION", "UNVERIFIED", "RIGHTS_REVIEW_REQUIRED"),
        ("JESSE_INTERVIEWS", "UNAVAILABLE", "CONSENT_AND_TRANSCRIPT_APPROVAL_REQUIRED"),
        ("PUBLIC_MANAGER_COMMENTARY", "UNAVAILABLE", "SOURCE_REVIEW_REQUIRED"),
        ("PUBLIC_PORTFOLIO_OBSERVATIONS", "UNAVAILABLE", "DISCLOSURE_DELAY_AND_PRIMARY_VERIFICATION_REQUIRED"),
        ("PUBLIC_FILINGS_AND_INTERVIEWS", "UNAVAILABLE", "RIGHTS_AND_POINT_IN_TIME_REVIEW_REQUIRED"),
    )
    return tuple({"source": source, "state": state, "blocker": blocker, "attributed_hypothesis": True,
                  "candidate_creation": False, "promotion": False, "paper_sleeve_creation": False,
                  "recommendation": False, "score": None, "authority": AUTHORITY.copy()} for source, state, blocker in rows)


def rehearsal(scenario: dict[str, Any]) -> dict[str, Any]:
    name = scenario.get("scenario")
    phase = scenario.get("phase")
    if not isinstance(name, str) or phase not in SESSION_PHASES:
        raise ValueError("REHEARSAL_SCENARIO_INVALID")
    products = [dict(item) for item in product_readiness()]
    methods = [dict(item) for item in method_readiness()]
    overrides = scenario.get("product_overrides", {})
    if not isinstance(overrides, dict): raise ValueError("REHEARSAL_SCENARIO_INVALID")
    by_id = {item["product_id"]: item for item in products}
    for product_id, state in overrides.items():
        if product_id not in by_id or state not in TRUTH_STATES: raise ValueError("REHEARSAL_SCENARIO_INVALID")
        by_id[product_id].update(state=state, blocker=None if state == "CURRENT" else state,
                                 evidence_available=state in {"CURRENT", "AVAILABLE"},
                                 contract_complete=state in {"CURRENT", "AVAILABLE"})
    candidate_state = scenario.get("candidate_state", "AVAILABLE_EMPTY")
    if candidate_state not in TRUTH_STATES: raise ValueError("REHEARSAL_SCENARIO_INVALID")
    has_fixture_candidate = name in {"valid_immutable_candidate", "committee_rejection", "risk_rejection"}
    candidates = ({"candidate_id": "fixture_candidate_0001", "instrument_id": "SYNTHETIC_TEST_INSTRUMENT",
                   "discovery_timestamp": "2026-09-08T13:30:00+00:00", "source_cycle_id": "fixture_tuesday_cycle_001",
                   "immutable_lineage": True, "fixture": True, "research_eligible": False,
                   "paper_eligible": False, "authority": AUTHORITY.copy()},) if has_fixture_candidate else ()
    return {"schema_version": SCHEMA_VERSION, "fixture_label": "SYNTHETIC_FIXTURE_NON_LIVE",
            "scenario": name, "phase": phase, "products": products, "methods": methods,
            "sleeves": synthetic_sleeves(), "professional": professional_readiness(),
            "candidate_state": candidate_state, "candidate_count": len(candidates), "candidates": candidates,
            "operational_paper": {"nav": 10_000.0, "cash": 10_000.0, "positions": 0,
                                  "transactions": 0, "orders": 0, "fills": 0, "changed": False},
            "ambient": ambient_scene(session_phase=phase, evidence_state=scenario.get("evidence_state", "UNAVAILABLE")),
            "provider_requests": 0, "provider_credits": 0, "publisher_control": False,
            "keychain_access": False, "ledger_access": False, "authority": AUTHORITY.copy()}


def post_close_report(rehearsal_result: dict[str, Any]) -> dict[str, Any]:
    products = rehearsal_result.get("products", [])
    methods = rehearsal_result.get("methods", [])
    counts = {state.lower(): sum(item.get("state") == state for item in products) for state in TRUTH_STATES}
    return {"schema_version": "iios-opening-day-post-close-v1", "fixture": True,
            "session_transitions": ["PRE_MARKET", "REGULAR_SESSION", "POST_MARKET", "POST_CLOSE"],
            "products_tested": len(products), "product_states": counts,
            "method_observations": 0, "rankable_methods": sum(item.get("ranking_eligible") is True for item in methods),
            "candidate_lineage": rehearsal_result.get("candidate_state", "UNAVAILABLE"),
            "committee_decisions": 0, "risk_decisions": 0, "synthetic_sleeve_activity": 0,
            "costs": None, "drawdown": None, "calibration": None, "professional_observations": 0,
            "provider_requests": 0, "provider_credits": 0, "operational_paper_changes": 0,
            "errors": [], "blockers": sorted({item.get("blocker") for item in products if item.get("blocker")}),
            "next_source_activation_wave": "HUMAN_APPROVED_SOURCE_CONTRACTS_ONLY",
            "profitability_claim": False, "authority": AUTHORITY.copy()}


def validate_commissioning(value: dict[str, Any]) -> None:
    if (value.get("schema_version") != SCHEMA_VERSION or len(value.get("products", ())) != 24
            or len(value.get("methods", ())) != 16 or len(value.get("sleeves", ())) != 24
            or value.get("candidate_count", 6) > 5 or value.get("publisher_control") is not False
            or value.get("keychain_access") is not False or value.get("ledger_access") is not False
            or any(value.get("authority", {}).values())):
        raise ValueError("COMMISSIONING_CONTRACT_INVALID")
    paper = value.get("operational_paper", {})
    if paper != {"nav": 10_000.0, "cash": 10_000.0, "positions": 0, "transactions": 0,
                 "orders": 0, "fills": 0, "changed": False}:
        raise ValueError("OPERATIONAL_PAPER_CHANGED")
    if any(item.get("score") is not None for item in value["methods"]):
        raise ValueError("MISSING_METHOD_RESULT_BECAME_ZERO")
    if any(item.get("operational_capital") is not False or item.get("pooled") is not False for item in value["sleeves"]):
        raise ValueError("SYNTHETIC_OPERATIONAL_BOUNDARY_FAILED")
