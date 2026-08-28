#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "batch9p-chief-intelligence-office-v1"
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
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    tmp.replace(path)


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


def _metrics(scorecard: dict[str, Any]) -> dict[str, Any]:
    raw = scorecard.get("metrics") if isinstance(scorecard.get("metrics"), dict) else {}
    benchmark = _int(raw.get("benchmark_opportunity_count", raw.get("opportunity_count")))
    detected = _int(raw.get("eventual_detected_count", raw.get("radar_detected_count", raw.get("detected_count"))))
    promoted = _int(raw.get("eventual_promotion_count", raw.get("promotion_count", raw.get("promoted_count"))))
    miss_count = max(0, benchmark - detected)
    return {
        "benchmark_opportunity_count": benchmark,
        "detected_count": detected,
        "promoted_count": promoted,
        "aggregate_miss_count": miss_count,
        "detection_rate_pct": _num(raw.get("eventual_detection_rate_pct", raw.get("detection_rate_pct"))),
        "opportunity_miss_rate_pct": _num(raw.get("eventual_opportunity_miss_rate_pct", raw.get("opportunity_miss_rate_pct"))),
        "false_positive_rate_pct": _num(raw.get("false_positive_rate_pct")),
        "average_detection_latency_minutes": _num(raw.get("average_detection_latency_minutes")),
        "provider_error_count": _int(raw.get("provider_error_count")),
    }


def _model_measurement_gaps(telemetry: dict[str, Any]) -> list[str]:
    model_perf = telemetry.get("model_performance")
    if isinstance(model_perf, dict) and model_perf:
        return []
    return [
        "Grok/Gemini/OpenAI/Kimi task-level accuracy is not yet persisted in a common scorecard.",
        "Per-model latency and cost attribution are not yet persisted by task type.",
        "New model capability scouting is not yet a governed persisted input to the factory.",
    ]


def _candidate(
    key: str,
    title: str,
    why: str,
    evidence: list[str],
    impact: str,
    effort: str,
    cost: str,
    risk: str,
    recommendation: str,
    batch: str,
    score: int,
) -> dict[str, Any]:
    return {
        "upgrade_id": key,
        "title": title,
        "why_it_should_improve_intelligence": why,
        "supporting_evidence": evidence,
        "expected_impact": impact,
        "engineering_effort": effort,
        "data_provider_cost": cost,
        "safety_governance_risk": risk,
        "production_shadow_research_recommendation": recommendation,
        "suggested_implementation_batch": batch,
        "priority_score": score,
    }


