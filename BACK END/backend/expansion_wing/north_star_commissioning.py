from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import re
from typing import Any, Iterable

from .multi_product_research import AUTHORITY, METHODS, PRODUCTS

CASE_SCHEMA = "iios-browser-safe-case-registry-v1"
COMMISSIONING_SCHEMA = "iios-north-star-tuesday-commissioning-v1"
SYNTHETIC_LABEL = "Synthetic comparison basis — not deployable capital."
CASE_FIELDS = frozenset({"case_id", "ticker", "instrument", "title", "created_at", "updated_at", "stage", "status", "originating_cycle_id", "evidence_completeness", "thesis_summary", "bear_case_summary", "invalidation", "validation_9h_state", "shadow_9i_state", "outcome_9j_state", "committee_state", "risk_state", "paper_eligibility", "position_state", "closure_state", "outcome_availability", "blockers", "receipt_categories"})
CASE_STAGES = frozenset({"AWAITING_EVIDENCE", "RESEARCH", "COMMITTEE", "RISK", "REJECTED", "CLOSED", "UNAVAILABLE"})
CASE_STATES = frozenset({"CURRENT", "INCOMPLETE", "UNAVAILABLE", "REJECTED", "CLOSED"})
PRODUCT_CLASSIFICATIONS = {"EQUITY_ETF": "RESEARCH_ONLY", "TREASURY": "INCOMPLETE", "CREDIT": "INCOMPLETE", "OPTION": "INCOMPLETE", "COMMODITY": "INCOMPLETE", "FX": "INCOMPLETE", "CRYPTO": "INCOMPLETE", "INCOME": "RESEARCH_ONLY"}
PROHIBITED_CASE_KEYS = frozenset({"prompt", "model_response", "session_results", "provider_body", "credential", "headers", "source_path", "private_9i", "raw_error", "ledger_contents"})


