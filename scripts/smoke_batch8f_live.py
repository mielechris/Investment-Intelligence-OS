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
SIBLING = (
    REPO.parent
    / "Investment-Intelligence-OS"
    / "BACK END"
    / "backend"
)
PYTHON = SIBLING / ".venv" / "bin" / "python"
ENV_FILE = SIBLING / ".env"
BASE = "http://127.0.0.1:8002"
LOG = Path("/tmp/iios_backend_8002_v019.log")
REPORT = Path(
    "/tmp/iios_batch8f_live_smoke.json"
)


def call(
    path: str,
    method: str = "GET",
    payload=None,
    timeout: int = 180,
):
    body = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(
        BASE + path,
        data=body,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(
            request,
            timeout=timeout,
        ) as response:
            raw = response.read().decode("utf-8")
            return {
                "ok": True,
                "status": response.status,
                "data": (
                    json.loads(raw)
                    if raw
                    else {}
                ),
            }
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8")
        try:
            data = json.loads(raw)
        except Exception:
            data = raw
        return {
            "ok": False,
            "status": exc.code,
            "data": data,
        }
    except Exception as exc:
        return {
            "ok": False,
            "status": None,
            "data": (
                f"{type(exc).__name__}: {exc}"
            ),
        }


def env() -> dict[str, str]:
    output = os.environ.copy()
    if ENV_FILE.exists():
        for raw in ENV_FILE.read_text().splitlines():
            line = raw.strip()
            if (
                not line
                or line.startswith("#")
                or "=" not in line
            ):
                continue
            key, value = line.split("=", 1)
            output[key.strip()] = (
                value.strip()
                .strip("'")
                .strip('"')
            )
    output["IIOS_DB_PATH"] = str(
        BACKEND / "iios_ledger.db"
    )
    return output


def kill_8002() -> None:
    result = subprocess.run(
        [
            "lsof",
            "-tiTCP:8002",
            "-sTCP:LISTEN",
        ],
        text=True,
        capture_output=True,
    )
    pids = [
        int(value)
        for value in result.stdout.split()
        if value.isdigit()
    ]
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    deadline = time.time() + 5
    while time.time() < deadline:
        check = subprocess.run(
            [
                "lsof",
                "-tiTCP:8002",
                "-sTCP:LISTEN",
            ],
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
    LOG.write_text("")
    log = LOG.open("ab", buffering=0)
    py = str(
        PYTHON
        if PYTHON.exists()
        else Path("python3")
    )
    proc = subprocess.Popen(
        [
            py,
            "-m",
            "uvicorn",
            "app:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8002",
        ],
        cwd=BACKEND,
        env=env(),
        stdout=log,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    deadline = time.time() + 30
    last = None
    while time.time() < deadline:
        last = call(
            "/system/status",
            timeout=2,
        )
        if (
            last["ok"]
            and (
                last["data"] or {}
            ).get("version")
            == "0.19.0"
        ):
            return proc.pid, last["data"]
        time.sleep(0.5)
    raise SystemExit(
        "v0.19.0 backend did not become ready. "
        f"Last={last}; log={LOG}"
    )


def metric_row(
    model: str,
    task_type: str,
    benchmark_id: str,
    score: float,
):
    return {
        "model": model,
        "task_type": task_type,
        "benchmark_id": benchmark_id,
        "human_or_governed_benchmark_attested":
            True,
        "benchmark_source":
            "BATCH_8F_LIVE_SOFTWARE_SMOKE",
        "metrics": {
            "factual_accuracy": score,
            "citation_quality": score,
            "completeness": score,
            "dissent_detection": score,
            "committee_usefulness": score,
        },
        "latency_ms": (
            900
            if model == "IIOS_OPENAI_CORE"
            else 1200
        ),
        "cost_usd": (
            0.04
            if model == "IIOS_OPENAI_CORE"
            else 0.06
        ),
    }


def main() -> int:
    print("=" * 72)
    print(
        "IIOS GROUP BATCH 8F - "
        "LIVE SCALE VALIDATION SMOKE"
    )
    print("=" * 72)

    kill_8002()
    pid, system = start_backend()

    status = call(
        "/intelligence/model-calibration/status"
    )

    evaluations = []
    for index in range(5):
        benchmark = f"smoke_benchmark_{index}"
        evaluations.extend(
            [
                metric_row(
                    "IIOS_OPENAI_CORE",
                    "POLICY_MACRO",
                    benchmark,
                    0.93,
                ),
                metric_row(
                    "KIMI_RESEARCH",
                    "POLICY_MACRO",
                    benchmark,
                    0.78,
                ),
            ]
        )

    calibration_run = call(
        "/intelligence/model-calibration/run",
        method="POST",
        payload={
            "evaluations": evaluations,
            "persist": False,
        },
    )

    sd = (
        status.get("data")
        if status["ok"]
        else {}
    )
    rd = (
        calibration_run.get("data")
        if calibration_run["ok"]
        else {}
    )
    task = (
        (rd.get("tasks") or {})
        .get("POLICY_MACRO")
        or {}
    )
    recommendations = (
        task.get("model_recommendations")
        or {}
    )
    iios_weight = (
        recommendations
        .get("IIOS_OPENAI_CORE", {})
        .get("recommended_task_weight")
    )
    kimi_weight = (
        recommendations
        .get("KIMI_RESEARCH", {})
        .get("recommended_task_weight")
    )

    print("\nSYSTEM")
    print("  Version:", system.get("version"))
    print("  Paper mode:", system.get("paper_mode"))
    print(
        "  Scale validation:",
        system.get(
            "multi_model_scale_validation"
        ),
    )
    print(
        "  Task calibration:",
        system.get(
            "task_specific_model_calibration"
        ),
    )

    print("\nCALIBRATION")
    print(
        "  Status endpoint:",
        status.get("status"),
    )
    print(
        "  Weighting mode:",
        sd.get("model_weighting_mode"),
    )
    print(
        "  Minimum samples:",
        sd.get(
            "minimum_samples_per_model_task"
        ),
    )
    print(
        "  Dry run HTTP:",
        calibration_run.get("status"),
    )
    print(
        "  Task status:",
        task.get("status"),
    )
    print(
        "  IIOS policy weight:",
        iios_weight,
    )
    print(
        "  Kimi policy weight:",
        kimi_weight,
    )
    print(
        "  Persisted:",
        rd.get("persisted"),
    )

    required = [
        system.get("version") == "0.19.0",
        system.get("paper_mode") is True,
        system.get(
            "multi_model_scale_validation"
        )
        is True,
        system.get(
            "task_specific_model_calibration"
        )
        is True,
        system.get(
            "model_calibration_manual_promotion_only"
        )
        is True,
        system.get(
            "universal_model_weighting"
        )
        is False,
        status["ok"],
        sd.get(
            "universal_model_weighting"
        )
        is False,
        sd.get(
            "manual_promotion_required"
        )
        is True,
        sd.get(
            "automatically_applied_to_council"
        )
        is False,
        sd.get("committee_override") is False,
        sd.get("risk_override") is False,
        sd.get(
            "trade_execution_permission"
        )
        is False,
        sd.get("live_execution") is False,
        calibration_run["ok"],
        rd.get("persisted") is False,
        task.get("status")
        == "READY_FOR_MANUAL_REVIEW",
        isinstance(iios_weight, (int, float)),
        isinstance(kimi_weight, (int, float)),
        (
            isinstance(iios_weight, (int, float))
            and isinstance(
                kimi_weight,
                (int, float),
            )
            and iios_weight > kimi_weight
        ),
        rd.get(
            "universal_model_weighting"
        )
        is False,
        rd.get(
            "automatically_applied_to_council"
        )
        is False,
        rd.get("committee_override") is False,
        rd.get("risk_override") is False,
        rd.get(
            "trade_execution_permission"
        )
        is False,
        rd.get("live_execution") is False,
    ]

    software_ok = all(required)
    verdict = (
        "SCALE_VALIDATION_READY"
        if software_ok
        else "NEEDS_ATTENTION"
    )

    report = {
        "backend_pid": pid,
        "system": system,
        "calibration_status": sd,
        "dry_calibration": rd,
        "software_ready": software_ok,
        "verdict": verdict,
        "universal_model_weighting": False,
        "automatically_applied_to_council":
            False,
        "live_execution": False,
    }
    REPORT.write_text(
        json.dumps(
            report,
            indent=2,
            default=str,
        )
    )

    print("\n" + "=" * 72)
    print("BATCH 8F VERDICT:", verdict)
    print("Software ready:", software_ok)
    print("Backend PID:", pid)
    print("Backend log:", LOG)
    print("Report:", REPORT)
    print("Universal model weighting: FALSE")
    print("Automatic council promotion: FALSE")
    print("Committee / Risk override: FALSE")
    print("Capital / trade authority: FALSE")
    print("Live execution authority: FALSE")
    print("=" * 72)
    return 0 if software_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
