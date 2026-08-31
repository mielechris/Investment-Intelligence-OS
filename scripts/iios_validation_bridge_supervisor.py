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


def pgrep(pattern: str) -> list[int]:
    result = subprocess.run(
        ["pgrep", "-f", pattern],
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


def terminate(pids: list[int]) -> None:
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
    parser = argparse.ArgumentParser(description="IIOS 9H/9I validation Terminal-Bridge supervisor")
    parser.add_argument("--config", required=True)
    args = parser.parse_args()

    config_path = expand(args.config)
    config = read_json(config_path)
    services = config.get("services") or {}
    required = {"9H_COLLECTOR", "9H_VALIDATOR", "9I_SHADOW"}
    if set(services) != required:
        raise SystemExit("Validation bridge runtime config must define exactly 9H_COLLECTOR, 9H_VALIDATOR, and 9I_SHADOW")

    runtime_root = expand(str(config.get("runtime_root") or "~/.iios/validation-bridge"))
    heartbeat_dir = expand(str(config.get("heartbeat_directory") or "~/.iios/validation-heartbeats"))
    log_dir = expand(str(config.get("log_directory") or "~/.iios/logs"))
    state_path = runtime_root / "supervisor_state.json"
    status_path = runtime_root / "latest_status.json"
    supervisor_log = log_dir / "validation-bridge-supervisor.log"
    runtime_root.mkdir(parents=True, exist_ok=True)
    heartbeat_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)

    state = read_json(state_path)
    state.setdefault("services", {})
    reference = now()
    cooldown_seconds = max(300, int(config.get("restart_cooldown_seconds") or 600))
    summary: dict[str, Any] = {
        "checked_at": reference.isoformat(),
        "services": {},
        "9A_touched": False,
        "9B_touched": False,
        "9E_touched": False,
        "9G_touched": False,
        "9J_touched": False,
        "paper_mode": True,
        "auto_apply_threshold_changes": False,
        "trade_execution_permission": False,
        "broker_connected": False,
        "live_execution": False,
    }

    worker_path = runtime_root / "bin" / "iios_validation_bridge_worker.py"
    with supervisor_log.open("a", encoding="utf-8") as log:
        for service_key in ("9H_COLLECTOR", "9H_VALIDATOR", "9I_SHADOW"):
            service = services[service_key]
            heartbeat_path = heartbeat_dir / f"{service_key.lower()}.json"
            heartbeat = read_json(heartbeat_path)
            pattern = rf"{worker_path.name}.*--service {service_key}"
            pids = pgrep(pattern)
            last_completed = parse_time(heartbeat.get("last_run_completed_at"))
            last_started = parse_time(heartbeat.get("last_run_started_at"))
            last_success = parse_time(heartbeat.get("last_success_at"))
            stale_after = max(
                int(service.get("interval_seconds") or 300) * 2,
                int(service.get("stale_after_seconds") or 1200),
            )
            service_state = state["services"].setdefault(service_key, {})
            last_restart = parse_time(service_state.get("last_restart_at"))

            anchor_candidates = [value for value in (last_completed, last_started) if value]
            anchor = max(anchor_candidates) if anchor_candidates else None
            due = False
            reason = "HEALTHY"
            if not pids:
                due = True
                reason = "PROCESS_MISSING"
            elif anchor is None:
                due = True
                reason = "NO_HEARTBEAT"
            elif age_seconds(anchor, reference) is not None and age_seconds(anchor, reference) > stale_after:
                due = True
                reason = "STALE_HEARTBEAT"

            if due and last_restart is not None and age_seconds(last_restart, reference) < cooldown_seconds:
                due = False
                reason = "RECOVERY_COOLDOWN"

            action = "NONE"
            open_returncode: int | None = None
            if due:
                child_pid = heartbeat.get("child_pid")
                terminate(pids + ([int(child_pid)] if isinstance(child_pid, int) else []))
                command_path = runtime_root / f"start_{service_key.lower()}.command"
                result = subprocess.run(
                    ["/usr/bin/open", "-g", "-a", "Terminal", str(command_path)],
                    text=True,
                    capture_output=True,
                    check=False,
                    timeout=20,
                )
                open_returncode = result.returncode
                service_state["last_restart_at"] = reference.isoformat()
                service_state["last_restart_reason"] = reason
                service_state["last_open_returncode"] = result.returncode
                action = "OPEN_TERMINAL_BRIDGE"
                log.write(
                    f"{iso_now()} {service_key} recovery reason={reason} pids={pids} open_rc={result.returncode}\n"
                )
                log.flush()

            summary["services"][service_key] = {
                "pids": pids,
                "heartbeat_status": heartbeat.get("status"),
                "last_status": heartbeat.get("last_status"),
                "last_run_started_at": heartbeat.get("last_run_started_at"),
                "last_run_completed_at": heartbeat.get("last_run_completed_at"),
                "last_success_at": heartbeat.get("last_success_at"),
                "last_productive_at": heartbeat.get("last_productive_at"),
                "last_success_age_seconds": round(age_seconds(last_success, reference), 1) if last_success else None,
                "reason": reason,
                "recovery_due": due,
                "action": action,
                "open_returncode": open_returncode,
                "last_restart_at": service_state.get("last_restart_at"),
            }

    state["last_checked_at"] = reference.isoformat()
    write_json(state_path, state)
    write_json(status_path, summary)
    print(json.dumps(summary, indent=2, sort_keys=True, default=str), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
