from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
from pathlib import Path
from typing import Any


BASELINE_PROFILE = "baseline"
SPEED_PROFILE = "speed_trial"
DEFAULT_RUNS_PER_PROFILE = 2
MAX_RUNS_PER_PROFILE = 3
CHILD_MARKER = "IIOS_AB_RESULT="

_CHILD_CODE = r'''
import json
import sys

# Importing the public router installs runtime routing + timing layers before
# the orchestrator is called. The process inherits the profile from its env.
import public_case_router  # noqa: F401
import eight_agent_orchestrator as orch

result = orch.run_eight_agent_orchestration(sys.argv[1])
print("IIOS_AB_RESULT=" + json.dumps(result, default=str))
'''


def normalize_runs(value: Any) -> int:
    try:
        runs = int(value)
    except (TypeError, ValueError):
        runs = DEFAULT_RUNS_PER_PROFILE
    return max(1, min(runs, MAX_RUNS_PER_PROFILE))


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def quality_signature(result: dict[str, Any]) -> dict[str, Any]:
    orchestration = result.get("orchestration") or {}
    committee = result.get("committee") or {}
    performance = result.get("performance") or {}
    agents = orchestration.get("agents") or committee.get("agents") or {}
    guard = committee.get("orchestration_guard") or {}

    agent_rows = [row for row in agents.values() if isinstance(row, dict)]
    error_count = sum(1 for row in agent_rows if row.get("status") != "complete")
    safety_ok = all(
        value is False
        for value in (
            committee.get("paper_order_permission"),
            committee.get("trade_execution_permission"),
            committee.get("live_execution"),
            orchestration.get("paper_order_permission"),
            orchestration.get("trade_execution_permission"),
            orchestration.get("live_execution"),
            performance.get("paper_order_permission"),
            performance.get("trade_execution_permission"),
            performance.get("live_execution"),
        )
        if value is not None
    )

    required = committee.get("required_evidence")
    required = required if isinstance(required, list) else []

    return {
        "runtime_profile": committee.get("runtime_profile"),
        "latency_ms": _float(performance.get("total_latency_ms")),
        "disposition": str(committee.get("disposition") or ""),
        "confidence": _float(committee.get("confidence")),
        "required_evidence_count": len(required),
        "required_evidence": [str(item) for item in required],
        "failed_guard_checks": list(guard.get("failed_checks") or []),
        "agent_count": len(agent_rows),
        "agent_error_count": error_count,
        "bull_case_present": bool(str(committee.get("bull_case") or "").strip()),
        "bear_case_present": bool(str(committee.get("bear_case") or "").strip()),
        "dissent_present": bool(str(committee.get("dissent") or "").strip()),
        "safety_ok": safety_ok,
        "paper_mode": committee.get("paper_mode") is True,
    }


def aggregate_profile(signatures: list[dict[str, Any]]) -> dict[str, Any]:
    if not signatures:
        raise ValueError("At least one benchmark signature is required")

    latencies = [_float(row.get("latency_ms")) for row in signatures]
    confidences = [_float(row.get("confidence")) for row in signatures]
    evidence_counts = [int(row.get("required_evidence_count") or 0) for row in signatures]
    dispositions = [str(row.get("disposition") or "") for row in signatures]

    counts: dict[str, int] = {}
    for disposition in dispositions:
        counts[disposition] = counts.get(disposition, 0) + 1

    majority = max(counts, key=counts.get) if counts else ""

    return {
        "run_count": len(signatures),
        "median_latency_ms": round(statistics.median(latencies), 2),
        "median_confidence": round(statistics.median(confidences), 4),
        "confidence_range": round(max(confidences) - min(confidences), 4),
        "median_required_evidence_count": statistics.median(evidence_counts),
        "disposition_counts": counts,
        "majority_disposition": majority,
        "disposition_stable": len(set(dispositions)) == 1,
        "all_eight_agents_complete": all(
            row.get("agent_count") == 8 and row.get("agent_error_count") == 0
            for row in signatures
        ),
        "all_guards_clean": all(not row.get("failed_guard_checks") for row in signatures),
        "all_quality_sections_present": all(
            row.get("bull_case_present")
            and row.get("bear_case_present")
            and row.get("dissent_present")
            for row in signatures
        ),
        "all_safety_locked": all(row.get("safety_ok") and row.get("paper_mode") for row in signatures),
    }


