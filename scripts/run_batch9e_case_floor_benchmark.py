#!/usr/bin/env python3
from __future__ import annotations

import argparse
import math
import os
import sqlite3
import statistics
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any
from uuid import uuid4

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND = REPO_ROOT / "BACK END" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

try:
    from dotenv import load_dotenv

    load_dotenv(BACKEND / ".env")
except Exception:
    pass

# This benchmark must never touch the live ledger. Set the isolated DB path
# before importing ledger or any backend module that imports ledger.
TMP_DIR = Path(tempfile.mkdtemp(prefix="iios_batch9e_case_floor_benchmark_"))
BENCH_DB = TMP_DIR / "benchmark.db"
os.environ["IIOS_DB_PATH"] = str(BENCH_DB)

import ledger  # noqa: E402
from evidence_engine import build_packet  # noqa: E402
import eight_agent_orchestrator as orchestrator  # noqa: E402


DEFAULT_TRIALS = 10
CASES_PER_TRIAL = 2
EXPECTED_AGENT_COUNT = 8


def _git_output(*args: str) -> str:
    try:
        return subprocess.check_output(
            ["git", "-C", str(REPO_ROOT), *args],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return "UNKNOWN"


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(0.95 * len(ordered)) - 1))
    return ordered[index]


def _fixture_evidence(case_number: int) -> list[dict[str, Any]]:
    now = ledger.utc_now()
    prefix = f"Benchmark fixture {case_number:02d}"
    return [
        {
            "source": "IIOS Case Floor Benchmark",
            "source_type": "benchmark_fixture",
            "evidence_type": "fundamental",
            "url": f"iios://benchmark/{case_number}/fundamental",
            "title": f"{prefix} fundamental packet",
            "claim": (
                "Synthetic benchmark evidence: operating performance improved while "
                "capital intensity remained elevated. This is a latency fixture only, "
                "not a statement about a real security."
            ),
            "timestamp": now,
            "reliability_score": 0.90,
            "freshness_score": 1.0,
            "gap_resolution_eligible": False,
            "benchmark_fixture": True,
        },
        {
            "source": "IIOS Case Floor Benchmark",
            "source_type": "benchmark_fixture",
            "evidence_type": "market",
            "url": f"iios://benchmark/{case_number}/market",
            "title": f"{prefix} market packet",
            "claim": (
                "Synthetic benchmark evidence: price and volume moved materially around "
                "a disclosed catalyst, with uncertainty about how much was already priced in."
            ),
            "timestamp": now,
            "reliability_score": 0.88,
            "freshness_score": 1.0,
            "gap_resolution_eligible": False,
            "benchmark_fixture": True,
        },
        {
            "source": "IIOS Case Floor Benchmark",
            "source_type": "benchmark_fixture",
            "evidence_type": "macro_policy",
            "url": f"iios://benchmark/{case_number}/macro",
            "title": f"{prefix} macro packet",
            "claim": (
                "Synthetic benchmark evidence: the macro backdrop is mixed and policy "
                "transmission remains uncertain. Agents must preserve unknowns and dissent."
            ),
            "timestamp": now,
            "reliability_score": 0.87,
            "freshness_score": 1.0,
            "gap_resolution_eligible": False,
            "benchmark_fixture": True,
        },
        {
            "source": "IIOS Case Floor Benchmark",
            "source_type": "benchmark_fixture",
            "evidence_type": "risk",
            "url": f"iios://benchmark/{case_number}/risk",
            "title": f"{prefix} risk packet",
            "claim": (
                "Synthetic benchmark evidence: plausible upside and downside explanations "
                "both remain open; the Skeptic must identify a falsifier."
            ),
            "timestamp": now,
            "reliability_score": 0.89,
            "freshness_score": 1.0,
            "gap_resolution_eligible": False,
            "benchmark_fixture": True,
        },
    ]


def _create_prepared_case(case_number: int) -> str:
    case_id = f"case_benchmark_{case_number:02d}_{uuid4().hex}"
    packet_id = f"packet_benchmark_{case_number:02d}_{uuid4().hex}"
    evidence = _fixture_evidence(case_number)
    packet = {
        **build_packet(evidence),
        "evidence_packet_id": packet_id,
        "case_id": case_id,
        "benchmark_fixture": True,
    }
    topic = (
        f"IIOS throughput benchmark case {case_number:02d}: assess a synthetic "
        "public-company catalyst packet under PAPER-ONLY governance."
    )
    case = {
        "case_id": case_id,
        "topic": topic,
        "evidence_packet_id": packet_id,
        "evidence": evidence,
        "evidence_summary": packet["summary"],
        "benchmark_fixture": True,
        "created_at": ledger.utc_now(),
        "paper_mode": True,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }
    ledger.record_object(case_id, "case", case_id, case, topic=topic)
    ledger.record_object(
        packet_id,
        "evidence_packet",
        case_id,
        packet,
        parent_id=case_id,
        topic=topic,
    )
    return case_id


