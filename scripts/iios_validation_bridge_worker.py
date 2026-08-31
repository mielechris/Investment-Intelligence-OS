#!/usr/bin/env python3
from __future__ import annotations

import argparse
import fcntl
import json
import os
import signal
import subprocess
import time
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
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    temporary.replace(path)


def parse_payload(stdout: str) -> dict[str, Any]:
    text = (stdout or "").strip()
    if not text:
        return {}
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def main() -> int:
    parser = argparse.ArgumentParser(description="IIOS 9H/9I Terminal-Bridge service worker")
    parser.add_argument("--config", required=True)
    parser.add_argument("--service", required=True)
    args = parser.parse_args()

    config_path = expand(args.config)
    config = read_json(config_path)
    services = config.get("services") or {}
    service_key = str(args.service)
    if service_key not in services:
        raise SystemExit(f"Unknown validation bridge service: {service_key}")
    service = services[service_key]

    runtime_root = expand(str(config.get("runtime_root") or "~/.iios/validation-bridge"))
    heartbeat_dir = expand(str(config.get("heartbeat_directory") or "~/.iios/validation-heartbeats"))
    log_dir = expand(str(config.get("log_directory") or "~/.iios/logs"))
    lock_dir = runtime_root / "locks"
    for path in (runtime_root, heartbeat_dir, log_dir, lock_dir):
        path.mkdir(parents=True, exist_ok=True)

    heartbeat_path = heartbeat_dir / f"{service_key.lower()}.json"
    log_path = log_dir / f"{service_key.lower()}.validation-bridge.log"
    lock_path = lock_dir / f"{service_key.lower()}.lock"
    command = [str(item) for item in service.get("command") or []]
    cwd = expand(str(service.get("working_directory") or service.get("worktree") or ""))
    interval = max(60, int(service.get("interval_seconds") or 300))
    run_timeout = max(30, int(service.get("run_timeout_seconds") or interval))
    allowed_statuses = {str(item) for item in service.get("allowed_statuses") or []}
    productive_statuses = {str(item) for item in service.get("productive_statuses") or []}
    if not command:
        raise SystemExit(f"{service_key} runtime command is empty")
    if not cwd.exists():
        raise SystemExit(f"{service_key} working directory missing: {cwd}")

    lock_handle = lock_path.open("a+")
    try:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        heartbeat = read_json(heartbeat_path)
        heartbeat.update(
            {
                "service": service_key,
                "status": "DUPLICATE_BRIDGE_REFUSED",
                "checked_at": utc_now(),
                "paper_mode": True,
                "live_execution": False,
            }
        )
        write_json(heartbeat_path, heartbeat)
        print(f"{service_key} bridge already owns lock {lock_path}", flush=True)
        return 0

    stop_requested = False
    child: subprocess.Popen[str] | None = None

    def handle_stop(_signum, _frame) -> None:
        nonlocal stop_requested, child
        stop_requested = True
        if child and child.poll() is None:
            try:
                child.terminate()
            except ProcessLookupError:
                pass

    signal.signal(signal.SIGINT, handle_stop)
    signal.signal(signal.SIGTERM, handle_stop)

    env = dict(os.environ)
    env["PYTHONUNBUFFERED"] = "1"
    path_env = str(config.get("path_env") or "").strip()
    if path_env:
        env["PATH"] = path_env

    heartbeat: dict[str, Any] = {
        "service": service_key,
        "name": service.get("name"),
        "status": "RUNNING",
        "bridge_pid": os.getpid(),
        "started_at": utc_now(),
        "last_run_started_at": None,
        "last_run_completed_at": None,
        "last_success_at": None,
        "last_productive_at": None,
        "last_status": None,
        "last_exit_code": None,
        "interval_seconds": interval,
        "run_timeout_seconds": run_timeout,
        "paper_mode": True,
        "ledger_mode": (
            "NONE"
            if service_key == "9H_COLLECTOR"
            else "READ_ONLY"
        ),
        "auto_apply_threshold_changes": False,
        "trade_execution_permission": False,
        "broker_connected": False,
        "live_execution": False,
    }
    write_json(heartbeat_path, heartbeat)

    with log_path.open("a", encoding="utf-8") as log:
        log.write(f"{utc_now()} [{service_key}] validation bridge started pid={os.getpid()}\n")
        log.flush()
        while not stop_requested:
            cycle_started_monotonic = time.monotonic()
            heartbeat["status"] = "RUNNING_COMMAND"
            heartbeat["last_run_started_at"] = utc_now()
            write_json(heartbeat_path, heartbeat)

            timed_out = False
            stdout = ""
            try:
                child = subprocess.Popen(
                    command,
                    cwd=str(cwd),
                    env=env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                )
                heartbeat["child_pid"] = child.pid
                write_json(heartbeat_path, heartbeat)
                try:
                    stdout, _ = child.communicate(timeout=run_timeout)
                except subprocess.TimeoutExpired:
                    timed_out = True
                    child.terminate()
                    try:
                        stdout, _ = child.communicate(timeout=10)
                    except subprocess.TimeoutExpired:
                        child.kill()
                        stdout, _ = child.communicate()
                rc = int(child.returncode or 0)
            except Exception as exc:
                rc = 1
                stdout = f"{type(exc).__name__}: {exc}"
            finally:
                child = None

            completed_at = utc_now()
            payload = parse_payload(stdout)
            reported_status = str(payload.get("status") or "").strip() or None
            log.write(
                f"{completed_at} [{service_key}] rc={rc} timeout={timed_out} status={reported_status}\n"
            )
            if stdout:
                log.write(stdout[-12000:] + ("\n" if not stdout.endswith("\n") else ""))
            log.flush()
            if stdout:
                print(stdout, end="" if stdout.endswith("\n") else "\n", flush=True)

            heartbeat["status"] = "IDLE" if rc == 0 and not timed_out else "RUN_ERROR"
            heartbeat["last_run_completed_at"] = completed_at
            heartbeat["last_exit_code"] = rc
            heartbeat["last_timeout"] = timed_out
            heartbeat["last_status"] = reported_status
            heartbeat["last_output_tail"] = stdout[-2000:]
            heartbeat.pop("child_pid", None)
            if rc == 0 and not timed_out:
                heartbeat["last_success_at"] = completed_at
                if reported_status in productive_statuses:
                    heartbeat["last_productive_at"] = completed_at
            if reported_status and allowed_statuses and reported_status not in allowed_statuses:
                heartbeat["status"] = "UNEXPECTED_STATUS"
            write_json(heartbeat_path, heartbeat)

            if stop_requested:
                break
            elapsed = time.monotonic() - cycle_started_monotonic
            sleep_for = max(5.0, float(interval) - elapsed)
            deadline = time.monotonic() + sleep_for
            while not stop_requested and time.monotonic() < deadline:
                time.sleep(min(1.0, max(0.0, deadline - time.monotonic())))

        heartbeat["status"] = "STOPPED"
        heartbeat["stopped_at"] = utc_now()
        write_json(heartbeat_path, heartbeat)
        log.write(f"{utc_now()} [{service_key}] validation bridge stopped\n")
        log.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
