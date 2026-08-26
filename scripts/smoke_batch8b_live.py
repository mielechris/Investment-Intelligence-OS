#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import signal
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path("/Users/crm/Documents/GitHub/Investment-Intelligence-OS-Batch8")
BACKEND = REPO / "BACK END" / "backend"
PYTHON = Path("/Users/crm/Documents/GitHub/Investment-Intelligence-OS/BACK END/backend/.venv/bin/python")
ENV_FILE = Path("/Users/crm/Documents/GitHub/Investment-Intelligence-OS/BACK END/backend/.env")
LOG_FILE = Path("/tmp/iios_backend_8002_v015.log")
REPORT_FILE = Path("/tmp/iios_batch8b_live_smoke.json")
BASE = "http://127.0.0.1:8002"


def call(path: str, method: str = "GET", payload=None, timeout: int = 300):
    body = None
    headers = {}
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(BASE + path, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            return {"ok": True, "status": response.status, "data": json.loads(raw) if raw else {}}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8")
        try:
            data = json.loads(raw)
        except Exception:
            data = raw
        return {"ok": False, "status": exc.code, "data": data}
    except Exception as exc:
        return {"ok": False, "status": None, "data": f"{type(exc).__name__}: {exc}"}


def load_env():
    env = os.environ.copy()
    if ENV_FILE.exists():
        for raw in ENV_FILE.read_text().splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            env[key.strip()] = value.strip().strip("'").strip('"')
    env["IIOS_DB_PATH"] = str(BACKEND / "iios_ledger.db")
    return env


def kill_8002():
    result = subprocess.run(["lsof", "-tiTCP:8002", "-sTCP:LISTEN"], text=True, capture_output=True)
    pids = [int(x) for x in result.stdout.split() if x.isdigit()]
    if not pids:
        print("Port 8002 is free.")
        return
    print("Stopping old 8002 listener(s):", pids)
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    deadline = time.time() + 5
    while time.time() < deadline:
        check = subprocess.run(["lsof", "-tiTCP:8002", "-sTCP:LISTEN"], text=True, capture_output=True)
        if not check.stdout.strip():
            return
        time.sleep(0.25)
    for pid in pids:
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def start_backend():
    LOG_FILE.write_text("")
    log = LOG_FILE.open("ab", buffering=0)
    proc = subprocess.Popen(
        [str(PYTHON), "-m", "uvicorn", "app:app", "--host", "127.0.0.1", "--port", "8002"],
        cwd=BACKEND,
        env=load_env(),
        stdout=log,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    print("Started backend PID:", proc.pid)
    deadline = time.time() + 30
    last = None
    while time.time() < deadline:
        last = call("/system/status", timeout=2)
        if last["ok"] and (last["data"] or {}).get("version") == "0.15.0":
            return proc.pid, last["data"]
        time.sleep(0.5)
    print(LOG_FILE.read_text()[-5000:])
    raise SystemExit(f"v0.15.0 backend did not become ready. Last response: {last}")


def main():
    print("=" * 72)
    print("IIOS GROUP BATCH 8B - LIVE PRODUCTION SMOKE")
    print("=" * 72)

    kill_8002()
    time.sleep(1)
    pid, system = start_backend()

    print("\nSYSTEM")
    print("  Version:", system.get("version"))
    print("  Paper mode:", system.get("paper_mode"))
    print("  Live source acquisition:", system.get("jesse_live_source_acquisition"))
    print("  Jesse scheduler:", system.get("jesse_internal_scheduler"))
    print("  11AM Pacific scheduler:", system.get("dislocation_11am_pacific_scheduler"))
    print("  Outcome calibration:", system.get("dislocation_next_day_calibration"))

    source_status = call("/intelligence/source-acquisition/status")
    scheduler_status = call("/intelligence/jesse-scheduler/status")

    print("\nSOURCE ACQUISITION")
    sd = source_status.get("data") if source_status["ok"] else {}
    print("  Status:", source_status["status"])
    print("  Research inbox:", sd.get("research_inbox"))
    print("  Strict universe symbols:", ((sd.get("governed_dislocation_universe") or {}).get("symbol_count")))
    print("  Fed URL configured:", sd.get("fed_probability_url_configured"))
    print("  Private-bank entitlement bypass:", sd.get("private_bank_entitlement_bypass"))

    print("\nSCHEDULER")
    jd = scheduler_status.get("data") if scheduler_status["ok"] else {}
    print("  Status:", scheduler_status["status"])
    print("  Running:", jd.get("scheduler_running"))
    print("  Timezone:", jd.get("timezone"))
    print("  11AM last run:", (jd.get("state") or {}).get("last_dislocation_date"))
    print("  Calibration observations:", (jd.get("calibration") or {}).get("observation_count"))

    print("\nFORCING ONE PRODUCTION RESEARCH CYCLE...")
    cycle = call(
        "/intelligence/jesse-scheduler/run-now",
        method="POST",
        payload={"jobs": ["public_research", "authorized_inbox", "fed_probability", "tariff", "dislocation"]},
        timeout=600,
    )
    cd = cycle.get("data") if cycle["ok"] else {}
    print("  Status:", cycle["status"])
    print("  Jobs:", cd.get("jobs_attempted"))
    print("  Errors:", cd.get("errors"))

    public_research = (cd.get("results") or {}).get("public_research") or {}
    inbox = (cd.get("results") or {}).get("authorized_inbox") or {}
    fed = (cd.get("results") or {}).get("fed_probability") or {}
    tariff = (cd.get("results") or {}).get("tariff") or {}
    dislocation = (cd.get("results") or {}).get("dislocation") or {}

    print("\nPUBLIC INSTITUTIONAL RESEARCH")
    print("  Discoveries:", public_research.get("discovery_count"))
    print("  Institutions searched:", public_research.get("institution_count"))
    print("  Entitlement bypass:", public_research.get("private_bank_entitlement_bypass"))

    print("\nAUTHORIZED RESEARCH INBOX")
    print("  Imported:", inbox.get("imported_count"))
    print("  Errors:", inbox.get("error_count"))

    print("\nFED PROBABILITY FEED")
    print("  Status:", fed.get("status"))
    print("  Probabilities invented:", fed.get("probabilities_invented"))

    print("\nTARIFF TRANSMISSION")
    print("  Events:", tariff.get("event_count"))
    print("  Sector impacts:", len(tariff.get("sector_impacts") or []))

    print("\n11AM DISLOCATION ENGINE")
    print("  Scope:", dislocation.get("universe_scope"))
    print("  Strict membership:", dislocation.get("strict_index_membership"))
    print("  Losers reviewed:", dislocation.get("loser_count"))
    print("  Top three:")
    for row in dislocation.get("top_three") or []:
        print(
            "   ",
            row.get("ticker"),
            "|", row.get("recommendation"),
            "| financial", row.get("financial_strength_score"),
            "| P(+5%)", row.get("estimated_probability_next_day_plus_5"),
        )

    post_scheduler = call("/intelligence/jesse-scheduler/status")
    pd = post_scheduler.get("data") if post_scheduler["ok"] else {}
    calibration = pd.get("calibration") or {}

    required_features = [
        system.get("version") == "0.15.0",
        system.get("paper_mode") is True,
        system.get("jesse_live_source_acquisition") is True,
        system.get("jesse_internal_scheduler") is True,
        system.get("dislocation_11am_pacific_scheduler") is True,
        source_status["ok"],
        scheduler_status["ok"],
        cycle["ok"],
        not cd.get("errors"),
        cd.get("live_execution", False) is not True,
    ]
    verdict = "PASS" if all(required_features) else "NEEDS_ATTENTION"

    report = {
        "backend_pid": pid,
        "system": system,
        "source_status": sd,
        "scheduler_before": jd,
        "cycle": cd,
        "scheduler_after": pd,
        "calibration": calibration,
        "verdict": verdict,
    }
    REPORT_FILE.write_text(json.dumps(report, indent=2, default=str))

    print("\n" + "=" * 72)
    print("LIVE PRODUCTION SMOKE VERDICT:", verdict)
    print("Backend PID:", pid)
    print("Backend log:", LOG_FILE)
    print("Report:", REPORT_FILE)
    print("Strict S&P/Nasdaq universe configured:", bool((sd.get("governed_dislocation_universe") or {}).get("symbol_count")))
    print("Governed Fed probability feed configured:", bool(sd.get("fed_probability_url_configured") or fed.get("status") == "CAPTURED"))
    print("Live execution authority: FALSE")
    print("=" * 72)
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
