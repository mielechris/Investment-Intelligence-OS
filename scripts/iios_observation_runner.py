#!/usr/bin/env python3
"""IIOS Batch 9A — governed Observation & Paper Operations runner.

This process is intentionally separate from the Batch Supervisor and web server.
It builds a paper-only operating history by:
  * running bounded market/event + opportunity discovery,
  * promoting at most one eligible research candidate per scan,
  * running newly promoted cases through the eight specialist desks + Committee,
  * refreshing due monitoring/thesis profiles,
  * reconciling and marking the governed $10K paper portfolio,
  * recording a portfolio snapshot and an Observation ledger checkpoint.

It NEVER creates live authority, submits a broker order, bypasses Risk/Capital,
or enables live execution. Governed paper orders remain downstream of the existing
Risk -> sizing -> paper authorization -> governed paper execution chain.
"""
from __future__ import annotations

import argparse
import json
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND = REPO_ROOT / "BACK END" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from eight_agent_orchestrator import run_eight_agent_orchestration  # noqa: E402
from ledger import latest_object, record_event, record_object, utc_now  # noqa: E402
from market_event_radar import run_market_event_radar  # noqa: E402
from monitoring_engine import refresh_due_profiles  # noqa: E402
from opportunity_acquisition import promote_candidate, scan_universe  # noqa: E402
from paper_portfolio_core import (  # noqa: E402
    build_performance_history,
    build_portfolio_state,
    record_live_portfolio_snapshot,
)

OBSERVATION_CASE_ID = "observation_operations"
OBSERVATION_STATE_ID = "observation_operations_state_v1"
OBSERVATION_STATE_TYPE = "observation_operations_state"
POLICY_VERSION = "batch9a-observation-v1"
DEFAULT_CYCLE_MINUTES = 15
DEFAULT_MARKET_SCAN_MINUTES = 30
DEFAULT_OFF_HOURS_SCAN_MINUTES = 120
DEFAULT_NEWS_LIMIT = 8
DEFAULT_MAX_CANDIDATES = 10
MAX_PROMOTIONS_PER_SCAN = 1

_STOP = False


def _log(message: str) -> None:
    print(message, flush=True)


def _handle_stop(_signum: int, _frame: Any) -> None:
    global _STOP
    _STOP = True


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


