#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[1]
CONFIG_PATH = REPO / "config" / "iios_worker_supervision.json"
SUPERVISION_CASE_ID = "worker_supervision"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    return utc_now().isoformat()


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


def load_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(f"Missing worker supervision config: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SystemExit("Worker supervision config must be a JSON object")
    workers = value.get("workers")
    if not isinstance(workers, dict) or not workers:
        raise SystemExit("Worker supervision config must define workers")
    return value


def expand_path(value: Any) -> Path:
    return Path(os.path.expanduser(str(value or ""))).resolve()


def state_directory(config: dict[str, Any]) -> Path:
    path = expand_path(config.get("state_directory") or "~/.iios/worker-supervision")
    path.mkdir(parents=True, exist_ok=True)
    return path


def state_path(config: dict[str, Any]) -> Path:
    return state_directory(config) / "state.json"


def latest_status_path(config: dict[str, Any]) -> Path:
    return state_directory(config) / "latest_status.json"


def watchdog_log_path(config: dict[str, Any]) -> Path:
    return state_directory(config) / "watchdog.log"


def load_runtime_state(config: dict[str, Any]) -> dict[str, Any]:
    path = state_path(config)
    if not path.exists():
        return {"activated_at": None, "workers": {}}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        value = {}
    if not isinstance(value, dict):
        value = {}
    value.setdefault("activated_at", None)
    value.setdefault("workers", {})
    return value


def save_runtime_state(config: dict[str, Any], value: dict[str, Any]) -> None:
    state_path(config).write_text(
        json.dumps(value, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )


def append_log(config: dict[str, Any], message: str) -> None:
    line = f"{iso_now()} {message}\n"
    with watchdog_log_path(config).open("a", encoding="utf-8") as handle:
        handle.write(line)
    print(message, flush=True)


def read_worker_checkpoint(
    ledger_path: Path,
    *,
    object_type: str,
    case_id: str,
) -> dict[str, Any] | None:
    if not ledger_path.exists():
        raise FileNotFoundError(f"IIOS ledger not found: {ledger_path}")
    uri = f"file:{ledger_path}?mode=ro"
    connection = sqlite3.connect(uri, uri=True, timeout=5)
    connection.row_factory = sqlite3.Row
    try:
        row = connection.execute(
            """
            SELECT payload_json
            FROM ledger_objects
            WHERE object_type = ? AND case_id = ?
            ORDER BY rowid DESC
            LIMIT 1
            """,
            (object_type, case_id),
        ).fetchone()
    finally:
        connection.close()
    if not row:
        return None
    value = json.loads(row["payload_json"])
    return value if isinstance(value, dict) else None


def age_seconds(last_completed: datetime | None, now: datetime) -> float | None:
    if last_completed is None:
        return None
    return max(0.0, (now - last_completed).total_seconds())


def recovery_due(
    *,
    last_completed: datetime | None,
    now: datetime,
    stale_after_seconds: int,
    grace_anchor: datetime | None,
    grace_seconds: int,
    last_action: datetime | None,
    cooldown_seconds: int,
) -> tuple[bool, str]:
    if grace_anchor is not None and (now - grace_anchor).total_seconds() < grace_seconds:
        return False, "STARTUP_GRACE"
    if last_action is not None and (now - last_action).total_seconds() < cooldown_seconds:
        return False, "RECOVERY_COOLDOWN"
    if last_completed is None:
        return True, "NO_COMPLETION_CHECKPOINT"
    if (now - last_completed).total_seconds() > stale_after_seconds:
        return True, "STALE_COMPLETION_CHECKPOINT"
    return False, "ON_CADENCE"


def launchctl_kickstart(label: str) -> subprocess.CompletedProcess[str]:
    target = f"gui/{os.getuid()}/{label}"
    return subprocess.run(
        ["launchctl", "kickstart", "-k", target],
        text=True,
        capture_output=True,
        check=False,
    )


def record_recovery_event(
    config: dict[str, Any],
    event_type: str,
    *,
    worker_key: str,
    payload: dict[str, Any],
) -> None:
    ledger_path = expand_path(config.get("ledger_path"))
    backend = ledger_path.parent
    if str(backend) not in sys.path:
        sys.path.insert(0, str(backend))
    os.environ["IIOS_DB_PATH"] = str(ledger_path)
    try:
        from ledger import record_event

        record_event(
            SUPERVISION_CASE_ID,
            event_type,
            entity_id=str(worker_key),
            payload={
                **payload,
                "worker": worker_key,
                "paper_mode": True,
                "trade_execution_permission": False,
                "live_execution": False,
                "broker_connected": False,
            },
        )
    except Exception as exc:
        # Recovery must not depend on audit logging. The watchdog log remains the
        # fallback audit trail if ledger event persistence is temporarily blocked.
        append_log(
            config,
            f"AUDIT EVENT FAILED {worker_key} {event_type}: {type(exc).__name__}: {exc}",
        )


def run_once(config: dict[str, Any]) -> dict[str, Any]:
    now = utc_now()
    ledger_path = expand_path(config.get("ledger_path"))
    stale_after_seconds = max(45 * 60, int(config.get("stale_after_minutes") or 45) * 60)
    startup_grace_seconds = max(45 * 60, int(config.get("startup_grace_minutes") or 60) * 60)
    cooldown_seconds = max(45 * 60, int(config.get("recovery_cooldown_minutes") or 60) * 60)

    runtime = load_runtime_state(config)
    runtime_workers = runtime.setdefault("workers", {})
    activated_at = parse_time(runtime.get("activated_at"))

    summary: dict[str, Any] = {
        "checked_at": now.isoformat(),
        "ledger_path": str(ledger_path),
        "stale_after_seconds": stale_after_seconds,
        "startup_grace_seconds": startup_grace_seconds,
        "recovery_cooldown_seconds": cooldown_seconds,
        "workers": {},
        "recovery_count": 0,
        "errors": [],
        "paper_mode": True,
        "trade_execution_permission": False,
        "live_execution": False,
        "broker_connected": False,
    }

    for worker_key, worker in (config.get("workers") or {}).items():
        if not isinstance(worker, dict):
            continue
        label = str(worker.get("label") or "").strip()
        object_type = str(worker.get("object_type") or "").strip()
        case_id = str(worker.get("case_id") or "").strip()
        completed_field = str(worker.get("completed_at_field") or "").strip()
        row: dict[str, Any] = {
            "label": label,
            "name": worker.get("name"),
            "object_type": object_type,
            "case_id": case_id,
            "completed_at_field": completed_field,
        }

        try:
            checkpoint = read_worker_checkpoint(
                ledger_path,
                object_type=object_type,
                case_id=case_id,
            )
        except Exception as exc:
            row["status"] = "LEDGER_READ_ERROR"
            row["error"] = f"{type(exc).__name__}: {exc}"
            summary["errors"].append(f"{worker_key}: {row['error']}")
            summary["workers"][worker_key] = row
            continue

        completed_value = checkpoint.get(completed_field) if checkpoint else None
        last_completed = parse_time(completed_value)
        worker_runtime = runtime_workers.setdefault(worker_key, {})
        last_action = parse_time(worker_runtime.get("last_action_at"))
        worker_grace_anchor = parse_time(worker_runtime.get("activated_at")) or activated_at

        due, reason = recovery_due(
            last_completed=last_completed,
            now=now,
            stale_after_seconds=stale_after_seconds,
            grace_anchor=worker_grace_anchor,
            grace_seconds=startup_grace_seconds,
            last_action=last_action,
            cooldown_seconds=cooldown_seconds,
        )

        row.update(
            {
                "last_completed_at": last_completed.isoformat() if last_completed else None,
                "age_seconds": round(age_seconds(last_completed, now) or 0.0, 1)
                if last_completed
                else None,
                "recovery_due": due,
                "reason": reason,
                "last_action_at": last_action.isoformat() if last_action else None,
            }
        )

        if not due:
            row["status"] = reason
            summary["workers"][worker_key] = row
            continue

        event_payload = {
            "label": label,
            "reason": reason,
            "last_completed_at": row.get("last_completed_at"),
            "age_seconds": row.get("age_seconds"),
            "stale_after_seconds": stale_after_seconds,
            "action": "LAUNCHCTL_KICKSTART_K",
        }
        record_recovery_event(
            config,
            "WORKER_AUTO_RECOVERY_REQUESTED",
            worker_key=worker_key,
            payload=event_payload,
        )
        append_log(
            config,
            f"RECOVERY REQUEST {worker_key} label={label} reason={reason} age={row.get('age_seconds')}",
        )

        result = launchctl_kickstart(label)
        worker_runtime["last_action_at"] = now.isoformat()
        worker_runtime["last_action_reason"] = reason
        worker_runtime["last_returncode"] = result.returncode
        worker_runtime["last_stdout"] = (result.stdout or "")[-2000:]
        worker_runtime["last_stderr"] = (result.stderr or "")[-2000:]

        if result.returncode == 0:
            row["status"] = "RECOVERY_KICKSTARTED"
            summary["recovery_count"] += 1
            record_recovery_event(
                config,
                "WORKER_AUTO_RECOVERY_KICKSTARTED",
                worker_key=worker_key,
                payload={**event_payload, "returncode": result.returncode},
            )
            append_log(config, f"RECOVERY STARTED {worker_key} label={label}")
        else:
            row["status"] = "RECOVERY_KICKSTART_FAILED"
            row["returncode"] = result.returncode
            row["stderr"] = (result.stderr or "")[-2000:]
            summary["errors"].append(
                f"{worker_key}: launchctl kickstart failed rc={result.returncode}"
            )
            record_recovery_event(
                config,
                "WORKER_AUTO_RECOVERY_FAILED",
                worker_key=worker_key,
                payload={
                    **event_payload,
                    "returncode": result.returncode,
                    "stderr_tail": (result.stderr or "")[-1000:],
                },
            )
            append_log(
                config,
                f"RECOVERY FAILED {worker_key} rc={result.returncode} stderr={(result.stderr or '').strip()[-500:]}",
            )

        summary["workers"][worker_key] = row

    runtime["last_watchdog_run_at"] = now.isoformat()
    runtime["workers"] = runtime_workers
    save_runtime_state(config, runtime)
    latest_status_path(config).write_text(
        json.dumps(summary, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    return summary


def status_only(config: dict[str, Any]) -> int:
    path = latest_status_path(config)
    if not path.exists():
        print("No IIOS worker watchdog status has been recorded yet.")
        return 1
    print(path.read_text(encoding="utf-8"))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="IIOS 9A/9B stale-heartbeat watchdog"
    )
    parser.add_argument("--status", action="store_true")
    args = parser.parse_args()

    config = load_config()
    if args.status:
        return status_only(config)

    summary = run_once(config)
    print(json.dumps(summary, indent=2, sort_keys=True, default=str), flush=True)
    return 1 if summary.get("errors") else 0


if __name__ == "__main__":
    raise SystemExit(main())
