#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, time as clock_time, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "BACK END" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import production_index_universe  # noqa: E402
import production_index_universe_resilient  # noqa: E402
from market_benchmark import collect_independent_snapshot  # noqa: E402

NEW_YORK = ZoneInfo("America/New_York")
DEFAULT_STATE_DIR = (
    Path.home()
    / "Library"
    / "Application Support"
    / "IIOS"
    / "market-validation"
)
UNIVERSE_CACHE_NAME = "benchmark_universe.json"
UNIVERSE_CACHE_MAX_AGE_HOURS = 24.0
UNIVERSE_SCHEMA_VERSION = "batch9h-benchmark-universe-v1"

FAILURE_CATEGORIES = {
    "HTTP_FORBIDDEN",
    "RATE_LIMITED",
    "TIMEOUT",
    "TLS_VALIDATION_FAILED",
    "PAGINATION_INCOMPLETE",
    "STALE_RESPONSE",
    "WRONG_SESSION_DATE",
    "MALFORMED_ROWS",
    "COUNT_OUT_OF_RANGE",
    "SOURCE_UNAVAILABLE",
}


class UniverseRefreshIncomplete(RuntimeError):
    def __init__(self, diagnostics: dict) -> None:
        super().__init__("OFFICIAL_BENCHMARK_UNIVERSE_REFRESH_INCOMPLETE")
        self.diagnostics = diagnostics


def _failure_category(error: object) -> str:
    text = str(error or "").lower()
    if "403" in text or "forbidden" in text:
        return "HTTP_FORBIDDEN"
    if "429" in text or "rate limit" in text:
        return "RATE_LIMITED"
    if "timed out" in text or "timeout" in text:
        return "TIMEOUT"
    if "certificate" in text or "tls" in text or "ssl" in text:
        return "TLS_VALIDATION_FAILED"
    if "pagination" in text or "next page" in text:
        return "PAGINATION_INCOMPLETE"
    if "stale" in text or "expired" in text:
        return "STALE_RESPONSE"
    if "session date" in text or "wrong date" in text:
        return "WRONG_SESSION_DATE"
    if "malformed" in text or "invalid symbol" in text:
        return "MALFORMED_ROWS"
    if "parsed" in text or "governed range" in text or "count" in text:
        return "COUNT_OUT_OF_RANGE"
    return "SOURCE_UNAVAILABLE"


def _refresh_diagnostics(capture: object) -> dict:
    payload = capture if isinstance(capture, dict) else {}
    indexes = payload.get("indexes") if isinstance(payload.get("indexes"), dict) else {}
    sources: list[dict] = []
    for index_key in ("SP500", "NASDAQ100"):
        row = indexes.get(index_key) if isinstance(indexes.get(index_key), dict) else {}
        minimum, maximum = production_index_universe.EXPECTED_COUNTS[index_key]
        received = max(0, int(row.get("received_count", row.get("symbol_count", 0)) or 0))
        valid = max(0, int(row.get("valid_count", row.get("symbol_count", 0)) or 0))
        rejected = max(0, int(row.get("rejected_count", received - valid) or 0))
        verified = row.get("verified_complete") is True
        sources.append(
            {
                "index": index_key,
                "expected_min": minimum,
                "expected_max": maximum,
                "received": received,
                "valid": valid,
                "rejected": rejected,
                "duplicate_count": max(0, int(row.get("duplicate_count", 0) or 0)),
                "provider_category": str(row.get("source_mode") or "UNKNOWN")[:80],
                "failure_category": None if verified else _failure_category(row.get("error")),
                "verified_complete": verified,
            }
        )
    return {
        "failure_category": "OFFICIAL_UNIVERSE_INCOMPLETE",
        "expected": {
            "SP500": {"minimum": 490, "maximum": 520},
            "NASDAQ100": {"minimum": 95, "maximum": 110},
        },
        "received": sum(row["received"] for row in sources),
        "valid": sum(row["valid"] for row in sources),
        "rejected": sum(row["rejected"] for row in sources),
        "sources": sources,
        "verified_complete": payload.get("verified_complete") is True,
        "strict_membership": payload.get("strict_membership") is True,
        "ledger_read": False,
        "ledger_write": False,
        "trade_execution_permission": False,
        "broker_connected": False,
        "live_execution": False,
    }


def _regular_session(now: datetime) -> tuple[datetime, datetime]:
    local = now.astimezone(NEW_YORK)
    start = datetime.combine(
        local.date(),
        clock_time(9, 30),
        tzinfo=NEW_YORK,
    )
    end = datetime.combine(
        local.date(),
        clock_time(16, 0),
        tzinfo=NEW_YORK,
    )
    return start, end


def _parse_time(value) -> datetime | None:
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


def _atomic_write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _append_jsonl(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(payload, sort_keys=True, default=str) + "\n"
        )
        handle.flush()
        os.fsync(handle.fileno())


def _valid_universe(payload: dict) -> bool:
    return bool(
        isinstance(payload, dict)
        and payload.get("verified_complete") is True
        and payload.get("strict_membership") is True
        and isinstance(payload.get("symbols"), list)
        and payload.get("symbols")
    )


