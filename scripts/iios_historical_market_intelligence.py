#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import io
import json
import math
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus
from urllib.request import Request, urlopen

SCHEMA_VERSION = "batch10h-historical-market-intelligence-v1"
DEFAULT_STATE_DIR = Path.home() / "Library" / "Application Support" / "IIOS" / "market-validation"
DEFAULT_TELEMETRY_DIR = Path.home() / "Library" / "Application Support" / "IIOS" / "telemetry"
DEFAULT_RESEARCH_DIR = Path.home() / "Library" / "Application Support" / "IIOS" / "historical-research"
REFRESH_TTL_SECONDS = 6 * 60 * 60
FORWARD_HORIZONS = (1, 5, 20, 60)
CORE_TARGETS = [
    {"symbol": "^SPX", "label": "S&P 500 Index", "class": "MARKET_INDEX"},
    {"symbol": "^DJI", "label": "Dow Jones Industrial Average", "class": "MARKET_INDEX"},
    {"symbol": "^NDQ", "label": "Nasdaq Composite", "class": "MARKET_INDEX"},
    {"symbol": "SPY", "label": "SPDR S&P 500 ETF", "class": "MARKET_ETF"},
    {"symbol": "QQQ", "label": "Invesco QQQ", "class": "MARKET_ETF"},
    {"symbol": "IWM", "label": "iShares Russell 2000 ETF", "class": "MARKET_ETF"},
    {"symbol": "SMH", "label": "VanEck Semiconductor ETF", "class": "SECTOR_ETF"},
    {"symbol": "XLF", "label": "Financial Select Sector SPDR", "class": "SECTOR_ETF"},
    {"symbol": "XLE", "label": "Energy Select Sector SPDR", "class": "SECTOR_ETF"},
]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists() or not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    tmp.replace(path)


