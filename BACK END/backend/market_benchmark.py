from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode

from batch8c_production_inputs import current_strict_governed_universe
from provider_hardening import _json_request

SCHEMA_VERSION = "batch9h-independent-market-benchmark-v1"
SOURCE = "BATCH_9H_INDEPENDENT_YAHOO_SCREENER_SIDECAR"
SCREENER_IDS = ("day_gainers", "day_losers", "most_actives")
DEFAULT_INTERVAL_SECONDS = 300
DEFAULT_MIN_ABS_MOVE_PCT = 3.0
DEFAULT_MIN_ABS_MOVE_WITH_VOLUME_PCT = 2.0
DEFAULT_MIN_VOLUME_RATIO = 1.5
DEFAULT_MIN_COVERAGE_PCT = 60.0


def _safe_float(value: Any, default: float | None = None) -> float | None:
    if isinstance(value, dict) and "raw" in value:
        value = value.get("raw")
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


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


def _canonical_symbol(value: Any) -> str:
    return str(value or "").strip().upper().replace(".", "-")


def _strict_universe_aliases() -> tuple[set[str], dict[str, str]]:
    governed = current_strict_governed_universe()
    if not isinstance(governed, dict):
        raise RuntimeError("STRICT_GOVERNED_UNIVERSE_UNAVAILABLE")
    if governed.get("verified_complete") is not True or governed.get("strict_membership") is not True:
        raise RuntimeError("STRICT_GOVERNED_UNIVERSE_NOT_VERIFIED")
    symbols: set[str] = set()
    aliases: dict[str, str] = {}
    for row in governed.get("symbols") or []:
        ticker = str(row.get("ticker") if isinstance(row, dict) else row or "").strip().upper()
        if not ticker:
            continue
        symbols.add(ticker)
        aliases[_canonical_symbol(ticker)] = ticker
    if not symbols:
        raise RuntimeError("STRICT_GOVERNED_UNIVERSE_EMPTY")
    return symbols, aliases


def _yahoo_screener(scr_id: str, count: int = 100) -> list[dict[str, Any]]:
    params = urlencode(
        {
            "formatted": "false",
            "lang": "en-US",
            "region": "US",
            "scrIds": scr_id,
            "count": max(10, min(int(count), 100)),
            "corsDomain": "finance.yahoo.com",
        }
    )
    errors: list[str] = []
    for host in ("query1.finance.yahoo.com", "query2.finance.yahoo.com"):
        try:
            payload = _json_request(
                url=f"https://{host}/v1/finance/screener/predefined/saved?{params}",
                provider="yahoo_9h_independent_benchmark",
                minimum_interval_seconds=0.18,
                retries=1,
                cache_ttl_seconds=45,
            )
            result = ((payload.get("finance") or {}).get("result") or [None])[0]
            quotes = result.get("quotes") if isinstance(result, dict) else None
            if isinstance(quotes, list):
                return [row for row in quotes if isinstance(row, dict)]
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{host}:{type(exc).__name__}:{exc}")
    raise RuntimeError(" | ".join(errors) or f"Yahoo screener unavailable: {scr_id}")


