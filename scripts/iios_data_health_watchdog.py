#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "batch10m-data-health-watchdog-v1"
DEFAULT_STATE_DIR = Path.home() / "Library" / "Application Support" / "IIOS" / "market-validation"
DEFAULT_TELEMETRY_DIR = Path.home() / "Library" / "Application Support" / "IIOS" / "telemetry"
DEFAULT_HISTORICAL_DIR = Path.home() / "Library" / "Application Support" / "IIOS" / "historical-research"
DEFAULT_EVENT_DIR = Path.home() / "Library" / "Application Support" / "IIOS" / "historical-event-reconstruction"
DEFAULT_MACRO_DIR = Path.home() / "Library" / "Application Support" / "IIOS" / "historical-macro-regime"
DEFAULT_BENCHMARK_DIR = Path.home() / "Library" / "Application Support" / "IIOS" / "benchmark-alpha"
DEFAULT_BROWSER_DIR = Path.home() / "Library" / "Application Support" / "IIOS" / "browser-health"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists() or not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    tmp.replace(path)


def _age_seconds(path: Path, now: float) -> float | None:
    try:
        return max(0.0, now - path.stat().st_mtime)
    except OSError:
        return None


def _status(payload: dict[str, Any]) -> str | None:
    raw = payload.get("status")
    return str(raw) if raw is not None else None


def _health_row(name: str, source: Path, *, max_age_seconds: int, browser_copy: Path | None, launch_label: str | None, launch_dir: Path, now: float) -> dict[str, Any]:
    payload = _read_json(source)
    exists = bool(payload)
    age = _age_seconds(source, now)
    fresh = age is not None and age <= max_age_seconds
    analysis = bool(_status(payload))
    downstream = browser_copy.exists() if browser_copy is not None else True
    plist = launch_dir / f"{launch_label}.plist" if launch_label else None
    process_alive = plist.exists() if plist is not None else None
    if not exists:
        state = "NO_DATA"
    elif not fresh:
        state = "STALE"
    elif not analysis:
        state = "NO_ANALYSIS_STATUS"
    elif not downstream:
        state = "NOT_CONSUMED"
    elif process_alive is False:
        state = "WORKER_NOT_INSTALLED"
    else:
        state = "HEALTHY"
    return {
        "module": name,
        "state": state,
        "source": str(source),
        "source_status": _status(payload),
        "age_seconds": round(age, 1) if age is not None else None,
        "freshness_budget_seconds": max_age_seconds,
        "process_alive": process_alive,
        "data_flowing": exists,
        "data_fresh": fresh,
        "analysis_produced": analysis,
        "downstream_consumed": downstream,
    }


def build_watchdog(*, state_dir: Path, telemetry_dir: Path, historical_dir: Path, event_dir: Path, macro_dir: Path, benchmark_dir: Path, browser_dir: Path, launch_dir: Path | None = None, now: float | None = None) -> dict[str, Any]:
    now_value = datetime.now(timezone.utc).timestamp() if now is None else now
    launch_root = launch_dir or (Path.home() / "Library" / "LaunchAgents")
    specs = [
        ("9G_FACTORY_TELEMETRY", telemetry_dir / "latest.json", 7200, None, None),
        ("9H_MARKET_VALIDATION", state_dir / "latest_market_validation.json", 172800, None, None),
        ("10H_HISTORICAL_RESEARCH", historical_dir / "latest_historical_market_intelligence.json", 7200, "historical_market_intelligence.json", "com.iios.historical-market-intelligence"),
        ("10J_EVENT_RECONSTRUCTION", event_dir / "latest_historical_event_reconstruction.json", 10800, "historical_event_reconstruction.json", "com.iios.historical-event-reconstruction"),
        ("10K_MACRO_REGIME", macro_dir / "latest_historical_macro_regime_library.json", 14400, "historical_macro_regime_library.json", "com.iios.historical-macro-regime-library"),
        ("10L_BENCHMARK_ATTRIBUTION", benchmark_dir / "latest_benchmark_alpha_attribution.json", 14400, "benchmark_alpha_attribution.json", "com.iios.benchmark-alpha-attribution"),
    ]
    rows = [
        _health_row(name, source, max_age_seconds=budget, browser_copy=(browser_dir / browser_name if browser_name else None), launch_label=label, launch_dir=launch_root, now=now_value)
        for name, source, budget, browser_name, label in specs
    ]
    critical = [row for row in rows if row["module"] in {"10H_HISTORICAL_RESEARCH", "10J_EVENT_RECONSTRUCTION", "10K_MACRO_REGIME", "10L_BENCHMARK_ATTRIBUTION"}]
    healthy = sum(1 for row in critical if row["state"] == "HEALTHY")
    issues = [row for row in rows if row["state"] != "HEALTHY" and row["module"] != "9H_MARKET_VALIDATION"]
    status = "DATA_HEALTH_WATCHDOG_ACTIVE" if healthy == len(critical) and not issues else "DATA_HEALTH_WATCHDOG_ATTENTION_REQUIRED"
    chain = {
        "PROCESS_ALIVE": all(row["process_alive"] is not False for row in critical),
        "DATA_FLOWING": all(row["data_flowing"] for row in critical),
        "DATA_FRESH": all(row["data_fresh"] for row in critical),
        "ANALYSIS_PRODUCED": all(row["analysis_produced"] for row in critical),
        "DOWNSTREAM_CONSUMED": all(row["downstream_consumed"] for row in critical),
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _utc_now(),
        "status": status,
        "central_data_health": True,
        "health_chain": chain,
        "modules": rows,
        "healthy_critical_modules": healthy,
        "critical_module_count": len(critical),
        "issues": issues,
        "policy": {
            "worker_alive_is_not_equal_to_data_healthy": True,
            "market_validation_freshness_is_weekend_tolerant": True,
            "silent_degradation_is_visible": True,
        },
        "safety": {
            "observability_only": True,
            "auto_restart_workers": False,
            "auto_change_providers": False,
            "auto_change_thresholds": False,
            "capital_authority": False,
            "trade_execution_permission": False,
            "live_execution": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Batch 10M end-to-end IIOS data health watchdog.")
    parser.add_argument("--state-dir", default=str(DEFAULT_STATE_DIR))
    parser.add_argument("--telemetry-dir", default=str(DEFAULT_TELEMETRY_DIR))
    parser.add_argument("--historical-dir", default=str(DEFAULT_HISTORICAL_DIR))
    parser.add_argument("--event-dir", default=str(DEFAULT_EVENT_DIR))
    parser.add_argument("--macro-dir", default=str(DEFAULT_MACRO_DIR))
    parser.add_argument("--benchmark-dir", default=str(DEFAULT_BENCHMARK_DIR))
    parser.add_argument("--browser-dir", required=True)
    args = parser.parse_args()
    browser_dir = Path(args.browser_dir).expanduser()
    payload = build_watchdog(
        state_dir=Path(args.state_dir).expanduser(), telemetry_dir=Path(args.telemetry_dir).expanduser(), historical_dir=Path(args.historical_dir).expanduser(), event_dir=Path(args.event_dir).expanduser(), macro_dir=Path(args.macro_dir).expanduser(), benchmark_dir=Path(args.benchmark_dir).expanduser(), browser_dir=browser_dir,
    )
    out_dir = DEFAULT_BROWSER_DIR
    _atomic_write(out_dir / "latest_data_health_watchdog.json", payload)
    print(json.dumps({"status": payload["status"], "health_chain": payload["health_chain"], "issues": len(payload["issues"]), "live_execution": False}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
