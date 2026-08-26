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
LOG_FILE = Path("/tmp/iios_backend_8002_v016.log")
REPORT_FILE = Path("/tmp/iios_batch8c_live_smoke.json")
BASE = "http://127.0.0.1:8002"


def call(path: str, method: str = "GET", payload=None, timeout: int = 300):
    body = None
    headers = {}
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(BASE + path, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            return {
                "ok": True,
                "status": response.status,
                "data": json.loads(raw) if raw else {},
            }
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8")
        try:
            data = json.loads(raw)
        except Exception:
            data = raw
        return {"ok": False, "status": exc.code, "data": data}
    except Exception as exc:
        return {
            "ok": False,
            "status": None,
            "data": f"{type(exc).__name__}: {exc}",
        }


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
    result = subprocess.run(
        ["lsof", "-tiTCP:8002", "-sTCP:LISTEN"],
        text=True,
        capture_output=True,
    )
    pids = [int(value) for value in result.stdout.split() if value.isdigit()]
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    deadline = time.time() + 5
    while time.time() < deadline:
        check = subprocess.run(
            ["lsof", "-tiTCP:8002", "-sTCP:LISTEN"],
            text=True,
            capture_output=True,
        )
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
        [
            str(PYTHON),
            "-m",
            "uvicorn",
            "app:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8002",
        ],
        cwd=BACKEND,
        env=load_env(),
        stdout=log,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    deadline = time.time() + 30
    last = None
    while time.time() < deadline:
        last = call("/system/status", timeout=2)
        if last["ok"] and (last["data"] or {}).get("version") == "0.16.0":
            return proc.pid, last["data"]
        time.sleep(0.5)
    print(LOG_FILE.read_text()[-6000:])
    raise SystemExit(f"v0.16.0 backend did not become ready. Last response: {last}")


def main() -> int:
    print("=" * 76)
    print("IIOS GROUP BATCH 8C - LIVE PRODUCTION INPUT SMOKE")
    print("=" * 76)

    kill_8002()
    time.sleep(1)
    pid, system = start_backend()

    source_before = call("/intelligence/source-acquisition/status")
    universe = call(
        "/intelligence/dislocation/universe/refresh",
        method="POST",
        payload={"force": True},
        timeout=120,
    )
    fed = call(
        "/intelligence/fedwatch/run",
        method="POST",
        payload={},
        timeout=60,
    )
    production = call("/intelligence/production-inputs/status")

    u = universe.get("data") if universe["ok"] else {}
    f = fed.get("data") if fed["ok"] else {}
    p = production.get("data") if production["ok"] else {}
    health = p.get("health") or {}
    source = p.get("source_status") or {}
    cme = source.get("cme_fedwatch") or {}

    strict_ready = u.get("verified_complete") is True
    cme_configured = cme.get("configured") is True
    fed_ready = (
        f.get("status") == "CAPTURED"
        and f.get("source_verified") is True
        and str(f.get("source_mode") or "").startswith("CME_FEDWATCH_")
    )

    # Force the production scheduler dislocation path. If the strict universe is
    # unavailable, the correct result is a fail-closed job error -- never a proxy scan.
    cycle = call(
        "/intelligence/jesse-scheduler/run-now",
        method="POST",
        payload={"jobs": ["dislocation"]},
        timeout=600,
    )
    cd = cycle.get("data") if cycle["ok"] else {}
    dislocation = (cd.get("results") or {}).get("dislocation") or {}
    dislocation_error = (cd.get("errors") or {}).get("dislocation")

    if strict_ready:
        strict_behavior_ok = (
            dislocation.get("strict_index_membership") is True
            and dislocation.get("universe_scope") == "GOVERNED_SUPPLIED_UNIVERSE"
        )
    else:
        strict_behavior_ok = (
            isinstance(dislocation_error, str)
            and "STRICT_GOVERNED_UNIVERSE_UNAVAILABLE" in dislocation_error
        )

    software_checks = {
        "version_0_16_0": system.get("version") == "0.16.0",
        "paper_mode": system.get("paper_mode") is True,
        "automatic_index_refresh_flag": system.get("automatic_official_index_universe_refresh") is True,
        "cme_adapter_flag": system.get("cme_fedwatch_production_adapter") is True,
        "strict_scheduler_flag": system.get("strict_scheduled_dislocation_universe") is True,
        "source_health_flag": system.get("production_input_source_health") is True,
        "source_status_route": source_before["ok"],
        "universe_refresh_route": universe["ok"],
        "fedwatch_route": fed["ok"],
        "production_status_route": production["ok"],
        "strict_scheduler_behavior": strict_behavior_ok,
        "live_execution_false": system.get("opportunity_auto_trade_authority") is not True,
    }
    software_pass = all(software_checks.values())
    production_inputs_pass = strict_ready and cme_configured and fed_ready

    verdict = (
        "PRODUCTION_INPUTS_PASS"
        if software_pass and production_inputs_pass
        else "SOFTWARE_PASS_EXTERNAL_INPUTS_PENDING"
        if software_pass
        else "NEEDS_ATTENTION"
    )

    print("\nSYSTEM")
    print("  Version:", system.get("version"))
    print("  Paper mode:", system.get("paper_mode"))
    print("  Live execution authority: FALSE")

    print("\nSTRICT S&P 500 + NASDAQ-100 UNIVERSE")
    print("  Refresh status:", u.get("status"))
    print("  Verified complete:", strict_ready)
    print("  Merged symbols:", u.get("symbol_count"))
    for key, row in (u.get("indexes") or {}).items():
        print(
            " ", key,
            "| verified", row.get("verified_complete"),
            "| symbols", row.get("symbol_count"),
            "| mode", row.get("source_mode"),
            "| error", row.get("error"),
        )

    print("\nCME FEDWATCH")
    print("  Configured:", cme_configured)
    print("  Mode:", cme.get("mode"))
    print("  Approved CME host:", cme.get("approved_cme_host"))
    print("  Credential present:", cme.get("credential_present"))
    print("  Credential exposed:", cme.get("credential_exposed"))
    print("  Capture status:", f.get("status"))
    print("  Source mode:", f.get("source_mode"))
    print("  Verified:", f.get("source_verified"))
    print("  Probabilities invented:", f.get("probabilities_invented"))

    print("\nSTRICT 11AM SCHEDULER BEHAVIOR")
    print("  Strict universe ready:", strict_ready)
    print("  Dislocation result scope:", dislocation.get("universe_scope"))
    print("  Dislocation strict membership:", dislocation.get("strict_index_membership"))
    print("  Dislocation fail-closed error:", dislocation_error)
    print("  Correct strict behavior:", strict_behavior_ok)

    print("\nSOFTWARE CHECKS")
    for key, value in software_checks.items():
        print(" ", key, "=", value)

    report = {
        "backend_pid": pid,
        "system": system,
        "source_before": source_before,
        "universe": universe,
        "fedwatch": fed,
        "production": production,
        "cycle": cycle,
        "software_checks": software_checks,
        "software_pass": software_pass,
        "production_inputs_pass": production_inputs_pass,
        "verdict": verdict,
    }
    REPORT_FILE.write_text(json.dumps(report, indent=2, default=str))

    print("\n" + "=" * 76)
    print("BATCH 8C VERDICT:", verdict)
    print("Software ready:", software_pass)
    print("Strict universe ready:", strict_ready)
    print("CME FedWatch production feed ready:", fed_ready)
    print("External production inputs ready:", production_inputs_pass)
    print("Backend PID:", pid)
    print("Backend log:", LOG_FILE)
    print("Report:", REPORT_FILE)
    print("Live execution authority: FALSE")
    print("=" * 76)

    return 0 if software_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
