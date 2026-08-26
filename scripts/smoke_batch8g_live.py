#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
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
LOG = Path("/tmp/iios_backend_8002_v020.log")
REPORT = Path("/tmp/iios_batch8g_live_smoke.json")


def call(path: str, timeout: int = 30) -> dict:
    request = urllib.request.Request(
        BASE + path,
        headers={"Accept": "application/json"},
        method="GET",
    )
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


def runtime_env() -> dict[str, str]:
    env = os.environ.copy()
    if ENV_FILE.exists():
        for raw in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            env[key.strip()] = value.strip().strip("'").strip('"')
    env["IIOS_DB_PATH"] = str(BACKEND / "iios_ledger.db")
    return env


def listening_pids() -> list[int]:
    if shutil.which("lsof") is None:
        return []
    result = subprocess.run(
        ["lsof", "-tiTCP:8002", "-sTCP:LISTEN"],
        text=True,
        capture_output=True,
        check=False,
    )
    return [int(value) for value in result.stdout.split() if value.isdigit()]


def kill_8002() -> None:
    pids = listening_pids()
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    deadline = time.time() + 5
    while time.time() < deadline:
        if not listening_pids():
            return
        time.sleep(0.25)
    for pid in pids:
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def stop_backend(process: subprocess.Popen | None) -> None:
    if process is None or process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=5)
        return
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        return
    process.wait(timeout=5)


def start_backend() -> tuple[subprocess.Popen, dict]:
    LOG.write_text("", encoding="utf-8")
    log = LOG.open("ab", buffering=0)
    python = str(PYTHON if PYTHON.exists() else Path(sys.executable))
    try:
        process = subprocess.Popen(
            [
                python, "-m", "uvicorn", "app:app",
                "--host", "127.0.0.1", "--port", "8002",
                "--lifespan", "off",
            ],
            cwd=BACKEND,
            env=runtime_env(),
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    finally:
        log.close()

    deadline = time.time() + 30
    last = None
    while time.time() < deadline:
        if process.poll() is not None:
            break
        last = call("/system/status", timeout=2)
        if last["ok"] and (last["data"] or {}).get("version") == "0.20.0":
            return process, last["data"]
        time.sleep(0.5)

    exit_code = process.poll()
    stop_backend(process)
    log_text = LOG.read_text(encoding="utf-8", errors="replace")
    raise RuntimeError(
        "v0.20.0 backend did not become ready. "
        f"exit_code={exit_code}; last={last}; log={LOG}\n"
        f"--- backend log ---\n{log_text}"
    )


def false_authority(payload: dict) -> bool:
    return all(
        payload.get(key) is False
        for key in (
            "committee_override",
            "risk_override",
            "capital_authority",
            "auto_trade_authority",
            "trade_execution_permission",
            "live_execution",
        )
    )


def main() -> int:
    print("=" * 72)
    print("IIOS GROUP BATCH 8G - LIVE FACTORY INTELLIGENCE UI SMOKE")
    print("=" * 72)
    process: subprocess.Popen | None = None
    try:
        kill_8002()
        process, system = start_backend()
        status = call("/experience/factory-intelligence/status")
        overview = call("/experience/factory-intelligence/overview")
        sd = status.get("data") if status["ok"] else {}
        od = overview.get("data") if overview["ok"] else {}
        cases = od.get("cases") if isinstance(od.get("cases"), list) else []
        case_result = None
        if cases and isinstance(cases[0], dict) and cases[0].get("case_id"):
            case_result = call(
                "/experience/factory-intelligence/case/"
                + str(cases[0]["case_id"])
            )

        safety = od.get("safety") if isinstance(od.get("safety"), dict) else {}
        council = od.get("council") if isinstance(od.get("council"), dict) else {}
        calibration = (
            od.get("calibration")
            if isinstance(od.get("calibration"), dict)
            else {}
        )
        required = [
            system.get("version") == "0.20.0",
            system.get("paper_mode") is True,
            system.get("factory_intelligence_ui") is True,
            system.get("factory_intelligence_live_overview") is True,
            system.get("factory_model_council_visualization") is True,
            system.get("factory_task_calibration_visualization") is True,
            system.get("factory_ui_unknown_state_semantics") is True,
            system.get("factory_ui_read_only_aggregation") is True,
            system.get("factory_ui_decision_authority") is False,
            system.get("factory_ui_trade_authority") is False,
            status["ok"], overview["ok"],
            sd.get("installed") is True,
            sd.get("read_only_aggregation") is True,
            sd.get("unknown_state_semantics") is True,
            false_authority(sd),
            od.get("system_version") == "0.20.0",
            od.get("data_state") in {"LIVE", "PARTIAL"},
            len(od.get("pipeline") or []) == 4,
            len(council.get("models") or []) == 3,
            calibration.get("universal_model_weighting") is False,
            calibration.get("manual_promotion_required") is True,
            calibration.get("automatically_applied_to_council") is False,
            safety.get("paper_mode") is True,
            safety.get("live_capital_locked") is True,
            false_authority(safety),
            od.get("trade_execution_permission") is False,
            od.get("live_execution") is False,
        ]
        if case_result is not None:
            case_data = case_result.get("data") if case_result.get("ok") else {}
            required.extend([
                case_result.get("ok") is True,
                case_data.get("capital_authority") is False,
                case_data.get("auto_trade_authority") is False,
                case_data.get("trade_execution_permission") is False,
                case_data.get("live_execution") is False,
            ])

        software_ready = all(required)
        verdict = "FACTORY_INTELLIGENCE_UI_READY" if software_ready else "NEEDS_ATTENTION"
        report = {
            "system": system,
            "status": sd,
            "overview": od,
            "case_detail": case_result,
            "software_ready": software_ready,
            "verdict": verdict,
            "read_only": True,
            "live_execution": False,
        }
        REPORT.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

        print("\nSYSTEM")
        print("  Version:", system.get("version"))
        print("  Data state:", od.get("data_state"))
        print("  Cases:", od.get("case_count"))
        print("  Model cards:", len(council.get("models") or []))
        print("  Calibration tasks:", len(calibration.get("tasks") or []))
        print("  Production gates:", len(od.get("production_gates") or []))
        print("\n" + "=" * 72)
        print("BATCH 8G VERDICT:", verdict)
        print("Software ready:", software_ready)
        print("Backend PID:", process.pid)
        print("Backend log:", LOG)
        print("Report:", REPORT)
        print("Scheduler side effects: DISABLED FOR API SMOKE")
        print("Read-only aggregation: TRUE")
        print("Unknown / offline semantics: TRUE")
        print("Committee / Risk override: FALSE")
        print("Capital / trade authority: FALSE")
        print("Live execution authority: FALSE")
        print("=" * 72)
        return 0 if software_ready else 1
    except Exception as exc:
        print(f"Batch 8G smoke error: {type(exc).__name__}: {exc}")
        return 1
    finally:
        stop_backend(process)
        kill_8002()


if __name__ == "__main__":
    raise SystemExit(main())
