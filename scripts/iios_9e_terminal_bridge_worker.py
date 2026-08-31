#!/usr/bin/env python3
from __future__ import annotations

import argparse
import fcntl
import json
import os
import signal
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def expand(value: str) -> Path:
    return Path(os.path.expanduser(value)).resolve()


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")
    temporary.replace(path)


def pgrep(fragment: str) -> list[int]:
    result = subprocess.run(["pgrep", "-f", fragment], text=True, capture_output=True, check=False)
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


def main() -> int:
    parser = argparse.ArgumentParser(description="IIOS Batch 9E Terminal-Bridge worker")
    parser.add_argument("--config", required=True)
    args = parser.parse_args()

    config_path = expand(args.config)
    config = read_json(config_path)
    launcher = expand(str(config.get("launcher_path") or ""))
    if not launcher.exists():
        raise SystemExit(f"Missing 9E launcher: {launcher}")

    runtime_root = expand(str(config.get("runtime_root") or "~/.iios/radar-bridge"))
    heartbeat_dir = expand(str(config.get("heartbeat_directory") or "~/.iios/radar-heartbeats"))
    log_dir = expand(str(config.get("log_directory") or "~/.iios/logs"))
    for path in (runtime_root, heartbeat_dir, log_dir, runtime_root / "locks"):
        path.mkdir(parents=True, exist_ok=True)

    lock_path = runtime_root / "locks" / "9e.lock"
    lock_handle = lock_path.open("a+", encoding="utf-8")
    try:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print("9E Terminal-Bridge already owns the worker lock; refusing duplicate start.", flush=True)
        return 0

    lock_handle.seek(0)
    lock_handle.truncate()
    lock_handle.write(f"pid={os.getpid()} started_at={utc_now()}\n")
    lock_handle.flush()

    heartbeat_path = heartbeat_dir / "9e.json"
    log_path = log_dir / "9e.bridge.log"
    completion_pattern = str(config.get("radar_completion_pattern") or "[RADAR] COMPLETE")
    runner_fragment = str(config.get("runner_process_fragment") or "scripts/iios_high_speed_factory_runner.py")

    existing = pgrep(runner_fragment)
    if existing:
        write_json(heartbeat_path, {
            "worker": "9E",
            "status": "ALREADY_RUNNING",
            "checked_at": utc_now(),
            "runner_pids": existing,
            "paper_mode": True,
            "broker_connected": False,
            "trade_execution_permission": False,
            "live_execution": False,
        })
        print(f"9E runner already exists: {existing}; refusing duplicate ownership.", flush=True)
        return 0

    heartbeat: dict[str, Any] = {
        "worker": "9E",
        "status": "STARTING",
        "bridge_pid": os.getpid(),
        "started_at": utc_now(),
        "last_output_at": None,
        "last_radar_completed_at": None,
        "last_completion_line": None,
        "launcher_path": str(launcher),
        "paper_mode": True,
        "broker_connected": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }
    write_json(heartbeat_path, heartbeat)

    child: subprocess.Popen[str] | None = None

    def handle_stop(_signum: int, _frame: Any) -> None:
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
        banner = f"{utc_now()} [9E] Terminal-Bridge starting {launcher}\n"
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
            stamp = utc_now()
            print(line, end="", flush=True)
            log.write(line)
            log.flush()
            heartbeat["last_output_at"] = stamp
            heartbeat["status"] = "RUNNING"
            if completion_pattern in line:
                heartbeat["last_radar_completed_at"] = stamp
                heartbeat["last_completion_line"] = line.strip()[-1500:]
            write_json(heartbeat_path, heartbeat)

        rc = child.wait()
        heartbeat["status"] = "EXITED"
        heartbeat["exited_at"] = utc_now()
        heartbeat["exit_code"] = int(rc)
        write_json(heartbeat_path, heartbeat)
        log.write(f"{utc_now()} [9E] Terminal-Bridge child exited rc={rc}\n")
        log.flush()
        return int(rc)


if __name__ == "__main__":
    raise SystemExit(main())
