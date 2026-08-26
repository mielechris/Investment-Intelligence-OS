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

REPO = Path(__file__).resolve().parents[1]
BACKEND = REPO / "BACK END" / "backend"
SIBLING = REPO.parent / "Investment-Intelligence-OS" / "BACK END" / "backend"
PYTHON = SIBLING / ".venv" / "bin" / "python"
ENV_FILE = SIBLING / ".env"
BASE = "http://127.0.0.1:8002"
LOG = Path("/tmp/iios_backend_8002_v018.log")
REPORT = Path("/tmp/iios_batch8e_live_smoke.json")


def call(path: str, method: str = "GET", payload=None, timeout: int = 180):
    body = None
    headers = {"Accept": "application/json"}
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


def env() -> dict[str, str]:
    output = os.environ.copy()
    if ENV_FILE.exists():
        for raw in ENV_FILE.read_text().splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            output[key.strip()] = value.strip().strip("'").strip('"')
    output["IIOS_DB_PATH"] = str(BACKEND / "iios_ledger.db")
    return output


def kill_8002() -> None:
    result = subprocess.run(["lsof", "-tiTCP:8002", "-sTCP:LISTEN"], text=True, capture_output=True)
    pids = [int(x) for x in result.stdout.split() if x.isdigit()]
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
    LOG.write_text("")
    log = LOG.open("ab", buffering=0)
    py = str(PYTHON if PYTHON.exists() else Path("python3"))
    proc = subprocess.Popen(
        [py, "-m", "uvicorn", "app:app", "--host", "127.0.0.1", "--port", "8002"],
        cwd=BACKEND,
        env=env(),
        stdout=log,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    deadline = time.time() + 30
    last = None
    while time.time() < deadline:
        last = call("/system/status", timeout=2)
        if last["ok"] and (last["data"] or {}).get("version") == "0.18.0":
            return proc.pid, last["data"]
        time.sleep(0.5)
    raise SystemExit(f"v0.18.0 backend did not become ready. Last={last}; log={LOG}")


def main() -> int:
    print("=" * 72)
    print("IIOS GROUP BATCH 8E - LIVE MULTI-MODEL COUNCIL SMOKE")
    print("=" * 72)
    kill_8002()
    pid, system = start_backend()

    status = call("/intelligence/multi-model-council/status")
    dashboard = call("/monitoring/dashboard")
    council_run = None
    case_id = None
    if dashboard["ok"]:
        for row in (dashboard["data"] or {}).get("cases") or []:
            if row.get("case_id"):
                case_id = str(row["case_id"])
                break
    if case_id:
        council_run = call(
            f"/intelligence/multi-model-council/case/{case_id}/run",
            method="POST",
            payload={"run_grok": False},
        )

    sd = status.get("data") if status["ok"] else {}
    grok = (((sd.get("models") or {}).get("grok") or {}).get("provider") or {})
    kimi = ((sd.get("models") or {}).get("kimi") or {})

    print("\nSYSTEM")
    print("  Version:", system.get("version"))
    print("  Paper mode:", system.get("paper_mode"))
    print("  Multi-model council:", system.get("multi_model_intelligence_council"))
    print("  Grok X search layer:", system.get("grok_x_search_intelligence"))
    print("  Grok web search layer:", system.get("grok_web_search_intelligence"))
    print("  Skeptic divergence escalation:", system.get("model_divergence_skeptic_escalation"))

    print("\nPROVIDERS")
    print("  Grok configured:", grok.get("configured"))
    print("  Grok credential exposed:", grok.get("credential_exposed"))
    print("  Kimi live provider required:", kimi.get("provider_required_for_live"))

    print("\nCOUNCIL")
    print("  Status endpoint:", status.get("status"))
    print("  Universal model weighting:", sd.get("universal_model_weighting"))
    print("  Committee override:", sd.get("committee_override"))
    print("  Risk override:", sd.get("risk_override"))
    if council_run is not None:
        cd = council_run.get("data") if council_run.get("ok") else {}
        print("  Dry council case:", case_id)
        print("  Dry council HTTP:", council_run.get("status"))
        print("  Available models:", ((cd.get("reconciliation") or {}).get("available_model_count")))
        print("  Live execution:", cd.get("live_execution"))
    else:
        print("  Dry council case: none available; route not exercised")

    required = [
        system.get("version") == "0.18.0",
        system.get("paper_mode") is True,
        system.get("multi_model_intelligence_council") is True,
        system.get("grok_x_search_intelligence") is True,
        system.get("grok_web_search_intelligence") is True,
        system.get("model_divergence_skeptic_escalation") is True,
        status["ok"],
        sd.get("universal_model_weighting") is False,
        sd.get("committee_override") is False,
        sd.get("risk_override") is False,
        sd.get("live_execution") is False,
        grok.get("credential_exposed") is False,
    ]
    if council_run is not None:
        required.extend([
            council_run.get("ok") is True,
            (council_run.get("data") or {}).get("live_execution") is False,
            (council_run.get("data") or {}).get("committee_override") is False,
        ])

    software_ok = all(required)
    external_ready = grok.get("configured") is True
    verdict = (
        "PRODUCTION_MODEL_PROVIDERS_READY" if software_ok and external_ready
        else "SOFTWARE_PASS_EXTERNAL_MODELS_PENDING" if software_ok
        else "NEEDS_ATTENTION"
    )

    report = {
        "backend_pid": pid,
        "system": system,
        "council_status": sd,
        "case_id": case_id,
        "dry_council": council_run,
        "software_ready": software_ok,
        "external_models_ready": external_ready,
        "verdict": verdict,
        "live_execution": False,
    }
    REPORT.write_text(json.dumps(report, indent=2, default=str))

    print("\n" + "=" * 72)
    print("BATCH 8E VERDICT:", verdict)
    print("Software ready:", software_ok)
    print("External model providers ready:", external_ready)
    print("Backend PID:", pid)
    print("Backend log:", LOG)
    print("Report:", REPORT)
    print("Live execution authority: FALSE")
    print("=" * 72)
    return 0 if software_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