def _cache_fresh(payload: dict, now: datetime) -> bool:
    if not _valid_universe(payload):
        return False
    cached_at = _parse_time(
        payload.get("cached_at")
        or payload.get("created_at")
        or payload.get("as_of")
    )
    if cached_at is None:
        return False
    age_hours = max(
        0.0,
        (now.astimezone(timezone.utc) - cached_at).total_seconds()
        / 3600.0,
    )
    return age_hours <= UNIVERSE_CACHE_MAX_AGE_HOURS


def _load_cached_universe(
    path: Path,
    now: datetime,
) -> dict | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if _cache_fresh(payload, now) else None


def _refresh_official_universe(
    path: Path,
    now: datetime,
) -> dict:
    capture = production_index_universe_resilient.refresh_official_index_universe()
    if (
        not isinstance(capture, dict)
        or capture.get("verified_complete") is not True
        or capture.get("strict_membership") is not True
        or not capture.get("symbols")
    ):
        raise UniverseRefreshIncomplete(_refresh_diagnostics(capture))

    payload = {
        "schema_version": UNIVERSE_SCHEMA_VERSION,
        "source": "OFFICIAL_SP500_PLUS_NASDAQ100_BENCHMARK_SIDECAR",
        "verified_complete": True,
        "strict_membership": True,
        "symbols": capture.get("symbols") or [],
        "symbol_count": int(capture.get("symbol_count") or 0),
        "source_lineage": capture.get("source_lineage") or [],
        "official_capture_created_at": capture.get("created_at"),
        "cached_at": now.astimezone(timezone.utc).isoformat(),
        "ledger_read": False,
        "ledger_write": False,
        "independent_of_iios_promotion_decisions": True,
        "live_execution": False,
    }
    _atomic_write(path, payload)
    return payload


def _load_or_refresh_universe(
    state_dir: Path,
    now: datetime,
) -> dict:
    path = state_dir / UNIVERSE_CACHE_NAME
    cached = _load_cached_universe(path, now)
    if cached is not None:
        return cached
    return _refresh_official_universe(path, now)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Collect an independent IIOS market-validation benchmark "
            "sample without touching the ledger."
        )
    )
    parser.add_argument(
        "--state-dir",
        default=str(DEFAULT_STATE_DIR),
    )
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--stdout", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    state_dir = Path(args.state_dir).expanduser()
    now = datetime.now(NEW_YORK)
    start, end = _regular_session(now)

    if now.weekday() >= 5 and not args.force:
        print(
            json.dumps(
                {
                    "status": "SKIPPED_NON_MARKET_DAY",
                    "as_of": now.isoformat(),
                }
            )
        )
        return 0
    if not args.force and not (start <= now <= end):
        print(
            json.dumps(
                {
                    "status": "SKIPPED_OUTSIDE_REGULAR_SESSION",
                    "as_of": now.isoformat(),
                }
            )
        )
        return 0

    try:
        governed_universe = _load_or_refresh_universe(
            state_dir,
            now,
        )
        snapshot = collect_independent_snapshot(
            governed_universe=governed_universe,
            observed_at=now,
        )
    except Exception as exc:  # noqa: BLE001
        diagnostics = (
            exc.diagnostics
            if isinstance(exc, UniverseRefreshIncomplete)
            else {
                "failure_category": _failure_category(exc),
                "ledger_read": False,
                "ledger_write": False,
                "trade_execution_permission": False,
                "broker_connected": False,
                "live_execution": False,
            }
        )
        failure = {
            "status": "BENCHMARK_COLLECTION_FAILED",
            "observed_at": now.isoformat(),
            "error_code": (
                "OFFICIAL_BENCHMARK_UNIVERSE_REFRESH_INCOMPLETE"
                if isinstance(exc, UniverseRefreshIncomplete)
                else "BENCHMARK_COLLECTION_SOURCE_ERROR"
            ),
            "diagnostics": diagnostics,
            "ledger_read": False,
            "ledger_write": False,
            "trade_execution_permission": False,
            "broker_connected": False,
            "live_execution": False,
        }
        _atomic_write(
            state_dir / "collector_status.json",
            failure,
        )
        print(json.dumps(failure, sort_keys=True))
        return 2

    session_date = now.date().isoformat()
    raw_path = (
        state_dir
        / "benchmark_raw"
        / f"{session_date}.jsonl"
    )
    _append_jsonl(raw_path, snapshot)
    status = {
        "status": "BENCHMARK_SAMPLE_RECORDED",
        "session_date": session_date,
        "observed_at": snapshot.get("observed_at"),
        "candidate_count": snapshot.get("candidate_count"),
        "snapshot_complete": snapshot.get("snapshot_complete"),
        "provider_error_count": len(
            snapshot.get("provider_errors") or []
        ),
        "raw_path": str(raw_path),
        "source": snapshot.get("source"),
        "governed_universe_source": snapshot.get(
            "governed_universe_source"
        ),
        "governed_universe_count": snapshot.get(
            "governed_universe_count"
        ),
        "independent_of_iios_promotion_decisions": True,
        "ledger_read": False,
        "ledger_write": False,
        "live_execution": False,
    }
    _atomic_write(
        state_dir / "collector_status.json",
        status,
    )
    print(
        json.dumps(
            snapshot if args.stdout else status,
            indent=2 if args.stdout else None,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
