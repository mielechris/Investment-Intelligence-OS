#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

from iios_historical_event_reconstruction import run_cycle as run_event_reconstruction
from iios_historical_macro_regime_library import run_cycle as run_macro_regime

BATCH = "10M.7"
SCHEMA_VERSION = "batch10m7-nightly-post-close-reconstruction-v1"
ET = ZoneInfo("America/New_York")
POST_CLOSE_HOUR = 16
POST_CLOSE_MINUTE = 20
SYMBOLS_PER_NIGHT = 8
DEFAULT_BASE_DIR = Path.home() / "Library" / "Application Support" / "IIOS"

SAFETY: dict[str, bool] = {
    "advisory_only": True,
    "paper_mode_only": True,
    "live_execution": False,
    "live_capital_locked": True,
    "trade_execution_permission": False,
    "no_broker_authority": True,
    "no_committee_or_risk_authority": True,
    "no_automatic_parameter_changes": True,
    "no_case_promotion_authority": True,
}


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    temp.replace(path)


def _paths(base_dir: Path) -> dict[str, Path]:
    nightly_dir = base_dir / "nightly-reconstruction"
    return {
        "historical_dir": base_dir / "historical-research",
        "event_dir": base_dir / "historical-event-reconstruction",
        "macro_dir": base_dir / "historical-macro-regime",
        "nightly_dir": nightly_dir,
        "latest": nightly_dir / "latest_nightly_reconstruction.json",
        "state": nightly_dir / "nightly_reconstruction_state.json",
    }


def _resolve_asof_et(asof_et: str | None) -> datetime:
    if not asof_et:
        return _now_utc().astimezone(ET)
    value = datetime.fromisoformat(asof_et)
    if value.tzinfo is None:
        value = value.replace(tzinfo=ET)
    return value.astimezone(ET)


def post_close_guard(asof_et: datetime) -> str:
    if asof_et.weekday() >= 5:
        return "MARKET_CLOSED_WEEKEND"
    if (asof_et.hour, asof_et.minute) < (POST_CLOSE_HOUR, POST_CLOSE_MINUTE):
        return "WAITING_FOR_POST_CLOSE"
    return "READY"


def _base_payload(*, asof_et: datetime, status: str, force: bool) -> dict[str, Any]:
    return {
        "batch": BATCH,
        "schema_version": SCHEMA_VERSION,
        "surface": "Nightly_Post_Close_Reconstruction",
        "status": status,
        "generated_at": _iso(_now_utc()),
        "market_date_et": asof_et.date().isoformat(),
        "asof_et": asof_et.isoformat(),
        "post_close_guard": {
            "timezone": "America/New_York",
            "earliest_run_time": "16:20",
            "weekday_only": True,
            "force_override": force,
        },
        "scope": {
            "source_batches": ["10J", "10K"],
            "symbols_per_night": SYMBOLS_PER_NIGHT,
            "purpose": "post_close_historical_reconstruction_and_macro_regime_refresh",
            "current_market_trading_authority": False,
        },
        "safety": dict(SAFETY),
    }


def _persist_report(paths: dict[str, Path], payload: dict[str, Any]) -> None:
    market_date = str(payload.get("market_date_et") or "unknown")
    _write_json(paths["latest"], payload)
    _write_json(paths["nightly_dir"] / f"nightly_reconstruction_{market_date}.json", payload)


