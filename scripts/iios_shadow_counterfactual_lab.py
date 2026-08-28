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

from shadow_counterfactual import (  # noqa: E402
    aggregate_counterfactual_sessions,
    build_session_counterfactual,
)

NEW_YORK = ZoneInfo("America/New_York")
DEFAULT_STATE_DIR = Path.home() / "Library" / "Application Support" / "IIOS" / "market-validation"
REPORT_HEADER = "IIOS SHADOW STRATEGY — BATCH 9I READ ONLY"
DEFAULT_MAX_SESSIONS = 20


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _run_gh(*args: str) -> str:
    gh = shutil.which("gh")
    if not gh:
        raise RuntimeError("GitHub CLI (gh) is required for private shadow publishing")
    result = subprocess.run(
        [gh, *args],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"gh {' '.join(args[:3])} failed: "
            f"{(result.stderr or result.stdout).strip()[:1000]}"
        )
    return result.stdout.strip()


def _require_private_repo(repo: str) -> None:
    private = _run_gh(
        "api",
        f"repos/{repo}",
        "--jq",
        ".private",
    ).strip().lower()
    if private != "true":
        raise RuntimeError(
            "Refusing shadow-strategy publish: target GitHub repository must be private"
        )


def _compact_remote_report(
    rollup: dict[str, Any],
    latest_session: dict[str, Any] | None,
) -> dict[str, Any]:
    scenarios = list(rollup.get("scenario_rollup") or [])
    scenarios.sort(
        key=lambda row: (
            int((row.get("vs_baseline") or {}).get("marginal_captured_count") or 0),
            -int((row.get("vs_baseline") or {}).get("marginal_extra_nonbenchmark_ticker_count") or 0),
        ),
        reverse=True,
    )
    breadth = []
    if isinstance(latest_session, dict):
        breadth = latest_session.get("radar_breadth_analysis") or []
    return {
        "schema_version": "batch9i-remote-shadow-strategy-v1",
        "generated_at": rollup.get("generated_at"),
        "status": rollup.get("status"),
        "complete_session_count": rollup.get("complete_session_count"),
        "minimum_complete_sessions_for_advice": rollup.get(
            "minimum_complete_sessions_for_advice"
        ),
        "session_ids": rollup.get("session_ids"),
        "baseline": rollup.get("baseline"),
        "top_shadow_scenarios": scenarios[:8],
        "advisory_frontier": rollup.get("advisory_frontier"),
        "recommendations": rollup.get("recommendations"),
        "latest_session_id": (
            latest_session.get("session_id")
            if isinstance(latest_session, dict)
            else None
        ),
        "latest_radar_breadth_analysis": breadth,
        "safety": {
            "shadow_only": True,
            "ledger_mode": "READ_ONLY",
            "advisory_only": True,
            "auto_apply_threshold_changes": False,
            "committee_gate_change_authority": False,
            "risk_gate_change_authority": False,
            "capital_authority": False,
            "trade_execution_permission": False,
            "live_execution": False,
        },
    }


def _publish_private_issue(
    repo: str,
    issue: int,
    payload: dict[str, Any],
) -> None:
    _require_private_repo(repo)
    body = (
        f"{REPORT_HEADER}\n\n"
        "Machine-updated shadow/counterfactual analysis over complete Batch 9H market-validation sessions. "
        "Results are advisory only; this process cannot change factory thresholds or execution authority.\n\n"
        "```json\n"
        + json.dumps(payload, indent=2, sort_keys=True, default=str)
        + "\n```\n"
    )
    _run_gh(
        "api",
        "--method",
        "PATCH",
        f"repos/{repo}/issues/{issue}",
        "-f",
        f"body={body}",
    )


