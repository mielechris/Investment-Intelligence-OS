#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LIVE = Path(
    os.getenv(
        "IIOS_LIVE_CHECKOUT",
        "/Users/crm/Documents/GitHub/Investment-Intelligence-OS-Batch8",
    )
).expanduser()
DEFAULT_LEDGER = Path(
    os.getenv(
        "IIOS_DB_PATH",
        str(DEFAULT_LIVE / "BACK END" / "backend" / "iios_ledger.db"),
    )
).expanduser()
DEFAULT_STATE_DIR = (
    Path.home() / "Library" / "Application Support" / "IIOS" / "market-validation"
)
LAUNCH_DIR = Path.home() / "Library" / "LaunchAgents"
NEW_YORK = ZoneInfo("America/New_York")

ACTIVATORS = {
    "9H": ROOT / "scripts" / "activate_batch9h_autonomous_market_validation.py",
    "9I": ROOT / "scripts" / "activate_batch9i_shadow_counterfactual.py",
    "9J": ROOT / "scripts" / "activate_batch9j_outcome_labeling_memory.py",
}
WORKER_PLISTS = {
    "9H_BENCHMARK": LAUNCH_DIR / "com.iios.market-benchmark.plist",
    "9H_VALIDATION": LAUNCH_DIR / "com.iios.market-validation.plist",
    "9I_SHADOW": LAUNCH_DIR / "com.iios.shadow-counterfactual.plist",
    "9J_OUTCOME": LAUNCH_DIR / "com.iios.outcome-learning.plist",
}


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists() or not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _parse_time(value: Any) -> datetime | None:
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


def _age_seconds(payload: dict[str, Any] | None, path: Path) -> int | None:
    if payload is None:
        return None
    observed = _parse_time(payload.get("generated_at"))
    if observed is None:
        try:
            observed = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        except OSError:
            return None
    return max(0, int((datetime.now(timezone.utc) - observed).total_seconds()))


def _complete_report_dirs(state_dir: Path) -> list[Path]:
    reports_root = state_dir / "reports"
    if not reports_root.exists():
        return []
    output: list[Path] = []
    for directory in reports_root.iterdir():
        if not directory.is_dir():
            continue
        benchmark = _read_json(directory / "benchmark.json")
        scorecard = _read_json(directory / "scorecard.json")
        if not benchmark or not scorecard:
            continue
        if benchmark.get("benchmark_complete") is not True:
            continue
        output.append(directory)
    output.sort(key=lambda path: path.name)
    return output


def _market_context(now: datetime | None = None) -> str:
    now = (now or datetime.now(NEW_YORK)).astimezone(NEW_YORK)
    if now.weekday() >= 5:
        return "NON_MARKET_DAY"
    close_minutes = 16 * 60 + 5
    minutes = now.hour * 60 + now.minute
    if minutes < 9 * 60 + 30:
        return "PRE_MARKET"
    if minutes < close_minutes:
        return "MARKET_OR_VALIDATION_WINDOW_PENDING"
    return "AFTER_VALIDATION_WINDOW"


def _worker_state() -> dict[str, dict[str, Any]]:
    return {
        key: {
            "plist": str(path),
            "installed": path.exists(),
        }
        for key, path in WORKER_PLISTS.items()
    }


def _chain_state(
    *,
    complete_session_count: int,
    shadow: dict[str, Any] | None,
    outcome: dict[str, Any] | None,
) -> str:
    if complete_session_count <= 0:
        return "ARMED_WAITING_FOR_COMPLETE_9H_SESSION"
    if not shadow:
        return "READY_FOR_9I_SHADOW_REFRESH"
    shadow_sessions = int(shadow.get("complete_session_count") or 0)
    if shadow_sessions <= 0:
        return "READY_FOR_9I_SHADOW_REFRESH"
    if not outcome:
        return "READY_FOR_9J_OUTCOME_REFRESH"
    shadow_status = str(shadow.get("status") or "").upper()
    if shadow_status == "ADVISORY_READY":
        return "ACTIVE_ADVISORY_READY"
    return "ACTIVE_LEARNING_WARMUP"