def build_office(
    *,
    scorecard: dict[str, Any],
    shadow: dict[str, Any],
    learning: dict[str, Any],
    telemetry: dict[str, Any],
    episode: dict[str, Any],
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    now = generated_at or datetime.now(timezone.utc)
    validation = _metrics(scorecard)
    miss_rate = validation.get("opportunity_miss_rate_pct") or 0.0
    latency = validation.get("average_detection_latency_minutes")
    fp_rate = validation.get("false_positive_rate_pct")
    shadow_sessions = _int(shadow.get("complete_session_count"))
    outcomes = _int(learning.get("outcome_count"))
    mature_5d = _int(learning.get("mature_5d_count"))
    providers = telemetry.get("providers") if isinstance(telemetry.get("providers"), dict) else {}
    provider_errors = _int(providers.get("provider_error_count", validation.get("provider_error_count")))
    paper = telemetry.get("paper_fund") if isinstance(telemetry.get("paper_fund"), dict) else {}
    paper_positions = _int(paper.get("position_count"))
    model_gaps = _model_measurement_gaps(telemetry)

    candidates: list[dict[str, Any]] = []
    if miss_rate >= 20:
        candidates.append(_candidate(
            "RADAR_RECALL_REVIEW",
            "Improve radar recall without bypassing governance",
            "A high independent miss rate means the factory is leaving too many benchmark opportunities unseen.",
            [f"9H miss rate: {miss_rate:.1f}%", f"Aggregate misses: {validation['aggregate_miss_count']} of {validation['benchmark_opportunity_count']}"],
            "Higher opportunity capture while preserving promotion and risk gates.",
            "MEDIUM",
            "LOW_TO_MEDIUM",
            "MEDIUM — threshold changes can increase noise, so shadow test only first.",
            "SHADOW",
            "9Q",
            100,
        ))
    if shadow_sessions < 5:
        candidates.append(_candidate(
            "SHADOW_MATURITY",
            "Increase shadow experiment sample size",
            "9I does not yet have enough complete sessions to support confident parameter comparisons.",
            [f"9I complete sessions: {shadow_sessions}"],
            "Better evidence before any threshold or routing proposal reaches human review.",
            "LOW",
            "LOW",
            "LOW",
            "RESEARCH",
            "9Q",
            88,
        ))
    if outcomes == 0 or mature_5d == 0:
        candidates.append(_candidate(
            "OUTCOME_MEMORY_MATURITY",
            "Accelerate outcome-label maturity and coverage",
            "The learning loop cannot calibrate decisions until more cases mature into measured outcomes.",
            [f"9J outcomes: {outcomes}", f"9J mature 5d outcomes: {mature_5d}"],
            "Improved false-positive/false-negative attribution and agent calibration evidence.",
            "LOW_TO_MEDIUM",
            "LOW",
            "LOW — read-only measurement improvement.",
            "PRODUCTION",
            "9S",
            95,
        ))
    if provider_errors:
        candidates.append(_candidate(
            "PROVIDER_RELIABILITY",
            "Reduce provider error and timeout exposure",
            "Provider errors create blind spots and slow evidence acquisition.",
            [f"Persisted provider errors: {provider_errors}"],
            "Fresher evidence, lower latency, fewer silent coverage gaps.",
            "MEDIUM",
            "VARIABLE",
            "LOW_TO_MEDIUM",
            "PRODUCTION",
            "9R",
            92,
        ))
    if latency is not None and latency > 15:
        candidates.append(_candidate(
            "DETECTION_LATENCY",
            "Reduce detection latency",
            "Slow discovery erodes the value of otherwise-correct signals.",
            [f"Average detection latency: {latency:.1f} minutes"],
            "Faster research and promotion of time-sensitive opportunities.",
            "MEDIUM",
            "LOW_TO_MEDIUM",
            "MEDIUM — faster paths must not weaken evidence gates.",
            "SHADOW",
            "9Q",
            90,
        ))
    if fp_rate is not None and fp_rate > 30:
        candidates.append(_candidate(
            "FALSE_POSITIVE_CONTROL",
            "Reduce low-value promotions",
            "A high false-positive rate consumes expensive agent and model cycles without adding decision quality.",
            [f"9H false-positive rate: {fp_rate:.1f}%"],
            "Lower research cost and less Committee noise.",
            "MEDIUM",
            "LOW",
            "MEDIUM",
            "SHADOW",
            "9Q",
            86,
        ))
    if model_gaps:
        candidates.append(_candidate(
            "MODEL_TASK_LEAGUE",
            "Create task-level model performance and cost scorecards",
            "IIOS cannot optimize model routing responsibly until Grok, Gemini, OpenAI and Kimi are measured on the same persisted task rubric.",
            model_gaps,
            "Evidence-based model routing, lower cost, better specialization by task.",
            "MEDIUM_TO_HIGH",
            "LOW initially; provider usage may change after evidence exists.",
            "MEDIUM — routing changes remain human-approved and shadow-tested.",
            "RESEARCH",
            "9S",
            98,
        ))
    if paper_positions == 0:
        candidates.append(_candidate(
            "PAPER_QUALIFICATION_SAMPLE",
            "Increase qualified paper-decision sample size without forcing trades",
            "The governed paper book has not accumulated enough executed decisions to evaluate portfolio behavior.",
            [f"Paper positions: {paper_positions}", f"Paper NAV: {paper.get('nav', 'unknown')}"],
            "More evidence for 10B paper qualification and portfolio/risk analysis.",
            "MEDIUM",
            "LOW",
            "HIGH if interpreted as pressure to trade; therefore qualification gates must remain unchanged.",
            "RESEARCH",
            "10B",
            78,
        ))

    candidates.sort(key=lambda row: int(row.get("priority_score", 0)), reverse=True)
    top_five = candidates[:5]
    rejected = [
        {
            "upgrade": "AUTO_TUNE_THRESHOLDS",
            "reason": "Rejected: 9P is advisory only and cannot alter promotion thresholds automatically.",
        },
        {
            "upgrade": "AUTO_REWEIGHT_AGENTS",
            "reason": "Rejected: agent weights require measured evidence and explicit human approval.",
        },
        {
            "upgrade": "LIVE_CAPITAL_ACCELERATION",
            "reason": "Rejected: current evidence is insufficient and live execution authority remains false.",
        },
    ]

    weaknesses = [
        {"area": "RADAR_QUALITY", "state": "ATTENTION" if miss_rate >= 20 else "MONITOR", "evidence": f"9H miss rate {miss_rate:.1f}%"},
        {"area": "OUTCOME_LEARNING", "state": "WARM_UP" if outcomes == 0 else "ACTIVE", "evidence": f"{outcomes} outcomes; {mature_5d} mature 5d"},
        {"area": "SHADOW_EXPERIMENTS", "state": "WARM_UP" if shadow_sessions < 5 else "ACTIVE", "evidence": f"{shadow_sessions} complete sessions"},
        {"area": "MODEL_ROUTING_EVIDENCE", "state": "MEASUREMENT_GAP" if model_gaps else "MEASURED", "evidence": model_gaps[0] if model_gaps else "Task scorecard available"},
    ]

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": now.astimezone(timezone.utc).isoformat(),
        "status": "CHIEF_INTELLIGENCE_OFFICE_ADVISORY_READY",
        "question": "How do we make this investment firm smarter next?",
        "current_weaknesses": weaknesses,
        "improvement_memo": {
            "top_five_upgrades": top_five,
            "rejected_upgrades_and_why": rejected,
        },
        "experiments_underway": shadow.get("recommendations") if isinstance(shadow.get("recommendations"), list) else [],
        "approved_upgrades": [],
        "rejected_upgrades": rejected,
        "measured_improvement_after_implementation": [],
        "analysis_coverage": {
            "missed_opportunities": True,
            "caught_opportunities": True,
            "committee_false_negatives_false_positives": outcomes > 0,
            "risk_decisions_vs_later_outcomes": outcomes > 0,
            "agent_accuracy_calibration": outcomes > 0,
            "model_performance_by_task": not bool(model_gaps),
            "evidence_gaps": True,
            "latency": latency is not None,
            "radar_quality": True,
            "promotion_thresholds": True,
            "paper_performance": True,
            "portfolio_risk_behavior": paper_positions > 0,
            "unused_new_data_sources": False,
            "new_model_capabilities": False,
            "architecture_bottlenecks": True,
            "expensive_low_value_processes": fp_rate is not None,
            "emerging_investment_methods": False,
        },
        "source_state": {
            "scorecard_generated_at": scorecard.get("generated_at"),
            "shadow_generated_at": shadow.get("generated_at"),
            "learning_generated_at": learning.get("generated_at"),
            "telemetry_generated_at": telemetry.get("generated_at"),
            "episode_status": episode.get("status"),
        },
        "safety": {
            "advisory_only": True,
            "auto_apply_thresholds": False,
            "agent_weight_change_authority": False,
            "committee_change_authority": False,
            "risk_rule_change_authority": False,
            "provider_change_authority": False,
            "capital_authority": False,
            "trade_execution_permission": False,
            "live_execution": False,
            "human_approval_required": True,
        },
    }


def build_from_state(state_dir: Path, telemetry_dir: Path) -> dict[str, Any]:
    return build_office(
        scorecard=_read_json(state_dir / "latest_market_validation.json"),
        shadow=_read_json(state_dir / "shadow_strategy" / "latest_shadow_counterfactual.json"),
        learning=_read_json(state_dir / "latest_outcome_learning.json"),
        telemetry=_read_json(telemetry_dir / "latest.json"),
        episode=_read_json(state_dir / "browser" / "daily_factory_episode.json"),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the Batch 9P advisory Chief Intelligence Office memo.")
    parser.add_argument("--state-dir", default=str(DEFAULT_STATE_DIR))
    parser.add_argument("--telemetry-dir", default=str(DEFAULT_TELEMETRY_DIR))
    parser.add_argument("--output")
    parser.add_argument("--stdout", action="store_true")
    args = parser.parse_args()
    payload = build_from_state(Path(args.state_dir).expanduser(), Path(args.telemetry_dir).expanduser())
    if args.output:
        _atomic_write(Path(args.output).expanduser(), payload)
    print(json.dumps(payload if args.stdout or not args.output else {"status": payload["status"], "output": args.output}, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
