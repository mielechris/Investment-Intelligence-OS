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
    "CA_BUNDLE_UNAVAILABLE",
    "TLS_VALIDATION_FAILED",
    "PAGINATION_INCOMPLETE",
    "STALE_RESPONSE",
    "WRONG_SESSION_DATE",
    "MALFORMED_ROWS",
    "COUNT_OUT_OF_RANGE",
    "SOURCE_UNAVAILABLE",
}
PROVIDER_CATEGORIES = {
    "NASDAQ",
    "SP_DJI",
    "BLACKROCK_ISHARES_IQQ",
    "BLACKROCK_ISHARES_IVV",
}
PROVIDER_ROLES = {"OFFICIAL_PRIMARY", "GOVERNED_FALLBACK", "SOURCE"}
TRUST_SOURCES = {"SYSTEM_CA", "CERTIFI_CA"}
SOURCE_MODES = {
    "OFFICIAL_WEB_SOURCE",
    "GOVERNED_INDEX_TRACKER_MIRROR",
    "GOVERNED_LOCAL_FILE",
    "ERROR",
}
SOURCE_IDS = {
    "SP500_SP_DJI_OFFICIAL",
    "SP500_GOVERNED_IVV",
    "SP500_OPERATOR_GOVERNED_FILE",
    "SP500_SOURCE_ERROR",
    "NASDAQ100_OFFICIAL_COMPANIES",
    "NASDAQ100_GOVERNED_IQQ",
    "NASDAQ100_OPERATOR_GOVERNED_FILE",
    "NASDAQ100_SOURCE_ERROR",
}
AUTHORITY = {
    "ledger_read": False,
    "ledger_write": False,
    "trade_execution_permission": False,
    "broker_connected": False,
    "live_execution": False,
}


class UniverseRefreshIncomplete(RuntimeError):
    def __init__(self, diagnostics: dict) -> None:
        super().__init__("OFFICIAL_BENCHMARK_UNIVERSE_REFRESH_INCOMPLETE")
        self.diagnostics = diagnostics


class UnsafeArtifact(RuntimeError):
    pass


def _has_explicit_no_authority(payload: object) -> bool:
    return isinstance(payload, dict) and all(
        key in payload and payload.get(key) is False for key in AUTHORITY
    )


def _contains_url(value: object) -> bool:
    if isinstance(value, str):
        lowered = value.lower()
        return "http://" in lowered or "https://" in lowered
    if isinstance(value, dict):
        return any(_contains_url(key) or _contains_url(item) for key, item in value.items())
    if isinstance(value, (list, tuple)):
        return any(_contains_url(item) for item in value)
    return False


def _require_safe_artifact(payload: object) -> None:
    if not _has_explicit_no_authority(payload) or _contains_url(payload):
        raise UnsafeArtifact("UNSAFE_ARTIFACT_REJECTED")


def _sanitize_snapshot(payload: object) -> dict:
    snapshot = dict(payload) if isinstance(payload, dict) else {}
    errors = snapshot.get("provider_errors")
    snapshot["provider_errors"] = sorted(
        {
            _failure_category(error)
            for error in (errors if isinstance(errors, list) else [])
        }
    )
    snapshot.update(AUTHORITY)
    _require_safe_artifact(snapshot)
    return snapshot


def _success_status(snapshot: dict, session_date: str) -> dict:
    status = {
        "status": "BENCHMARK_SAMPLE_RECORDED",
        "session_date": session_date,
        "observed_at": snapshot.get("observed_at"),
        "candidate_count": snapshot.get("candidate_count"),
        "snapshot_complete": snapshot.get("snapshot_complete"),
        "provider_error_count": len(snapshot.get("provider_errors") or []),
        "artifact_id": f"benchmark_raw/{session_date}.jsonl",
        "source": snapshot.get("source"),
        "governed_universe_source": snapshot.get("governed_universe_source"),
        "governed_universe_count": snapshot.get("governed_universe_count"),
        "independent_of_iios_promotion_decisions": True,
        **AUTHORITY,
    }
    _require_safe_artifact(status)
    return status


def _failure_status(exc: Exception, now: datetime) -> dict:
    diagnostics = (
        exc.diagnostics
        if isinstance(exc, UniverseRefreshIncomplete)
        else {
            "failure_category": _failure_category(exc),
            **AUTHORITY,
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
        **AUTHORITY,
    }
    _require_safe_artifact(failure)
    return failure


def _failure_category(error: object) -> str:
    text = str(error or "").lower()
    if "ca_bundle_unavailable" in text:
        return "CA_BUNDLE_UNAVAILABLE"
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
                "provider_category": (
                    row.get("source_mode")
                    if row.get("source_mode") in SOURCE_MODES
                    else "ERROR"
                ),
                "source_id": (
                    row.get("source_id")
                    if row.get("source_id") in SOURCE_IDS
                    else f"{index_key}_SOURCE_ERROR"
                ),
                "trust_source": (
                    row.get("trust_source")
                    if row.get("trust_source") in {"SYSTEM_CA", "CERTIFI_CA"}
                    else None
                ),
                "provider_attempts": [
                    {
                        "provider": (
                            attempt.get("provider")
                            if attempt.get("provider") in PROVIDER_CATEGORIES
                            else "UNKNOWN"
                        ),
                        "role": (
                            attempt.get("role")
                            if attempt.get("role") in PROVIDER_ROLES
                            else "SOURCE"
                        ),
                        "result": (
                            attempt.get("result")
                            if attempt.get("result") in FAILURE_CATEGORIES | {"SUCCESS"}
                            else "SOURCE_UNAVAILABLE"
                        ),
                        "trust_source": (
                            attempt.get("trust_source")
                            if attempt.get("trust_source") in TRUST_SOURCES
                            else None
                        ),
                    }
                    for attempt in (row.get("source_attempts") or [])
                    if isinstance(attempt, dict)
                ],
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
        **AUTHORITY,
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
        and _has_explicit_no_authority(payload)
        and not _contains_url(payload)
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
        "independent_of_iios_promotion_decisions": True,
        **AUTHORITY,
    }
    _require_safe_artifact(payload)
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
        snapshot = _sanitize_snapshot(snapshot)
    except Exception as exc:  # noqa: BLE001
        failure = _failure_status(exc, now)
        _atomic_write(
            state_dir / "collector_status.json",
            failure,
        )
        print(json.dumps(failure, sort_keys=True))
        return 2

    session_date = now.date().isoformat()
    artifact_path = (
        state_dir
        / "benchmark_raw"
        / f"{session_date}.jsonl"
    )
    _append_jsonl(artifact_path, snapshot)
    status = _success_status(snapshot, session_date)
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