def build_status_snapshot(
    *,
    state_dir: Path = DEFAULT_STATE_DIR,
    now: datetime | None = None,
) -> dict[str, Any]:
    latest_9h_path = state_dir / "latest_market_validation.json"
    latest_9i_path = state_dir / "shadow_strategy" / "latest_shadow_counterfactual.json"
    latest_9j_path = state_dir / "latest_outcome_learning.json"
    latest_9h = _read_json(latest_9h_path)
    latest_9i = _read_json(latest_9i_path)
    latest_9j = _read_json(latest_9j_path)
    complete_dirs = _complete_report_dirs(state_dir)
    complete_ids = [path.name for path in complete_dirs]
    latest_complete = complete_ids[-1] if complete_ids else None

    market_context = _market_context(now)
    age_9h = _age_seconds(latest_9h, latest_9h_path)
    age_9i = _age_seconds(latest_9i, latest_9i_path)
    age_9j = _age_seconds(latest_9j, latest_9j_path)

    if market_context in {"NON_MARKET_DAY", "PRE_MARKET"} and latest_9h:
        validation_age_interpretation = "EXPECTED_OFF_HOURS_AGE"
    else:
        validation_age_interpretation = "SESSION_FRESHNESS_APPLIES"

    shadow_complete = int((latest_9i or {}).get("complete_session_count") or 0)
    outcome_complete = int((latest_9j or {}).get("complete_session_count") or 0)
    outcome_count = int((latest_9j or {}).get("outcome_count") or 0)

    return {
        "schema_version": "batch9h-9j-learning-activation-superbatch-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "market_context": market_context,
        "chain_state": _chain_state(
            complete_session_count=len(complete_dirs),
            shadow=latest_9i,
            outcome=latest_9j,
        ),
        "workers": _worker_state(),
        "9H": {
            "latest_snapshot_present": latest_9h is not None,
            "age_seconds": age_9h,
            "age_interpretation": validation_age_interpretation,
            "complete_session_count": len(complete_dirs),
            "complete_session_ids": complete_ids[-20:],
            "latest_complete_session_id": latest_complete,
            "benchmark_complete": (latest_9h or {}).get("benchmark_complete"),
            "status": (latest_9h or {}).get("status"),
        },
        "9I": {
            "latest_snapshot_present": latest_9i is not None,
            "age_seconds": age_9i,
            "status": (latest_9i or {}).get("status"),
            "complete_session_count": shadow_complete,
            "minimum_complete_sessions_for_advice": int(
                (latest_9i or {}).get("minimum_complete_sessions_for_advice") or 5
            ),
            "recommendation_count": len((latest_9i or {}).get("recommendations") or []),
        },
        "9J": {
            "latest_snapshot_present": latest_9j is not None,
            "age_seconds": age_9j,
            "status": (latest_9j or {}).get("status"),
            "complete_session_count": outcome_complete,
            "outcome_count": outcome_count,
            "mature_5d_count": int((latest_9j or {}).get("mature_5d_count") or 0),
            "pending_5d_count": int((latest_9j or {}).get("pending_5d_count") or 0),
        },
        "safety": {
            "ledger_mode": "READ_ONLY",
            "shadow_only": True,
            "auto_apply_threshold_changes": False,
            "automatic_judgment_bank_writes": False,
            "automatic_agent_weight_changes": False,
            "committee_gate_change_authority": False,
            "risk_gate_change_authority": False,
            "capital_authority": False,
            "broker_connected": False,
            "trade_execution_permission": False,
            "live_execution": False,
        },
    }


def _run_command(args: list[str], *, cwd: Path = ROOT) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=str(cwd),
        text=True,
        capture_output=True,
        check=False,
    )


def _run_activator(code: str) -> dict[str, Any]:
    path = ACTIVATORS[code]
    result = _run_command([sys.executable, str(path)])
    if result.returncode != 0:
        raise RuntimeError(
            f"{code} activation failed ({result.returncode}): "
            f"{(result.stderr or result.stdout).strip()[-3000:]}"
        )
    return {
        "code": code,
        "status": "ACTIVATOR_COMPLETED",
        "stdout_tail": result.stdout.strip()[-2400:],
    }


def _resolve_backend_python(live: Path) -> Path:
    candidates = [
        live / "BACK END" / "backend" / ".venv" / "bin" / "python",
        Path(
            "/Users/crm/Documents/GitHub/Investment-Intelligence-OS/"
            "BACK END/backend/.venv/bin/python"
        ),
    ]
    for candidate in candidates:
        if candidate.exists() and os.access(candidate, os.X_OK):
            return candidate
    raise RuntimeError("No IIOS backend virtualenv Python found")


def _parse_last_json(text: str) -> dict[str, Any]:
    text = text.strip()
    if not text:
        return {}
    decoder = json.JSONDecoder()
    for index, char in enumerate(text):
        if char != "{":
            continue
        try:
            value, end = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict) and not text[index + end :].strip():
            return value
    try:
        value = json.loads(text.splitlines()[-1])
    except (json.JSONDecodeError, IndexError):
        return {}
    return value if isinstance(value, dict) else {}