def compare_profiles(
    baseline_signatures: list[dict[str, Any]],
    speed_signatures: list[dict[str, Any]],
) -> dict[str, Any]:
    baseline = aggregate_profile(baseline_signatures)
    speed = aggregate_profile(speed_signatures)

    baseline_latency = max(_float(baseline["median_latency_ms"]), 1.0)
    speed_latency = _float(speed["median_latency_ms"])
    latency_improvement_pct = round(
        ((baseline_latency - speed_latency) / baseline_latency) * 100.0,
        2,
    )
    confidence_delta = round(
        abs(_float(baseline["median_confidence"]) - _float(speed["median_confidence"])),
        4,
    )
    baseline_evidence = max(_float(baseline["median_required_evidence_count"]), 1.0)
    evidence_ratio = round(
        _float(speed["median_required_evidence_count"]) / baseline_evidence,
        3,
    )

    checks = {
        "baseline_safety_locked": baseline["all_safety_locked"],
        "speed_safety_locked": speed["all_safety_locked"],
        "baseline_eight_agents_complete": baseline["all_eight_agents_complete"],
        "speed_eight_agents_complete": speed["all_eight_agents_complete"],
        "baseline_guards_clean": baseline["all_guards_clean"],
        "speed_guards_clean": speed["all_guards_clean"],
        "baseline_disposition_stable": baseline["disposition_stable"],
        "speed_disposition_stable": speed["disposition_stable"],
        "cross_profile_disposition_match": (
            baseline["majority_disposition"] == speed["majority_disposition"]
        ),
        "quality_sections_preserved": speed["all_quality_sections_present"],
        "confidence_delta_within_025": confidence_delta <= 0.25,
        "required_evidence_not_collapsed": evidence_ratio >= 0.5,
        "latency_improvement_at_least_10pct": latency_improvement_pct >= 10.0,
    }

    eligible = all(checks.values())
    return {
        "baseline": baseline,
        "speed_trial": speed,
        "latency_improvement_pct": latency_improvement_pct,
        "confidence_delta": confidence_delta,
        "required_evidence_ratio": evidence_ratio,
        "checks": checks,
        "speed_profile_eligible_for_manual_default_review": eligible,
        "recommendation": (
            "ELIGIBLE_FOR_MANUAL_DEFAULT_REVIEW" if eligible else "KEEP_BASELINE_AND_CONTINUE_TRIAL"
        ),
        "automatic_default_change": False,
        "paper_mode": True,
        "auto_trade_authority": False,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }


def _parse_child_result(stdout: str) -> dict[str, Any]:
    for line in reversed(stdout.splitlines()):
        if line.startswith(CHILD_MARKER):
            return json.loads(line[len(CHILD_MARKER):])
    raise RuntimeError("Benchmark child returned no IIOS result marker")


def run_profile_once(case_id: str, profile: str) -> dict[str, Any]:
    if profile not in {BASELINE_PROFILE, SPEED_PROFILE}:
        raise ValueError("Unknown benchmark profile")
    if not str(case_id).startswith("case_"):
        raise ValueError("case_id must start with case_")

    env = os.environ.copy()
    env["IIOS_ORCHESTRATION_PROFILE"] = profile
    env["IIOS_PROMPT_CACHE_ENABLED"] = "0"

    completed = subprocess.run(
        [sys.executable, "-c", _CHILD_CODE, case_id],
        cwd=str(Path(__file__).resolve().parent),
        env=env,
        capture_output=True,
        text=True,
        timeout=240,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"{profile} benchmark child failed: {completed.stderr.strip() or completed.stdout.strip()}"
        )
    return _parse_child_result(completed.stdout)


def run_ab_benchmark(case_id: str, runs_per_profile: int = DEFAULT_RUNS_PER_PROFILE) -> dict[str, Any]:
    runs = normalize_runs(runs_per_profile)
    baseline_signatures: list[dict[str, Any]] = []
    speed_signatures: list[dict[str, Any]] = []

    # Alternate profiles to reduce time-of-day/provider effects. Each run occurs in
    # its own process, so profile env settings cannot leak into the live server.
    for _ in range(runs):
        baseline_signatures.append(quality_signature(run_profile_once(case_id, BASELINE_PROFILE)))
        speed_signatures.append(quality_signature(run_profile_once(case_id, SPEED_PROFILE)))

    comparison = compare_profiles(baseline_signatures, speed_signatures)
    return {
        "case_id": case_id,
        "runs_per_profile": runs,
        "baseline_runs": baseline_signatures,
        "speed_trial_runs": speed_signatures,
        "comparison": comparison,
        "automatic_default_change": False,
        "paper_mode": True,
        "auto_trade_authority": False,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }


def _print_report(result: dict[str, Any]) -> None:
    comparison = result["comparison"]
    baseline = comparison["baseline"]
    speed = comparison["speed_trial"]

    print()
    print("IIOS ORCHESTRATION QUALITY A/B")
    print("------------------------------")
    print("Case:", result["case_id"])
    print("Runs per profile:", result["runs_per_profile"])
    print()
    print("BASELINE median latency:", baseline["median_latency_ms"], "ms")
    print("SPEED median latency:", speed["median_latency_ms"], "ms")
    print("Latency improvement:", comparison["latency_improvement_pct"], "%")
    print()
    print("BASELINE disposition:", baseline["majority_disposition"], "stable=", baseline["disposition_stable"])
    print("SPEED disposition:", speed["majority_disposition"], "stable=", speed["disposition_stable"])
    print("Confidence delta:", comparison["confidence_delta"])
    print("Required evidence ratio:", comparison["required_evidence_ratio"])
    print()
    print("CHECKS")
    for key, passed in comparison["checks"].items():
        print(f"  {key}: {passed}")
    print()
    print("RECOMMENDATION:", comparison["recommendation"])
    print("Automatic default change:", comparison["automatic_default_change"])
    print()
    print("SAFETY")
    print("auto_trade_authority:", result["auto_trade_authority"])
    print("paper_order_permission:", result["paper_order_permission"])
    print("trade_execution_permission:", result["trade_execution_permission"])
    print("live_execution:", result["live_execution"])


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare IIOS baseline vs speed_trial research quality.")
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--runs", type=int, default=DEFAULT_RUNS_PER_PROFILE)
    parser.add_argument("--json-out", default="")
    args = parser.parse_args()

    result = run_ab_benchmark(args.case_id, args.runs)
    _print_report(result)

    if args.json_out:
        Path(args.json_out).write_text(json.dumps(result, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
