#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def now() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    return now().isoformat()


def parse_time(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def expand(value: str) -> Path:
    return Path(os.path.expanduser(value)).resolve()


def read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    temp.replace(path)


def pgrep(fragment: str) -> list[int]:
    result = subprocess.run(["pgrep", "-f", fragment], text=True, capture_output=True, check=False)
    if result.returncode not in (0, 1):
        return []
    pids: list[int] = []
    for raw in (result.stdout or "").splitlines():
        try:
            pid = int(raw.strip())
        except ValueError:
            continue
        if pid != os.getpid():
            pids.append(pid)
    return sorted(set(pids))


def terminate_pids(pids: list[int]) -> None:
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            pass


def age_seconds(value: datetime | None, reference: datetime) -> float | None:
    if value is None:
        return None
    return max(0.0, (reference - value).total_seconds())


def main() -> int:
    parser = argparse.ArgumentParser(description="IIOS Terminal-Bridge supervisor")
    parser.add_argument("--config", required=True)
    args = parser.parse_args()

    config_path = expand(args.config)
    config = read_json(config_path, {})
    if not isinstance(config, dict) or set((config.get("workers") or {}).keys()) != {"9A", "9B"}:
        raise SystemExit("Invalid Terminal-Bridge runtime config")

    runtime_root = expand(str(config.get("runtime_root") or "~/.iios/terminal-bridge"))
    heartbeat_dir = expand(str(config.get("heartbeat_directory") or "~/.iios/heartbeats"))
    log_dir = expand(str(config.get("log_directory") or "~/.iios/logs"))
    state_path = runtime_root / "supervisor_state.json"
    status_path = runtime_root / "latest_status.json"
    supervisor_log = log_dir / "terminal-bridge-supervisor.log"
    state = read_json(state_path, {"workers": {}})
    if not isinstance(state, dict):
        state = {"workers": {}}
    state.setdefault("workers", {})

    reference = now()
    stale_seconds = max(45 * 60, int(config.get("stale_after_minutes") or 45) * 60)
    grace_seconds = max(45 * 60, int(config.get("startup_grace_minutes") or 45) * 60)
    cooldown_seconds = max(10 * 60, int(config.get("restart_cooldown_minutes") or 15) * 60)
    summary: dict[str, Any] = {
        "checked_at": reference.isoformat(),
        "workers": {},
        "9E_touched": False,
        "paper_mode": True,
        "live_execution": False,
    }

    log_dir.mkdir(parents=True, exist_ok=True)
    with supervisor_log.open("a", encoding="utf-8") as log:
        for worker_key in ("9A", "9B"):
            worker = config["workers"][worker_key]
            fragment = str(worker["runner_process_fragment"])
            pids = pgrep(fragment)
            heartbeat_path = heartbeat_dir / f"{worker_key.lower()}.json"
            heartbeat = read_json(heartbeat_path, {})
            if not isinstance(heartbeat, dict):
                heartbeat = {}

            last_completed = parse_time(heartbeat.get("last_completed_at"))
            started_at = parse_time(heartbeat.get("started_at"))
            last_output = parse_time(heartbeat.get("last_output_at"))
            worker_state = state["workers"].setdefault(worker_key, {})
            last_restart = parse_time(worker_state.get("last_restart_at"))

            due = False
            reason = "HEALTHY"
            if not pids:
                due = True
                reason = "PROCESS_MISSING"
            elif last_completed is None:
                anchor = started_at or last_output
                if anchor is None or age_seconds(anchor, reference) is None or age_seconds(anchor, reference) > grace_seconds:
                    due = True
                    reason = "NO_COMPLETION_HEARTBEAT"
                else:
                    reason = "STARTUP_GRACE"
            elif age_seconds(last_completed, reference) > stale_seconds:
                due = True
                reason = "STALE_COMPLETION_HEARTBEAT"

            if due and last_restart is not None and age_seconds(last_restart, reference) < cooldown_seconds:
                due = False
                reason = "RECOVERY_COOLDOWN"

            action = "NONE"
            if due:
                if pids:
                    terminate_pids(pids)
                    action = "SIGTERM_STALE_RUNNER"
                command_path = runtime_root / f"start_{worker_key.lower()}.command"
                result = subprocess.run(
                    ["/usr/bin/open", "-g", "-a", "Terminal", str(command_path)],
                    text=True,
                    capture_output=True,
                    check=False,
                    timeout=20,
                )
                worker_state["last_restart_at"] = reference.isoformat()
                worker_state["last_restart_reason"] = reason
                worker_state["last_open_returncode"] = result.returncode
                action = f"{action}+OPEN_TERMINAL_BRIDGE" if action != "NONE" else "OPEN_TERMINAL_BRIDGE"
                log.write(
                    f"{iso_now()} {worker_key} recovery reason={reason} pids={pids} open_rc={result.returncode}\n"
                )
                log.flush()

            summary["workers"][worker_key] = {
                "pids": pids,
                "heartbeat_status": heartbeat.get("status"),
                "last_completed_at": heartbeat.get("last_completed_at"),
                "last_completed_age_seconds": round(age_seconds(last_completed, reference), 1) if last_completed else None,
                "last_output_at": heartbeat.get("last_output_at"),
                "reason": reason,
                "recovery_due": due,
                "action": action,
                "last_restart_at": worker_state.get("last_restart_at"),
            }

    state["last_checked_at"] = reference.isoformat()
    write_json(state_path, state)
    write_json(status_path, summary)
    print(json.dumps(summary, indent=2, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
