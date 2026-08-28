#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, time as clock_time
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "BACK END" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from market_benchmark import collect_independent_snapshot  # noqa: E402

NEW_YORK = ZoneInfo("America/New_York")
DEFAULT_STATE_DIR = Path.home() / "Library" / "Application Support" / "IIOS" / "market-validation"


def _regular_session(now: datetime) -> tuple[datetime, datetime]:
    local = now.astimezone(NEW_YORK)
    start = datetime.combine(local.date(), clock_time(9, 30), tzinfo=NEW_YORK)
    end = datetime.combine(local.date(), clock_time(16, 0), tzinfo=NEW_YORK)
    return start, end


def _atomic_write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def _append_jsonl(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, default=str) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect an independent IIOS market-validation benchmark sample without touching the ledger.")
    parser.add_argument("--state-dir", default=str(DEFAULT_STATE_DIR))
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--stdout", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    state_dir = Path(args.state_dir).expanduser()
    now = datetime.now(NEW_YORK)
    start, end = _regular_session(now)

    if now.weekday() >= 5 and not args.force:
        print(json.dumps({"status": "SKIPPED_NON_MARKET_DAY", "as_of": now.isoformat()}))
        return 0
    if not args.force and not (start <= now <= end):
        print(json.dumps({"status": "SKIPPED_OUTSIDE_REGULAR_SESSION", "as_of": now.isoformat()}))
        return 0

    try:
        snapshot = collect_independent_snapshot(observed_at=now)
    except Exception as exc:  # noqa: BLE001
        failure = {
            "status": "BENCHMARK_COLLECTION_FAILED",
            "observed_at": now.isoformat(),
            "error": f"{type(exc).__name__}: {exc}"[:1200],
            "ledger_read": False,
            "ledger_write": False,
            "live_execution": False,
        }
        _atomic_write(state_dir / "collector_status.json", failure)
        print(json.dumps(failure, sort_keys=True))
        return 2

    session_date = now.date().isoformat()
    raw_path = state_dir / "benchmark_raw" / f"{session_date}.jsonl"
    _append_jsonl(raw_path, snapshot)
    status = {
        "status": "BENCHMARK_SAMPLE_RECORDED",
        "session_date": session_date,
        "observed_at": snapshot.get("observed_at"),
        "candidate_count": snapshot.get("candidate_count"),
        "snapshot_complete": snapshot.get("snapshot_complete"),
        "provider_error_count": len(snapshot.get("provider_errors") or []),
        "raw_path": str(raw_path),
        "source": snapshot.get("source"),
        "independent_of_iios_promotion_decisions": True,
        "ledger_read": False,
        "ledger_write": False,
        "live_execution": False,
    }
    _atomic_write(state_dir / "collector_status.json", status)
    print(json.dumps(snapshot if args.stdout else status, indent=2 if args.stdout else None, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
