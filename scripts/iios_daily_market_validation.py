#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import date, datetime, time as clock_time
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "BACK END" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from market_benchmark import build_opportunity_benchmark  # noqa: E402
from market_validation_learning import build_learning_report  # noqa: E402
from market_validation_scorecard import build_market_validation_scorecard  # noqa: E402

NEW_YORK = ZoneInfo("America/New_York")
DEFAULT_STATE_DIR = Path.home() / "Library" / "Application Support" / "IIOS" / "market-validation"
REPORT_HEADER = "IIOS MARKET VALIDATION — BATCH 9H READ ONLY"


def _session_bounds(session_date: date) -> tuple[datetime, datetime]:
    start = datetime.combine(session_date, clock_time(9, 30), tzinfo=NEW_YORK)
    end = datetime.combine(session_date, clock_time(16, 0), tzinfo=NEW_YORK)
    return start, end


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    output: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            output.append(value)
    return output


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    temporary.replace(path)


def _run_gh(*args: str) -> str:
    gh = shutil.which("gh")
    if not gh:
        raise RuntimeError("GitHub CLI (gh) is required for private validation publishing")
    result = subprocess.run([gh, *args], text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"gh {' '.join(args[:3])} failed: {(result.stderr or result.stdout).strip()[:1000]}")
    return result.stdout.strip()


def _require_private_repo(repo: str) -> None:
    private = _run_gh("api", f"repos/{repo}", "--jq", ".private").strip().lower()
    if private != "true":
        raise RuntimeError("Refusing market-validation publish: target GitHub repository must be private")


def _compact_remote_report(
    benchmark: dict[str, Any],
    scorecard: dict[str, Any],
    learning: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": "batch9h-remote-market-validation-v1",
        "generated_at": learning.get("generated_at"),
        "session_id": benchmark.get("session_id"),
        "benchmark_complete": benchmark.get("benchmark_complete"),
        "benchmark_meta": benchmark.get("benchmark_meta"),
        "metrics": scorecard.get("metrics"),
        "missed_opportunities": learning.get("missed_opportunities"),
        "detected_not_promoted": learning.get("detected_not_promoted"),
        "recommendations": learning.get("recommendations"),
        "status": learning.get("status"),
        "safety": {
            "market_validation_only": True,
            "ledger_mode": "READ_ONLY",
            "auto_apply_threshold_changes": False,
            "broker_connected": False,
            "live_capital_locked": True,
            "trade_execution_permission": False,
            "live_execution": False,
        },
    }


def _publish_private_issue(repo: str, issue: int, payload: dict[str, Any]) -> None:
    _require_private_repo(repo)
    body = (
        f"{REPORT_HEADER}\n\n"
        "Machine-updated end-of-session market-validation report. Benchmark collection is independent of IIOS promotion decisions. "
        "Recommendations are advisory only and cannot change trading authority.\n\n"
        "```json\n"
        + json.dumps(payload, indent=2, sort_keys=True, default=str)
        + "\n```\n"
    )
    _run_gh("api", "--method", "PATCH", f"repos/{repo}/issues/{issue}", "-f", f"body={body}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the Batch 9H independent market benchmark and grade IIOS against it.")
    parser.add_argument("--db", help="IIOS ledger path; defaults to IIOS_DB_PATH")
    parser.add_argument("--state-dir", default=str(DEFAULT_STATE_DIR))
    parser.add_argument("--session-date", help="YYYY-MM-DD; defaults to today in New York")
    parser.add_argument("--auto", action="store_true", help="Run only after 16:05 New York time and only once per session")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--github-repo", default=os.getenv("IIOS_TELEMETRY_GITHUB_REPO"))
    parser.add_argument("--github-issue", type=int, default=int(os.getenv("IIOS_MARKET_VALIDATION_GITHUB_ISSUE", "0") or 0))
    parser.add_argument("--stdout", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    now = datetime.now(NEW_YORK)
    try:
        session_date = date.fromisoformat(args.session_date) if args.session_date else now.date()
    except ValueError as exc:
        raise SystemExit(f"Invalid --session-date: {exc}") from exc

    if session_date.weekday() >= 5 and not args.force:
        print(json.dumps({"status": "SKIPPED_NON_MARKET_DAY", "session_date": session_date.isoformat()}))
        return 0

    start, end = _session_bounds(session_date)
    state_dir = Path(args.state_dir).expanduser()
    session_dir = state_dir / "reports" / session_date.isoformat()
    report_path = session_dir / "learning_report.json"

    if args.auto and not args.force:
        if session_date != now.date() or now < end.replace(hour=16, minute=5):
            print(json.dumps({"status": "SKIPPED_BEFORE_VALIDATION_WINDOW", "as_of": now.isoformat()}))
            return 0
        if report_path.exists():
            print(json.dumps({"status": "SKIPPED_ALREADY_VALIDATED", "report": str(report_path)}))
            return 0

    raw_path = state_dir / "benchmark_raw" / f"{session_date.isoformat()}.jsonl"
    snapshots = _read_jsonl(raw_path)
    if not snapshots and not args.force:
        print(json.dumps({"status": "SKIPPED_NO_BENCHMARK_SAMPLES", "session_date": session_date.isoformat(), "raw_path": str(raw_path)}))
        return 0

    benchmark = build_opportunity_benchmark(
        snapshots,
        session_start=start,
        session_end=end,
    )
    scorecard = build_market_validation_scorecard(
        benchmark,
        args.db,
    )
    learning = build_learning_report(
        scorecard,
        benchmark_meta=benchmark.get("benchmark_meta") or {},
    )

    _atomic_write(session_dir / "benchmark.json", benchmark)
    _atomic_write(session_dir / "scorecard.json", scorecard)
    _atomic_write(report_path, learning)
    _atomic_write(state_dir / "latest_market_validation.json", _compact_remote_report(benchmark, scorecard, learning))

    publish_status = "NOT_CONFIGURED"
    if args.github_repo or args.github_issue:
        if not args.github_repo or not args.github_issue:
            raise RuntimeError("Both --github-repo and --github-issue are required for market-validation publishing")
        remote = _compact_remote_report(benchmark, scorecard, learning)
        _publish_private_issue(args.github_repo, args.github_issue, remote)
        publish_status = "PUBLISHED_PRIVATE_GITHUB_ISSUE"

    summary = {
        "status": "BATCH9H_DAILY_MARKET_VALIDATION_COMPLETE",
        "session_date": session_date.isoformat(),
        "benchmark_complete": benchmark.get("benchmark_complete"),
        "benchmark_opportunity_count": len(benchmark.get("opportunities") or []),
        "detection_rate_pct": (scorecard.get("metrics") or {}).get("detection_rate_pct"),
        "opportunity_miss_rate_pct": (scorecard.get("metrics") or {}).get("opportunity_miss_rate_pct"),
        "paper_fill_count": (scorecard.get("metrics") or {}).get("paper_fill_count"),
        "learning_status": learning.get("status"),
        "recommendation_count": len(learning.get("recommendations") or []),
        "publish_status": publish_status,
        "report": str(report_path),
        "ledger_mode": "READ_ONLY",
        "auto_apply_threshold_changes": False,
        "live_execution": False,
    }
    print(json.dumps(_compact_remote_report(benchmark, scorecard, learning) if args.stdout else summary, indent=2 if args.stdout else None, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
