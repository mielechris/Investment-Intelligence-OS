from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

from .multi_product_research import AUTHORITY, METHODS, PRODUCTS, method_scoreboard

SCHEMA_VERSION = "iios-tuesday-opening-day-factory-v1"
SYNTHETIC_LABEL = "Synthetic comparison basis — not deployable capital."
ALLOWED_STATES = frozenset({"AVAILABLE", "AVAILABLE_EMPTY", "CURRENT", "STALE", "INCOMPLETE", "UNAVAILABLE",
                            "FAILED_CLOSED", "NOT_ACTIVATED", "RESEARCH_ONLY_UNPRICEABLE",
                            "CLOSED_HOLIDAY", "OPEN_24_7"})
SESSION_GATES = ("PRE_MARKET", "REGULAR_SESSION", "POST_MARKET", "POST_CLOSE")


def _state(value: Any, default: str = "UNAVAILABLE") -> str:
    return value if isinstance(value, str) and value in ALLOWED_STATES else default


@dataclass(frozen=True)
class ProfessionalResearchRecord:
    observation_id: str
    analyst_identity: str
    firm_identity: str
    method_classification: str
    product_scope: tuple[str, ...]
    publication_timestamp: str
    effective_timestamp: str
    factory_observation_timestamp: str
    rights_status: str
    disclosure_delay_status: str
    conflict_disclosures: str
    point_in_time_available: bool
    source_class: str
    corroboration_status: str
    browser_safe_hypothesis: str
    invalidation_conditions: str
    permitted_use: str
    promotion_prohibited: bool = True

    def validate(self, *, now: datetime) -> None:
        timestamps = []
        for raw in (self.publication_timestamp, self.effective_timestamp, self.factory_observation_timestamp):
            try:
                value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                raise ValueError("PROFESSIONAL_TIMESTAMP_INVALID") from None
            if value.tzinfo is None or value.astimezone(timezone.utc) > now.astimezone(timezone.utc):
                raise ValueError("PROFESSIONAL_POINT_IN_TIME_INVALID")
            timestamps.append(value)
        if (not all((self.observation_id, self.analyst_identity, self.firm_identity, self.method_classification,
                     self.product_scope, self.rights_status, self.conflict_disclosures, self.source_class,
                     self.browser_safe_hypothesis, self.invalidation_conditions, self.permitted_use))
                or self.corroboration_status not in {"UNAVAILABLE", "UNVERIFIED", "VERIFIED_UNCORROBORATED",
                                                     "INDEPENDENTLY_CORROBORATED"}
                or self.rights_status not in {"PUBLIC_OFFICIAL", "LICENSED_APPROVED"}
                or not self.point_in_time_available or not self.promotion_prohibited):
            raise ValueError("PROFESSIONAL_OBSERVATION_REJECTED")

    def browser_projection(self, *, now: datetime) -> dict[str, Any]:
        self.validate(now=now)
        return {"observation_id": self.observation_id, "method_classification": self.method_classification,
                "product_count": len(self.product_scope), "rights_status": self.rights_status,
                "disclosure_delay_status": self.disclosure_delay_status,
                "corroboration_status": self.corroboration_status, "attributed_hypothesis": True,
                "endorsement": False, "promotion_prohibited": True, "authority": AUTHORITY.copy()}


def professional_readiness_audit() -> tuple[dict[str, Any], ...]:
    return (
        {"capability": "GOVERNED_OBSERVATION_CONTRACT", "implementation": "FUNCTIONAL", "tuesday": "FIXTURE_ONLY", "human_review": True, "licensing": "SOURCE_SPECIFIC"},
        {"capability": "KOYFIN", "implementation": "MANUAL_HUMAN_COCKPIT", "tuesday": "NOT_ACTIVATED", "human_review": True, "licensing": "REQUIRED"},
        {"capability": "MARKET_VISION", "implementation": "SECONDARY_DOMAIN_EXPERT", "tuesday": "RIGHTS_REVIEW_REQUIRED", "human_review": True, "licensing": "REQUIRED"},
        {"capability": "JESSE_INTERVIEWS", "implementation": "SOURCE_REVIEW_REQUIRED", "tuesday": "NOT_ACTIVATED", "human_review": True, "licensing": "CONSENT_REQUIRED"},
        {"capability": "PUBLIC_PORTFOLIO_OBSERVATIONS", "implementation": "CONTRACT_ONLY", "tuesday": "UNAVAILABLE", "human_review": True, "licensing": "RIGHTS_REVIEW_REQUIRED"},
    )


def product_readiness(*, source_states: dict[str, str] | None = None) -> tuple[dict[str, Any], ...]:
    states = source_states or {}
    output = []
    for product in PRODUCTS:
        source_state = _state(states.get(product.product_id), "NOT_ACTIVATED")
        output.append({"product_id": product.product_id, "display_name": product.display_name,
                       "family": product.family, "exposure_classification": product.exposure_classification,
                       "source_licensing": product.licensing_status, "source_state": source_state,
                       "candidate_count": None, "research_eligible": False, "paper_eligible": False,
                       "synthetic_basis": 10_000.0, "synthetic_label": SYNTHETIC_LABEL,
                       "operational_capital": False, "authority": AUTHORITY.copy()})
    return tuple(output)


