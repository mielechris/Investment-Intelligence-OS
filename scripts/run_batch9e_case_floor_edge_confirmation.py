#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import os
import statistics
import sys
import threading
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
BASE_PATH = REPO_ROOT / "scripts" / "batch9e_scaling_base_tmp.py"

if not BASE_PATH.exists():
    raise SystemExit("Missing scripts/batch9e_scaling_base_tmp.py; fetch the scaling base before running edge confirmation")

spec = importlib.util.spec_from_file_location("batch9e_scaling_base_tmp", BASE_PATH)
if spec is None or spec.loader is None:
    raise SystemExit("Unable to load scaling base module")
base = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = base
spec.loader.exec_module(base)

WORKERS = 6
EDGE_CASES = (6, 7, 8)
DEFAULT_TRIALS = 3


def _classify_error(text: str) -> str:
    value = str(text or "").lower()
    if "429" in value or "rate limit" in value or "rate_limit" in value:
        return "RATE_LIMIT"
    if "503" in value or "unavailable" in value or "overloaded" in value:
        return "PROVIDER_UNAVAILABLE"
    if "timeout" in value or "timed out" in value:
        return "TIMEOUT"
    if "connection" in value:
        return "CONNECTION"
    if "missing credentials" in value or "api key" in value:
        return "CREDENTIAL"
    return "OTHER"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Confirm the Batch 9E six-worker capacity edge at 6, 7, and 8 concurrent cases."
    )
    parser.add_argument("--trials", type=int, default=DEFAULT_TRIALS)
    args = parser.parse_args()
    trials = max(2, min(int(args.trials), 5))

    base.ledger.init_ledger()
    branch_before = base._git_output("branch", "--show-current")
    status_before = base._git_output("status", "--porcelain")
    case_counter = [0]

    lock = threading.Lock()
    failures: list[dict[str, Any]] = []
    original_specialist = base.orchestrator.run_specialist

    def diagnostic_specialist(agent_key: str, topic: str, evidence: list[dict[str, Any]]) -> dict[str, Any]:
        started = time.perf_counter()
        try:
            result = original_specialist(agent_key, topic, evidence)
        except Exception as exc:  # should normally be converted by orchestrator, but retain exact provider failure
            elapsed = time.perf_counter() - started
            with lock:
                failures.append(
                    {
                        "agent": agent_key,
                        "class": _classify_error(f"{type(exc).__name__}: {exc}"),
                        "error": f"{type(exc).__name__}: {exc}"[:1200],
                        "seconds": elapsed,
                    }
                )
            raise
        elapsed = time.perf_counter() - started
        if result.get("status") != "complete":
            error = str(result.get("error") or result.get("view") or "UNKNOWN_AGENT_FAILURE")
            with lock:
                failures.append(
                    {
                        "agent": agent_key,
                        "class": _classify_error(error),
                        "error": error[:1200],
                        "seconds": elapsed,
                    }
                )
        return result

    base.orchestrator.run_specialist = diagnostic_specialist

    print("IIOS BATCH 9E — CASE-FLOOR EDGE CAPACITY CONFIRMATION", flush=True)
    print(f"Specialist workers: {WORKERS}", flush=True)
    print(f"Concurrent-case edge: {list(EDGE_CASES)}", flush=True)
    print(f"Trials per configuration: {trials}", flush=True)
    print(f"Isolated ledger: {base.BENCH_DB}", flush=True)
    print("Reasoning order unchanged: first wave -> Skeptic -> Portfolio -> Committee", flush=True)
    print("Paper order authority: FALSE", flush=True)
    print("Broker connected: FALSE", flush=True)
    print("Live execution: FALSE", flush=True)

    rows: list[dict[str, Any]] = []
    try:
        for concurrent_cases in EDGE_CASES:
            failure_start = len(failures)
            row = base._run_configuration(
                workers=WORKERS,
                concurrent_cases=concurrent_cases,
                trials=trials,
                case_counter=case_counter,
            )
            config_failures = failures[failure_start:]
            by_class: dict[str, int] = {}
            by_agent: dict[str, int] = {}
            for failure in config_failures:
                by_class[failure["class"]] = by_class.get(failure["class"], 0) + 1
                by_agent[failure["agent"]] = by_agent.get(failure["agent"], 0) + 1
            row["failure_count"] = len(config_failures)
            row["failure_classes"] = by_class
            row["failure_agents"] = by_agent
            rows.append(row)
            if config_failures:
                sample = config_failures[0]
                print(
                    f"[DIAGNOSTIC cases={concurrent_cases}] failures={len(config_failures)} "
                    f"classes={by_class} agents={by_agent}",
                    flush=True,
                )
                print(
                    f"[FIRST FAILURE] agent={sample['agent']} class={sample['class']} "
                    f"seconds={sample['seconds']:.3f} error={sample['error']}",
                    flush=True,
                )
    finally:
        base.orchestrator.run_specialist = original_specialist

    stable = [row for row in rows if row["all_complete"]]
    highest_stable = max(stable, key=lambda row: int(row["concurrent_cases"])) if stable else None
    fastest_stable = max(stable, key=lambda row: float(row["throughput_cases_per_hour"])) if stable else None

    print("\n=== EDGE CAPACITY MATRIX ===", flush=True)
    print("workers | cases | mean_s | p95_s | cases/hour | complete | failures", flush=True)
    for row in rows:
        print(
            f"{row['workers']:>7} | {row['concurrent_cases']:>5} | "
            f"{row['mean_batch_seconds']:>6.3f} | {row['p95_batch_seconds']:>6.3f} | "
            f"{row['throughput_cases_per_hour']:>10.2f} | "
            f"{row['completed_cases']}/{row['expected_cases']} | {row['failure_count']}",
            flush=True,
        )

    forbidden = base._count_forbidden_objects()
    branch_after = base._git_output("branch", "--show-current")
    status_after = base._git_output("status", "--porcelain")
    branch_unchanged = branch_before == branch_after
    status_unchanged = status_before == status_after

    print("\n=== EDGE CAPACITY SUMMARY ===", flush=True)
    if highest_stable:
        print(
            f"Highest fully stable concurrency tested: {highest_stable['concurrent_cases']} cases",
            flush=True,
        )
        print(
            f"Stable throughput at that edge: {highest_stable['throughput_cases_per_hour']:.2f} cases/hour",
            flush=True,
        )
        print(
            f"Stable mean/P95 batch wall-clock: {highest_stable['mean_batch_seconds']:.3f}/"
            f"{highest_stable['p95_batch_seconds']:.3f}s",
            flush=True,
        )
    else:
        print("Highest fully stable concurrency tested: NONE", flush=True)
    if fastest_stable:
        print(
            f"Fastest fully stable configuration: workers={fastest_stable['workers']} "
            f"cases={fastest_stable['concurrent_cases']} "
            f"throughput={fastest_stable['throughput_cases_per_hour']:.2f} cases/hour",
            flush=True,
        )
    print(f"Total specialist/provider failures captured: {len(failures)}", flush=True)
    if failures:
        aggregate_classes: dict[str, int] = {}
        for failure in failures:
            aggregate_classes[failure["class"]] = aggregate_classes.get(failure["class"], 0) + 1
        print(f"Failure classes: {aggregate_classes}", flush=True)
    print(f"Forbidden execution/authorization/position objects: {forbidden}", flush=True)
    print(f"Repo branch unchanged: {branch_unchanged} ({branch_after})", flush=True)
    print(f"Repo tracked status unchanged: {status_unchanged}", flush=True)

    passed = bool(
        highest_stable is not None
        and int(highest_stable["concurrent_cases"]) >= 6
        and forbidden == 0
        and branch_unchanged
        and status_unchanged
    )
    print(
        "RESULT: PASS — stable production edge identified with provider diagnostics"
        if passed
        else "RESULT: FAIL — six-case stability or safety invariant not confirmed",
        flush=True,
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
