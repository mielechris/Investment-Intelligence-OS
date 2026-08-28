#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "batch9r-data-expansion-factory-v1"
DEFAULT_STATE_DIR = Path.home() / "Library" / "Application Support" / "IIOS" / "market-validation"
DEFAULT_TELEMETRY_DIR = Path.home() / "Library" / "Application Support" / "IIOS" / "telemetry"


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists() or not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _num(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _validation_metrics(scorecard: dict[str, Any]) -> dict[str, Any]:
    raw = scorecard.get("metrics") if isinstance(scorecard.get("metrics"), dict) else {}
    benchmark = _int(raw.get("benchmark_opportunity_count", raw.get("opportunity_count")))
    detected = _int(
        raw.get(
            "eventual_detected_count",
            raw.get("radar_detected_count", raw.get("detected_count")),
        )
    )
    return {
        "benchmark_opportunity_count": benchmark,
        "detected_count": detected,
        "aggregate_miss_count": max(0, benchmark - detected),
        "detection_rate_pct": _num(
            raw.get("eventual_detection_rate_pct", raw.get("detection_rate_pct"))
        ),
        "opportunity_miss_rate_pct": _num(
            raw.get(
                "eventual_opportunity_miss_rate_pct",
                raw.get("opportunity_miss_rate_pct"),
            )
        ),
        "average_detection_latency_minutes": _num(
            raw.get("average_detection_latency_minutes")
        ),
        "provider_error_count": _int(raw.get("provider_error_count")),
    }


def _existing_sources() -> list[dict[str, Any]]:
    """Source implementations already evidenced in the IIOS repository.

    This inventory says only that adapters/implementation paths exist. It does
    not claim production availability, contractual rights, or current health.
    """
    return [
        {
            "source_id": "GOOGLE_NEWS_RSS",
            "source_name": "Google News RSS",
            "domain": "NEWS_AGGREGATION",
            "implementation_evidence": "BACK END/backend/provider_hardening.py",
            "inventory_state": "IMPLEMENTATION_PRESENT",
        },
        {
            "source_id": "GDELT_NEWS",
            "source_name": "GDELT news search",
            "domain": "GLOBAL_NEWS_EVENTS",
            "implementation_evidence": "BACK END/backend/provider_hardening.py",
            "inventory_state": "IMPLEMENTATION_PRESENT",
        },
        {
            "source_id": "SEC_COMPANYFACTS",
            "source_name": "SEC EDGAR Company Facts",
            "domain": "CORPORATE_FUNDAMENTALS",
            "implementation_evidence": "BACK END/backend/provider_hardening.py",
            "inventory_state": "IMPLEMENTATION_PRESENT",
        },
        {
            "source_id": "STOOQ_MARKET_DATA",
            "source_name": "Stooq market data",
            "domain": "MARKET_PRICES",
            "implementation_evidence": "BACK END/backend/provider_hardening.py",
            "inventory_state": "IMPLEMENTATION_PRESENT",
        },
        {
            "source_id": "YAHOO_CHART",
            "source_name": "Yahoo chart market data",
            "domain": "MARKET_PRICES",
            "implementation_evidence": "BACK END/backend/provider_hardening.py",
            "inventory_state": "IMPLEMENTATION_PRESENT",
        },
        {
            "source_id": "OFFICIAL_WEB",
            "source_name": "First-party official web pages",
            "domain": "PRIMARY_EVIDENCE",
            "implementation_evidence": "BACK END/backend/official_sources.py",
            "inventory_state": "IMPLEMENTATION_PRESENT",
        },
    ]


def _candidate_catalog() -> list[dict[str, Any]]:
    """Governed research candidates, not approved or connected providers.

    Commercial entries deliberately avoid vendor names until coverage, pricing,
    redistribution rights, latency and contract terms are researched and
    persisted. Public/official entries still require access/licensing review.
    """
    return [
        {
            "source_id": "SEC_EDGAR_EVENT_FILINGS",
            "source_name": "SEC EDGAR event-filings expansion",
            "domain": "CORPORATE_EVENTS_INSIDER_OWNERSHIP",
            "source_class": "OFFICIAL_PUBLIC",
            "closes_gaps": ["RADAR_EVENT_COVERAGE", "PRIMARY_EVIDENCE", "INSIDER_OWNERSHIP"],
            "research_basis": "Extend beyond current Company Facts coverage into event-oriented filings and ownership forms.",
            "access_state": "NOT_CONNECTED",
            "intake_stage": "RESEARCH_READY",
        },
        {
            "source_id": "FED_MACRO_OFFICIAL",
            "source_name": "Federal Reserve / official macro-release feeds",
            "domain": "MACRO_RATES_LIQUIDITY",
            "source_class": "OFFICIAL_PUBLIC",
            "closes_gaps": ["MACRO_RELEASE_COVERAGE", "EVENT_TIMING", "PRIMARY_EVIDENCE"],
            "research_basis": "Add structured official macro-release observations and release-time evidence.",
            "access_state": "NOT_CONNECTED",
            "intake_stage": "RESEARCH_READY",
        },
        {
            "source_id": "FEDERAL_REGISTER_POLICY",
            "source_name": "Federal Register / official rulemaking feed",
            "domain": "POLICY_REGULATION",
            "source_class": "OFFICIAL_PUBLIC",
            "closes_gaps": ["POLICY_EVENT_COVERAGE", "PRIMARY_EVIDENCE"],
            "research_basis": "Structured official policy events can reduce dependence on secondary-news discovery.",
            "access_state": "NOT_CONNECTED",
            "intake_stage": "RESEARCH_READY",
        },
        {
            "source_id": "NOAA_NWS_WEATHER",
            "source_name": "NOAA / NWS weather and hazard feeds",
            "domain": "WEATHER_CLIMATE_HAZARDS",
            "source_class": "OFFICIAL_PUBLIC",
            "closes_gaps": ["WEATHER_SHOCK_COVERAGE", "AGRICULTURE_RISK", "ENERGY_RISK"],
            "research_basis": "Structured weather and hazard evidence can improve commodity, agriculture and regional-risk detection.",
            "access_state": "NOT_CONNECTED",
            "intake_stage": "RESEARCH_READY",
        },
        {
            "source_id": "EIA_ENERGY_OPEN_DATA",
            "source_name": "U.S. energy official data feed",
            "domain": "ENERGY_PHYSICAL_MARKETS",
            "source_class": "OFFICIAL_PUBLIC",
            "closes_gaps": ["ENERGY_SUPPLY_DEMAND", "COMMODITY_FUNDAMENTALS"],
            "research_basis": "Physical energy inventory and supply-demand evidence can strengthen energy theses beyond price/news signals.",
            "access_state": "NOT_CONNECTED",
            "intake_stage": "RESEARCH_READY",
        },
        {
            "source_id": "USDA_AGRICULTURE_OFFICIAL",
            "source_name": "USDA agriculture / crop / market data",
            "domain": "AGRICULTURE_PHYSICAL_MARKETS",
            "source_class": "OFFICIAL_PUBLIC",
            "closes_gaps": ["AGRICULTURE_SUPPLY_DEMAND", "COMMODITY_FUNDAMENTALS", "WEATHER_TRANSMISSION"],
            "research_basis": "Official agriculture observations can strengthen crop, livestock and food-commodity research.",
            "access_state": "NOT_CONNECTED",
            "intake_stage": "RESEARCH_READY",
        },
        {
            "source_id": "CFTC_POSITIONING",
            "source_name": "CFTC positioning data",
            "domain": "FUTURES_POSITIONING",
            "source_class": "OFFICIAL_PUBLIC",
            "closes_gaps": ["POSITIONING_CROWDING", "COMMODITY_CONTEXT"],
            "research_basis": "Positioning evidence can help distinguish fundamental signals from crowded exposure.",
            "access_state": "NOT_CONNECTED",
            "intake_stage": "RESEARCH_READY",
        },
        {
            "source_id": "COMPANY_IR_PRIMARY",
            "source_name": "Company investor-relations / press-release feeds",
            "domain": "CORPORATE_PRIMARY_EVENTS",
            "source_class": "FIRST_PARTY_PUBLIC",
            "closes_gaps": ["RADAR_EVENT_COVERAGE", "PRIMARY_EVIDENCE", "EARNINGS_EVENTS"],
            "research_basis": "First-party corporate releases can provide faster primary evidence than secondary aggregation for some events.",
            "access_state": "NOT_CONNECTED",
            "intake_stage": "RESEARCH_READY",
        },
        {
            "source_id": "REALTIME_NEWS_COMMERCIAL_TBD",
            "source_name": "Commercial real-time news candidate — provider TBD",
            "domain": "REAL_TIME_NEWS",
            "source_class": "COMMERCIAL_RESEARCH",
            "closes_gaps": ["RADAR_EVENT_COVERAGE", "DETECTION_LATENCY", "NEWS_REDUNDANCY"],
            "research_basis": "9H recall and latency can justify comparing a commercial low-latency news feed, but provider claims must be measured before selection.",
            "access_state": "NOT_CONNECTED",
            "intake_stage": "VENDOR_RESEARCH_REQUIRED",
        },
        {
            "source_id": "OPTIONS_VOLATILITY_COMMERCIAL_TBD",
            "source_name": "Options / volatility data candidate — provider TBD",
            "domain": "OPTIONS_POSITIONING_VOLATILITY",
            "source_class": "COMMERCIAL_RESEARCH",
            "closes_gaps": ["OPTIONS_POSITIONING", "VOLATILITY_REGIME", "EVENT_RISK"],
            "research_basis": "Evaluate whether richer options evidence improves event-risk and positioning intelligence beyond current signals.",
            "access_state": "NOT_CONNECTED",
            "intake_stage": "VENDOR_RESEARCH_REQUIRED",
        },
        {
            "source_id": "CONSENSUS_ESTIMATES_COMMERCIAL_TBD",
            "source_name": "Consensus / estimate-revision candidate — provider TBD",
            "domain": "EXPECTATIONS_REVISIONS",
            "source_class": "COMMERCIAL_RESEARCH",
            "closes_gaps": ["EXPECTATIONS_GAP", "REVISION_MOMENTUM", "EARNINGS_CONTEXT"],
            "research_basis": "Estimate-revision data could distinguish price dislocation from changing fundamental expectations if validated.",
            "access_state": "NOT_CONNECTED",
            "intake_stage": "VENDOR_RESEARCH_REQUIRED",
        },
        {
            "source_id": "SHORT_BORROW_COMMERCIAL_TBD",
            "source_name": "Short-interest / borrow candidate — provider TBD",
            "domain": "SHORT_POSITIONING_BORROW",
            "source_class": "COMMERCIAL_RESEARCH",
            "closes_gaps": ["POSITIONING_CROWDING", "SQUEEZE_RISK"],
            "research_basis": "Short and borrow evidence could improve crowding and squeeze-risk context if the data proves timely and reliable.",
            "access_state": "NOT_CONNECTED",
            "intake_stage": "VENDOR_RESEARCH_REQUIRED",
        },
        {
            "source_id": "MODEL_TASK_TELEMETRY",
            "source_name": "Internal model task/cost/latency telemetry",
            "domain": "INTERNAL_INTELLIGENCE_TELEMETRY",
            "source_class": "INTERNAL_MEASUREMENT",
            "closes_gaps": ["MODEL_PERFORMANCE_BY_TASK", "MODEL_COST_ATTRIBUTION", "MODEL_LATENCY"],
            "research_basis": "9P cannot compare Grok, Gemini, OpenAI and Kimi responsibly until task-level results, latency and cost are persisted under one rubric.",
            "access_state": "NOT_PERSISTED",
            "intake_stage": "INTERNAL_INSTRUMENTATION_REQUIRED",
        },
    ]


def _gap_signals(
    *,
    office: dict[str, Any],
    lab: dict[str, Any],
    scorecard: dict[str, Any],
    telemetry: dict[str, Any],
) -> list[dict[str, Any]]:
    validation = _validation_metrics(scorecard)
    output: list[dict[str, Any]] = []
    miss_rate = validation.get("opportunity_miss_rate_pct")
    if miss_rate is not None and miss_rate >= 20:
        output.append(
            {
                "gap_id": "RADAR_EVENT_COVERAGE",
                "severity": "HIGH",
                "evidence": f"9H opportunity miss rate {miss_rate:.1f}% with {validation['aggregate_miss_count']} aggregate misses.",
            }
        )
    provider_errors = _int(
        (telemetry.get("providers") or {}).get("provider_error_count")
        if isinstance(telemetry.get("providers"), dict)
        else validation.get("provider_error_count")
    )
    if provider_errors:
        output.append(
            {
                "gap_id": "NEWS_REDUNDANCY",
                "severity": "HIGH",
                "evidence": f"Persisted provider error count: {provider_errors}.",
            }
        )
    coverage = office.get("analysis_coverage") if isinstance(office.get("analysis_coverage"), dict) else {}
    if coverage.get("model_performance_by_task") is not True:
        output.append(
            {
                "gap_id": "MODEL_PERFORMANCE_BY_TASK",
                "severity": "HIGH",
                "evidence": "9P marks task-level model performance as a measurement gap.",
            }
        )
    if coverage.get("unused_new_data_sources") is not True:
        output.append(
            {
                "gap_id": "DATA_SOURCE_SCOUTING",
                "severity": "MEDIUM",
                "evidence": "9P does not yet have a governed persisted new-source scouting program.",
            }
        )
    lab_summary = lab.get("summary") if isinstance(lab.get("summary"), dict) else {}
    if _int(lab_summary.get("need_more_data_count")):
        output.append(
            {
                "gap_id": "EXPERIMENT_SAMPLE_DEPTH",
                "severity": "MEDIUM",
                "evidence": f"9Q reports {_int(lab_summary.get('need_more_data_count'))} experiment(s) waiting for more evidence.",
            }
        )
    return output


def _priority_score(candidate: dict[str, Any], gap_signals: list[dict[str, Any]]) -> int:
    severity_weight = {"HIGH": 24, "MEDIUM": 12, "LOW": 5}
    signal_by_gap = {str(row.get("gap_id")): row for row in gap_signals}
    score = 34
    candidate_gaps = {str(value) for value in candidate.get("closes_gaps") or []}
    for gap_id in candidate_gaps:
        row = signal_by_gap.get(gap_id)
        if row:
            score += severity_weight.get(str(row.get("severity")), 5)
    if "RADAR_EVENT_COVERAGE" in candidate_gaps and "RADAR_EVENT_COVERAGE" in signal_by_gap:
        score += 14
    source_class = str(candidate.get("source_class") or "")
    if source_class == "OFFICIAL_PUBLIC":
        score += 10
    elif source_class == "FIRST_PARTY_PUBLIC":
        score += 8
    elif source_class == "INTERNAL_MEASUREMENT":
        score += 12
    if candidate.get("intake_stage") == "VENDOR_RESEARCH_REQUIRED":
        score -= 4
    return max(0, min(100, score))


def _enrich_candidate(candidate: dict[str, Any], gap_signals: list[dict[str, Any]]) -> dict[str, Any]:
    source_class = str(candidate.get("source_class") or "")
    publicish = source_class in {"OFFICIAL_PUBLIC", "FIRST_PARTY_PUBLIC"}
    internal = source_class == "INTERNAL_MEASUREMENT"
    return {
        **candidate,
        "priority_score": _priority_score(candidate, gap_signals),
        "current_in_factory": False,
        "shadow_feed_connected": False,
        "production_feed_enabled": False,
        "quality_measurement_state": "NOT_MEASURED_IN_9R",
        "latency_measurement_state": "NOT_MEASURED_IN_9R",
        "coverage_measurement_state": "NOT_MEASURED_IN_9R",
        "data_provider_cost": "NO_PERSISTED_COST_EVIDENCE",
        "licensing_state": "REVIEW_REQUIRED",
        "credential_state": "NOT_REQUESTED",
        "governance_risk": (
            "LOW_TO_MEDIUM_PUBLIC_SOURCE_REVIEW"
            if publicish
            else "LOW_INTERNAL_INSTRUMENTATION"
            if internal
            else "MEDIUM_COMMERCIAL_CONTRACT_AND_USAGE_RIGHTS_REVIEW"
        ),
        "recommended_action": (
            "RESEARCH_ACCESS_AND_BUILD_READ_ONLY_SHADOW_ADAPTER"
            if publicish
            else "PERSIST_INTERNAL_MEASUREMENT_RUBRIC"
            if internal
            else "RESEARCH_VENDOR_TERMS_BEFORE_ANY_SHADOW_CONNECTION"
        ),
        "shadow_acceptance_tests": [
            "COVERAGE_GAIN_VS_EXISTING_SOURCES",
            "FRESHNESS_AND_LATENCY",
            "MISSINGNESS_AND_OUTAGE_RATE",
            "DUPLICATE_AND_FALSE_POSITIVE_LOAD",
            "EVIDENCE_QUALITY_AND_TRACEABILITY",
            "MARGINAL_9H_DETECTION_IMPROVEMENT",
            "COST_PER_USEFUL_SIGNAL_IF_COST_EXISTS",
            "LICENSE_AND_REDISTRIBUTION_FIT",
        ],
        "suggested_implementation_batch": "9R.SHADOW",
    }


def build_data_expansion_factory(
    *,
    office: dict[str, Any],
    lab: dict[str, Any],
    scorecard: dict[str, Any],
    telemetry: dict[str, Any],
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    now = generated_at or datetime.now(timezone.utc)
    gaps = _gap_signals(office=office, lab=lab, scorecard=scorecard, telemetry=telemetry)
    candidates = [_enrich_candidate(row, gaps) for row in _candidate_catalog()]
    candidates.sort(key=lambda row: int(row.get("priority_score", 0)), reverse=True)
    top = candidates[:10]

    public_count = sum(
        1 for row in candidates if row.get("source_class") in {"OFFICIAL_PUBLIC", "FIRST_PARTY_PUBLIC"}
    )
    commercial_count = sum(1 for row in candidates if row.get("source_class") == "COMMERCIAL_RESEARCH")
    internal_count = sum(1 for row in candidates if row.get("source_class") == "INTERNAL_MEASUREMENT")

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": now.astimezone(timezone.utc).isoformat(),
        "status": "DATA_EXPANSION_FACTORY_ADVISORY_READY",
        "mission": "Find the next data source that closes a measured IIOS intelligence gap without silently changing production.",
        "current_source_inventory": _existing_sources(),
        "data_gaps": gaps,
        "candidate_sources": top,
        "full_candidate_count": len(candidates),
        "comparison_dimensions": [
            "COVERAGE",
            "LATENCY",
            "QUALITY",
            "MISSINGNESS",
            "REDUNDANCY",
            "COST",
            "LICENSING_AND_USAGE_RIGHTS",
            "TRACEABILITY",
            "MARGINAL_DETECTION_GAIN",
        ],
        "intake_pipeline": [
            "DISCOVERY",
            "SOURCE_RESEARCH",
            "COST_LICENSE_REVIEW",
            "READ_ONLY_ADAPTER_DRY_RUN",
            "SHADOW_INGESTION",
            "QUALITY_AND_LATENCY_GRADE",
            "9Q_AB_VALIDATION",
            "HUMAN_APPROVAL",
            "PRODUCTION_ELIGIBILITY_REVIEW",
        ],
        "shadow_trials": [],
        "approved_sources": [],
        "rejected_sources": [],
        "summary": {
            "existing_implementation_count": len(_existing_sources()),
            "identified_gap_count": len(gaps),
            "candidate_source_count": len(candidates),
            "public_first_party_candidate_count": public_count,
            "commercial_research_candidate_count": commercial_count,
            "internal_measurement_candidate_count": internal_count,
            "shadow_connected_count": 0,
            "approved_source_count": 0,
            "production_sources_added": 0,
        },
        "source_state": {
            "chief_office_status": office.get("status"),
            "experiment_lab_status": lab.get("status"),
            "scorecard_generated_at": scorecard.get("generated_at"),
            "telemetry_generated_at": telemetry.get("generated_at"),
        },
        "safety": {
            "advisory_only": True,
            "research_only_until_human_approval": True,
            "auto_connect_provider": False,
            "auto_request_credentials": False,
            "credential_use_authority": False,
            "purchase_authority": False,
            "license_acceptance_authority": False,
            "production_feed_change_authority": False,
            "auto_apply_thresholds": False,
            "agent_weight_change_authority": False,
            "committee_change_authority": False,
            "risk_rule_change_authority": False,
            "capital_authority": False,
            "trade_execution_permission": False,
            "live_execution": False,
            "human_approval_required": True,
        },
    }


def build_from_state(state_dir: Path, telemetry_dir: Path) -> dict[str, Any]:
    browser = state_dir / "browser"
    return build_data_expansion_factory(
        office=_read_json(browser / "chief_intelligence_office.json"),
        lab=_read_json(browser / "experiment_ab_laboratory.json"),
        scorecard=_read_json(state_dir / "latest_market_validation.json"),
        telemetry=_read_json(telemetry_dir / "latest.json"),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the Batch 9R governed Data Expansion Factory artifact.")
    parser.add_argument("--state-dir", default=str(DEFAULT_STATE_DIR))
    parser.add_argument("--telemetry-dir", default=str(DEFAULT_TELEMETRY_DIR))
    parser.add_argument("--output")
    parser.add_argument("--stdout", action="store_true")
    args = parser.parse_args()
    payload = build_from_state(Path(args.state_dir).expanduser(), Path(args.telemetry_dir).expanduser())
    if args.output:
        _atomic_write(Path(args.output).expanduser(), payload)
    print(
        json.dumps(
            payload if args.stdout or not args.output else {"status": payload["status"], "output": args.output},
            indent=2,
            sort_keys=True,
            default=str,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
