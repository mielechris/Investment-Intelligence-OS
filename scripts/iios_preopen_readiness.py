#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.request import urlopen
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")
PT = ZoneInfo("America/Los_Angeles")
APP = Path.home() / "Library" / "Application Support" / "IIOS"


def expand(value: str) -> Path:
    return Path(os.path.expanduser(value)).resolve()


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    temporary.replace(path)


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


def age_seconds(value: Any, reference: datetime) -> float | None:
    parsed = parse_time(value)
    if parsed is None:
        return None
    return max(0.0, (reference - parsed).total_seconds())


def launchd_loaded(label: str) -> bool:
    if os.name != "posix" or not hasattr(os, "getuid"):
        return False
    try:
        result = subprocess.run(
            ["launchctl", "print", f"gui/{os.getuid()}/{label}"],
            text=True,
            capture_output=True,
            check=False,
            timeout=10,
        )
    except Exception:
        return False
    return result.returncode == 0


def backend_healthy(url: str) -> bool:
    try:
        with urlopen(url, timeout=4) as response:
            return 200 <= int(getattr(response, "status", 0)) < 300
    except Exception:
        return False


def market_phase(now_et: datetime) -> str:
    if now_et.weekday() >= 5:
        return "WEEKEND"
    minute = now_et.hour * 60 + now_et.minute
    if minute < 360:
        return "OVERNIGHT"
    if minute < 540:
        return "PREMARKET"
    if minute < 570:
        return "PREOPEN_WINDOW"
    if minute < 960:
        return "REGULAR_SESSION"
    return "AFTER_HOURS"


def build_readiness(config: dict[str, Any], *, reference: datetime | None = None) -> dict[str, Any]:
    now_utc = reference or datetime.now(timezone.utc)
    now_et = now_utc.astimezone(NY)
    now_pt = now_utc.astimezone(PT)
    phase = market_phase(now_et)

    core_hb_dir = Path.home() / ".iios" / "heartbeats"
    radar_hb_dir = expand(str(config.get("heartbeat_directory") or "~/.iios/radar-heartbeats"))
    validation_hb_dir = Path.home() / ".iios" / "validation-heartbeats"

    hb_9a = read_json(core_hb_dir / "9a.json")
    hb_9b = read_json(core_hb_dir / "9b.json")
    hb_9e = read_json(radar_hb_dir / "9e.json")
    hb_9h = read_json(validation_hb_dir / "9h_collector.json")

    a9 = age_seconds(hb_9a.get("last_completed_at") or hb_9a.get("last_output_at"), now_utc)
    b9 = age_seconds(hb_9b.get("last_completed_at") or hb_9b.get("last_output_at"), now_utc)
    e9 = age_seconds(hb_9e.get("last_radar_completed_at") or hb_9e.get("last_output_at"), now_utc)
    h9 = age_seconds(hb_9h.get("last_run_completed_at") or hb_9h.get("last_run_started_at"), now_utc)

    telemetry = read_json(expand(str(config.get("local_telemetry_path") or APP / "telemetry" / "latest.json")))
    source = telemetry.get("source") if isinstance(telemetry.get("source"), dict) else {}
    safety = telemetry.get("safety") if isinstance(telemetry.get("safety"), dict) else {}
    generated = age_seconds(telemetry.get("generated_at"), now_utc)

    checks = {
        "backend_8002": backend_healthy(str(config.get("backend_url") or "http://127.0.0.1:8002/")),
        "core_supervisor_loaded": launchd_loaded(str(config.get("core_supervisor_label") or "com.iios.terminal-bridge-supervisor")),
        "radar_supervisor_loaded": launchd_loaded(str(config.get("radar_supervisor_label") or "com.iios.batch9e-radar-bridge-supervisor")),
        "validation_supervisor_loaded": launchd_loaded(str(config.get("validation_supervisor_label") or "com.iios.validation-bridge-supervisor")),
        "scientific_measurement_loaded": launchd_loaded(str(config.get("scientific_measurement_label") or "com.iios.scientific-measurement")),
        "awake_guard_loaded": launchd_loaded(str(config.get("awake_label") or "com.iios.market-awake")),
        "9A_fresh": a9 is not None and a9 <= 45 * 60,
        "9B_fresh": b9 is not None and b9 <= 45 * 60,
        "9E_fresh": e9 is not None and e9 <= 15 * 60,
        "9H_collector_heartbeat_fresh": h9 is not None and h9 <= 20 * 60,
        "telemetry_fresh": generated is not None and generated <= 10 * 60,
        "telemetry_local_ledger_read_only": source.get("mode") == "LOCAL_LEDGER_READ_ONLY",
        "telemetry_read_only": safety.get("telemetry_read_only") is True,
        "live_execution_false": safety.get("live_execution") is False,
        "live_capital_locked": safety.get("live_capital_locked") is True,
        "trade_execution_permission_false": safety.get("trade_execution_permission") is False,
    }

    failed = [name for name, passed in checks.items() if not passed]
    hard_required = {
        "backend_8002",
        "core_supervisor_loaded",
        "radar_supervisor_loaded",
        "validation_supervisor_loaded",
        "9A_fresh",
        "9B_fresh",
        "9E_fresh",
        "9H_collector_heartbeat_fresh",
        "telemetry_fresh",
        "telemetry_local_ledger_read_only",
        "telemetry_read_only",
        "live_execution_false",
        "live_capital_locked",
        "trade_execution_permission_false",
    }
    hard_failed = [name for name in failed if name in hard_required]

    if not hard_failed and phase == "PREOPEN_WINDOW":
        status = "READY_FOR_OPENING_BELL"
    elif not hard_failed:
        status = "RUNTIME_READY_OUTSIDE_PREOPEN"
    else:
        status = "NOT_READY"

    return {
        "schema_version": "batch10m3-preopen-readiness-v1",
        "generated_at": now_utc.isoformat(),
        "local_time_pt": now_pt.isoformat(),
        "market_time_et": now_et.isoformat(),
        "market_phase": phase,
        "status": status,
        "failed_checks": failed,
        "hard_failed_checks": hard_failed,
        "checks": checks,
        "freshness_seconds": {"9A": a9, "9B": b9, "9E": e9, "9H_COLLECTOR": h9, "TELEMETRY": generated},
        "opening_bell_contract": "READY_FOR_OPENING_BELL requires Backend 8002, 9A, 9B, 9E, 9H collector, core/radar/validation supervisors, fresh verified read-only telemetry, live capital locked, live execution false, and trade execution permission false.",
        "sleep_note": "Software supervision cannot execute while macOS itself is asleep. The Batch 10M.3 awake guard is intended to prevent idle sleep; keep the Mac plugged in, logged in, and the lid open.",
        "safety": {
            "paper_mode": True,
            "model_routing_auto_change": False,
            "capital_authority": False,
            "broker_connected": False,
            "trade_execution_permission": False,
            "live_execution": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="IIOS pre-open readiness gate")
    parser.add_argument("--config", required=True)
    args = parser.parse_args()
    config = read_json(expand(args.config))
    snapshot = build_readiness(config)
    output = expand(str(config.get("preopen_output_path") or APP / "overnight-readiness" / "latest_preopen_readiness.json"))
    atomic_write(output, snapshot)
    print(json.dumps(snapshot, indent=2, sort_keys=True, default=str), flush=True)
    return 0 if snapshot["status"] != "NOT_READY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
