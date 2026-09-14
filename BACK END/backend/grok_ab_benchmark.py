from __future__ import annotations

import json
import os
import statistics
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Body, HTTPException

from grok_social_intelligence import build_case_grok_context, grok_plan
from ledger import DB_PATH, get_object, record_event, record_object, utc_now
from orchestration_ab_benchmark import snapshot_ledger


router = APIRouter()
DEFAULT_RUNS = 1
MAX_RUNS = 2
CHILD_MARKER = "IIOS_GROK_AB_RESULT="

_CHILD_CODE = r'''
import json
import sys
import public_case_router  # installs the exact IIOS V1 orchestration layers
import eight_agent_orchestrator as orch
result = orch.run_eight_agent_orchestration(sys.argv[1])
print("IIOS_GROK_AB_RESULT=" + json.dumps(result, default=str))
'''


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def normalize_runs(value: Any) -> int:
    try:
        runs = int(value)
    except (TypeError, ValueError):
        runs = DEFAULT_RUNS
    return max(1, min(runs, MAX_RUNS))


def _parse_child(stdout: str) -> dict[str, Any]:
    for line in reversed(stdout.splitlines()):
        if line.startswith(CHILD_MARKER):
            return json.loads(line[len(CHILD_MARKER):])
    raise RuntimeError("A/B child returned no IIOS Grok result marker")


def _run_child(case_id: str, db_path: Path, *, context_path: Path | None = None) -> dict[str, Any]:
    env = os.environ.copy()
    env["IIOS_DB_PATH"] = str(Path(db_path).resolve())
    env["IIOS_ORCHESTRATION_PROFILE"] = "baseline"
    env["IIOS_PROMPT_CACHE_ENABLED"] = "0"
    if context_path is None:
        env.pop("IIOS_GROK_CONTEXT_FILE", None)
    else:
        env["IIOS_GROK_CONTEXT_FILE"] = str(Path(context_path).resolve())

    completed = subprocess.run(
        [sys.executable, "-c", _CHILD_CODE, case_id],
        cwd=str(Path(__file__).resolve().parent),
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or completed.stdout.strip() or "A/B child failed")
    return _parse_child(completed.stdout)


def quality_signature(result: dict[str, Any]) -> dict[str, Any]:
    orchestration = result.get("orchestration") or {}
    committee = result.get("committee") or {}
    performance = result.get("performance") or {}
    agents = orchestration.get("agents") or committee.get("agents") or {}
    guard = committee.get("orchestration_guard") or {}
    rows = [row for row in agents.values() if isinstance(row, dict)]
    required = committee.get("required_evidence") if isinstance(committee.get("required_evidence"), list) else []
    safety_values = (
        orchestration.get("paper_order_permission"),
        orchestration.get("trade_execution_permission"),
        orchestration.get("live_execution"),
        committee.get("paper_order_permission"),
        committee.get("trade_execution_permission"),
        committee.get("live_execution"),
    )
    return {
        "latency_ms": _float(performance.get("total_latency_ms")),
        "disposition": str(committee.get("disposition") or ""),
        "confidence": _float(committee.get("confidence")),
        "required_evidence_count": len(required),
        "required_evidence": [str(item) for item in required],
        "agent_count": len(rows),
        "agent_error_count": sum(1 for row in rows if row.get("status") != "complete"),
        "failed_guard_checks": list(guard.get("failed_checks") or []),
        "bull_case_present": bool(str(committee.get("bull_case") or "").strip()),
        "bear_case_present": bool(str(committee.get("bear_case") or "").strip()),
        "dissent_present": bool(str(committee.get("dissent") or "").strip()),
        "safety_locked": all(value is False for value in safety_values),
        "paper_mode": committee.get("paper_mode") is True,
    }