def _float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _rows(value: Any) -> list[dict[str, Any]]:
    return [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []


def _normalize_symbol(symbol: str) -> str:
    return str(symbol or "").strip().upper().replace(" ", "")


def _stooq_symbol(symbol: str) -> str:
    text = _normalize_symbol(symbol).lower()
    if text.startswith("^") or "." in text:
        return text
    return f"{text}.us"


def _extract_targets(scorecard: dict[str, Any], telemetry: dict[str, Any]) -> list[dict[str, Any]]:
    targets = [dict(item) for item in CORE_TARGETS]
    source = scorecard.get("input") if isinstance(scorecard.get("input"), dict) else {}
    opportunities = _rows(source.get("opportunities")) or _rows(scorecard.get("opportunities"))
    for row in opportunities:
        symbol = _normalize_symbol(row.get("ticker") or row.get("symbol"))
        if not symbol:
            continue
        targets.append({
            "symbol": symbol,
            "label": str(row.get("company") or row.get("name") or symbol),
            "class": "CURRENT_OPPORTUNITY",
            "event_move_pct": _float(row.get("move_pct")),
        })
    fund = telemetry.get("paper_fund") if isinstance(telemetry.get("paper_fund"), dict) else {}
    for row in _rows(fund.get("positions")):
        symbol = _normalize_symbol(row.get("ticker") or row.get("symbol"))
        if symbol:
            targets.append({"symbol": symbol, "label": symbol, "class": "PAPER_POSITION"})
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in targets:
        symbol = _normalize_symbol(item.get("symbol"))
        if not symbol or symbol in seen:
            continue
        seen.add(symbol)
        item["symbol"] = symbol
        deduped.append(item)
    return deduped[:32]


def _parse_history_csv(text: str) -> list[dict[str, Any]]:
    parsed: list[dict[str, Any]] = []
    for row in csv.DictReader(io.StringIO(text)):
        date = str(row.get("Date") or row.get("date") or "").strip()
        close = _float(row.get("Close") or row.get("close"))
        if not date or close is None or close <= 0:
            continue
        parsed.append({
            "date": date,
            "open": _float(row.get("Open") or row.get("open")),
            "high": _float(row.get("High") or row.get("high")),
            "low": _float(row.get("Low") or row.get("low")),
            "close": close,
            "volume": _float(row.get("Volume") or row.get("volume")),
        })
    parsed.sort(key=lambda item: item["date"])
    return parsed


def _fetch_stooq_history(symbol: str) -> tuple[str, str]:
    normalized = _stooq_symbol(symbol)
    url = f"https://stooq.com/q/d/l/?s={quote_plus(normalized)}&i=d"
    request = Request(url, headers={"User-Agent": "Investment-Intelligence-OS/1.0 historical-research"})
    with urlopen(request, timeout=20) as response:
        return response.read().decode("utf-8-sig"), url


def _load_or_refresh_history(symbol: str, research_dir: Path, now: float | None = None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    now_value = time.time() if now is None else now
    cache_dir = research_dir / "datasets" / "stooq"
    cache_dir.mkdir(parents=True, exist_ok=True)
    safe = symbol.replace("^", "INDEX_").replace("/", "_").replace(".", "_")
    csv_path = cache_dir / f"{safe}.csv"
    meta_path = cache_dir / f"{safe}.meta.json"
    meta = _read_json(meta_path)
    cache_fresh = csv_path.exists() and (now_value - csv_path.stat().st_mtime) <= REFRESH_TTL_SECONDS
    provider_fetch = False
    error: str | None = None
    source_url = str(meta.get("source_url") or "")
    if not cache_fresh:
        try:
            text, source_url = _fetch_stooq_history(symbol)
            if len(text.strip().splitlines()) < 3:
                raise ValueError("provider returned insufficient history rows")
            tmp = csv_path.with_suffix(".tmp.csv")
            tmp.write_text(text, encoding="utf-8")
            tmp.replace(csv_path)
            provider_fetch = True
            _atomic_write(meta_path, {"symbol": symbol, "provider": "Stooq", "source_url": source_url, "fetched_at": _utc_now()})
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
    if not csv_path.exists():
        return [], {"provider": "Stooq", "source_url": source_url or None, "provider_fetch": provider_fetch, "cache_hit": False, "error": error or "history unavailable"}
    try:
        history = _parse_history_csv(csv_path.read_text(encoding="utf-8"))
    except OSError as exc:
        return [], {"provider": "Stooq", "source_url": source_url or None, "provider_fetch": provider_fetch, "cache_hit": not provider_fetch, "error": f"{type(exc).__name__}: {exc}"}
    return history, {"provider": "Stooq", "source_url": source_url or None, "provider_fetch": provider_fetch, "cache_hit": not provider_fetch, "error": error}


def _return_pct(rows: list[dict[str, Any]], start: int, end: int) -> float | None:
    if start < 0 or end >= len(rows) or end <= start:
        return None
    first = _float(rows[start].get("close")); last = _float(rows[end].get("close"))
    if first is None or last is None or first == 0:
        return None
    return (last / first - 1.0) * 100.0


def _features(rows: list[dict[str, Any]], index: int, event_move_pct: float | None = None) -> dict[str, float] | None:
    if index < 21 or index >= len(rows):
        return None
    ret1 = event_move_pct if event_move_pct is not None else _return_pct(rows, index - 1, index)
    ret5 = _return_pct(rows, index - 5, index)
    ret20 = _return_pct(rows, index - 20, index)
    daily = [_return_pct(rows, i - 1, i) for i in range(index - 19, index + 1)]
    clean_daily = [value for value in daily if value is not None]
    vol20 = statistics.pstdev(clean_daily) * math.sqrt(252) if len(clean_daily) >= 10 else None
    row = rows[index]
    high = _float(row.get("high")); low = _float(row.get("low")); close = _float(row.get("close"))
    range_pct = ((high - low) / close * 100.0) if high is not None and low is not None and close else None
    volumes = [_float(rows[i].get("volume")) for i in range(index - 20, index)]
    clean_volumes = [value for value in volumes if value is not None and value > 0]
    current_volume = _float(row.get("volume"))
    volume_ratio = (current_volume / statistics.mean(clean_volumes)) if current_volume and clean_volumes else None
    values = {"ret1_pct": ret1, "ret5_pct": ret5, "ret20_pct": ret20, "vol20_ann_pct": vol20, "range_pct": range_pct, "volume_ratio20": volume_ratio}
    if any(value is None for value in (ret1, ret5, ret20, vol20)):
        return None
    return {key: round(float(value), 4) for key, value in values.items() if value is not None}


def _distance(left: dict[str, float], right: dict[str, float]) -> float:
    scales = {"ret1_pct": 4.0, "ret5_pct": 8.0, "ret20_pct": 15.0, "vol20_ann_pct": 25.0, "range_pct": 5.0, "volume_ratio20": 2.0}
    weights = {"ret1_pct": 1.5, "ret5_pct": 1.25, "ret20_pct": 1.0, "vol20_ann_pct": 0.9, "range_pct": 0.4, "volume_ratio20": 0.3}
    total = 0.0; used = 0.0
    for key, scale in scales.items():
        if key not in left or key not in right:
            continue
        weight = weights[key]
        total += weight * abs(left[key] - right[key]) / scale
        used += weight
    return total / used if used else float("inf")


def build_analog_study(symbol: str, label: str, rows: list[dict[str, Any]], *, event_move_pct: float | None = None, max_analogs: int = 12) -> dict[str, Any]:
    if len(rows) < 100:
        return {"symbol": symbol, "label": label, "status": "INSUFFICIENT_HISTORY", "history_rows": len(rows), "analog_count": 0, "analogs": [], "summary": {}}
    current_index = len(rows) - 1
    current_features = _features(rows, current_index, event_move_pct=event_move_pct)
    if current_features is None:
        return {"symbol": symbol, "label": label, "status": "INSUFFICIENT_FEATURE_HISTORY", "history_rows": len(rows), "analog_count": 0, "analogs": [], "summary": {}}
    candidates: list[tuple[float, int, dict[str, float]]] = []
    max_forward = max(FORWARD_HORIZONS)
    # Exclude the most recent 120 observations so a current cluster cannot match itself.
    last_candidate = current_index - max(120, max_forward + 1)
    for idx in range(21, max(22, last_candidate + 1)):
        features = _features(rows, idx)
        if features is None or idx + max_forward >= len(rows):
            continue
        candidates.append((_distance(current_features, features), idx, features))
    candidates.sort(key=lambda item: item[0])
    analogs: list[dict[str, Any]] = []
    for distance, idx, features in candidates[:max_analogs]:
        forward = {f"fwd_{h}d_pct": round(_return_pct(rows, idx, idx + h) or 0.0, 2) for h in FORWARD_HORIZONS}
        analogs.append({"date": rows[idx]["date"], "similarity_score": round(max(0.0, 100.0 * (1.0 - min(distance, 1.0))), 1), "features": features, "forward_returns": forward})
    summary: dict[str, Any] = {}
    for horizon in FORWARD_HORIZONS:
        values = [float(item["forward_returns"][f"fwd_{horizon}d_pct"]) for item in analogs]
        if values:
            summary[f"fwd_{horizon}d"] = {"median_pct": round(statistics.median(values), 2), "mean_pct": round(statistics.mean(values), 2), "positive_rate_pct": round(sum(1 for value in values if value > 0) / len(values) * 100.0, 1), "sample_count": len(values)}
    return {
        "symbol": symbol,
        "label": label,
        "status": "ANALOG_STUDY_READY" if analogs else "NO_VALID_ANALOGS",
        "as_of_date": rows[current_index]["date"],
        "history_rows": len(rows),
        "current_setup": current_features,
        "event_move_override_pct": event_move_pct,
        "analog_count": len(analogs),
        "analogs": analogs,
        "summary": summary,
        "method": "FEATURE_DISTANCE_NO_FUTURE_LEAKAGE",
    }


def _coverage(symbol: str, label: str, rows: list[dict[str, Any]], provider: dict[str, Any]) -> dict[str, Any]:
    count = len(rows)
    quality = "DEEP" if count >= 5000 else "SUBSTANTIAL" if count >= 2000 else "MODERATE" if count >= 500 else "LIMITED"
    return {"symbol": symbol, "label": label, "provider": provider.get("provider"), "start_date": rows[0]["date"] if rows else None, "end_date": rows[-1]["date"] if rows else None, "row_count": count, "coverage_quality": quality if rows else "UNAVAILABLE", "source_url": provider.get("source_url"), "error": provider.get("error")}


def run_cycle(*, state_dir: Path, telemetry_dir: Path, research_dir: Path, targets_per_cycle: int = 3) -> dict[str, Any]:
    scorecard = _read_json(state_dir / "latest_market_validation.json")
    telemetry = _read_json(telemetry_dir / "latest.json")
    targets = _extract_targets(scorecard, telemetry)
    prior = _read_json(research_dir / "latest_historical_market_intelligence.json")
    prior_studies = {str(item.get("symbol")): item for item in _rows(prior.get("studies")) if item.get("symbol")}
    prior_coverage = {str(item.get("symbol")): item for item in _rows(prior.get("coverage")) if item.get("symbol")}
    cursor = int((prior.get("cycle") or {}).get("next_cursor") or 0) if isinstance(prior.get("cycle"), dict) else 0
    if targets:
        cursor %= len(targets)
    batch = [targets[(cursor + i) % len(targets)] for i in range(min(max(1, targets_per_cycle), len(targets)))] if targets else []
    provider_fetches = 0; cache_hits = 0; errors: list[str] = []; processed: list[str] = []
    for target in batch:
        symbol = target["symbol"]; label = str(target.get("label") or symbol)
        history, provider = _load_or_refresh_history(symbol, research_dir)
        provider_fetches += 1 if provider.get("provider_fetch") else 0
        cache_hits += 1 if provider.get("cache_hit") else 0
        if provider.get("error") and not history:
            errors.append(f"{symbol}: {provider['error']}")
        prior_coverage[symbol] = _coverage(symbol, label, history, provider)
        prior_studies[symbol] = build_analog_study(symbol, label, history, event_move_pct=_float(target.get("event_move_pct")))
        processed.append(symbol)
    next_cursor = (cursor + len(batch)) % len(targets) if targets else 0
    cycle_count = int((prior.get("cycle") or {}).get("cycle_count") or 0) + 1 if isinstance(prior.get("cycle"), dict) else 1
    ready = sum(1 for item in prior_studies.values() if item.get("status") == "ANALOG_STUDY_READY")
    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _utc_now(),
        "status": "HISTORICAL_RESEARCH_ACTIVE" if ready else ("HISTORICAL_RESEARCH_DEGRADED" if errors else "HISTORICAL_RESEARCH_WARM_UP"),
        "mode": "TWENTY_FOUR_SEVEN_READ_ONLY_RESEARCH",
        "historical_scope": {
            "ideal_research_horizon": "DEEPEST_TRUSTWORTHY_HISTORY_AVAILABLE",
            "coverage_policy": "NEVER_INFER_OR_BACKFILL_BEYOND_ACTUAL_PROVIDER_ROWS",
            "note": "NYSE history is older than modern machine-readable datasets. Each study reports its actual provider start/end dates instead of pretending complete coverage.",
        },
        "cycle": {"cycle_id": f"10H-{int(time.time())}", "cycle_count": cycle_count, "queue_size": len(targets), "processed_symbols": processed, "next_cursor": next_cursor, "targets_per_cycle": targets_per_cycle, "provider_fetches": provider_fetches, "cache_hits": cache_hits, "error_count": len(errors)},
        "pipeline": [
            {"stage": "ARCHIVE_SEARCH", "state": "ACTIVE"},
            {"stage": "ANALOG_MATCHING", "state": "ACTIVE" if ready else "WARM_UP"},
            {"stage": "REGIME_NORMALIZATION", "state": "PARTIAL", "note": "Price/volatility features measured; macro regime joins require validated historical macro inputs."},
            {"stage": "EVENT_RECONSTRUCTION", "state": "MEASUREMENT_GAP", "note": "Historical event/news corpus is not yet persisted under the 10H contract."},
            {"stage": "FORWARD_RETURN_STUDY", "state": "ACTIVE" if ready else "WARM_UP"},
            {"stage": "AGENT_MEMORY", "state": "ADVISORY_ONLY"},
            {"stage": "JUDGMENT_BANK", "state": "HUMAN_GATED"},
        ],
        "coverage": sorted(prior_coverage.values(), key=lambda item: str(item.get("symbol")))[:32],
        "studies": sorted(prior_studies.values(), key=lambda item: str(item.get("symbol")))[:32],
        "research_summary": {"targets_known": len(targets), "studies_ready": ready, "coverage_records": len(prior_coverage), "errors": errors[:10]},
        "next_research": [
            "Continue rotating through core market anchors and current IIOS opportunities 24/7.",
            "Add validated historical macro/regime series before claiming macro-normalized analogs.",
            "Add governed historical event/news corpora before claiming event-reconstruction coverage.",
            "Measure whether analog evidence improves 9H/9J outcomes before any production weighting proposal.",
        ],
        "safety": {
            "read_only_research": True,
            "twenty_four_seven_worker": True,
            "advisory_only": True,
            "auto_generate_trades": False,
            "auto_change_thresholds": False,
            "auto_change_agent_weights": False,
            "auto_change_model_routing": False,
            "auto_change_portfolio_exposure": False,
            "broker_connection_authority": False,
            "capital_authority": False,
            "trade_execution_permission": False,
            "live_execution": False,
            "human_approval_required": True,
        },
    }
    _atomic_write(research_dir / "latest_historical_market_intelligence.json", payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one governed Batch 10H historical-market research cycle.")
    parser.add_argument("--state-dir", default=str(DEFAULT_STATE_DIR))
    parser.add_argument("--telemetry-dir", default=str(DEFAULT_TELEMETRY_DIR))
    parser.add_argument("--research-dir", default=str(DEFAULT_RESEARCH_DIR))
    parser.add_argument("--targets-per-cycle", type=int, default=3)
    parser.add_argument("--stdout", action="store_true")
    args = parser.parse_args()
    payload = run_cycle(state_dir=Path(args.state_dir).expanduser(), telemetry_dir=Path(args.telemetry_dir).expanduser(), research_dir=Path(args.research_dir).expanduser(), targets_per_cycle=max(1, min(args.targets_per_cycle, 12)))
    if args.stdout:
        print(json.dumps(payload, indent=2, sort_keys=True, default=str))
    else:
        print(json.dumps({"status": payload["status"], "processed": payload["cycle"]["processed_symbols"], "studies_ready": payload["research_summary"]["studies_ready"], "live_execution": False}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