def collect_independent_snapshot(
    *,
    observed_at: datetime | None = None,
    count: int = 100,
) -> dict[str, Any]:
    observed_at = (observed_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
    symbols, aliases = _strict_universe_aliases()
    collected: dict[str, dict[str, Any]] = {}
    successful: list[str] = []
    errors: list[str] = []

    for screener_id in SCREENER_IDS:
        try:
            rows = _yahoo_screener(screener_id, count=count)
            successful.append(screener_id)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{screener_id}:{type(exc).__name__}:{exc}")
            continue
        for row in rows:
            ticker = aliases.get(_canonical_symbol(row.get("symbol")))
            if not ticker:
                continue
            item = collected.setdefault(
                ticker,
                {
                    "ticker": ticker,
                    "company": str(row.get("shortName") or row.get("longName") or ticker)[:240],
                    "screeners": set(),
                    "quote": row,
                },
            )
            item["screeners"].add(screener_id)
            if len(row) > len(item.get("quote") or {}):
                item["quote"] = row

    candidates: list[dict[str, Any]] = []
    for ticker, item in collected.items():
        quote = item.get("quote") or {}
        volume = _safe_float(quote.get("regularMarketVolume"), 0.0) or 0.0
        average_volume = (
            _safe_float(quote.get("averageDailyVolume3Month"))
            or _safe_float(quote.get("averageDailyVolume10Day"))
            or 0.0
        )
        volume_ratio = volume / average_volume if volume > 0 and average_volume > 0 else None
        candidates.append(
            {
                "ticker": ticker,
                "company": item["company"],
                "screeners": sorted(item["screeners"]),
                "current_price": _safe_float(quote.get("regularMarketPrice")),
                "change_pct": _safe_float(quote.get("regularMarketChangePercent")),
                "volume": volume or None,
                "average_volume": average_volume or None,
                "volume_ratio": round(volume_ratio, 4) if volume_ratio is not None else None,
                "market_cap": _safe_float(quote.get("marketCap")),
                "strict_governed_universe": True,
            }
        )
    candidates.sort(key=lambda row: abs(float(row.get("change_pct") or 0.0)), reverse=True)
    return {
        "schema_version": SCHEMA_VERSION,
        "source": SOURCE,
        "observed_at": observed_at.isoformat(),
        "governed_universe_count": len(symbols),
        "screeners_requested": list(SCREENER_IDS),
        "screeners_successful": sorted(successful),
        "snapshot_complete": set(successful) == set(SCREENER_IDS),
        "provider_errors": errors,
        "candidate_count": len(candidates),
        "candidates": candidates,
        "independent_of_iios_promotion_decisions": True,
        "ledger_read": False,
        "ledger_write": False,
        "live_execution": False,
    }


def _qualifies(
    row: dict[str, Any],
    *,
    min_abs_move_pct: float,
    min_abs_move_with_volume_pct: float,
    min_volume_ratio: float,
) -> bool:
    move = abs(float(row.get("change_pct") or 0.0))
    volume_ratio = float(row.get("volume_ratio") or 0.0)
    screeners = row.get("screeners") if isinstance(row.get("screeners"), list) else []
    if move >= min_abs_move_pct:
        return True
    if move >= min_abs_move_with_volume_pct and volume_ratio >= min_volume_ratio:
        return True
    return move >= min_abs_move_with_volume_pct and len(screeners) >= 2


def build_opportunity_benchmark(
    snapshots: list[dict[str, Any]],
    *,
    session_start: str | datetime,
    session_end: str | datetime,
    interval_seconds: int = DEFAULT_INTERVAL_SECONDS,
    min_abs_move_pct: float = DEFAULT_MIN_ABS_MOVE_PCT,
    min_abs_move_with_volume_pct: float = DEFAULT_MIN_ABS_MOVE_WITH_VOLUME_PCT,
    min_volume_ratio: float = DEFAULT_MIN_VOLUME_RATIO,
    min_coverage_pct: float = DEFAULT_MIN_COVERAGE_PCT,
) -> dict[str, Any]:
    start = session_start if isinstance(session_start, datetime) else _parse_time(session_start)
    end = session_end if isinstance(session_end, datetime) else _parse_time(session_end)
    if start is None or end is None or end <= start:
        raise ValueError("Valid session_start/session_end are required")
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    start = start.astimezone(timezone.utc)
    end = end.astimezone(timezone.utc)
    interval_seconds = max(60, int(interval_seconds))

    in_window: list[tuple[datetime, dict[str, Any]]] = []
    for snapshot in snapshots:
        observed = _parse_time(snapshot.get("observed_at"))
        if observed is None or observed < start or observed > end + timedelta(minutes=5):
            continue
        in_window.append((observed, snapshot))
    in_window.sort(key=lambda item: item[0])

    expected_samples = max(1, math.ceil((end - start).total_seconds() / interval_seconds))
    sample_count = len(in_window)
    coverage_pct = round(min(100.0, (sample_count / expected_samples) * 100.0), 2)
    all_screeners_seen: set[str] = set()
    complete_samples = 0
    provider_error_count = 0
    for _, snapshot in in_window:
        all_screeners_seen.update(str(x) for x in snapshot.get("screeners_successful") or [])
        complete_samples += int(snapshot.get("snapshot_complete") is True)
        provider_error_count += len(snapshot.get("provider_errors") or [])

    first_sample_at = in_window[0][0] if in_window else None
    last_sample_at = in_window[-1][0] if in_window else None
    opening_coverage = bool(first_sample_at and first_sample_at <= start + timedelta(minutes=20))
    closing_coverage = bool(last_sample_at and last_sample_at >= end - timedelta(minutes=15))
    benchmark_complete = bool(
        coverage_pct >= float(min_coverage_pct)
        and set(SCREENER_IDS).issubset(all_screeners_seen)
        and opening_coverage
        and closing_coverage
    )

    first_qualified: dict[str, dict[str, Any]] = {}
    peak_moves: dict[str, float] = {}
    for observed, snapshot in in_window:
        for row in snapshot.get("candidates") or []:
            if not isinstance(row, dict):
                continue
            ticker = str(row.get("ticker") or "").strip().upper()
            if not ticker:
                continue
            move = float(row.get("change_pct") or 0.0)
            if abs(move) > abs(peak_moves.get(ticker, 0.0)):
                peak_moves[ticker] = move
            if ticker in first_qualified:
                continue
            if not _qualifies(
                row,
                min_abs_move_pct=float(min_abs_move_pct),
                min_abs_move_with_volume_pct=float(min_abs_move_with_volume_pct),
                min_volume_ratio=float(min_volume_ratio),
            ):
                continue
            first_qualified[ticker] = {**row, "event_at": observed.isoformat()}

    opportunities: list[dict[str, Any]] = []
    for ticker, row in first_qualified.items():
        peak_move = peak_moves.get(ticker, float(row.get("change_pct") or 0.0))
        magnitude = abs(float(peak_move))
        importance = "HIGH" if magnitude >= 7.0 else "MEDIUM" if magnitude >= 4.0 else "LOW"
        opportunities.append(
            {
                "opportunity_id": f"9h_{start.date().isoformat()}_{ticker}",
                "ticker": ticker,
                "event_at": row["event_at"],
                "label": row.get("company") or ticker,
                "move_pct": round(float(peak_move), 4),
                "importance": importance,
                "source": SOURCE,
            }
        )
    opportunities.sort(key=lambda row: abs(float(row.get("move_pct") or 0.0)), reverse=True)

    return {
        "schema_version": SCHEMA_VERSION,
        "session_id": start.date().isoformat(),
        "session_start": start.isoformat(),
        "session_end": end.isoformat(),
        "benchmark_complete": benchmark_complete,
        "opportunities": opportunities,
        "benchmark_meta": {
            "source": SOURCE,
            "independent_of_iios_promotion_decisions": True,
            "expected_sample_count": expected_samples,
            "sample_count": sample_count,
            "coverage_pct": coverage_pct,
            "complete_sample_count": complete_samples,
            "provider_error_count": provider_error_count,
            "screeners_seen": sorted(all_screeners_seen),
            "opening_coverage": opening_coverage,
            "closing_coverage": closing_coverage,
            "first_sample_at": first_sample_at.isoformat() if first_sample_at else None,
            "last_sample_at": last_sample_at.isoformat() if last_sample_at else None,
            "thresholds": {
                "min_abs_move_pct": float(min_abs_move_pct),
                "min_abs_move_with_volume_pct": float(min_abs_move_with_volume_pct),
                "min_volume_ratio": float(min_volume_ratio),
            },
            "ledger_read": False,
            "ledger_write": False,
        },
        "safety": {
            "benchmark_only": True,
            "auto_tune_authority": False,
            "trade_execution_permission": False,
            "live_execution": False,
        },
    }