def _run_shadow_refresh(
    *,
    python: Path,
    ledger: Path,
    state_dir: Path,
) -> dict[str, Any]:
    result = _run_command(
        [
            str(python),
            str(ROOT / "scripts" / "iios_shadow_counterfactual_lab.py"),
            "--db",
            str(ledger),
            "--state-dir",
            str(state_dir),
            "--force",
        ]
    )
    if result.returncode != 0:
        raise RuntimeError(
            "9I governed off-hours refresh failed: "
            + (result.stderr or result.stdout).strip()[-3000:]
        )
    payload = _parse_last_json(result.stdout)
    if payload.get("live_execution") is True:
        raise RuntimeError("9I refresh violated live-execution safety invariant")
    return payload


def _run_outcome_refresh(
    *,
    python: Path,
    ledger: Path,
    state_dir: Path,
) -> dict[str, Any]:
    result = _run_command(
        [
            str(python),
            str(ROOT / "scripts" / "iios_outcome_learning_memory.py"),
            "--db",
            str(ledger),
            "--state-dir",
            str(state_dir),
        ]
    )
    if result.returncode != 0:
        raise RuntimeError(
            "9J governed outcome refresh failed: "
            + (result.stderr or result.stdout).strip()[-3000:]
        )
    payload = _parse_last_json(result.stdout)
    if payload.get("live_execution") is True:
        raise RuntimeError("9J refresh violated live-execution safety invariant")
    if payload.get("ledger_mode") not in {None, "READ_ONLY"}:
        raise RuntimeError("9J refresh did not preserve read-only ledger mode")
    return payload


def activate_learning_chain(
    *,
    live: Path = DEFAULT_LIVE,
    ledger: Path = DEFAULT_LEDGER,
    state_dir: Path = DEFAULT_STATE_DIR,
) -> dict[str, Any]:
    if sys.platform != "darwin":
        raise RuntimeError("Learning superbatch activation is macOS-only for this runtime")
    if not ledger.exists():
        raise RuntimeError(f"Live IIOS ledger not found: {ledger}")

    actions: list[dict[str, Any]] = []
    workers_before = _worker_state()

    if not (
        workers_before["9H_BENCHMARK"]["installed"]
        and workers_before["9H_VALIDATION"]["installed"]
    ):
        actions.append(_run_activator("9H"))

    workers_mid = _worker_state()
    if not workers_mid["9I_SHADOW"]["installed"]:
        actions.append(_run_activator("9I"))

    workers_mid = _worker_state()
    if not workers_mid["9J_OUTCOME"]["installed"]:
        actions.append(_run_activator("9J"))

    status_before_refresh = build_status_snapshot(state_dir=state_dir)
    complete_sessions = int(status_before_refresh["9H"]["complete_session_count"])
    python = _resolve_backend_python(live)

    if complete_sessions > 0:
        actions.append(
            {
                "code": "9I",
                "status": "OFF_HOURS_REAL_SESSION_REFRESH",
                "result": _run_shadow_refresh(
                    python=python,
                    ledger=ledger,
                    state_dir=state_dir,
                ),
            }
        )
        actions.append(
            {
                "code": "9J",
                "status": "OUTCOME_MEMORY_REFRESH",
                "result": _run_outcome_refresh(
                    python=python,
                    ledger=ledger,
                    state_dir=state_dir,
                ),
            }
        )
    else:
        actions.append(
            {
                "code": "CHAIN",
                "status": "ARMED_WAITING_FOR_FIRST_COMPLETE_9H_SESSION",
                "reason": "No complete independent 9H benchmark session exists; no synthetic session was created.",
            }
        )

    after = build_status_snapshot(state_dir=state_dir)
    return {
        "status": "BATCH9H_9J_LEARNING_SUPERBATCH_ACTIVATED",
        "actions": actions,
        "chain": after,
        "safety": after["safety"],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Inspect or activate the governed Batch 9H -> 9I -> 9J learning chain. "
            "Never creates synthetic validation sessions."
        )
    )
    parser.add_argument("--activate", action="store_true")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--state-dir", default=str(DEFAULT_STATE_DIR))
    parser.add_argument("--live", default=str(DEFAULT_LIVE))
    parser.add_argument("--ledger", default=str(DEFAULT_LEDGER))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    state_dir = Path(args.state_dir).expanduser()
    if args.activate:
        payload = activate_learning_chain(
            live=Path(args.live).expanduser(),
            ledger=Path(args.ledger).expanduser(),
            state_dir=state_dir,
        )
    else:
        payload = build_status_snapshot(state_dir=state_dir)
    print(json.dumps(payload, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
