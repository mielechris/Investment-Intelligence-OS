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


def age_seconds(value: datetime | None, reference: datetime) -> float | None:
    if value is None:
        return None
    return max(0.0, (reference - value).total_seconds())


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


def terminate(pids: list[int]) -> None:
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            pass


def main() -> int:
    parser = argparse.ArgumentParser(description="IIOS Batch 9E Terminal-Bridge supervisor")
    parser.add_argument("--config", required=True)
    args = parser.parse_args()

    config_path = expand(args.config)
    config = read_json(config_path)
    runtime_root = expand(str(config.get("runtime_root") or "~/.iios/radar-bridge"))
    heartbeat_dir = expand(str(config.get("heartbeat_directory") or "~/.iios/radar-heartbeats"))
    log_dir = expand(str(config.get("log_directory") or "~/.iios/logs"))
    runtime_root.mkdir(parents=True, exist_ok=True)
    heartbeat_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)

    reference = now()
    stale_after = max(600, int(config.get("radar_stale_after_seconds") or 900))
    cooldown = max(300, int(config.get("radar_restart_cooldown_seconds") or 600))
    fragment = str(config.get("runner_process_fragment") or "scripts/iios_high_speed_factory_runner.py")
    pids = pgrep(fragment)
    heartbeat = read_json(heartbeat_dir / "9e.json")
    last_completed = parse_time(heartbeat.get("last_radar_completed_at"))

    state_path = runtime_root / "supervisor_state.json"
    status_path = runtime_root / "latest_status.json"
    state = read_json(state_path)
    last_restart = parse_time(state.get("last_restart_at"))

    due = False
    reason = "HEALTHY"
    if not pids:
        due = True
        reason = "PROCESS_MISSING"
    elif last_completed is None:
        started = parse_time(heartbeat.get("started_at") or heartbeat.get("last_output_at"))
        if started is None or (age_seconds(started, reference) or 0) > stale_after:
            due = True
            reason = "NO_RADAR_COMPLETION_HEARTBEAT"
        else:
            reason = "STARTUP_GRACE"
    elif (age_seconds(last_completed, reference) or 0) > stale_after:
        due = True
        reason = "STALE_RADAR_COMPLETION"

    if due and last_restart is not None and (age_seconds(last_restart, reference) or 0) < cooldown:
        due = False
        reason = "RECOVERY_COOLDOWN"

    action = "NONE"
    open_returncode: int | None = None
    if due:
        if pids:
            terminate(pids)
            action = "SIGTERM_STALE_9E"
        command_path = runtime_root / "start_9e.command"
        result = subprocess.run(
            ["/usr/bin/open", "-g", "-a", "Terminal", str(command_path)],
            text=True,
            capture_output=True,
            check=False,
            timeout=20,
        )
        open_returncode = result.returncode
        state["last_restart_at"] = reference.isoformat()
        state["last_restart_reason"] = reason
        state["last_open_returncode"] = result.returncode
        action = f"{action}+OPEN_TERMINAL_BRIDGE" if action != "NONE" else "OPEN_TERMINAL_BRIDGE"

    state["last_checked_at"] = reference.isoformat()
    write_json(state_path, state)
    summary = {
        "checked_at": reference.isoformat(),
        "worker": "9E",
        "pids": pids,
        "heartbeat_status": heartbeat.get("status"),
        "last_radar_completed_at": heartbeat.get("last_radar_completed_at"),
        "last_radar_age_seconds": round(age_seconds(last_completed, reference), 1) if last_completed else None,
        "reason": reason,
        "recovery_due": due,
        "action": action,
        "open_returncode": open_returncode,
        "last_restart_at": state.get("last_restart_at"),
        "9A_touched": False,
        "9B_touched": False,
        "9H_touched": False,
        "9I_touched": False,
        "backend_8002_changed": False,
        "paper_mode": True,
        "broker_connected": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }
    write_json(status_path, summary)
    print(json.dumps(summary, indent=2, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