def method_readiness() -> tuple[dict[str, Any], ...]:
    return tuple({"method_id": method.method_id, "display_name": method.display_name,
                  "eligible_families": method.eligible_families, "required_freshness": method.required_freshness,
                  "minimum_sample_size": method.minimum_sample_size, "cost_model": method.cost_model,
                  "benchmark": method.benchmark, "risk_measure": method.risk_measure,
                  "drawdown_measure": method.drawdown_measure, "calibration_measure": method.calibration_measure,
                  "operational_status": method.operational_status, "ranking_state": "INSUFFICIENT_SAMPLE",
                  "score": None, "automatic_promotion": False} for method in METHODS)


def tuesday_command_projection(snapshot: dict[str, Any] | None, *, fixture: bool) -> dict[str, Any]:
    sections = snapshot.get("sections", {}) if isinstance(snapshot, dict) and isinstance(snapshot.get("sections"), dict) else {}
    def section_state(key: str) -> str:
        value = sections.get(key)
        return _state(value.get("state") if isinstance(value, dict) else None)
    activation_raw = sections.get("projection_activation", {}).get("data") if isinstance(sections.get("projection_activation"), dict) else None
    activation = activation_raw if isinstance(activation_raw, dict) else {}
    market_raw = sections.get("market_session", {}).get("data") if isinstance(sections.get("market_session"), dict) else None
    market = market_raw if isinstance(market_raw, dict) else {}
    books_raw = sections.get("books", {}).get("data") if isinstance(sections.get("books"), dict) else None
    books = books_raw if isinstance(books_raw, dict) else {}
    authorities_raw = sections.get("authority_lock", {}).get("data") if isinstance(sections.get("authority_lock"), dict) else None
    authorities = authorities_raw if isinstance(authorities_raw, dict) else {}
    authority = {key: False for key in AUTHORITY}
    unsafe = any(authorities.get(key) is True for key in ("provider", "credential", "paper_order", "broker", "ledger_write", "live_execution"))
    products = product_readiness()
    methods = method_readiness()
    blockers = sorted({item["source_state"] for item in products if item["source_state"] != "CURRENT"})
    return {"schema_version": SCHEMA_VERSION, "fixture": fixture, "factory_mode": "PAPER_RESEARCH_NO_LIVE_CAPITAL",
            "market_date": market.get("projection_generated_at"), "market_session": market.get("state") or "UNAVAILABLE",
            "projection_container": _state(activation.get("freshness_state")),
            "underlying_evidence": section_state("projection_freshness"),
            "publisher_observation": activation.get("publisher_state") or "UNAVAILABLE",
            "radar_cycle": section_state("radar"), "candidate_lineage": section_state("candidate_conveyor"),
            "benchmark_9h": section_state("benchmark_9h"), "shadow_9i": section_state("shadow_9i"),
            "outcomes_9j": section_state("outcomes_9j"),
            "professional_research": section_state("professional_strategy_observatory"),
            "provider_credit": section_state("provider_credit_meter"), "paper_state": section_state("books"),
            "paper": {key: books.get(key) for key in ("nav", "cash", "positions", "transactions", "orders", "fills")},
            "product_summary": {"total": len(products), "current": sum(x["source_state"] == "CURRENT" for x in products), "not_activated": sum(x["source_state"] == "NOT_ACTIVATED" for x in products)},
            "method_summary": {"total": len(methods), "rankable": 0, "insufficient_sample": len(methods)},
            "sleeves": {"product_count": 24, "basis_each": 10_000.0, "label": SYNTHETIC_LABEL,
                        "operational_fund_touched": False, "operational_positions_created": 0},
            "session_gates": {gate: "WAITING" for gate in SESSION_GATES}, "blockers": blockers,
            "max_briefing": "Sources are not activated. Twenty-four comparison sleeves wait; operational capital does not move.",
            "unsafe_authority": unsafe, "authority": authority,
            "research_eligible": False, "paper_eligible": False,
            "products": products, "methods": methods, "professional_audit": professional_readiness_audit(),
            "method_scoreboard": method_scoreboard(())}


def validate_browser_projection(value: dict[str, Any]) -> None:
    if (value.get("schema_version") != SCHEMA_VERSION or len(value.get("products", ())) != 24
            or len(value.get("methods", ())) != 16 or value.get("unsafe_authority") is not False
            or any(value.get("authority", {}).values()) or value.get("research_eligible") is not False
            or value.get("paper_eligible") is not False or value.get("sleeves", {}).get("operational_fund_touched") is not False):
        raise ValueError("TUESDAY_PROJECTION_INVALID")
    prohibited = ("credential_value", "private_9i", "session_results", "source_text", "transcript_text", "provider_body", "filesystem_path")
    if any(term in str(value).lower() for term in prohibited):
        raise ValueError("TUESDAY_PROJECTION_PRIVATE_FIELD")