def _timestamp(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or len(value) > 40:
        raise ValueError("CASE_TIMESTAMP_INVALID")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("CASE_TIMESTAMP_INVALID") from None
    if parsed.tzinfo is None or parsed.astimezone(timezone.utc) > datetime.now(timezone.utc):
        raise ValueError("CASE_TIMESTAMP_INVALID")
    return value


def browser_safe_case_registry(records: Iterable[dict[str, Any]] | None, *, source_state: str) -> dict[str, Any]:
    if source_state not in {"CURRENT", "STALE", "INCOMPLETE", "UNAVAILABLE", "FAILED_CLOSED"}:
        raise ValueError("CASE_SOURCE_STATE_INVALID")
    if records is None:
        return {"schema_version": CASE_SCHEMA, "state": source_state, "total": None, "counts": {key: None for key in ("active", "awaiting_evidence", "committee", "risk", "rejected", "closed", "with_outcomes", "without_browser_details")}, "cases": [], "mu_case_state": "UNAVAILABLE", "reason": "AUTHENTICATED_CASE_SOURCE_UNAVAILABLE", "authority": AUTHORITY.copy()}
    safe: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in records:
        if not isinstance(raw, dict) or set(raw) - CASE_FIELDS or set(raw) & PROHIBITED_CASE_KEYS:
            raise ValueError("CASE_RECORD_UNSAFE")
        case_id = raw.get("case_id")
        if not isinstance(case_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{7,127}", case_id) or case_id in seen:
            raise ValueError("CASE_ID_INVALID_OR_DUPLICATE")
        seen.add(case_id)
        stage, status = raw.get("stage"), raw.get("status")
        if stage not in CASE_STAGES or status not in CASE_STATES:
            raise ValueError("CASE_STATE_INVALID")
        row = {key: raw.get(key) for key in CASE_FIELDS}
        row["created_at"], row["updated_at"] = _timestamp(row["created_at"]), _timestamp(row["updated_at"])
        for key in ("ticker", "instrument", "title", "originating_cycle_id", "evidence_completeness", "thesis_summary", "bear_case_summary", "invalidation", "validation_9h_state", "shadow_9i_state", "outcome_9j_state", "committee_state", "risk_state", "position_state", "closure_state", "outcome_availability"):
            if row[key] is not None and (not isinstance(row[key], str) or len(row[key]) > 500):
                raise ValueError("CASE_FIELD_INVALID")
        for key in ("blockers", "receipt_categories"):
            value = row[key]
            if value is None:
                row[key] = []
            elif not isinstance(value, (list, tuple)) or len(value) > 24 or any(not isinstance(item, str) or len(item) > 96 for item in value):
                raise ValueError("CASE_FIELD_INVALID")
            else:
                row[key] = list(value)
        if row["paper_eligibility"] not in {True, False, None}:
            raise ValueError("CASE_FIELD_INVALID")
        safe.append(row)
    counts = {"active": sum(row["stage"] not in {"REJECTED", "CLOSED"} for row in safe), "awaiting_evidence": sum(row["stage"] == "AWAITING_EVIDENCE" for row in safe), "committee": sum(row["stage"] == "COMMITTEE" for row in safe), "risk": sum(row["stage"] == "RISK" for row in safe), "rejected": sum(row["stage"] == "REJECTED" for row in safe), "closed": sum(row["stage"] == "CLOSED" for row in safe), "with_outcomes": sum(row["outcome_availability"] == "AVAILABLE" for row in safe), "without_browser_details": sum(not row["title"] or not row["thesis_summary"] for row in safe)}
    mu = next((row for row in safe if row["ticker"] == "MU"), None)
    mu_state = "UNAVAILABLE" if mu is None else "INCOMPLETE" if mu["status"] == "INCOMPLETE" or mu["evidence_completeness"] != "COMPLETE" else mu["status"]
    return {"schema_version": CASE_SCHEMA, "state": source_state, "total": len(safe), "counts": counts, "cases": safe, "mu_case_state": mu_state, "reason": None, "authority": AUTHORITY.copy()}


def synthetic_accounts() -> tuple[dict[str, Any], ...]:
    return tuple({"account_id": f"synthetic_{p.product_id}", "product_id": p.product_id, "product_name": p.display_name, "label": SYNTHETIC_LABEL, "starting_basis": 10_000.0, "synthetic_nav": 10_000.0, "synthetic_cash": 10_000.0, "modeled_positions": 0, "modeled_trades": 0, "realized_result": None, "unrealized_result": None, "fees": None, "spread": None, "slippage": None, "drawdown": None, "favorable_excursion": None, "adverse_excursion": None, "sample_size": 0, "calibration": None, "assigned_methods": [m.method_id for m in METHODS if p.family in m.eligible_families], "evidence_state": "UNAVAILABLE", "data_source_state": "NOT_ACTIVATED", "tuesday_classification": PRODUCT_CLASSIFICATIONS[p.family], "research_eligibility": False, "paper_research_eligibility": False, "blocker": "AUTHENTIC_PRODUCT_EVIDENCE_REQUIRED", "next_observation": "SEPARATELY_AUTHORIZED_SOURCE_WAVE", "pooled": False, "operational_capital": False, "authority": AUTHORITY.copy()} for p in PRODUCTS)


def provider_inventory() -> tuple[dict[str, Any], ...]:
    rows = (("Financial Datasets", "API", "EQUITIES_COMPANY_FACTS", "REVIEWED_INTERNAL_USE", "APPROVED_FOR_BOUNDED_TEST", "KEYCHAIN_SELECTOR", "SEPARATE_AUTHORIZED_PROCESS"), ("Financial Modeling Prep", "API", "EQUITY_ENRICHMENT", "LICENSE_REVIEW_REQUIRED", "RIGHTS_REVIEW_REQUIRED", "KEYCHAIN_SELECTOR", "NOT_VERIFIED_THIS_BATCH"), ("Koyfin", "MANUAL", "CROSS_ASSET_RESEARCH", "DISPLAY_RIGHTS_UNVERIFIED", "MANUAL_RESEARCH_ONLY", "NONE", "NOT_APPLICABLE"), ("Market Vision", "MANUAL", "PHYSICAL_COMMODITIES", "RIGHTS_REVIEW_REQUIRED", "RIGHTS_REVIEW_REQUIRED", "NONE", "NOT_APPLICABLE"), ("SEC EDGAR", "OFFICIAL_PUBLIC", "PRIMARY_FILINGS", "ACCESS_POLICY_REVIEW", "MANUAL_RESEARCH_ONLY", "NONE", "NOT_APPLICABLE"), ("Issuer official sources", "OFFICIAL_PUBLIC", "FILINGS_AND_LETTERS", "PER_SOURCE_REVIEW", "MANUAL_RESEARCH_ONLY", "NONE", "NOT_APPLICABLE"), ("9A/9B/9E/9H/9I/9J sanitized artifacts", "LOCAL_READ_ONLY", "FACTORY_OBSERVATION", "INTERNAL_SANITIZED", "DELAYED_RESEARCH_ONLY", "NONE", "NOT_APPLICABLE"))
    return tuple({"provider": provider, "workflow": workflow, "products_covered": coverage, "rights": rights, "classification": classification, "credential_location": location, "credential_availability": availability, "rate_limit": None, "credit_limit": None, "timestamp_quality": "SOURCE_SPECIFIC", "operational_binding": False, "missing_fields": ["VERIFIED_DISPLAY_RIGHTS", "VERIFIED_PRODUCT_COVERAGE"], "provider_authority": False, "broker_interface": False, "ledger_interface": False} for provider, workflow, coverage, rights, classification, location, availability in rows)


def commissioning(case_records: Iterable[dict[str, Any]] | None = None, *, case_source_state: str = "UNAVAILABLE") -> dict[str, Any]:
    cases = browser_safe_case_registry(case_records, source_state=case_source_state)
    accounts = synthetic_accounts()
    methods = tuple({**asdict(method), "state": "INSUFFICIENT_SAMPLE", "sample_size": 0, "ranking_eligible": False, "score": None, "authority": AUTHORITY.copy()} for method in METHODS)
    payload = {"schema_version": COMMISSIONING_SCHEMA, "cases": cases, "products": [asdict(p) for p in PRODUCTS], "synthetic_accounts": accounts, "methods": methods, "sources": provider_inventory(), "source_waves": {wave: {"state": "NOT_ACTIVATED", "requests": 0, "credits": 0, "reason": "RIGHTS_COST_OR_COVERAGE_GATE_NOT_VERIFIED"} for wave in "ABCDEF"}, "operational_paper": {"nav": 10_000.0, "cash": 10_000.0, "positions": 0, "transactions": 0, "orders": 0, "fills": 0}, "provider_requests": 0, "provider_credits": 0, "authority": AUTHORITY.copy()}
    payload["content_hash"] = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")).hexdigest()
    return payload


def validate_commissioning(payload: dict[str, Any]) -> None:
    if payload.get("schema_version") != COMMISSIONING_SCHEMA or len(payload.get("products", ())) != 24 or len(payload.get("synthetic_accounts", ())) != 24 or len(payload.get("methods", ())) != 16:
        raise ValueError("NORTH_STAR_COMMISSIONING_INVALID")
    if payload.get("provider_requests") != 0 or payload.get("provider_credits") != 0 or any(payload.get("authority", {}).values()):
        raise ValueError("NORTH_STAR_AUTHORITY_INVALID")
    for account in payload["synthetic_accounts"]:
        if account["starting_basis"] != 10_000 or account["synthetic_nav"] != 10_000 or account["synthetic_cash"] != 10_000 or account["modeled_positions"] or account["modeled_trades"] or account["pooled"] or account["operational_capital"]:
            raise ValueError("SYNTHETIC_ACCOUNT_INVALID")
        if any(account[key] is not None for key in ("realized_result", "unrealized_result", "fees", "spread", "slippage", "drawdown", "favorable_excursion", "adverse_excursion", "calibration")):
            raise ValueError("MISSING_RESULT_INFERRED")