def _complete_report_dirs(state_dir: Path) -> list[Path]:
    reports_root = state_dir / "reports"
    if not reports_root.exists():
        return []
    output: list[Path] = []
    for path in reports_root.iterdir():
        if not path.is_dir():
            continue
        benchmark = _read_json(path / "benchmark.json")
        scorecard = _read_json(path / "scorecard.json")
        if not benchmark or not scorecard:
            continue
        if benchmark.get("benchmark_complete") is not True:
            continue
        output.append(path)
    output.sort(key=lambda path: path.name)
    return output


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate alternative IIOS radar/promotion configurations in "
            "read-only shadow mode against complete Batch 9H benchmarks."
        )
    )
    parser.add_argument("--db", help="Live IIOS ledger path; read-only only")
    parser.add_argument("--state-dir", default=str(DEFAULT_STATE_DIR))
    parser.add_argument("--max-sessions", type=int, default=DEFAULT_MAX_SESSIONS)
    parser.add_argument("--min-complete-sessions", type=int, default=5)
    parser.add_argument("--auto", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--github-repo", default=os.getenv("IIOS_TELEMETRY_GITHUB_REPO"))
    parser.add_argument(
        "--github-issue",
        type=int,
        default=int(os.getenv("IIOS_SHADOW_STRATEGY_GITHUB_ISSUE", "0") or 0),
    )
    parser.add_argument("--stdout", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    now = datetime.now(NEW_YORK)
    state_dir = Path(args.state_dir).expanduser()
    output_dir = state_dir / "shadow_strategy"
    latest_path = output_dir / "latest_shadow_counterfactual.json"

    if args.auto and not args.force:
        validation_time = datetime.combine(
            now.date(),
            clock_time(16, 20),
            tzinfo=NEW_YORK,
        )
        if now.weekday() >= 5:
            print(json.dumps({"status": "SKIPPED_NON_MARKET_DAY"}))
            return 0
        if now < validation_time:
            print(
                json.dumps(
                    {
                        "status": "SKIPPED_BEFORE_SHADOW_WINDOW",
                        "as_of": now.isoformat(),
                    }
                )
            )
            return 0

    report_dirs = _complete_report_dirs(state_dir)
    max_sessions = max(1, min(int(args.max_sessions), 60))
    report_dirs = report_dirs[-max_sessions:]
    if not report_dirs:
        print(
            json.dumps(
                {
                    "status": "SKIPPED_NO_COMPLETE_9H_SESSIONS",
                    "state_dir": str(state_dir),
                }
            )
        )
        return 0

    previous = _read_json(latest_path)
    latest_session_id = report_dirs[-1].name
    if (
        args.auto
        and not args.force
        and previous
        and previous.get("latest_session_id") == latest_session_id
        and int(previous.get("complete_session_count") or 0) == len(report_dirs)
    ):
        print(
            json.dumps(
                {
                    "status": "SKIPPED_ALREADY_EVALUATED",
                    "latest_session_id": latest_session_id,
                }
            )
        )
        return 0

    session_results: list[dict[str, Any]] = []
    for report_dir in report_dirs:
        benchmark = _read_json(report_dir / "benchmark.json")
        scorecard = _read_json(report_dir / "scorecard.json")
        if not benchmark or not scorecard:
            continue
        result = build_session_counterfactual(
            benchmark,
            scorecard,
            args.db,
        )
        session_results.append(result)
        _atomic_write(
            output_dir / "sessions" / f"{report_dir.name}.json",
            result,
        )

    rollup = aggregate_counterfactual_sessions(
        session_results,
        min_complete_sessions=max(1, int(args.min_complete_sessions)),
    )
    latest_session = session_results[-1] if session_results else None
    remote = _compact_remote_report(rollup, latest_session)
    local = {
        **remote,
        "session_results": session_results,
        "source": {
            "benchmark": "BATCH_9H_INDEPENDENT_MARKET_VALIDATION",
            "factory_cycles": "LOCAL_LEDGER_READ_ONLY",
        },
    }
    _atomic_write(latest_path, local)

    publish_status = "NOT_CONFIGURED"
    if args.github_repo or args.github_issue:
        if not args.github_repo or not args.github_issue:
            raise RuntimeError(
                "Both --github-repo and --github-issue are required for shadow publishing"
            )
        _publish_private_issue(args.github_repo, args.github_issue, remote)
        publish_status = "PUBLISHED_PRIVATE_GITHUB_ISSUE"

    summary = {
        "status": "BATCH9I_SHADOW_COUNTERFACTUAL_COMPLETE",
        "shadow_status": rollup.get("status"),
        "complete_session_count": rollup.get("complete_session_count"),
        "latest_session_id": latest_session_id,
        "recommendation_count": len(rollup.get("recommendations") or []),
        "publish_status": publish_status,
        "output": str(latest_path),
        "ledger_mode": "READ_ONLY",
        "auto_apply_threshold_changes": False,
        "live_execution": False,
    }
    print(
        json.dumps(
            remote if args.stdout else summary,
            indent=2 if args.stdout else None,
            sort_keys=True,
            default=str,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