def aggregate(signatures: list[dict[str, Any]]) -> dict[str, Any]:
    latencies = [_float(row.get("latency_ms")) for row in signatures]
    confidences = [_float(row.get("confidence")) for row in signatures]
    dispositions = [str(row.get("disposition") or "") for row in signatures]
    evidence_counts = [int(row.get("required_evidence_count") or 0) for row in signatures]
    return {
        "run_count": len(signatures),
        "median_latency_ms": round(statistics.median(latencies), 2) if latencies else 0.0,
        "median_confidence": round(statistics.median(confidences), 4) if confidences else 0.0,
        "median_required_evidence_count": statistics.median(evidence_counts) if evidence_counts else 0,
        "dispositions": dispositions,
        "disposition_stable": len(set(dispositions)) <= 1,
        "all_eight_agents_complete": all(row.get("agent_count") == 8 and row.get("agent_error_count") == 0 for row in signatures),
        "all_guards_clean": all(not row.get("failed_guard_checks") for row in signatures),
        "all_safety_locked": all(row.get("safety_locked") and row.get("paper_mode") for row in signatures),
        "all_quality_sections_present": all(row.get("bull_case_present") and row.get("bear_case_present") and row.get("dissent_present") for row in signatures),
    }


def compare_ab(baseline_runs: list[dict[str, Any]], grok_runs: list[dict[str, Any]], grok_context: dict[str, Any]) -> dict[str, Any]:
    baseline = aggregate(baseline_runs)
    grok = aggregate(grok_runs)
    baseline_disposition = baseline["dispositions"][0] if baseline["dispositions"] else ""
    grok_disposition = grok["dispositions"][0] if grok["dispositions"] else ""
    confidence_delta = round(_float(grok["median_confidence"]) - _float(baseline["median_confidence"]), 4)
    evidence_delta = _float(grok["median_required_evidence_count"]) - _float(baseline["median_required_evidence_count"])

    checks = {
        "baseline_safety_locked": baseline["all_safety_locked"],
        "grok_safety_locked": grok["all_safety_locked"],
        "baseline_eight_agents_complete": baseline["all_eight_agents_complete"],
        "grok_eight_agents_complete": grok["all_eight_agents_complete"],
        "baseline_guards_clean": baseline["all_guards_clean"],
        "grok_guards_clean": grok["all_guards_clean"],
        "grok_context_is_advisory_only": grok_context.get("qualification_evidence") is False and grok_context.get("capital_authority") is False,
        "grok_has_verified_multi_source_context": int(grok_context.get("admitted_count") or 0) > 0,
    }

    # No single A/B case can promote Grok into permanent architecture. Promotion
    # requires a portfolio of experiments plus realized paper outcomes.
    return {
        "baseline": baseline,
        "iios_plus_grok": grok,
        "committee_disposition_changed": baseline_disposition != grok_disposition,
        "baseline_disposition": baseline_disposition,
        "grok_disposition": grok_disposition,
        "confidence_delta": confidence_delta,
        "required_evidence_count_delta": evidence_delta,
        "grok_context_admitted_count": int(grok_context.get("admitted_count") or 0),
        "grok_context_quarantined_count": int(grok_context.get("quarantined_count") or 0),
        "grok_x_citation_count": int(grok_context.get("citation_count") or 0),
        "grok_usage": grok_context.get("usage") or {},
        "checks": checks,
        "experiment_valid": all(value for key, value in checks.items() if key != "grok_has_verified_multi_source_context"),
        "architecture_promotion_eligible": False,
        "promotion_blockers": [
            "multi-case A/B sample required",
            "realized paper outcome comparison required",
            "false-positive rate comparison required",
            "discovery lead-time comparison required",
        ],
        "recommendation": "CONTINUE_EXPERIMENT" if checks["grok_has_verified_multi_source_context"] else "NO_USABLE_GROK_CONTEXT_IN_THIS_CASE",
        "automatic_configuration_change": False,
        "paper_mode": True,
        "auto_trade_authority": False,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }


def run_grok_ab(case_id: str, *, runs: int = DEFAULT_RUNS, days: int = 3, persist: bool = True) -> dict[str, Any]:
    if not get_object(case_id):
        raise ValueError("Unknown case_id")
    plan = grok_plan()
    if not plan["enabled"]:
        raise RuntimeError("Grok experiment is disabled")
    if not plan["api_key_configured"]:
        raise RuntimeError("XAI_API_KEY is not configured")

    run_count = normalize_runs(runs)
    # Fetch Grok once and hold the context constant across paired runs.
    grok_context = build_case_grok_context(case_id, days=days, persist=False)
    source_db = Path(DB_PATH).expanduser().resolve()
    baseline_signatures: list[dict[str, Any]] = []
    grok_signatures: list[dict[str, Any]] = []

    with tempfile.TemporaryDirectory(prefix="iios_grok_ab_") as tempdir:
        root = Path(tempdir)
        context_path = root / "grok_context.json"
        context_path.write_text(json.dumps({"items_by_agent": grok_context.get("items_by_agent") or {}}, default=str), encoding="utf-8")
        for index in range(run_count):
            baseline_db = root / f"baseline_{index}.db"
            grok_db = root / f"grok_{index}.db"
            snapshot_ledger(source_db, baseline_db)
            snapshot_ledger(source_db, grok_db)
            baseline_signatures.append(quality_signature(_run_child(case_id, baseline_db)))
            grok_signatures.append(quality_signature(_run_child(case_id, grok_db, context_path=context_path)))

    comparison = compare_ab(baseline_signatures, grok_signatures, grok_context)
    result_id = f"grok_ab_{uuid4().hex}"
    result = {
        "grok_ab_result_id": result_id,
        "case_id": case_id,
        "runs_per_arm": run_count,
        "ledger_isolation": "temporary_snapshot_per_arm",
        "grok_context_fixed_across_paired_runs": True,
        "baseline_runs": baseline_signatures,
        "grok_runs": grok_signatures,
        "grok_context_summary": {
            "summary": grok_context.get("summary"),
            "admitted_count": grok_context.get("admitted_count"),
            "quarantined_count": grok_context.get("quarantined_count"),
            "citation_count": grok_context.get("citation_count"),
            "usage": grok_context.get("usage"),
        },
        "comparison": comparison,
        "automatic_architecture_promotion": False,
        "research_only": True,
        "paper_mode": True,
        "auto_trade_authority": False,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
        "created_at": utc_now(),
    }
    if persist:
        case = get_object(case_id) or {}
        record_object(result_id, "grok_ab_result", case_id, result, parent_id=case_id, topic=case.get("topic"))
        record_event(case_id, "GROK_AB_EXPERIMENT_COMPLETE", entity_id=result_id, payload={
            "experiment_valid": comparison.get("experiment_valid"),
            "recommendation": comparison.get("recommendation"),
            "architecture_promotion_eligible": False,
            "trade_execution_permission": False,
        })
    return result


@router.get("/grok/ab/plan")
def grok_ab_plan():
    return {
        "baseline": "IIOS_V1_0",
        "experimental_arm": "IIOS_V1_0_PLUS_GROK_X_CONTEXT",
        "runs_default": DEFAULT_RUNS,
        "runs_max": MAX_RUNS,
        "same_case": True,
        "same_ledger_snapshot": True,
        "same_iios_orchestration_profile": "baseline",
        "grok_context_fixed_per_experiment": True,
        "live_decision_history_pollution": False,
        "architecture_promotion_automatic": False,
        "paper_mode": True,
        "auto_trade_authority": False,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }


@router.post("/grok/ab/{case_id}/run")
def run_grok_ab_route(case_id: str, request: dict[str, Any] = Body(default={})):
    try:
        return run_grok_ab(
            case_id,
            runs=normalize_runs(request.get("runs") or DEFAULT_RUNS),
            days=int(request.get("days") or 3),
            persist=True,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)[:1000])
