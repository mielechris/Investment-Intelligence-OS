#!/usr/bin/env python3
"""Fast Batch 9A live-ledger acceptance cycle.

Purpose: prove that the merged IIOS stack can collect fresh governed market/news
observations and write a paper-portfolio snapshot against the existing live ledger
without invoking the long eight-agent/Committee production cycle.

This script cannot create paper orders or live authority.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND = REPO_ROOT / "BACK END" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from ledger import record_event, record_object, utc_now  # noqa: E402
from opportunity_acquisition import current_universe, scan_universe  # noqa: E402
from paper_portfolio_core import (  # noqa: E402
    build_performance_history,
    build_portfolio_state,
    record_live_portfolio_snapshot,
)

CASE_ID = "observation_operations"
STATE_ID = "observation_acceptance_state_v1"
STATE_TYPE = "observation_acceptance_state"
PREFERRED_SYMBOLS = ("SPY", "QQQ", "MU")


def log(message: str) -> None:
    print(message, flush=True)


def compact_portfolio(value: dict[str, Any]) -> dict[str, Any]:
    return {
        "nav": value.get("nav"),
        "cash": value.get("cash"),
        "positions": value.get("position_count"),
        "transactions": value.get("transaction_count"),
        "paper_mode": value.get("paper_mode"),
        "live_execution": value.get("live_execution"),
    }


def acceptance_universe() -> list[dict[str, str]]:
    universe = current_universe()
    by_ticker = {
        str(row.get("ticker") or "").upper(): row
        for row in universe
        if isinstance(row, dict)
    }
    selected = [by_ticker[ticker] for ticker in PREFERRED_SYMBOLS if ticker in by_ticker]
    if len(selected) < 3:
        for row in universe:
            if row in selected:
                continue
            selected.append(row)
            if len(selected) >= 3:
                break
    return selected[:3]


def main() -> int:
    log("IIOS BATCH 9A — FAST LIVE-DATA ACCEPTANCE")
    log("Authority: PAPER/SHADOW ONLY — broker connected FALSE — live execution FALSE")

    try:
        log("[1/4] Reading governed $10K paper portfolio...")
        before = build_portfolio_state()
        log(
            f"      NAV={before.get('nav')} cash={before.get('cash')} "
            f"positions={before.get('position_count')}"
        )

        sample = acceptance_universe()
        tickers = [str(row.get("ticker") or "") for row in sample]
        log(f"[2/4] Collecting live quote/news data for: {', '.join(tickers)}")
        scan = scan_universe(
            universe=sample,
            news_limit=4,
            timespan="24h",
            max_candidates=3,
        )
        log(
            f"      scanned={scan.get('scanned_count')} queued={scan.get('queued_count')} "
            f"scan_id={scan.get('opportunity_scan_id')}"
        )
        for row in (scan.get("candidates") or []):
            log(
                f"      {row.get('ticker')}: score={row.get('score')} "
                f"priority={row.get('priority')} evidence={row.get('evidence_count')} "
                f"eligible={row.get('eligible_for_promotion')}"
            )

        log("[3/4] Marking and snapshotting the $10K paper portfolio...")
        snapshot = record_live_portfolio_snapshot()
        performance = build_performance_history()
        log(
            f"      snapshot={snapshot.get('paper_portfolio_snapshot_id')} "
            f"NAV={snapshot.get('nav')} positions={snapshot.get('position_count')} "
            f"history={performance.get('snapshot_count')} snapshots"
        )

        log("[4/4] Writing Batch 9A acceptance checkpoint to the governed ledger...")
        state = {
            "observation_acceptance_state_id": STATE_ID,
            "status": "PASS",
            "sample_tickers": tickers,
            "scan_id": scan.get("opportunity_scan_id"),
            "scanned_count": scan.get("scanned_count"),
            "queued_count": scan.get("queued_count"),
            "paper_portfolio_before": compact_portfolio(before),
            "paper_portfolio_snapshot": compact_portfolio(snapshot),
            "snapshot_id": snapshot.get("paper_portfolio_snapshot_id"),
            "snapshot_count": performance.get("snapshot_count"),
            "paper_mode": True,
            "auto_trade_authority": False,
            "paper_order_permission": False,
            "trade_execution_permission": False,
            "live_execution": False,
            "broker_connected": False,
            "created_at": utc_now(),
        }
        record_object(
            STATE_ID,
            STATE_TYPE,
            CASE_ID,
            state,
            topic="IIOS Batch 9A fast acceptance",
        )
        record_event(
            CASE_ID,
            "OBSERVATION_FAST_ACCEPTANCE_PASS",
            entity_id=STATE_ID,
            payload={
                "sample_tickers": tickers,
                "scanned_count": scan.get("scanned_count"),
                "queued_count": scan.get("queued_count"),
                "nav": snapshot.get("nav"),
                "live_execution": False,
            },
        )

        log("RESULT: PASS — live data collected and paper portfolio snapshot recorded")
        log(json.dumps(state, indent=2, default=str))
        return 0
    except KeyboardInterrupt:
        log("RESULT: STOPPED — operator interrupted acceptance cycle")
        return 130
    except Exception as exc:
        log(f"RESULT: FAIL — {type(exc).__name__}: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
