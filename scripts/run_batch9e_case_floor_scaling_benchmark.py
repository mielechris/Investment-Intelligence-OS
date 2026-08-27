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

TMP_DIR = Path(tempfile.mkdtemp(prefix="iios_batch9e_scaling_benchmark_"))
BENCH_DB = TMP_DIR / "scaling.db"
os.environ["IIOS_DB_PATH"] = str(BENCH_DB)

import ledger  # noqa: E402
from evidence_engine import build_packet  # noqa: E402
import eight_agent_orchestrator as orchestrator  # noqa: E402

EXPECTED_AGENT_COUNT = 8
BASELINE_WORKERS = 3
BASELINE_CASES = 2
BASELINE_CASES_PER_HOUR = 201.02
WORKER_SWEEP = (4, 5, 6)
CASE_SWEEP = (4, 6, 8)


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
    prefix = f"Scaling fixture {case_number:03d}"
    return [
        {
            "source": "IIOS Case Floor Scaling Benchmark",
            "source_type": "benchmark_fixture",
            "evidence_type": "fundamental",
            "url": f"iios://scaling/{case_number}/fundamental",
            "title": f"{prefix} fundamental packet",
            "claim": "Synthetic benchmark evidence: operating performance improved while capital intensity remained elevated. This is a latency fixture only, not a real security claim.",
            "timestamp": now,
            "reliability_score": 0.90,
            "freshness_score": 1.0,
            "gap_resolution_eligible": False,
            "benchmark_fixture": True,
        },
        {
            "source": "IIOS Case Floor Scaling Benchmark",
            "source_type": "benchmark_fixture",
            "evidence_type": "market",
            "url": f"iios://scaling/{case_number}/market",
            "title": f"{prefix} market packet",
            "claim": "Synthetic benchmark evidence: price and volume moved around a disclosed catalyst, with uncertainty about how much was already priced in.",
            "timestamp": now,
            "reliability_score": 0.88,
            "freshness_score": 1.0,
            "gap_resolution_eligible": False,
            "benchmark_fixture": True,
        },
        {
            "source": "IIOS Case Floor Scaling Benchmark",
            "source_type": "benchmark_fixture",
            "evidence_type": "macro_policy",
            "url": f"iios://scaling/{case_number}/macro",
            "title": f"{prefix} macro packet",
            "claim": "Synthetic benchmark evidence: the macro backdrop is mixed and policy transmission remains uncertain; agents must preserve unknowns and dissent.",
            "timestamp": now,
            "reliability_score": 0.87,
            "freshness_score": 1.0,
            "gap_resolution_eligible": False,
            "benchmark_fixture": True,
        },
        {
            "source": "IIOS Case Floor Scaling Benchmark",
            "source_type": "benchmark_fixture",
            "evidence_type": "risk",
            "url": f"iios://scaling/{case_number}/risk",
            "title": f"{prefix} risk packet",
            "claim": "Synthetic benchmark evidence: plausible upside and downside explanations remain open; the Skeptic must identify a falsifier.",
            "timestamp": now,
            "reliability_score": 0.89,
            "freshness_score": 1.0,
            "gap_resolution_eligible": False,
            "benchmark_fixture": True,
        },
    ]


def _create_case(case_number: int) -> str:
    case_id = f"case_scaling_{case_number:03d}_{uuid4().hex}"
    packet_id = f"packet_scaling_{case_number:03d}_{uuid4().hex}"
    evidence = _fixture_evidence(case_number)
    packet = {
        **build_packet(evidence),
        "evidence_packet_id": packet_id,
        "case_id": case_id,
        "benchmark_fixture": True,
    }
    topic = f"IIOS scaling benchmark case {case_number:03d}: assess a synthetic public-company catalyst packet under PAPER-ONLY governance."
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
    ledger.record_object(packet_id, "evidence_packet", case_id, packet, parent_id=case_id, topic=topic)
    return case_id


def _count_forbidden_objects() -> int:
    if not BENCH_DB.exists():
        return 0
    connection = sqlite3.connect(BENCH_DB, timeout=30)
    try:
        row = connection.execute(
            """
            SELECT COUNT(*) FROM ledger_objects
            WHERE object_type IN ('execution','governed_paper_execution','paper_authorization','paper_position')
            """
        ).fetchone()
    finally:
        connection.close()
    return int(row[0] if row else 0)


