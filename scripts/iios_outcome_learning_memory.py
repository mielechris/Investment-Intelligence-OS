#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "BACK END" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from outcome_labeling_memory import (  # noqa: E402
    aggregate_outcome_memory,
    build_browser_summary,
    build_session_outcome_memory,
    parse_yahoo_chart,
)

DEFAULT_STATE_DIR = Path.home() / "Library" / "Application Support" / "IIOS" / "market-validation"
REPORT_HEADER = "IIOS OUTCOME LEARNING — BATCH 9J READ ONLY"
DEFAULT_LOOKBACK_SESSIONS = 20


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return value if isinstance(value, dict) else None


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    temporary.replace(path)


def _run_gh(*args: str) -> str:
    gh = shutil.which("gh")
    if not gh:
        raise RuntimeError("GitHub CLI (gh) is required for private outcome-learning publishing")
    result = subprocess.run([gh, *args], text=True, capture_output=True, check=False)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(f"gh {' '.join(args[:3])} failed: {detail[:1200]}")
    return result.stdout.strip()


def _require_private_repo(repo: str) -> None:
    private = _run_gh("api", f"repos/{repo}", "--jq", ".private").strip().lower()
    if private != "true":
        raise RuntimeError("Refusing outcome-learning publish: target GitHub repository must be private")


def _publish_private_issue(repo: str, issue: int, payload: dict[str, Any]) -> None:
    _require_private_repo(repo)
    compact = {
        "schema_version": payload.get("schema_version"),
        "generated_at": payload.get("generated_at"),
        "status": payload.get("status"),
        "complete_session_count": payload.get("complete_session_count"),
        "outcome_count": payload.get("outcome_count"),
        "mature_5d_count": payload.get("mature_5d_count"),
        "pending_5d_count": payload.get("pending_5d_count"),
        "decision_quality_counts": payload.get("decision_quality_counts"),
        "market_outcome_counts": payload.get("market_outcome_counts"),
        "agent_scorecards": payload.get("agent_scorecards"),
        "judgment_bank_review_queue": (payload.get("judgment_bank_review_queue") or [])[:20],
        "recent_outcomes": (payload.get("recent_outcomes") or [])[:20],
        "safety": payload.get("safety"),
    }
    body = (
        f"{REPORT_HEADER}\n\n"
        "Machine-updated outcome memory from complete Batch 9H sessions and read-only IIOS decision provenance. "
        "Outcome labels are review inputs only; they cannot automatically write the Judgment Bank or change agent/Committee/Risk authority.\n\n"
        "```json\n"
        + json.dumps(compact, indent=2, sort_keys=True, default=str)
        + "\n```\n"
    )
    _run_gh("api", "--method", "PATCH", f"repos/{repo}/issues/{issue}", "-f", f"body={body}")


def _fetch_chart(
    ticker: str,
    *,
    start: datetime,
    end: datetime,
    interval: str,
) -> list[dict[str, Any]]:
    from provider_hardening import _json_request

    yahoo_symbol = ticker.replace(".", "-")
    period1 = int(start.astimezone(timezone.utc).timestamp())
    period2 = int(end.astimezone(timezone.utc).timestamp())
    query = (
        f"period1={period1}&period2={period2}&interval={interval}"
        "&includePrePost=false&events=div%2Csplits"
    )
    errors: list[str] = []
    for host in ("query1.finance.yahoo.com", "query2.finance.yahoo.com"):
        try:
            payload = _json_request(
                url=f"https://{host}/v8/finance/chart/{quote(yahoo_symbol)}?{query}",
                provider="yahoo_9j_outcome_learning",
                minimum_interval_seconds=0.18,
                retries=1,
                cache_ttl_seconds=300,
            )
            rows = parse_yahoo_chart(payload)
            if rows:
                return rows
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{host}:{type(exc).__name__}:{exc}")
    if errors:
        return []
    return []


def _price_data_for_opportunity(opportunity: dict[str, Any], now: datetime) -> dict[str, list[dict[str, Any]]]:
    ticker = str(opportunity.get("ticker") or "").strip().upper()
    event_text = str(opportunity.get("event_at") or "")
    try:
        event_at = datetime.fromisoformat(event_text.replace("Z", "+00:00"))
    except ValueError:
        return {"intraday": [], "daily": []}
    if event_at.tzinfo is None:
        event_at = event_at.replace(tzinfo=timezone.utc)
    event_at = event_at.astimezone(timezone.utc)
    intraday_start = event_at - timedelta(hours=2)
    intraday_end = min(now + timedelta(hours=1), event_at + timedelta(days=1))
    daily_start = event_at - timedelta(days=2)
    daily_end = now + timedelta(days=2)
    return {
        "intraday": _fetch_chart(
            ticker,
            start=intraday_start,
            end=intraday_end,
            interval="5m",
        ),
        "daily": _fetch_chart(
            ticker,
            start=daily_start,
            end=daily_end,
            interval="1d",
        ),
    }