def _market_phase(now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    eastern = now.astimezone(ZoneInfo("America/New_York"))
    if eastern.weekday() >= 5:
        return "WEEKEND"
    minute = eastern.hour * 60 + eastern.minute
    if 570 <= minute < 960:
        return "REGULAR_SESSION"
    if 240 <= minute < 570:
        return "PRE_MARKET"
    if 960 <= minute < 1200:
        return "AFTER_HOURS"
    return "OVERNIGHT"


def _scan_interval_minutes(phase: str) -> int:
    if phase == "REGULAR_SESSION":
        return DEFAULT_MARKET_SCAN_MINUTES
    return DEFAULT_OFF_HOURS_SCAN_MINUTES


def _last_state() -> dict[str, Any]:
    return latest_object(OBSERVATION_STATE_TYPE, case_id=OBSERVATION_CASE_ID) or {}


def _scan_due(state: dict[str, Any], phase: str, now: datetime) -> bool:
    last = _parse_time(state.get("last_scan_at"))
    if last is None:
        return True
    interval = _scan_interval_minutes(phase)
    return (now - last).total_seconds() >= interval * 60


def _safe_call(label: str, function, *args, **kwargs) -> dict[str, Any]:
    try:
        value = function(*args, **kwargs)
        return {"status": "complete", "label": label, "result": value}
    except Exception as exc:
        return {
            "status": "error",
            "label": label,
            "error": f"{type(exc).__name__}: {exc}",
        }


def _promote_and_orchestrate(scan: dict[str, Any]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    queue = scan.get("queue") if isinstance(scan, dict) else []
    queue = queue if isinstance(queue, list) else []

    if not queue:
        _log("[DISCOVERY] No eligible candidate cleared the promotion gate.")
        return results

    for candidate in queue[:MAX_PROMOTIONS_PER_SCAN]:
        candidate_id = str(candidate.get("opportunity_candidate_id") or "").strip()
        ticker = str(candidate.get("ticker") or "UNKNOWN")
        if not candidate_id:
            continue

        _log(
            f"[PROMOTION] {ticker} score={candidate.get('score')} — promoting one governed research case..."
        )
        promotion = _safe_call("promote_candidate", promote_candidate, candidate_id)
        row: dict[str, Any] = {
            "candidate_id": candidate_id,
            "ticker": candidate.get("ticker"),
            "score": candidate.get("score"),
            "promotion": promotion,
        }

        if promotion.get("status") == "complete":
            promoted = promotion.get("result") or {}
            case = promoted.get("case") if isinstance(promoted, dict) else {}
            case_id = str((case or {}).get("case_id") or "").strip()
            row["case_id"] = case_id or None
            if case_id:
                _log(
                    f"[AGENTS] {ticker} case={case_id} — running eight specialist desks + Committee..."
                )
                row["orchestration"] = _safe_call(
                    "eight_agent_orchestration",
                    run_eight_agent_orchestration,
                    case_id,
                )
                orchestration = row.get("orchestration") or {}
                _log(
                    f"[AGENTS] {ticker} orchestration status={orchestration.get('status')}"
                )
        else:
            _log(
                f"[PROMOTION] {ticker} failed closed: {promotion.get('error', 'unknown error')}"
            )

        results.append(row)

    return results


def run_cycle(*, force_scan: bool = False) -> dict[str, Any]:
    started = datetime.now(timezone.utc)
    phase = _market_phase(started)
    previous = _last_state()

    _log(
        f"\n=== IIOS OBSERVATION CYCLE START · phase={phase} · {started.isoformat()} ==="
    )
    _log("[1/6] Reading governed $10K paper portfolio...")
    portfolio_before = _safe_call("paper_portfolio_before", build_portfolio_state)
    portfolio_payload = portfolio_before.get("result") or {}
    if isinstance(portfolio_payload, dict):
        _log(
            f"      NAV={portfolio_payload.get('nav')} cash={portfolio_payload.get('cash')} "
            f"positions={portfolio_payload.get('position_count')}"
        )

    _log("[2/6] Refreshing due monitoring / thesis profiles...")
    monitoring = _safe_call("refresh_due_profiles", refresh_due_profiles)
    _log(f"      monitoring={monitoring.get('status')}")

    scan_result: dict[str, Any] = {
        "status": "not_due",
        "label": "opportunity_scan",
        "scan_interval_minutes": _scan_interval_minutes(phase),
    }
    radar_result: dict[str, Any] = {
        "status": "not_due",
        "label": "market_event_radar",
    }
    promoted: list[dict[str, Any]] = []
    last_scan_at = previous.get("last_scan_at")
    due = force_scan or _scan_due(previous, phase, started)

    if due:
        _log("[3/6] Running market-event radar...")
        radar_result = _safe_call("market_event_radar", run_market_event_radar)
        radar_payload = radar_result.get("result") or {}
        _log(
            f"      radar={radar_result.get('status')} events={radar_payload.get('event_count') if isinstance(radar_payload, dict) else 'UNKNOWN'}"
        )

        _log("[4/6] Scanning governed opportunity universe (quotes + news)...")
        scan_result = _safe_call(
            "opportunity_scan",
            scan_universe,
            news_limit=DEFAULT_NEWS_LIMIT,
            max_candidates=DEFAULT_MAX_CANDIDATES,
        )
        last_scan_at = utc_now()
        scan_payload = scan_result.get("result") or {}
        if isinstance(scan_payload, dict):
            _log(
                f"      scan={scan_result.get('status')} scanned={scan_payload.get('scanned_count', 0)} "
                f"queue={scan_payload.get('queued_count', 0)}"
            )
        if scan_result.get("status") == "complete":
            promoted = _promote_and_orchestrate(scan_payload)
        else:
            _log(
                f"      discovery failed closed: {scan_result.get('error', 'unknown error')}"
            )
    else:
        _log(
            f"[3/6] Discovery not due — next scan cadence is {_scan_interval_minutes(phase)} minutes for {phase}."
        )
        _log("[4/6] Opportunity scan skipped this cycle.")

    _log("[5/6] Marking and snapshotting governed $10K paper portfolio...")
    portfolio_snapshot = _safe_call(
        "paper_portfolio_snapshot",
        record_live_portfolio_snapshot,
    )
    performance = _safe_call(
        "paper_portfolio_performance",
        build_performance_history,
    )

    completed = datetime.now(timezone.utc)
    scan_payload = (
        scan_result.get("result")
        if scan_result.get("status") == "complete"
        else {}
    )
    scan_payload = scan_payload if isinstance(scan_payload, dict) else {}
    snapshot_payload = (
        portfolio_snapshot.get("result")
        if portfolio_snapshot.get("status") == "complete"
        else {}
    )
    snapshot_payload = snapshot_payload if isinstance(snapshot_payload, dict) else {}
    performance_payload = (
        performance.get("result")
        if performance.get("status") == "complete"
        else {}
    )
    performance_payload = (
        performance_payload if isinstance(performance_payload, dict) else {}
    )
    _log(
        f"      NAV={snapshot_payload.get('nav')} cash={snapshot_payload.get('cash')} "
        f"positions={snapshot_payload.get('position_count')} snapshots={performance_payload.get('snapshot_count')}"
    )

    state = {
        "observation_operations_state_id": OBSERVATION_STATE_ID,
        "policy_version": POLICY_VERSION,
        "enabled": True,
        "mode": "OBSERVATION_AND_GOVERNED_PAPER",
        "market_phase": phase,
        "cycle_minutes": DEFAULT_CYCLE_MINUTES,
        "market_scan_minutes": DEFAULT_MARKET_SCAN_MINUTES,
        "off_hours_scan_minutes": DEFAULT_OFF_HOURS_SCAN_MINUTES,
        "last_cycle_started_at": started.isoformat(),
        "last_cycle_completed_at": completed.isoformat(),
        "last_cycle_duration_seconds": round(
            (completed - started).total_seconds(), 2
        ),
        "last_scan_at": last_scan_at,
        "last_scan_status": scan_result.get("status"),
        "last_scan_count": scan_payload.get("scanned_count", 0),
        "last_queue_count": scan_payload.get("queued_count", 0),
        "promoted_case_count": sum(
            1 for row in promoted if row.get("case_id")
        ),
        "monitoring": monitoring,
        "radar": radar_result,
        "scan": scan_result,
        "promotions": promoted,
        "paper_portfolio": {
            "snapshot_id": snapshot_payload.get(
                "paper_portfolio_snapshot_id"
            ),
            "nav": snapshot_payload.get("nav"),
            "cash": snapshot_payload.get("cash"),
            "positions": snapshot_payload.get("position_count"),
            "transactions": snapshot_payload.get("transaction_count"),
            "snapshot_count": performance_payload.get("snapshot_count"),
            "cumulative_return_pct": performance_payload.get(
                "cumulative_return_pct"
            ),
            "max_drawdown_pct": performance_payload.get(
                "max_drawdown_pct"
            ),
        },
        "authority": {
            "auto_trade_authority": False,
            "paper_order_permission": False,
            "trade_execution_permission": False,
            "live_execution": False,
            "broker_connected": False,
        },
        "paper_mode": True,
        "created_at": previous.get("created_at") or utc_now(),
        "updated_at": utc_now(),
    }

    _log("[6/6] Writing Observation cycle checkpoint to governed ledger...")
    record_object(
        OBSERVATION_STATE_ID,
        OBSERVATION_STATE_TYPE,
        OBSERVATION_CASE_ID,
        state,
        topic="IIOS Observation & Paper Operations",
    )
    record_event(
        OBSERVATION_CASE_ID,
        "OBSERVATION_CYCLE_COMPLETE",
        entity_id=OBSERVATION_STATE_ID,
        payload={
            "market_phase": phase,
            "scan_status": state["last_scan_status"],
            "scanned_count": state["last_scan_count"],
            "queued_count": state["last_queue_count"],
            "promoted_case_count": state["promoted_case_count"],
            "nav": state["paper_portfolio"]["nav"],
            "positions": state["paper_portfolio"]["positions"],
            "live_execution": False,
        },
    )
    _log(
        f"=== CYCLE COMPLETE · {state['last_cycle_duration_seconds']}s · "
        f"scan={state['last_scan_status']} scanned={state['last_scan_count']} "
        f"queue={state['last_queue_count']} promoted={state['promoted_case_count']} "
        f"NAV={state['paper_portfolio']['nav']} positions={state['paper_portfolio']['positions']} ==="
    )
    return state


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run IIOS governed Observation Mode"
    )
    parser.add_argument(
        "--once", action="store_true", help="Run one cycle and exit"
    )
    parser.add_argument(
        "--force-scan",
        action="store_true",
        help="Force discovery scan this cycle",
    )
    parser.add_argument(
        "--interval-minutes",
        type=int,
        default=DEFAULT_CYCLE_MINUTES,
        help="Loop cadence. Minimum 15 minutes.",
    )
    args = parser.parse_args()

    interval = max(DEFAULT_CYCLE_MINUTES, int(args.interval_minutes))
    signal.signal(signal.SIGINT, _handle_stop)
    signal.signal(signal.SIGTERM, _handle_stop)

    if args.once:
        state = run_cycle(force_scan=args.force_scan)
        print(json.dumps(state, indent=2, default=str), flush=True)
        return 0

    _log("IIOS BATCH 9A — OBSERVATION & PAPER OPERATIONS")
    _log(f"Repo: {REPO_ROOT}")
    _log(f"Cycle: every {interval} minutes")
    _log("Authority: PAPER/SHADOW ONLY — live execution FALSE")
    _log("Press Ctrl+C in this terminal only to stop Observation Mode cleanly.")

    first = True
    while not _STOP:
        state = run_cycle(force_scan=args.force_scan and first)
        first = False
        if _STOP:
            break
        _log(
            f"[IDLE] Next observation cycle in {interval} minutes. "
            f"Current NAV={state['paper_portfolio']['nav']} positions={state['paper_portfolio']['positions']}"
        )
        for _ in range(interval * 60):
            if _STOP:
                break
            time.sleep(1)

    _log("Observation runner stopped cleanly.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
