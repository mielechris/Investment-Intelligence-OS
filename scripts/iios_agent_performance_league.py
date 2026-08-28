#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "batch9s-agent-performance-league-v1"
DEFAULT_STATE_DIR = Path.home() / "Library" / "Application Support" / "IIOS" / "market-validation"
DEFAULT_TELEMETRY_DIR = Path.home() / "Library" / "Application Support" / "IIOS" / "telemetry"
MIN_OFFICIAL_DECISIVE_OUTCOMES = 20

AGENTS = (
    ("policy", "Policy Analyst"),
    ("macro", "Macro & Rates Analyst"),
    ("fundamentals", "Fundamentals Analyst"),
    ("market_structure", "Market Structure Analyst"),
    ("commodities", "Commodities & Supply Chain Analyst"),
    ("geo_weather", "Geopolitics & Weather Analyst"),
    ("skeptic", "Skeptic / Red Team"),
    ("portfolio", "Portfolio Context Analyst"),
)
MODELS = ("Grok", "Gemini", "OpenAI", "Kimi")


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


def _recent_participation(telemetry: dict[str, Any]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for promotion in _rows(telemetry.get("recent_promotions")):
        agents = promotion.get("agents") if isinstance(promotion.get("agents"), dict) else {}
        for key in agents.get("agent_keys") or []:
            key = str(key or "").strip()
            if key:
                counts[key] += 1
    return counts


def _agent_case_stats(learning: dict[str, Any]) -> dict[str, dict[str, int]]:
    stats: dict[str, Counter[str]] = {key: Counter() for key, _ in AGENTS}
    for outcome in _rows(learning.get("recent_outcomes")):
        quality = str(outcome.get("decision_quality") or "")
        detected = outcome.get("detected") is True
        case_id = str(outcome.get("case_id") or "").strip()
        agents = _rows(outcome.get("agents"))
        if not detected or not case_id or not agents:
            continue
        for agent in agents:
            key = str(agent.get("agent_key") or "").strip()
            if key not in stats:
                continue
            alignment = str(agent.get("alignment") or "INCONCLUSIVE").upper()
            stats[key]["cases_with_outcome_lineage"] += 1
            if alignment == "ALIGNED":
                stats[key]["aligned"] += 1
            elif alignment == "MISALIGNED":
                stats[key]["misaligned"] += 1
            if quality == "NO_TRADE_AVOIDED_DOWNSIDE" and alignment == "ALIGNED":
                stats[key]["downside_avoidance_alignment"] += 1
            if quality == "WATCH_FALSE_POSITIVE_OR_REVERSAL" and alignment == "MISALIGNED":
                stats[key]["false_positive_misalignment"] += 1
            if quality == "NO_TRADE_FOREGONE_UPSIDE" and alignment == "MISALIGNED":
                stats[key]["foregone_upside_misalignment"] += 1
    return {key: dict(value) for key, value in stats.items()}


def build_league(*, learning: dict[str, Any], telemetry: dict[str, Any], generated_at: datetime | None = None) -> dict[str, Any]:
    scorecards = {
        str(row.get("agent_key") or ""): row
        for row in _rows(learning.get("agent_scorecards"))
        if str(row.get("agent_key") or "").strip()
    }
    participation = _recent_participation(telemetry)
    case_stats = _agent_case_stats(learning)
    standings: list[dict[str, Any]] = []

    for key, name in AGENTS:
        row = scorecards.get(key) or {}
        decisive = _int(row.get("decisive_outcomes"))
        aligned = _int(row.get("aligned_outcomes"))
        rate = _float(row.get("alignment_rate_pct"))
        confidence = _float(row.get("average_confidence"))
        official = decisive >= MIN_OFFICIAL_DECISIVE_OUTCOMES and rate is not None
        provisional = decisive > 0 and rate is not None
        status = "OFFICIAL" if official else ("PROVISIONAL" if provisional else "WARM_UP")
        standings.append(
            {
                "agent_key": key,
                "agent": name,
                "status": status,
                "observations": _int(row.get("observations")),
                "decisive_outcomes": decisive,
                "aligned_outcomes": aligned,
                "alignment_rate_pct": rate,
                "average_confidence": confidence,
                "recent_case_participation": participation.get(key, 0),
                "outcome_attribution": case_stats.get(key) or {},
                "official_ranking_eligible": official,
                "official_sample_requirement": MIN_OFFICIAL_DECISIVE_OUTCOMES,
                "league_score": round(rate, 2) if provisional and rate is not None else None,
                "weight_change_authority": False,
            }
        )

    standings.sort(
        key=lambda row: (
            row.get("official_ranking_eligible") is True,
            row.get("status") == "PROVISIONAL",
            row.get("league_score") if row.get("league_score") is not None else -1,
            row.get("decisive_outcomes") or 0,
        ),
        reverse=True,
    )
    for index, row in enumerate(standings, start=1):
        row["display_rank"] = index if row["status"] != "WARM_UP" else None

    factory_misses = [
        row for row in _rows(learning.get("recent_outcomes"))
        if str(row.get("decision_quality") or "").startswith("FACTORY_MISS")
    ]
    unattributed_misses = sum(1 for row in factory_misses if not row.get("case_id"))

    model_league = [
        {
            "model": model,
            "status": "UNRANKED_MEASUREMENT_GAP",
            "task_accuracy": None,
            "latency": None,
            "cost_per_useful_result": None,
            "routing_change_authority": False,
            "why_unranked": "Task-level outcome, latency and cost telemetry is not yet persisted under a common 9S rubric.",
        }
        for model in MODELS
    ]

    measurement_contract = {
        "measured_now": [
            "9J agent observations and decisive outcomes",
            "9J aligned vs misaligned outcome rate",
            "average persisted agent confidence",
            "recent 9G case participation",
            "aligned downside-avoidance and adverse-call attribution when exact agent lineage exists",
        ],
        "measurement_gaps": [
            "per-agent research latency",
            "per-agent evidence-quality score",
            "Committee marginal influence / counterfactual contribution",
            "cost per useful agent result",
            "task-specific performance",
            "market-regime-specific performance",
            "Grok/Gemini/OpenAI/Kimi task-level accuracy, latency and cost under one persisted rubric",
        ],
        "miss_attribution_rule": "A factory miss with no governed case/agent lineage is UNATTRIBUTED_TO_AGENTS and cannot reduce an agent score.",
    }

    official_count = sum(1 for row in standings if row["status"] == "OFFICIAL")
    provisional_count = sum(1 for row in standings if row["status"] == "PROVISIONAL")
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": (generated_at or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat(),
        "status": "AGENT_PERFORMANCE_LEAGUE_ACTIVE" if official_count or provisional_count else "AGENT_PERFORMANCE_LEAGUE_WARM_UP",
        "purpose": "Measure specialist and model performance without granting automatic influence changes.",
        "summary": {
            "agent_count": len(standings),
            "officially_ranked_count": official_count,
            "provisional_count": provisional_count,
            "warm_up_count": len(standings) - official_count - provisional_count,
            "model_count": len(model_league),
            "ranked_model_count": 0,
            "unattributed_factory_miss_count": unattributed_misses,
            "automatic_weight_changes": 0,
            "automatic_model_routing_changes": 0,
        },
        "agent_standings": standings,
        "model_league": model_league,
        "measurement_contract": measurement_contract,
        "source_state": {
            "learning_status": learning.get("status"),
            "learning_outcome_count": learning.get("outcome_count"),
            "learning_mature_5d_count": learning.get("mature_5d_count"),
            "learning_complete_session_count": learning.get("complete_session_count"),
            "telemetry_generated_at": telemetry.get("generated_at"),
        },
        "safety": {
            "advisory_only": True,
            "scoreboard_only": True,
            "automatic_agent_weight_changes": False,
            "agent_weight_change_authority": False,
            "automatic_model_routing_changes": False,
            "model_routing_change_authority": False,
            "committee_change_authority": False,
            "risk_rule_change_authority": False,
            "capital_authority": False,
            "trade_execution_permission": False,
            "live_execution": False,
            "human_approval_required": True,
        },
    }


def build_from_state(state_dir: Path, telemetry_dir: Path) -> dict[str, Any]:
    return build_league(
        learning=_read_json(state_dir / "latest_outcome_learning.json"),
        telemetry=_read_json(telemetry_dir / "latest.json"),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the Batch 9S read-only Agent Performance League artifact.")
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
