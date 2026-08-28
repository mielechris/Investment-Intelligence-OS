#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import iios_chief_intelligence_office as chief

SCHEMA_VERSION = "batch9q-experiment-ab-laboratory-v1"
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


def _baseline_key(row: dict[str, Any]) -> tuple[float | None, int]:
    return (_float(row.get("min_promotion_score")), _int(row.get("max_cases_per_cycle")))


def _variant_score(row: dict[str, Any]) -> tuple[int, int, float]:
    delta = row.get("vs_baseline") if isinstance(row.get("vs_baseline"), dict) else {}
    marginal_capture = _int(delta.get("marginal_captured_count"))
    marginal_extra = _int(delta.get("marginal_extra_nonbenchmark_ticker_count"))
    load = _float(delta.get("selection_load_delta_pct")) or 0.0
    return (marginal_capture, -marginal_extra, -load)


def _radar_experiment(upgrade: dict[str, Any], shadow: dict[str, Any]) -> dict[str, Any]:
    complete = _int(shadow.get("complete_session_count"))
    minimum = max(1, _int(shadow.get("minimum_complete_sessions_for_advice")) or 5)
    baseline = shadow.get("baseline") if isinstance(shadow.get("baseline"), dict) else None
    scenarios = _rows(shadow.get("scenario_rollup"))
    frontier = _rows(shadow.get("advisory_frontier"))

    if complete < minimum or baseline is None:
        return {
            "experiment_id": "9Q_RADAR_RECALL_AB",
            "upgrade_id": upgrade.get("upgrade_id"),
            "title": "Radar recall A/B: governed baseline vs shadow variants",
            "status": "WAITING_FOR_SAMPLE",
            "verdict": "NEED_MORE_DATA",
            "sample": {"complete_sessions": complete, "minimum_sessions": minimum},
            "baseline_arm": baseline,
            "variant_arm": None,
            "decision_basis": [
                f"Only {complete} complete shadow session(s) are available; {minimum} required.",
                "No parameter recommendation can advance until the persisted 9I sample gate is satisfied.",
            ],
            "next_action": "COLLECT_MORE_SHADOW_SESSIONS",
        }

    candidates = frontier or [
        row
        for row in scenarios
        if _baseline_key(row) != _baseline_key(baseline)
        and _int((row.get("vs_baseline") or {}).get("marginal_captured_count")) > 0
    ]
    candidates.sort(key=_variant_score, reverse=True)
    variant = candidates[0] if candidates else None

    if variant is None:
        return {
            "experiment_id": "9Q_RADAR_RECALL_AB",
            "upgrade_id": upgrade.get("upgrade_id"),
            "title": "Radar recall A/B: governed baseline vs shadow variants",
            "status": "COMPLETE",
            "verdict": "REJECT",
            "sample": {"complete_sessions": complete, "minimum_sessions": minimum},
            "baseline_arm": baseline,
            "variant_arm": None,
            "decision_basis": [
                "No tested persisted 9I variant improved capture within the governed load/noise frontier.",
                "Keep the current governed baseline; no production change is recommended.",
            ],
            "next_action": "KEEP_GOVERNED_BASELINE",
        }

    delta = variant.get("vs_baseline") if isinstance(variant.get("vs_baseline"), dict) else {}
    marginal_capture = _int(delta.get("marginal_captured_count"))
    marginal_extra = _int(delta.get("marginal_extra_nonbenchmark_ticker_count"))
    load_delta = _float(delta.get("selection_load_delta_pct")) or 0.0
    acceptable_noise = marginal_extra <= max(5, marginal_capture * 5)
    acceptable_load = load_delta <= 50.0
    keep = marginal_capture > 0 and acceptable_noise and acceptable_load

    return {
        "experiment_id": "9Q_RADAR_RECALL_AB",
        "upgrade_id": upgrade.get("upgrade_id"),
        "title": "Radar recall A/B: governed baseline vs shadow variants",
        "status": "COMPLETE",
        "verdict": "KEEP" if keep else "REJECT",
        "keep_meaning": "KEEP_VARIANT_FOR_HUMAN_REVIEW_NOT_PRODUCTION" if keep else "KEEP_BASELINE",
        "sample": {"complete_sessions": complete, "minimum_sessions": minimum},
        "baseline_arm": baseline,
        "variant_arm": variant,
        "comparison": {
            "marginal_captured_count": marginal_capture,
            "marginal_extra_nonbenchmark_ticker_count": marginal_extra,
            "selection_load_delta_pct": load_delta,
            "acceptable_noise": acceptable_noise,
            "acceptable_load": acceptable_load,
        },
        "decision_basis": [
            f"Variant changes captured benchmark opportunities by {marginal_capture:+d} versus baseline.",
            f"Extra non-benchmark tickers changed by {marginal_extra:+d}; selection load changed {load_delta:+.1f}%.",
            "KEEP means only that the variant survives shadow evidence review and may proceed to explicit human review.",
        ],
        "next_action": "HUMAN_REVIEW_ONLY" if keep else "KEEP_GOVERNED_BASELINE",
    }


