#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def expand(value: str) -> Path:
    return Path(os.path.expanduser(value)).resolve()


def load_config(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SystemExit("Terminal-Bridge config must be a JSON object")
    return value


def pgrep(fragment: str) -> list[int]:
    result = subprocess.run(
        ["pgrep", "-f", fragment],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode not in (0, 1):
        return []
    output: list[int] = []
    for raw in (result.stdout or "").splitlines():
        try:
            pid = int(raw.strip())
        except ValueError:
            continue
        if pid != os.getpid():
            output.append(pid)
    return sorted(set(output))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    temp.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(description="IIOS Terminal-Bridge worker wrapper")
    parser.add_argument("--config", required=True)
    parser.add_argument("--worker", required=True, choices=("9A", "9B"))
    args = parser.parse_args()

    config_path = expand(args.config)
    config = load_config(config_path)
    worker_key = args.worker
    worker = config["workers"][worker_key]

    launcher = expand(str(worker["launcher_path"]))
    if not launcher.exists():
        raise SystemExit(f"Missing {worker_key} launcher: {launcher}")

    log_dir = expand(str(config.get("log_directory") or "~/.iios/logs"))
    heartbeat_dir = expand(str(config.get("heartbeat_directory") or "~/.iios/heartbeats"))
    log_dir.mkdir(parents=True, exist_ok=True)
    heartbeat_dir.mkdir(parents=True, exist_ok=True)

    log_path = log_dir / str(worker.get("bridge_log_name") or f"{worker_key.lower()}.bridge.log")
    heartbeat_path = heartbeat_dir / f"{worker_key.lower()}.json"
    runner_fragment = str(worker["runner_process_fragment"])
    completion_pattern = str(worker["completion_pattern"])

    existing = pgrep(runner_fragment)
    if existing:
        write_json(
            heartbeat_path,
            {
                "worker": worker_key,
                "status": "ALREADY_RUNNING",
                "checked_at": utc_now(),
                "runner_pids": existing,
                "paper_mode": True,
                "live_execution": False,
            },
        )
        print(f"{worker_key} already running: {existing}", flush=True)
        return 0

    heartbeat: dict[str, Any] = {
        "worker": worker_key,
        "status": "STARTING",
        "bridge_pid": os.getpid(),
        "started_at": utc_now(),
        "last_output_at": None,
        "last_completed_at": None,
        "launcher_path": str(launcher),
        "paper_mode": True,
        "broker_connected": False,
        "live_execution": False,
        "trade_execution_permission": False,
    }
    write_json(heartbeat_path, heartbeat)

    child: subprocess.Popen[str] | None = None

    def handle_stop(_signum, _frame) -> None:
        nonlocal child
        if child and child.poll() is None:
            try:
                child.terminate()
            except ProcessLookupError:
                pass

    signal.signal(signal.SIGINT, handle_stop)
    signal.signal(signal.SIGTERM, handle_stop)

    env = dict(os.environ)
    env["PYTHONUNBUFFERED"] = "1"

    with log_path.open("a", encoding="utf-8") as log:
        banner = f"{utc_now()} [{worker_key}] Terminal-Bridge starting {launcher}\n"
        log.write(banner)
        log.flush()
        print(banner, end="", flush=True)

        child = subprocess.Popen(
            ["/usr/bin/python3", str(launcher)],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=env,
        )
        heartbeat["launcher_pid"] = child.pid
        heartbeat["status"] = "RUNNING"
        write_json(heartbeat_path, heartbeat)

        assert child.stdout is not None
        for line in child.stdout:
            now = utc_now()
            print(line, end="", flush=True)
            log.write(line)
            log.flush()
            heartbeat["last_output_at"] = now
            heartbeat["status"] = "RUNNING"
            if completion_pattern in line:
                heartbeat["last_completed_at"] = now
                heartbeat["last_completion_line"] = line.strip()[-1000:]
            write_json(heartbeat_path, heartbeat)

        rc = child.wait()
        heartbeat["status"] = "EXITED"
        heartbeat["exited_at"] = utc_now()
        heartbeat["exit_code"] = int(rc)
        write_json(heartbeat_path, heartbeat)
        log.write(f"{utc_now()} [{worker_key}] Terminal-Bridge child exited rc={rc}\n")
        log.flush()
        return int(rc)


if __name__ == "__main__":
    raise SystemExit(main())