def _complete_report_dirs(state_dir: Path, limit: int) -> list[Path]:
    reports = state_dir / "reports"
    if not reports.exists():
        return []
    rows: list[Path] = []
    for directory in reports.iterdir():
        if not directory.is_dir():
            continue
        benchmark = _read_json(directory / "benchmark.json")
        scorecard = _read_json(directory / "scorecard.json")
        if not benchmark or not scorecard:
            continue
        if benchmark.get("benchmark_complete") is not True:
            continue
        rows.append(directory)
    rows.sort(key=lambda path: path.name, reverse=True)
    return rows[: max(1, int(limit))]


def run_outcome_learning(
    *,
    db_path: str | None,
    state_dir: Path,
    lookback_sessions: int,
    now: datetime | None = None,
) -> dict[str, Any]:
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    report_dirs = _complete_report_dirs(state_dir, lookback_sessions)
    session_memories: list[dict[str, Any]] = []

    for directory in reversed(report_dirs):
        benchmark = _read_json(directory / "benchmark.json") or {}
        scorecard = _read_json(directory / "scorecard.json") or {}
        price_data: dict[str, dict[str, list[dict[str, Any]]]] = {}
        for opportunity in benchmark.get("opportunities") or []:
            if not isinstance(opportunity, dict):
                continue
            ticker = str(opportunity.get("ticker") or "").strip().upper()
            if not ticker or ticker in price_data:
                continue
            price_data[ticker] = _price_data_for_opportunity(opportunity, now)
        memory = build_session_outcome_memory(
            benchmark,
            scorecard,
            price_data,
            db_path,
            now=now,
        )
        _atomic_write(directory / "outcome_memory.json", memory)
        session_memories.append(memory)

    aggregate = aggregate_outcome_memory(session_memories)
    aggregate["source"] = {
        "market_validation": "BATCH_9H_COMPLETE_SESSIONS_ONLY",
        "decision_provenance": "LOCAL_LEDGER_READ_ONLY",
        "market_prices": "YAHOO_CHART_SIDECAR",
        "ledger_path_exported": False,
    }
    aggregate["safety"] = {
        **(aggregate.get("safety") or {}),
        "price_collection_sidecar_only": True,
        "ledger_mode": "READ_ONLY",
        "auto_write_judgment_bank": False,
        "automatic_agent_weight_changes": False,
        "committee_gate_change_authority": False,
        "risk_gate_change_authority": False,
        "capital_authority": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }
    _atomic_write(state_dir / "latest_outcome_learning.json", aggregate)
    browser = build_browser_summary(aggregate)
    _atomic_write(state_dir / "browser" / "outcome_learning.json", browser)
    return aggregate


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build Batch 9J outcome labels and governed learning-memory review inputs.")
    parser.add_argument("--db", help="Live IIOS ledger path. Reads are SQLite read-only.")
    parser.add_argument("--state-dir", default=str(DEFAULT_STATE_DIR))
    parser.add_argument("--lookback-sessions", type=int, default=DEFAULT_LOOKBACK_SESSIONS)
    parser.add_argument("--github-repo", default=os.getenv("IIOS_TELEMETRY_GITHUB_REPO"))
    parser.add_argument("--github-issue", type=int, default=int(os.getenv("IIOS_OUTCOME_LEARNING_GITHUB_ISSUE", "0") or 0))
    parser.add_argument("--stdout", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    state_dir = Path(args.state_dir).expanduser()
    memory = run_outcome_learning(
        db_path=args.db,
        state_dir=state_dir,
        lookback_sessions=max(1, min(int(args.lookback_sessions), 60)),
    )

    publish_status = "NOT_CONFIGURED"
    if args.github_repo or args.github_issue:
        if not args.github_repo or not args.github_issue:
            raise RuntimeError("Both --github-repo and --github-issue are required for outcome-learning publishing")
        _publish_private_issue(args.github_repo, args.github_issue, memory)
        publish_status = "PUBLISHED_PRIVATE_GITHUB_ISSUE"

    summary = {
        "status": "BATCH9J_OUTCOME_LEARNING_REFRESH_COMPLETE",
        "learning_status": memory.get("status"),
        "complete_session_count": memory.get("complete_session_count"),
        "outcome_count": memory.get("outcome_count"),
        "mature_5d_count": memory.get("mature_5d_count"),
        "pending_5d_count": memory.get("pending_5d_count"),
        "judgment_bank_review_queue_count": len(memory.get("judgment_bank_review_queue") or []),
        "browser_ready_snapshot": str(state_dir / "browser" / "outcome_learning.json"),
        "publish_status": publish_status,
        "ledger_mode": "READ_ONLY",
        "auto_write_judgment_bank": False,
        "live_execution": False,
    }
    print(json.dumps(memory if args.stdout else summary, indent=2 if args.stdout else None, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
