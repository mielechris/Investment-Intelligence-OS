#!/usr/bin/env python3
from __future__ import annotations

import os
import shlex
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

LIVE = Path("/Users/crm/Documents/GitHub/Investment-Intelligence-OS-Batch8")
WORKTREE = Path("/Users/crm/Documents/GitHub/Investment-Intelligence-OS-batch9e-radar")
DOTENV = LIVE / "BACK END" / "backend" / ".env"
BRANCH = "feature/batch9e-high-speed-market-radar"


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        try:
            parsed = shlex.split(value.strip(), posix=True)
            os.environ[key] = parsed[0] if len(parsed) == 1 else value.strip().strip("\"'")
        except ValueError:
            os.environ[key] = value.strip().strip("\"'")


def main() -> int:
    load_dotenv(DOTENV)
    os.environ["IIOS_GEMINI_TIMEOUT_SECONDS"] = "60"
    os.environ["IIOS_GEMINI_RETRIES"] = "0"
    os.environ["IIOS_9E_GEMINI_FINALISTS"] = "2"
    os.environ["IIOS_9E_GEMINI_WORKERS"] = "2"

    backend = WORKTREE / "BACK END" / "backend"
    sys.path.insert(0, str(backend))

    # Match the production 9E/full-factory network path. This keeps certificate
    # and hostname verification enabled while selecting a trusted CA bundle.
    from index_tls_bootstrap import configure_verified_tls

    tls = configure_verified_tls()

    import gemini_provider
    import gemini_rapid_research

    status = gemini_provider.configuration_status()
    print("IIOS BATCH 9E — GEMINI FOCUSED ACCEPTANCE", flush=True)
    print(f"TLS configured: {tls.get('configured') is True}", flush=True)
    print(f"TLS mode: {tls.get('mode')}", flush=True)
    print(f"Certificate verification: {tls.get('certificate_verification') is True}", flush=True)
    print(f"Hostname verification: {tls.get('hostname_verification') is True}", flush=True)
    print(f"Gemini configured: {status.get('configured') is True}", flush=True)
    print(f"Flash model: {status.get('flash_model')}", flush=True)
    print(f"Request timeout seconds: {status.get('request_timeout_seconds')}", flush=True)
    print(f"Request retries: {status.get('request_retries')}", flush=True)
    print("Google Search grounding: REQUIRED", flush=True)
    print("URL Context: REQUIRED", flush=True)
    print("Structured output: REQUIRED", flush=True)
    print("Paper order authority: FALSE", flush=True)
    print("Broker connected: FALSE", flush=True)
    print("Live execution: FALSE", flush=True)

    if status.get("configured") is not True:
        print("RESULT: FAIL — Gemini provider not configured", flush=True)
        return 1
    if not (
        tls.get("configured") is True
        and tls.get("certificate_verification") is True
        and tls.get("hostname_verification") is True
    ):
        print("RESULT: FAIL — verified TLS bootstrap unavailable", flush=True)
        return 1

    rows = [
        {
            "ticker": "MSFT",
            "company": "Microsoft",
            "radar_score": 50.0,
            "price": None,
            "change_pct": 0.0,
            "relative_volume": 1.0,
            "screeners": ["focused_acceptance"],
        },
        {
            "ticker": "AAPL",
            "company": "Apple",
            "radar_score": 50.0,
            "price": None,
            "change_pct": 0.0,
            "relative_volume": 1.0,
            "screeners": ["focused_acceptance"],
        },
    ]

    started = time.perf_counter()
    heartbeat_stop = threading.Event()

    def run_test():
        return gemini_rapid_research.run_gemini_rapid_research(
            rows,
            finalist_count=2,
            max_workers=2,
        )

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(run_test)
        while not future.done():
            elapsed = time.perf_counter() - started
            print(
                f"[GEMINI WAIT] elapsed={elapsed:.0f}s · bounded focused acceptance still running",
                flush=True,
            )
            heartbeat_stop.wait(15)
        try:
            output, diagnostics = future.result()
        except Exception as exc:
            print(f"Gemini focused exception: {type(exc).__name__}: {exc}", flush=True)
            print(f"Total seconds: {time.perf_counter() - started:.3f}", flush=True)
            print("RESULT: FAIL", flush=True)
            return 1

    elapsed = time.perf_counter() - started
    print("\n=== GEMINI FOCUSED SUMMARY ===", flush=True)
    print(f"Candidate count: {len(output)}", flush=True)
    print(f"Candidates: {sorted(output.keys())}", flush=True)
    print(f"Diagnostics: {diagnostics or 'NONE'}", flush=True)
    print(f"Total seconds: {elapsed:.3f}", flush=True)
    grounded = (
        all(
            bool((row or {}).get("grounding_sources") or (row or {}).get("web_search_queries"))
            for row in output.values()
        )
        if output
        else False
    )
    print(f"Grounded research returned: {grounded}", flush=True)
    passed = bool(len(output) >= 1 and grounded)
    print(
        "RESULT: PASS — Gemini grounded research lane is healthy"
        if passed
        else "RESULT: FAIL — Gemini did not return a usable grounded finalist",
        flush=True,
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