def run_once(
    *,
    base_dir: Path = DEFAULT_BASE_DIR,
    asof_et: str | None = None,
    force: bool = False,
    event_runner: Callable[..., dict[str, Any]] = run_event_reconstruction,
    macro_runner: Callable[..., dict[str, Any]] = run_macro_regime,
) -> dict[str, Any]:
    base_dir = Path(base_dir).expanduser()
    paths = _paths(base_dir)
    resolved_asof = _resolve_asof_et(asof_et)
    guard = post_close_guard(resolved_asof)

    if guard != "READY" and not force:
        return _base_payload(asof_et=resolved_asof, status=guard, force=force)

    state = _read_json(paths["state"])
    market_date = resolved_asof.date().isoformat()
    if state.get("last_completed_market_date_et") == market_date and not force:
        payload = _base_payload(asof_et=resolved_asof, status="ALREADY_RECONSTRUCTED", force=force)
        payload["last_completed_at"] = state.get("last_completed_at")
        return payload

    payload = _base_payload(asof_et=resolved_asof, status="RUNNING", force=force)
    try:
        event_report = event_runner(
            historical_dir=paths["historical_dir"],
            event_dir=paths["event_dir"],
            symbols_per_cycle=SYMBOLS_PER_NIGHT,
        )
        macro_report = macro_runner(
            historical_dir=paths["historical_dir"],
            macro_dir=paths["macro_dir"],
        )

        completed_at = _iso(_now_utc())
        payload.update(
            {
                "status": "COMPLETE",
                "completed_at": completed_at,
                "event_reconstruction": {
                    "batch": "10J",
                    "status": event_report.get("status"),
                    "surface": event_report.get("surface"),
                    "reconstruction_count": len(event_report.get("reconstructions") or []),
                    "cycle": event_report.get("cycle"),
                },
                "macro_regime": {
                    "batch": "10K",
                    "status": macro_report.get("status"),
                    "surface": macro_report.get("surface"),
                    "research_summary": macro_report.get("research_summary"),
                },
                "provenance": {
                    "historical_source": str(paths["historical_dir"]),
                    "event_artifact_dir": str(paths["event_dir"]),
                    "macro_artifact_dir": str(paths["macro_dir"]),
                    "nightly_artifact_dir": str(paths["nightly_dir"]),
                    "execution_order": ["10J_event_reconstruction", "10K_macro_regime_refresh"],
                },
            }
        )
        _persist_report(paths, payload)
        _write_json(
            paths["state"],
            {
                "schema_version": SCHEMA_VERSION,
                "last_completed_market_date_et": market_date,
                "last_completed_at": completed_at,
                "last_status": "COMPLETE",
                "live_execution": False,
                "trade_execution_permission": False,
            },
        )
        return payload
    except Exception as exc:  # fail closed; leave the market date retryable
        payload.update(
            {
                "status": "ERROR",
                "error": f"{type(exc).__name__}: {exc}",
                "retryable": True,
                "state_advance": False,
            }
        )
        _persist_report(paths, payload)
        return payload


def status(*, base_dir: Path = DEFAULT_BASE_DIR) -> dict[str, Any]:
    base_dir = Path(base_dir).expanduser()
    paths = _paths(base_dir)
    latest = _read_json(paths["latest"])
    state = _read_json(paths["state"])
    return {
        "batch": BATCH,
        "schema_version": SCHEMA_VERSION,
        "surface": "Nightly_Post_Close_Reconstruction",
        "status": latest.get("status") or "NOT_YET_RUN",
        "latest_generated_at": latest.get("generated_at"),
        "latest_completed_at": latest.get("completed_at"),
        "last_completed_market_date_et": state.get("last_completed_market_date_et"),
        "latest_artifact": str(paths["latest"]),
        "state_artifact": str(paths["state"]),
        "safety": dict(SAFETY),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the governed Batch 10M.7 nightly post-close historical reconstruction worker.")
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--run-once", action="store_true")
    action.add_argument("--status", action="store_true")
    parser.add_argument("--base-dir", default=str(DEFAULT_BASE_DIR))
    parser.add_argument("--asof-et", default=None, help="ISO timestamp used for deterministic acceptance/backfill checks.")
    parser.add_argument("--force", action="store_true", help="Controlled advisory backfill override; does not change safety authority.")
    args = parser.parse_args()

    base_dir = Path(args.base_dir).expanduser()
    payload = status(base_dir=base_dir) if args.status else run_once(base_dir=base_dir, asof_et=args.asof_et, force=args.force)
    print(json.dumps(payload, indent=2, sort_keys=True, default=str))
    return 0 if payload.get("status") != "ERROR" else 1


if __name__ == "__main__":
    raise SystemExit(main())
