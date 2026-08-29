#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND = REPO_ROOT / "BACK END" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

try:
    from dotenv import load_dotenv
    load_dotenv(BACKEND / ".env")
except Exception as exc:
    print(f"dotenv load warning: {type(exc).__name__}: {exc}", flush=True)

# Never touch the live ledger during this diagnostic.
tmp_dir = Path(tempfile.mkdtemp(prefix="iios_batch9e_floor_preflight_"))
os.environ["IIOS_DB_PATH"] = str(tmp_dir / "preflight.db")

import ledger  # noqa: E402
from evidence_engine import build_packet  # noqa: E402
import eight_agent_orchestrator as orchestrator  # noqa: E402


def main() -> int:
    ledger.init_ledger()

    print("IIOS BATCH 9E — CASE-FLOOR MODEL PREFLIGHT", flush=True)
    print(f"Repo root: {REPO_ROOT}", flush=True)
    print(f"Backend env path: {BACKEND / '.env'}", flush=True)
    print(f"OPENAI_API_KEY: {'PRESENT' if bool(os.getenv('OPENAI_API_KEY')) else 'MISSING'}", flush=True)
    print(f"Isolated ledger: {os.environ['IIOS_DB_PATH']}", flush=True)
    print("Broker connected: FALSE", flush=True)
    print("Live execution: FALSE", flush=True)

    evidence = [
        {
            "source": "IIOS Case Floor Preflight",
            "source_type": "benchmark_fixture",
            "evidence_type": "fundamental",
            "url": "iios://benchmark/preflight",
            "title": "Synthetic latency preflight",
            "claim": "Synthetic benchmark evidence only. Evaluate uncertainty and identify missing evidence; do not treat this as a real security claim.",
            "timestamp": ledger.utc_now(),
            "reliability_score": 0.9,
            "freshness_score": 1.0,
            "gap_resolution_eligible": False,
            "benchmark_fixture": True,
        }
    ]
    packet = build_packet(evidence)
    topic = "IIOS throughput preflight: synthetic public-company catalyst packet under PAPER-ONLY governance."

    started = time.perf_counter()
    try:
        result = orchestrator.run_specialist("policy", topic, packet["items"])
    except Exception as exc:
        elapsed = time.perf_counter() - started
        print(f"Policy call seconds: {elapsed:.3f}", flush=True)
        print(f"Policy call result: FAIL", flush=True)
        print(f"Exact error: {type(exc).__name__}: {exc}", flush=True)
        print("RESULT: FAIL — fix model credential/model access before throughput benchmark", flush=True)
        return 1

    elapsed = time.perf_counter() - started
    print(f"Policy call seconds: {elapsed:.3f}", flush=True)
    print(f"Policy call status: {result.get('status')}", flush=True)
    print(f"Policy disposition: {result.get('disposition')}", flush=True)
    print(f"Policy confidence: {result.get('confidence')}", flush=True)

    passed = result.get("status") == "complete" and elapsed > 0.1
    print(
        "RESULT: PASS — real case-floor model call is reachable"
        if passed
        else "RESULT: FAIL — model call did not complete as a real inference",
        flush=True,
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
