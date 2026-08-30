#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "iios_worker_supervision.json"


def load_config() -> dict[str, Any]:
    value = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SystemExit("Invalid worker supervision config")
    workers = value.get("workers")
    if not isinstance(workers, dict) or set(workers) != {"9A", "9B"}:
        raise SystemExit("Diagnostic expects exactly 9A and 9B")
    return value


def expand(value: Any) -> Path:
    return Path(os.path.expanduser(str(value or ""))).resolve()


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(list(args), text=True, capture_output=True, check=False)


def launchctl_summary(label: str) -> dict[str, Any]:
    target = f"gui/{os.getuid()}/{label}"
    result = run("launchctl", "print", target)
    text = (result.stdout or "") + "\n" + (result.stderr or "")
    wanted: dict[str, Any] = {
        "label": label,
        "loaded": result.returncode == 0,
        "returncode": result.returncode,
    }
    for key, pattern in {
        "state": r"^\s*state\s*=\s*(.+)$",
        "pid": r"^\s*pid\s*=\s*(\d+)$",
        "runs": r"^\s*runs\s*=\s*(\d+)$",
        "last_exit_code": r"^\s*last exit code\s*=\s*(.+)$",
        "program": r"^\s*program\s*=\s*(.+)$",
        "working_directory": r"^\s*working directory\s*=\s*(.+)$",
    }.items():
        match = re.search(pattern, text, flags=re.MULTILINE | re.IGNORECASE)
        if match:
            wanted[key] = match.group(1).strip()
    if result.returncode != 0:
        wanted["error_tail"] = text.strip()[-1000:]
    return wanted


def pgrep(fragment: str) -> list[int]:
    result = run("pgrep", "-f", fragment)
    if result.returncode not in (0, 1):
        return []
    values: list[int] = []
    for line in (result.stdout or "").splitlines():
        try:
            pid = int(line.strip())
        except ValueError:
            continue
        if pid != os.getpid():
            values.append(pid)
    return sorted(set(values))


def tail(path: Path, lines: int = 80) -> str:
    if not path.exists():
        return "<missing>"
    try:
        content = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception as exc:
        return f"<read-error {type(exc).__name__}: {exc}>"
    return "\n".join(content[-lines:])


def ledger_probe(path: Path) -> dict[str, Any]:
    output: dict[str, Any] = {
        "path": str(path),
        "exists": path.exists(),
        "readable": False,
        "latest_observation": None,
        "latest_paper_trading": None,
    }
    if not path.exists():
        return output
    try:
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5)
        connection.row_factory = sqlite3.Row
        try:
            for object_type, key in (
                ("observation_operations_state", "latest_observation"),
                ("governed_paper_trading_state", "latest_paper_trading"),
            ):
                row = connection.execute(
                    """
                    SELECT created_at, payload_json
                    FROM ledger_objects
                    WHERE object_type = ?
                    ORDER BY rowid DESC
                    LIMIT 1
                    """,
                    (object_type,),
                ).fetchone()
                if row:
                    payload = json.loads(row["payload_json"])
                    output[key] = {
                        "created_at": row["created_at"],
                        "cycle_completed_at": payload.get("cycle_completed_at"),
                        "last_cycle_completed_at": payload.get("last_cycle_completed_at"),
                    }
            output["readable"] = True
        finally:
            connection.close()
    except Exception as exc:
        output["error"] = f"{type(exc).__name__}: {exc}"
    return output


def detect_signatures(text: str) -> list[str]:
    signatures = {
        "MACOS_PERMISSION_DENIED": ("operation not permitted", "permission denied"),
        "PYTHON_OR_VENV_MISSING": ("no iios backend virtualenv", "no such file or directory"),
        "GIT_STARTUP_FAILURE": ("fatal:", "git fetch", "could not read from remote repository"),
        "PYTHON_TRACEBACK": ("traceback (most recent call last)",),
        "PROCESS_KILLED": ("killed: 9", "signal 9", "sigkill"),
    }
    lowered = text.lower()
    found: list[str] = []
    for name, needles in signatures.items():
        if any(needle in lowered for needle in needles):
            found.append(name)
    return found


def main() -> int:
    if sys.platform != "darwin":
        print("Diagnostic is intended for the IIOS macOS runtime.")
    config = load_config()
    logs = expand(config.get("log_directory") or "~/.iios/logs")
    state = expand(config.get("state_directory") or "~/.iios/worker-supervision")
    ledger = expand(config.get("ledger_path"))

    watchdog_label = str(config.get("watchdog_label") or "com.iios.worker-watchdog")
    services = {
        "9A": launchctl_summary(str(config["workers"]["9A"]["label"])),
        "9B": launchctl_summary(str(config["workers"]["9B"]["label"])),
        "WATCHDOG": launchctl_summary(watchdog_label),
    }

    processes = {
        key: pgrep(str(worker.get("runner_process_fragment") or ""))
        for key, worker in config["workers"].items()
    }

    log_paths = {
        "9A_OUT": logs / "9a.launchd.out.log",
        "9A_ERR": logs / "9a.launchd.err.log",
        "9B_OUT": logs / "9b.launchd.out.log",
        "9B_ERR": logs / "9b.launchd.err.log",
        "WATCHDOG_OUT": logs / "worker-watchdog.launchd.out.log",
        "WATCHDOG_ERR": logs / "worker-watchdog.launchd.err.log",
        "WATCHDOG_AUDIT": state / "watchdog.log",
        "WATCHDOG_STATUS": state / "latest_status.json",
        "WATCHDOG_STATE": state / "state.json",
    }
    tails = {name: tail(path) for name, path in log_paths.items()}
    combined = "\n".join(tails.values())

    report = {
        "diagnostic_version": "iios-worker-supervision-diagnostic-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mutation": "NONE_READ_ONLY",
        "services": services,
        "runner_processes": processes,
        "ledger_probe": ledger_probe(ledger),
        "detected_signatures": detect_signatures(combined),
        "paths": {name: str(path) for name, path in log_paths.items()},
        "log_tails": tails,
        "safety": {
            "managed_workers": ["9A", "9B"],
            "9E_touched": False,
            "trade_execution_permission": False,
            "live_execution": False,
            "broker_connected": False,
        },
    }

    print("=" * 76)
    print("IIOS WORKER SUPERVISION — READ-ONLY DIAGNOSTIC")
    print("=" * 76)
    print("Mutation: NONE")
    print("9E: UNTOUCHED")
    for key in ("9A", "9B", "WATCHDOG"):
        service = services[key]
        print(
            f"{key}: loaded={service.get('loaded')} state={service.get('state')} "
            f"pid={service.get('pid')} runs={service.get('runs')} "
            f"last_exit={service.get('last_exit_code')}"
        )
    print("Runner PIDs:", processes)
    print("Ledger readable:", report["ledger_probe"].get("readable"))
    print("Detected signatures:", report["detected_signatures"] or ["NONE"])
    print("\n--- FULL JSON REPORT ---")
    print(json.dumps(report, indent=2, sort_keys=True, default=str))
    print("=" * 76)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
