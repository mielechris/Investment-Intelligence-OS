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
LOG_FILE = Path("/tmp/iios_backend_8002_v017.log")
REPORT_FILE = Path("/tmp/iios_batch8d_live_smoke.json")
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
    result = subprocess.run(
        ["lsof", "-tiTCP:8002", "-sTCP:LISTEN"],
        text=True,
        capture_output=True,
    )
    pids = [int(x) for x in result.stdout.split() if x.isdigit()]
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
        [str(PYTHON), "-m", "uvicorn", "app:app", "--host", "127.0.0.1", "--port", "8002"],
        cwd=BACKEND,
        env=load_env(),
        stdout=log,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    deadline = time.time() + 35
    last = None
    while time.time() < deadline:
        last = call("/system/status", timeout=2)
        if last["ok"] and (last["data"] or {}).get("version") == "0.17.0":
            return proc.pid, last["data"]
        time.sleep(0.5)
    print(LOG_FILE.read_text()[-6000:])
    raise SystemExit(f"v0.17.0 backend did not become ready. Last response: {last}")


def main():
    print("=" * 72)
    print("IIOS GROUP BATCH 8D - KIMI RESEARCH LIVE SMOKE")
    print("=" * 72)

    kill_8002()
    time.sleep(1)
    pid, system = start_backend()

    kimi_status = call("/intelligence/kimi/status")
    kd = kimi_status.get("data") if kimi_status["ok"] else {}
    provider = kd.get("provider") or {}
    swarm = kd.get("native_swarm") or {}

    print("\nSYSTEM")
    print("  Version:", system.get("version"))
    print("  Paper mode:", system.get("paper_mode"))
    print("  Kimi research layer:", system.get("kimi_research_intelligence"))
    print("  Kimi context-only default:", system.get("kimi_context_only_default"))
    print("  Kimi auto trade authority:", system.get("kimi_auto_trade_authority"))

    print("\nKIMI PLATFORM PROVIDER")
    print("  Status endpoint:", kimi_status.get("status"))
    print("  Configured:", provider.get("configured"))
    print("  Credential exposed:", provider.get("credential_exposed"))
    print("  Model preference:", provider.get("model_preference"))
    print("  K3 long context:", provider.get("k3_long_context_supported_by_provider"))
    print("  Formula web search:", provider.get("formula_web_search_supported"))
    print("  Consumer Deep Research API claimed:", provider.get("consumer_deep_research_api_available"))

    print("\nKIMI NATIVE SWARM BRIDGE")
    print("  Configured:", swarm.get("configured"))
    print("  Experimental server API:", swarm.get("experimental_server_api"))
    print("  Repo write access granted:", swarm.get("repo_write_access_granted"))

    live_validation = None
    if provider.get("configured") is True:
        print("\nRUNNING MINIMAL LIVE KIMI VALIDATION...")
        live_validation = call(
            "/intelligence/kimi/research/run",
            method="POST",
            payload={
                "objective": "Return a conservative research synthesis of this public test note.",
                "documents": [
                    {
                        "institution": "IIOS PUBLIC TEST",
                        "title": "Synthetic public validation note",
                        "source_url": "iios://batch8d-smoke",
                        "access_tier": "PUBLIC_TEST",
                        "content": "Semiconductor demand may benefit from AI infrastructure investment, while valuation and policy uncertainty remain material risks.",
                    }
                ],
                "use_web_search": False,
            },
            timeout=600,
        )
        print("  HTTP:", live_validation.get("status"))
        print("  Result status:", (live_validation.get("data") or {}).get("status") if live_validation.get("ok") else "FAILED")

    software_checks = {
        "version_0_17_0": system.get("version") == "0.17.0",
        "paper_mode": system.get("paper_mode") is True,
        "kimi_research_flag": system.get("kimi_research_intelligence") is True,
        "kimi_context_only": system.get("kimi_context_only_default") is True,
        "kimi_auto_trade_false": system.get("kimi_auto_trade_authority") is False,
        "kimi_status_route": kimi_status["ok"],
        "credential_not_exposed": provider.get("credential_exposed") is False,
        "deep_research_api_not_fabricated": provider.get("consumer_deep_research_api_available") is False,
        "native_swarm_repo_write_false": swarm.get("repo_write_access_granted") is False,
        "live_execution_false": kd.get("live_execution") is False,
    }
    software_ready = all(software_checks.values())

    provider_ready = provider.get("configured") is True
    live_ready = (
        live_validation is not None
        and live_validation.get("ok") is True
        and ((live_validation.get("data") or {}).get("status") == "COMPLETE")
    )

    if not software_ready:
        verdict = "SOFTWARE_NEEDS_ATTENTION"
        exit_code = 1
    elif provider_ready and not live_ready:
        verdict = "PROVIDER_CONFIGURED_LIVE_VALIDATION_FAILED"
        exit_code = 1
    elif provider_ready and live_ready:
        verdict = "KIMI_PROVIDER_PASS"
        exit_code = 0
    else:
        verdict = "SOFTWARE_PASS_KIMI_PROVIDER_PENDING"
        exit_code = 0

    report = {
        "backend_pid": pid,
        "system": system,
        "kimi_status": kd,
        "live_validation": live_validation,
        "software_checks": software_checks,
        "software_ready": software_ready,
        "provider_ready": provider_ready,
        "live_ready": live_ready,
        "verdict": verdict,
    }
    REPORT_FILE.write_text(json.dumps(report, indent=2, default=str))

    print("\n" + "=" * 72)
    print("BATCH 8D VERDICT:", verdict)
    print("Software ready:", software_ready)
    print("Kimi provider configured:", provider_ready)
    print("Kimi live validation ready:", live_ready)
    print("Backend PID:", pid)
    print("Backend log:", LOG_FILE)
    print("Report:", REPORT_FILE)
    print("Live execution authority: FALSE")
    print("=" * 72)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