def _sample_experiment(
    upgrade: dict[str, Any],
    *,
    experiment_id: str,
    title: str,
    current: int,
    required: int,
    next_action: str,
) -> dict[str, Any]:
    ready = current >= required
    return {
        "experiment_id": experiment_id,
        "upgrade_id": upgrade.get("upgrade_id"),
        "title": title,
        "status": "SAMPLE_GATE_COMPLETE" if ready else "WAITING_FOR_SAMPLE",
        "verdict": "KEEP" if ready else "NEED_MORE_DATA",
        "keep_meaning": "KEEP_MEASUREMENT_PROGRAM_ACTIVE",
        "sample": {"current": current, "required": required},
        "baseline_arm": {"state": "CURRENT_GOVERNED_MEASUREMENT"},
        "variant_arm": None,
        "decision_basis": [
            f"Persisted sample count is {current}; evidence gate is {required}.",
            "This experiment changes no market, Committee, Risk, paper, or capital behavior.",
        ],
        "next_action": next_action if not ready else "HUMAN_REVIEW_EVIDENCE_READY",
    }


def _measurement_gap_experiment(upgrade: dict[str, Any], title: str, gap: str) -> dict[str, Any]:
    return {
        "experiment_id": f"9Q_{str(upgrade.get('upgrade_id') or 'MEASUREMENT_GAP')}",
        "upgrade_id": upgrade.get("upgrade_id"),
        "title": title,
        "status": "BLOCKED_BY_MEASUREMENT_GAP",
        "verdict": "NEED_MORE_DATA",
        "baseline_arm": None,
        "variant_arm": None,
        "decision_basis": [gap, "9Q will not manufacture a comparison where the persisted measurement contract does not exist."],
        "next_action": "BUILD_MEASUREMENT_CONTRACT_FIRST",
    }