def _run_case(case_id: str) -> dict[str, Any]:
    started = time.perf_counter()
    result = orchestrator.run_eight_agent_orchestration(case_id)
    elapsed = time.perf_counter() - started
    orchestration = result.get("orchestration") or {}
    committee = result.get("committee") or {}
    metrics = orchestration.get("agent_metrics") or {}
    guard = committee.get("orchestration_guard") or {}
    complete = bool(
        int(metrics.get("agent_count") or 0) == EXPECTED_AGENT_COUNT
        and (guard.get("checks") or {}).get("all_eight_agents_complete") is True
        and committee.get("status") == "complete"
    )
    return {
        "case_id": case_id,
        "seconds": elapsed,
        "complete": complete,
        "committee_disposition": committee.get("disposition"),
        "failed_guard_checks": guard.get("failed_checks") or [],
    }


def _run_configuration(*, workers: int, concurrent_cases: int, trials: int, case_counter: list[int]) -> dict[str, Any]:
    original_workers = orchestrator.MAX_PARALLEL_SPECIALISTS
    orchestrator.MAX_PARALLEL_SPECIALISTS = int(workers)
    batch_times: list[float] = []
    case_times: list[float] = []
    completed_cases = 0
    try:
        for trial in range(1, trials + 1):
            ids: list[str] = []
            for _ in range(concurrent_cases):
                case_counter[0] += 1
                ids.append(_create_case(case_counter[0]))

            started = time.perf_counter()
            results: list[dict[str, Any]] = []
            with ThreadPoolExecutor(max_workers=concurrent_cases) as pool:
                future_map = {pool.submit(_run_case, case_id): case_id for case_id in ids}
                for future in as_completed(future_map):
                    results.append(future.result())
            elapsed = time.perf_counter() - started
            batch_times.append(elapsed)
            case_times.extend(float(row["seconds"]) for row in results)
            completed = sum(1 for row in results if row["complete"])
            completed_cases += completed
            print(
                f"[workers={workers} cases={concurrent_cases} trial={trial}/{trials}] "
                f"batch={elapsed:.3f}s complete={completed}/{concurrent_cases}",
                flush=True,
            )
    finally:
        orchestrator.MAX_PARALLEL_SPECIALISTS = original_workers

    mean_batch = statistics.mean(batch_times)
    median_batch = statistics.median(batch_times)
    p95_batch = _p95(batch_times)
    throughput = concurrent_cases * 3600.0 / mean_batch if mean_batch > 0 else 0.0
    return {
        "workers": workers,
        "concurrent_cases": concurrent_cases,
        "trials": trials,
        "mean_batch_seconds": mean_batch,
        "median_batch_seconds": median_batch,
        "p95_batch_seconds": p95_batch,
        "mean_case_seconds": statistics.mean(case_times) if case_times else 0.0,
        "throughput_cases_per_hour": throughput,
        "completed_cases": completed_cases,
        "expected_cases": concurrent_cases * trials,
        "all_complete": completed_cases == concurrent_cases * trials,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Scale Batch 9E case-floor concurrency while preserving the 8-agent + Committee reasoning structure.")
    parser.add_argument("--trials", type=int, default=2, help="Trials per configuration (default: 2)")
    args = parser.parse_args()
    trials = max(1, min(int(args.trials), 5))

    ledger.init_ledger()
    branch_before = _git_output("branch", "--show-current")
    status_before = _git_output("status", "--porcelain")
    case_counter = [0]

    print("IIOS BATCH 9E — CASE-FLOOR SCALING BENCHMARK", flush=True)
    print(f"Trials per configuration: {trials}", flush=True)
    print(f"Isolated ledger: {BENCH_DB}", flush=True)
    print(f"Baseline: workers={BASELINE_WORKERS}, cases={BASELINE_CASES}, throughput={BASELINE_CASES_PER_HOUR:.2f} cases/hour", flush=True)
    print("Phase A: specialist workers 4 -> 5 -> 6 at two concurrent cases", flush=True)
    print("Phase B: best worker count -> 4 -> 6 -> 8 concurrent cases", flush=True)
    print("Skeptic remains after first wave; Portfolio remains after Skeptic; Committee remains last", flush=True)
    print("Paper order authority: FALSE", flush=True)
    print("Broker connected: FALSE", flush=True)
    print("Live execution: FALSE", flush=True)

    phase_a: list[dict[str, Any]] = []
    for workers in WORKER_SWEEP:
        phase_a.append(
            _run_configuration(
                workers=workers,
                concurrent_cases=2,
                trials=trials,
                case_counter=case_counter,
            )
        )

    valid_a = [row for row in phase_a if row["all_complete"]]
    if not valid_a:
        print("RESULT: FAIL — no worker-sweep configuration completed successfully", flush=True)
        return 1

    best_workers_row = max(valid_a, key=lambda row: float(row["throughput_cases_per_hour"]))
    best_workers = int(best_workers_row["workers"])
    print(
        f"[PHASE A WINNER] workers={best_workers} throughput={best_workers_row['throughput_cases_per_hour']:.2f} cases/hour",
        flush=True,
    )

    phase_b: list[dict[str, Any]] = []
    for concurrent_cases in CASE_SWEEP:
        phase_b.append(
            _run_configuration(
                workers=best_workers,
                concurrent_cases=concurrent_cases,
                trials=trials,
                case_counter=case_counter,
            )
        )

    all_rows = phase_a + phase_b
    valid_rows = [row for row in all_rows if row["all_complete"]]
    best = max(valid_rows, key=lambda row: float(row["throughput_cases_per_hour"])) if valid_rows else None

    print("\n=== BATCH 9E SCALING MATRIX ===", flush=True)
    print("workers | cases | mean_s | median_s | p95_s | cases/hour | complete", flush=True)
    for row in all_rows:
        print(
            f"{row['workers']:>7} | {row['concurrent_cases']:>5} | "
            f"{row['mean_batch_seconds']:>6.3f} | {row['median_batch_seconds']:>8.3f} | "
            f"{row['p95_batch_seconds']:>5.3f} | {row['throughput_cases_per_hour']:>10.2f} | "
            f"{row['completed_cases']}/{row['expected_cases']}",
            flush=True,
        )

    forbidden = _count_forbidden_objects()
    branch_after = _git_output("branch", "--show-current")
    status_after = _git_output("status", "--porcelain")
    branch_unchanged = branch_before == branch_after
    status_unchanged = status_before == status_after

    print("\n=== SCALING SUMMARY ===", flush=True)
    print(f"Baseline throughput: {BASELINE_CASES_PER_HOUR:.2f} cases/hour", flush=True)
    print(f"Best specialist worker count at 2 cases: {best_workers}", flush=True)
    if best:
        improvement = (float(best['throughput_cases_per_hour']) / BASELINE_CASES_PER_HOUR - 1.0) * 100.0
        print(f"Best measured configuration: workers={best['workers']} concurrent_cases={best['concurrent_cases']}", flush=True)
        print(f"Best measured throughput: {best['throughput_cases_per_hour']:.2f} cases/hour", flush=True)
        print(f"Improvement vs V1 baseline: {improvement:.1f}%", flush=True)
        print(f"Best mean batch wall-clock: {best['mean_batch_seconds']:.3f}s", flush=True)
        print(f"Best P95 batch wall-clock: {best['p95_batch_seconds']:.3f}s", flush=True)
    print(f"Forbidden execution/authorization/position objects: {forbidden}", flush=True)
    print(f"Repo branch unchanged: {branch_unchanged} ({branch_after})", flush=True)
    print(f"Repo tracked status unchanged: {status_unchanged}", flush=True)

    passed = bool(
        best is not None
        and all(row["all_complete"] for row in all_rows)
        and forbidden == 0
        and branch_unchanged
        and status_unchanged
    )
    print(
        "RESULT: PASS — scaling curve measured with reasoning order and execution locks preserved"
        if passed
        else "RESULT: FAIL — inspect incomplete cases, provider capacity, or safety invariants",
        flush=True,
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
