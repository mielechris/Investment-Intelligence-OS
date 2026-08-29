#!/usr/bin/env python3
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

SCHEMA_VERSION = "batch10i-chief-intelligence-office-v2"


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _rows(value: Any) -> list[dict[str, Any]]:
    return [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []


def _candidate(upgrade_id: str, title: str, why: str, evidence: list[str], *, score: int, action_class: str, suggested_batch: str, effort: str, risk: str, measurement_goal: str) -> dict[str, Any]:
    return {
        "upgrade_id": upgrade_id,
        "title": title,
        "why_it_should_improve_intelligence": why,
        "supporting_evidence": evidence,
        "priority_score": score,
        "action_class": action_class,
        "suggested_implementation_batch": suggested_batch,
        "engineering_effort": effort,
        "safety_governance_risk": risk,
        "measurement_goal": measurement_goal,
    }


def _pipeline_state(historical: dict[str, Any], stage: str) -> tuple[str, str | None]:
    for row in _rows(historical.get("pipeline")):
        if str(row.get("stage") or "").upper() == stage.upper():
            return str(row.get("state") or "UNKNOWN"), str(row.get("note") or "") or None
    return "UNKNOWN", None


def _legacy_candidates(legacy: dict[str, Any]) -> list[dict[str, Any]]:
    memo = legacy.get("improvement_memo") if isinstance(legacy.get("improvement_memo"), dict) else {}
    output: list[dict[str, Any]] = []
    for row in _rows(memo.get("top_five_upgrades")):
        item = dict(row)
        item.setdefault("action_class", str(item.get("production_shadow_research_recommendation") or "RESEARCH"))
        item.setdefault("measurement_goal", str(item.get("expected_impact") or "Measure whether this change improves IIOS outcomes."))
        output.append(item)
    return output


def build_office_v2(
    *,
    legacy_office: dict[str, Any],
    experiment_lab: dict[str, Any],
    data_expansion: dict[str, Any],
    agent_league: dict[str, Any],
    regime: dict[str, Any],
    qualification: dict[str, Any],
    portfolio: dict[str, Any],
    readiness: dict[str, Any],
    qualification_watch: dict[str, Any],
    historical: dict[str, Any],
    event_reconstruction: dict[str, Any] | None = None,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    candidates = _legacy_candidates(legacy_office)
    event_reconstruction = event_reconstruction or {}

    historical_summary = historical.get("research_summary") if isinstance(historical.get("research_summary"), dict) else {}
    studies_ready = _int(historical_summary.get("studies_ready"))
    targets_known = _int(historical_summary.get("targets_known"))
    raw_errors = historical_summary.get("errors") if isinstance(historical_summary.get("errors"), list) else []
    historical_errors = [str(value) for value in raw_errors if value]

    event_state_10h, event_note = _pipeline_state(historical, "EVENT_RECONSTRUCTION")
    regime_state, regime_note = _pipeline_state(historical, "REGIME_NORMALIZATION")

    event_summary = event_reconstruction.get("research_summary") if isinstance(event_reconstruction.get("research_summary"), dict) else {}
    event_engine_status = str(event_reconstruction.get("status") or "")
    event_symbols_ready = _int(event_summary.get("symbols_ready"))
    event_contexts_ready = _int(event_summary.get("analog_contexts_ready"))
    event_engine_active = event_engine_status == "HISTORICAL_EVENT_RECONSTRUCTION_ACTIVE" and event_symbols_ready > 0
    effective_event_state = "ACTIVE" if event_engine_active else event_state_10h

    if not event_engine_active and event_state_10h in {"MEASUREMENT_GAP", "PARTIAL", "UNKNOWN"}:
        candidates.append(_candidate(
            "HISTORICAL_EVENT_RECONSTRUCTION",
            "Build governed historical event reconstruction",
            "Price analogs are useful, but IIOS cannot yet determine whether a historical match was driven by the same causal event type.",
            [
                f"10H event reconstruction: {event_state_10h}",
                event_note or "No governed historical event/news corpus is attached to the 10H analog contract.",
                f"10H analog studies ready: {studies_ready} of {targets_known or 'unknown'} targets",
            ],
            score=115,
            action_class="BUILD_RESEARCH_DATA_LAYER",
            suggested_batch="10J",
            effort="HIGH",
            risk="LOW_TO_MEDIUM — historical evidence only; no trading authority.",
            measurement_goal="Measure whether causal/event-matched analogs improve 9H detection precision and 9J decision-quality outcomes versus price-only analogs.",
        ))

    if regime_state in {"PARTIAL", "MEASUREMENT_GAP", "UNKNOWN"}:
        candidates.append(_candidate(
            "HISTORICAL_REGIME_LIBRARY",
            "Add governed historical macro and regime normalization",
            "The analog engine should compare current setups against prior periods with similar rates, inflation, volatility, liquidity and growth conditions instead of price structure alone.",
            [
                f"10H regime normalization: {regime_state}",
                regime_note or "Validated historical macro/regime joins are not complete.",
                f"9T current regime status: {regime.get('status', 'unknown')}",
            ],
            score=112,
            action_class="BUILD_RESEARCH_DATA_LAYER",
            suggested_batch="10K",
            effort="HIGH",
            risk="MEDIUM — source quality and timestamp alignment must be governed before use.",
            measurement_goal="Compare analog usefulness before and after macro/regime filtering using mature 9J outcomes.",
        ))

    benchmark_present = bool(portfolio.get("benchmark_alpha_attribution") or qualification.get("benchmark_alpha_attribution") or qualification_watch.get("benchmark_alpha_attribution"))
    if not benchmark_present:
        candidates.append(_candidate(
            "BENCHMARK_ALPHA_ATTRIBUTION",
            "Add benchmark and control-portfolio alpha attribution",
            "Absolute paper returns cannot prove investment edge. IIOS needs contemporaneous control portfolios so performance is judged against simple alternatives and risk taken.",
            [
                f"10B qualification status: {qualification.get('status', 'unknown')}",
                f"10C portfolio status: {portfolio.get('status', 'unknown')}",
                "No persisted benchmark-alpha attribution contract is present in 10B/10C/10G.",
            ],
            score=110,
            action_class="BUILD_MEASUREMENT_LAYER",
            suggested_batch="10L",
            effort="MEDIUM",
            risk="LOW — measurement only; no allocation authority.",
            measurement_goal="Measure IIOS paper return, drawdown and risk-adjusted performance versus SPY, QQQ, cash/T-bill proxy and at least one simple mechanical control.",
        ))

    centralized_health = bool(legacy_office.get("central_data_health") or data_expansion.get("central_data_health") or qualification_watch.get("data_health"))
    if not centralized_health:
        historical_error_count = _int((historical.get("cycle") or {}).get("error_count") if isinstance(historical.get("cycle"), dict) else 0)
        candidates.append(_candidate(
            "DATA_HEALTH_WATCHDOG",
            "Create end-to-end data health and stale-input watchdog",
            "A process can be alive while its data fuel is stale or broken. IIOS needs one persisted health contract that distinguishes worker uptime from fresh usable downstream evidence.",
            [
                f"10H latest cycle errors: {historical_error_count}",
                "No whole-stack persisted PROCESS_ALIVE → DATA_FLOWING → DATA_FRESH → ANALYSIS_PRODUCED → DOWNSTREAM_CONSUMED scorecard is present.",
            ],
            score=108,
            action_class="BUILD_OPERATING_CONTROL",
            suggested_batch="10M",
            effort="MEDIUM",
            risk="LOW — observability only.",
            measurement_goal="Reduce time-to-detect silent provider, freshness and downstream-consumption failures.",
        ))

    league_status = str(agent_league.get("status") or "UNKNOWN")
    mature_outcomes = _int(qualification.get("mature_5d_outcomes"))
    if mature_outcomes < 30 or "WARM" in league_status.upper():
        candidates.append(_candidate(
            "DECISION_ATTRIBUTION_DEPTH",
            "Deepen case-level decision attribution before changing agent weights",
            "IIOS should know which evidence, agents, objections, committee decisions and historical analogs contributed to each outcome before reweighting the system.",
            [
                f"10B mature 5D outcomes: {mature_outcomes}",
                f"9S agent league status: {league_status}",
                "Historical-analog contribution is not yet part of a mature outcome-attribution scorecard.",
            ],
            score=104,
            action_class="WAIT_AND_MEASURE_THEN_BUILD",
            suggested_batch="10N",
            effort="MEDIUM_TO_HIGH",
            risk="LOW_TO_MEDIUM — attribution only until evidence supports a human-approved change.",
            measurement_goal="Attribute false positives, false negatives, saves and wins to exact case/evidence/agent/committee/risk/10H lineage.",
        ))

    qualification_progress = _float(qualification_watch.get("qualification_progress_pct")) or 0.0
    if qualification_progress < 100.0:
        candidates.append(_candidate(
            "PAPER_EVIDENCE_CAMPAIGN",
            "Continue governed paper qualification without forcing trades",
            "Some weaknesses are evidence deficits rather than engineering defects. The factory should keep collecting real sessions, paper decisions and mature outcomes instead of coding around the sample requirement.",
            [
                f"10G qualification progress: {qualification_progress:.1f}%",
                f"10B status: {qualification.get('status', 'unknown')}",
                f"10E readiness: {readiness.get('status', 'unknown')}",
            ],
            score=96,
            action_class="WAIT_FOR_EVIDENCE",
            suggested_batch="NO_NEW_BATCH_REQUIRED",
            effort="TIME_AND_MARKET_SESSIONS",
            risk="HIGH if interpreted as pressure to trade; qualification gates must remain unchanged.",
            measurement_goal="Reach the existing 10B sample gates organically, then evaluate performance and attribution.",
        ))

    deduped: dict[str, dict[str, Any]] = {}
    for row in candidates:
        key = str(row.get("upgrade_id") or row.get("title") or "UNKNOWN")
        previous = deduped.get(key)
        if previous is None or _int(row.get("priority_score")) > _int(previous.get("priority_score")):
            deduped[key] = row
    ranked = sorted(deduped.values(), key=lambda row: _int(row.get("priority_score")), reverse=True)

    whole_stack = [
        {"layer": "9P", "name": "Chief Intelligence Office V1", "status": legacy_office.get("status")},
        {"layer": "9Q", "name": "Experiment Lab", "status": experiment_lab.get("status")},
        {"layer": "9R", "name": "Data Expansion", "status": data_expansion.get("status")},
        {"layer": "9S", "name": "Agent Performance", "status": agent_league.get("status")},
        {"layer": "9T", "name": "Market Regime", "status": regime.get("status")},
        {"layer": "10B", "name": "Paper Qualification", "status": qualification.get("status")},
        {"layer": "10C", "name": "Portfolio Intelligence", "status": portfolio.get("status")},
        {"layer": "10E", "name": "Capital Readiness", "status": readiness.get("status")},
        {"layer": "10G", "name": "Qualification Watch", "status": qualification_watch.get("status")},
        {"layer": "10H", "name": "Historical Intelligence", "status": historical.get("status")},
    ]
    if event_reconstruction:
        whole_stack.append({"layer": "10J", "name": "Historical Event Reconstruction", "status": event_reconstruction.get("status")})
    observed = sum(1 for row in whole_stack if row.get("status"))

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": (generated_at or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat(),
        "status": "CHIEF_INTELLIGENCE_OFFICE_V2_WHOLE_STACK_ADVISORY_READY",
        "question": "What measured weakness should IIOS improve next?",
        "whole_stack_inputs": whole_stack,
        "whole_stack_inputs_observed": observed,
        "whole_stack_input_count": len(whole_stack),
        "ranked_upgrades": ranked[:8],
        "top_recommendation": ranked[0] if ranked else None,
        "historical_diagnostics": {
            "studies_ready": studies_ready,
            "targets_known": targets_known,
            "event_reconstruction_state": effective_event_state,
            "event_reconstruction_engine_status": event_engine_status or None,
            "event_symbols_ready": event_symbols_ready,
            "event_analog_contexts_ready": event_contexts_ready,
            "regime_normalization_state": regime_state,
            "historical_error_count": len(historical_errors),
        },
        "decision_policy": {
            "build_when": "A persisted measurement gap or operating-control gap has a testable improvement hypothesis.",
            "wait_when": "The limitation is insufficient governed sample rather than missing engineering.",
            "shadow_when": "A proposal changes thresholds, routing, ranking, weights or promotion behavior.",
            "human_review_when": "A proposal changes material configuration, providers, mandate, risk or capital readiness.",
        },
        "rejected_shortcuts": [
            "AUTO_APPLY_TOP_RECOMMENDATION",
            "AUTO_TUNE_THRESHOLDS",
            "AUTO_REWEIGHT_AGENTS",
            "AUTO_CHANGE_MODEL_ROUTING",
            "AUTO_CONNECT_PROVIDER",
            "AUTO_ADVANCE_CAPITAL",
        ],
        "safety": {
            "advisory_only": True,
            "auto_apply_recommendations": False,
            "auto_change_thresholds": False,
            "auto_change_agent_weights": False,
            "auto_change_model_routing": False,
            "provider_change_authority": False,
            "committee_change_authority": False,
            "risk_rule_change_authority": False,
            "broker_connection_authority": False,
            "capital_authority": False,
            "trade_execution_permission": False,
            "live_execution": False,
            "human_approval_required": True,
        },
    }