def _count_execution_objects() -> int:
    if not BENCH_DB.exists():
        return 0
    connection = sqlite3.connect(BENCH_DB, timeout=30)
    try:
        row = connection.execute(
            """
            SELECT COUNT(*)
            FROM ledger_objects
            WHERE object_type IN (
                'execution',
                'governed_paper_execution',
                'paper_authorization',
                'paper_position'
            )
            """
        ).fetchone()
    finally:
        connection.close()
    return int(row[0] if row else 0)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Measure Batch 9E wall-clock throughput for two concurrent prepared "
            "cases through all eight agents plus Investment Committee."
        )
    )
    parser.add_argument(
        "--trials",
        type=int,
        default=DEFAULT_TRIALS,
        help="Number of consecutive two-case trials (default: 10)",
    )
    args = parser.parse_args()
    trials = max(1, min(int(args.trials), 50))

    ledger.init_ledger()
    branch_before = _git_output("branch", "--show-current")
    status_before = _git_output("status", "--porcelain")

    # Instrument the actual production orchestrator in memory. No production
    # source file is changed and the timing wrappers add only microseconds.
    lock = threading.Lock()
    agent_timings: list[dict[str, Any]] = []
    committee_timings: list[dict[str, Any]] = []
    topic_to_case: dict[str, str] = {}

    original_specialist = orchestrator.run_specialist
    original_committee = orchestrator._synthesize_committee

    def timed_specialist(agent_key: str, topic: str, evidence: list[dict[str, Any]]) -> dict[str, Any]:
        started = time.perf_counter()
        try:
            return original_specialist(agent_key, topic, evidence)
        finally:
            elapsed = time.perf_counter() - started
            with lock:
                agent_timings.append(
                    {
                        "case_id": topic_to_case.get(topic),
                        "agent_key": agent_key,
                        "seconds": elapsed,
                    }
                )

    def timed_committee(**kwargs: Any) -> dict[str, Any]:
        started = time.perf_counter()
        try:
            return original_committee(**kwargs)
        finally:
            elapsed = time.perf_counter() - started
            with lock:
                committee_timings.append(
                    {
                        "case_id": kwargs.get("case_id"),
                        "seconds": elapsed,
                    }
                )

    orchestrator.run_specialist = timed_specialist
    orchestrator._synthesize_committee = timed_committee

    print("IIOS BATCH 9E — TWO-CASE AGENT-FLOOR THROUGHPUT BENCHMARK", flush=True)
    print(f"Trials: {trials}", flush=True)
    print(f"Cases per trial: {CASES_PER_TRIAL}", flush=True)
    print(f"Total cases: {trials * CASES_PER_TRIAL}", flush=True)
    print(f"Isolated ledger: {BENCH_DB}", flush=True)
    print("Timing boundary: BOTH CASES ENTER FLOOR -> BOTH COMMITTEES COMPLETE", flush=True)
    print("Included: all 8 agents + Committee", flush=True)
    print("Excluded: radar, evidence acquisition, Gap Hunter, Risk, Capital, execution", flush=True)
    print(f"Per-case specialist concurrency: {orchestrator.MAX_PARALLEL_SPECIALISTS}", flush=True)
    print("Concurrent cases: 2", flush=True)
    print("Paper order authority: FALSE", flush=True)
    print("Broker connected: FALSE", flush=True)
    print("Live execution: FALSE", flush=True)

    pair_times: list[float] = []
    case_times: list[float] = []
    trial_rows: list[dict[str, Any]] = []
    case_number = 0

    def run_case(case_id: str) -> dict[str, Any]:
        started = time.perf_counter()
        result = orchestrator.run_eight_agent_orchestration(case_id)
        elapsed = time.perf_counter() - started
        orchestration = result.get("orchestration") or {}
        committee = result.get("committee") or {}
        metrics = orchestration.get("agent_metrics") or {}
        guard = committee.get("orchestration_guard") or {}
        return {
            "case_id": case_id,
            "seconds": elapsed,
            "agent_count": int(metrics.get("agent_count") or 0),
            "all_eight_complete": (guard.get("checks") or {}).get("all_eight_agents_complete") is True,
            "failed_guard_checks": guard.get("failed_checks") or [],
            "committee_status": committee.get("status"),
            "committee_disposition": committee.get("disposition"),
        }

    try:
        for trial in range(1, trials + 1):
            ids: list[str] = []
            for _ in range(CASES_PER_TRIAL):
                case_number += 1
                case_id = _create_prepared_case(case_number)
                case = ledger.get_object(case_id) or {}
                topic_to_case[str(case.get("topic") or "")] = case_id
                ids.append(case_id)

            pair_started = time.perf_counter()
            results: list[dict[str, Any]] = []
            with ThreadPoolExecutor(max_workers=CASES_PER_TRIAL) as pool:
                futures = {pool.submit(run_case, case_id): case_id for case_id in ids}
                for future in as_completed(futures):
                    results.append(future.result())
            pair_elapsed = time.perf_counter() - pair_started

            results.sort(key=lambda row: row["case_id"])
            pair_times.append(pair_elapsed)
            case_times.extend(float(row["seconds"]) for row in results)
            complete = sum(
                1
                for row in results
                if row["agent_count"] == EXPECTED_AGENT_COUNT
                and row["all_eight_complete"]
                and row["committee_status"] == "complete"
            )
            trial_rows.append(
                {
                    "trial": trial,
                    "pair_seconds": pair_elapsed,
                    "complete": complete,
                    "results": results,
                }
            )
            case_display = " / ".join(f"{row['seconds']:.3f}s" for row in results)
            print(
                f"[TRIAL {trial:02d}/{trials:02d}] pair={pair_elapsed:.3f}s "
                f"cases=({case_display}) complete={complete}/2",
                flush=True,
            )
    finally:
        orchestrator.run_specialist = original_specialist
        orchestrator._synthesize_committee = original_committee

    mean_pair = statistics.mean(pair_times)
    median_pair = statistics.median(pair_times)
    p95_pair = _p95(pair_times)
    stdev_pair = statistics.stdev(pair_times) if len(pair_times) > 1 else 0.0
    cases_per_hour = 7200.0 / mean_pair if mean_pair > 0 else 0.0
    median_cases_per_hour = 7200.0 / median_pair if median_pair > 0 else 0.0

    by_agent: dict[str, list[float]] = {}
    for row in agent_timings:
        by_agent.setdefault(str(row.get("agent_key") or "UNKNOWN"), []).append(float(row["seconds"]))
    agent_summary = {
        key: {
            "mean": statistics.mean(values),
            "median": statistics.median(values),
            "p95": _p95(values),
            "max": max(values),
        }
        for key, values in sorted(by_agent.items())
        if values
    }
    bottleneck_agent = max(
        agent_summary,
        key=lambda key: agent_summary[key]["mean"],
        default="NONE",
    )

    committee_values = [float(row["seconds"]) for row in committee_timings]
    committee_mean = statistics.mean(committee_values) if committee_values else 0.0
    committee_p95 = _p95(committee_values)

    all_cases_complete = all(row["complete"] == CASES_PER_TRIAL for row in trial_rows)
    branch_after = _git_output("branch", "--show-current")
    status_after = _git_output("status", "--porcelain")
    execution_objects = _count_execution_objects()
    branch_unchanged = branch_before == branch_after
    status_unchanged = status_before == status_after

    print("\n=== BATCH 9E CASE-FLOOR THROUGHPUT SUMMARY ===", flush=True)
    print(f"Mean pair wall-clock seconds: {mean_pair:.3f}", flush=True)
    print(f"Median pair wall-clock seconds: {median_pair:.3f}", flush=True)
    print(f"P95 pair wall-clock seconds: {p95_pair:.3f}", flush=True)
    print(f"Pair-time standard deviation: {stdev_pair:.3f}", flush=True)
    print(f"Mean individual case seconds: {statistics.mean(case_times):.3f}", flush=True)
    print(f"Sustainable throughput from mean: {cases_per_hour:.2f} cases/hour", flush=True)
    print(f"Throughput from median: {median_cases_per_hour:.2f} cases/hour", flush=True)
    print(f"Committee mean seconds: {committee_mean:.3f}", flush=True)
    print(f"Committee P95 seconds: {committee_p95:.3f}", flush=True)
    print(f"Bottleneck agent by mean latency: {bottleneck_agent}", flush=True)
    if bottleneck_agent != "NONE":
        stats = agent_summary[bottleneck_agent]
        print(
            f"Bottleneck latency mean/median/P95/max: "
            f"{stats['mean']:.3f}/{stats['median']:.3f}/{stats['p95']:.3f}/{stats['max']:.3f}s",
            flush=True,
        )
    print(f"All {trials * CASES_PER_TRIAL} cases completed 8 agents + Committee: {all_cases_complete}", flush=True)
    print(f"Execution/authorization/position objects created: {execution_objects}", flush=True)
    print(f"Repo branch unchanged: {branch_unchanged} ({branch_after})", flush=True)
    print(f"Repo tracked status unchanged: {status_unchanged}", flush=True)

    passed = bool(
        all_cases_complete
        and execution_objects == 0
        and branch_unchanged
        and status_unchanged
        and len(agent_timings) == trials * CASES_PER_TRIAL * EXPECTED_AGENT_COUNT
        and len(committee_timings) == trials * CASES_PER_TRIAL
    )
    print(
        "RESULT: PASS — throughput benchmark completed with no execution authority"
        if passed
        else "RESULT: FAIL — inspect incomplete cases, timing instrumentation, or safety invariants",
        flush=True,
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