def _experiment_for_upgrade(
    upgrade: dict[str, Any],
    *,
    shadow: dict[str, Any],
    learning: dict[str, Any],
    telemetry: dict[str, Any],
) -> dict[str, Any]:
    key = str(upgrade.get("upgrade_id") or "")
    if key in {"RADAR_RECALL_REVIEW", "DETECTION_LATENCY", "FALSE_POSITIVE_CONTROL"}:
        return _radar_experiment(upgrade, shadow)
    if key == "SHADOW_MATURITY":
        return _sample_experiment(
            upgrade,
            experiment_id="9Q_SHADOW_SAMPLE_GATE",
            title="Shadow evidence maturity gate",
            current=_int(shadow.get("complete_session_count")),
            required=max(5, _int(shadow.get("minimum_complete_sessions_for_advice"))),
            next_action="COLLECT_MORE_SHADOW_SESSIONS",
        )
    if key == "OUTCOME_MEMORY_MATURITY":
        return _sample_experiment(
            upgrade,
            experiment_id="9Q_OUTCOME_SAMPLE_GATE",
            title="Outcome-learning maturity gate",
            current=_int(learning.get("mature_5d_count")),
            required=20,
            next_action="COLLECT_MORE_MATURE_OUTCOMES",
        )
    if key == "MODEL_TASK_LEAGUE":
        return _measurement_gap_experiment(
            upgrade,
            "Model-by-task routing A/B readiness",
            "A common persisted Grok/Gemini/OpenAI/Kimi task-level accuracy, latency, and cost scorecard does not yet exist.",
        )
    if key == "PAPER_QUALIFICATION_SAMPLE":
        paper = telemetry.get("paper_fund") if isinstance(telemetry.get("paper_fund"), dict) else {}
        return _sample_experiment(
            upgrade,
            experiment_id="9Q_PAPER_QUALIFICATION_GATE",
            title="Paper qualification sample gate",
            current=_int(paper.get("transaction_count")),
            required=20,
            next_action="WAIT_FOR_GOVERNED_PAPER_DECISIONS",
        )
    if key == "PROVIDER_RELIABILITY":
        return _measurement_gap_experiment(
            upgrade,
            "Provider reliability A/B readiness",
            "Persisted provider-level error, latency, cost, and coverage fields are not yet sufficient for a controlled provider replacement comparison.",
        )
    return _measurement_gap_experiment(
        upgrade,
        "Upgrade experiment readiness",
        f"No governed 9Q A/B contract exists yet for upgrade {key or 'UNKNOWN'}.",
    )


def build_lab(
    *,
    office: dict[str, Any],
    shadow: dict[str, Any],
    learning: dict[str, Any],
    telemetry: dict[str, Any],
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    upgrades = _rows((office.get("improvement_memo") or {}).get("top_five_upgrades"))
    experiments = [
        _experiment_for_upgrade(upgrade, shadow=shadow, learning=learning, telemetry=telemetry)
        for upgrade in upgrades
    ]
    verdict_counts = {"KEEP": 0, "REJECT": 0, "NEED_MORE_DATA": 0}
    for experiment in experiments:
        verdict = str(experiment.get("verdict") or "NEED_MORE_DATA")
        if verdict in verdict_counts:
            verdict_counts[verdict] += 1

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": (generated_at or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat(),
        "status": "EXPERIMENT_AB_LAB_ADVISORY_READY",
        "purpose": "Compare governed baseline vs shadow variants using persisted evidence only.",
        "experiments": experiments,
        "summary": {
            "experiment_count": len(experiments),
            "keep_count": verdict_counts["KEEP"],
            "reject_count": verdict_counts["REJECT"],
            "need_more_data_count": verdict_counts["NEED_MORE_DATA"],
            "production_changes_applied": 0,
        },
        "decision_dictionary": {
            "KEEP": "Variant or measurement program survives evidence review; human review is still required and no production change occurs.",
            "REJECT": "Variant does not beat the governed baseline within the current evidence/load constraints.",
            "NEED_MORE_DATA": "The persisted sample or measurement contract is insufficient for a valid comparison.",
        },
        "source_state": {
            "chief_office_status": office.get("status"),
            "shadow_status": shadow.get("status"),
            "shadow_complete_session_count": shadow.get("complete_session_count"),
            "learning_status": learning.get("status"),
            "learning_outcome_count": learning.get("outcome_count"),
            "telemetry_generated_at": telemetry.get("generated_at"),
        },
        "safety": {
            "shadow_only": True,
            "advisory_only": True,
            "browser_controls_execute_factory": False,
            "auto_apply_variants": False,
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
    office = chief.build_from_state(state_dir, telemetry_dir)
    return build_lab(
        office=office,
        shadow=_read_json(state_dir / "shadow_strategy" / "latest_shadow_counterfactual.json"),
        learning=_read_json(state_dir / "latest_outcome_learning.json"),
        telemetry=_read_json(telemetry_dir / "latest.json"),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the Batch 9Q read-only Experiment & A/B Laboratory artifact.")
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
