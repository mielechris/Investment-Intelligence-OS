#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import io
import json
import math
import statistics
import subprocess
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

SCHEMA_VERSION = "batch10k-historical-macro-regime-library-v1"
DEFAULT_HISTORICAL_DIR = Path.home() / "Library" / "Application Support" / "IIOS" / "historical-research"
DEFAULT_MACRO_DIR = Path.home() / "Library" / "Application Support" / "IIOS" / "historical-macro-regime"
SYSTEM_CURL = Path("/usr/bin/curl")
CACHE_TTL_SECONDS = 6 * 60 * 60

# Tier A is eligible for analog normalization because these are market-observable
# or policy-rate series that do not depend on revised macro vintages.
SERIES: dict[str, dict[str, Any]] = {
    "DFF": {"name": "Effective Federal Funds Rate", "family": "POLICY_RATE", "tier": "A", "max_age_days": 7},
    "DGS2": {"name": "2-Year Treasury Constant Maturity", "family": "YIELD_CURVE", "tier": "A", "max_age_days": 7},
    "DGS10": {"name": "10-Year Treasury Constant Maturity", "family": "YIELD_CURVE", "tier": "A", "max_age_days": 7},
    "VIXCLS": {"name": "CBOE Volatility Index", "family": "VOLATILITY", "tier": "A", "max_age_days": 7},
    "BAMLH0A0HYM2": {"name": "ICE BofA US High Yield Option-Adjusted Spread", "family": "CREDIT", "tier": "A", "max_age_days": 10},
    # Tier B series are persisted for context only. Current FRED history can be
    # revised and is not treated as point-in-time vintage-safe backtest truth.
    "CPIAUCSL": {"name": "CPI All Urban Consumers", "family": "INFLATION", "tier": "B", "availability_lag_days": 45},
    "UNRATE": {"name": "Unemployment Rate", "family": "GROWTH_LABOR", "tier": "B", "availability_lag_days": 21},
    "GDPC1": {"name": "Real Gross Domestic Product", "family": "GROWTH", "tier": "B", "availability_lag_days": 120},
    "WALCL": {"name": "Federal Reserve Total Assets", "family": "LIQUIDITY", "tier": "B", "availability_lag_days": 14},
}

SCALES = {
    "fed_funds_pct": 2.0,
    "curve_10y2y_pct": 2.0,
    "vix": 20.0,
    "high_yield_spread_pct": 4.0,
}
WEIGHTS = {
    "fed_funds_pct": 1.2,
    "curve_10y2y_pct": 1.1,
    "vix": 1.0,
    "high_yield_spread_pct": 1.1,
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    tmp.replace(path)


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists() or not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _parse_date(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def _curl_text(url: str) -> str:
    command = str(SYSTEM_CURL if SYSTEM_CURL.exists() else "curl")
    result = subprocess.run(
        [command, "--fail", "--silent", "--show-error", "--location", "--connect-timeout", "10", "--max-time", "45", "--user-agent", "Investment-Intelligence-OS/1.0 macro-regime", url],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "curl failed").strip()
        raise RuntimeError(f"system curl failed ({result.returncode}): {detail[:800]}")
    return result.stdout


def _parse_fred_csv(text: str, series_id: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    reader = csv.DictReader(io.StringIO(text))
    for raw in reader:
        dt = _parse_date(raw.get("DATE") or raw.get("observation_date"))
        value = _float(raw.get(series_id) or raw.get("VALUE") or raw.get("value"))
        if dt is None or value is None:
            continue
        rows.append({"date": dt.isoformat(), "value": value})
    rows.sort(key=lambda row: row["date"])
    return rows


def _fetch_series(series_id: str, macro_dir: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    cache = macro_dir / "datasets" / "fred"
    cache.mkdir(parents=True, exist_ok=True)
    csv_path = cache / f"{series_id}.csv"
    meta_path = cache / f"{series_id}.meta.json"
    meta = _read_json(meta_path)
    fresh = csv_path.exists() and (time.time() - csv_path.stat().st_mtime) <= CACHE_TTL_SECONDS
    if fresh:
        rows = _parse_fred_csv(csv_path.read_text(encoding="utf-8"), series_id)
        if rows:
            return rows, {"provider": "FRED", "cache_hit": True, "error": None, "source_url": meta.get("source_url")}
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={quote_plus(series_id)}"
    try:
        text = _curl_text(url)
        rows = _parse_fred_csv(text, series_id)
        if len(rows) < 2:
            raise ValueError(f"FRED returned only {len(rows)} usable rows")
        csv_path.write_text(text, encoding="utf-8")
        _atomic_write(meta_path, {"series_id": series_id, "source_url": url, "fetched_at": _utc_now(), "row_count": len(rows)})
        return rows, {"provider": "FRED", "cache_hit": False, "error": None, "source_url": url}
    except Exception as exc:  # noqa: BLE001
        if csv_path.exists():
            rows = _parse_fred_csv(csv_path.read_text(encoding="utf-8"), series_id)
            if rows:
                return rows, {"provider": "FRED", "cache_hit": True, "error": f"refresh failed; using cache: {type(exc).__name__}: {exc}", "source_url": meta.get("source_url")}
        return [], {"provider": "FRED", "cache_hit": False, "error": f"{type(exc).__name__}: {exc}", "source_url": url}


def _last_value(rows: list[dict[str, Any]], target: date, *, max_age_days: int | None = None, lag_days: int = 0) -> dict[str, Any] | None:
    effective = target - timedelta(days=lag_days)
    chosen: dict[str, Any] | None = None
    for row in rows:
        dt = _parse_date(row.get("date"))
        if dt is None or dt > effective:
            break
        chosen = row
    if chosen is None:
        return None
    dt = _parse_date(chosen.get("date"))
    if dt is None:
        return None
    age = (effective - dt).days
    if max_age_days is not None and age > max_age_days:
        return None
    return {"value": float(chosen["value"]), "observation_date": dt.isoformat(), "effective_target_date": effective.isoformat(), "age_days": age}


def _yoy(rows: list[dict[str, Any]], target: date, *, lag_days: int) -> dict[str, Any] | None:
    current = _last_value(rows, target, lag_days=lag_days)
    prior = _last_value(rows, target - timedelta(days=365), lag_days=lag_days)
    if not current or not prior or not prior["value"]:
        return None
    value = (current["value"] / prior["value"] - 1.0) * 100.0
    return {"value": round(value, 3), "observation_date": current["observation_date"], "effective_target_date": current["effective_target_date"]}


def macro_snapshot(target: date, series_data: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    dff = _last_value(series_data.get("DFF", []), target, max_age_days=7)
    dgs2 = _last_value(series_data.get("DGS2", []), target, max_age_days=7)
    dgs10 = _last_value(series_data.get("DGS10", []), target, max_age_days=7)
    vix = _last_value(series_data.get("VIXCLS", []), target, max_age_days=7)
    hy = _last_value(series_data.get("BAMLH0A0HYM2", []), target, max_age_days=10)
    tier_a: dict[str, Any] = {}
    if dff: tier_a["fed_funds_pct"] = dff
    if dgs2 and dgs10:
        tier_a["curve_10y2y_pct"] = {"value": round(dgs10["value"] - dgs2["value"], 3), "observation_date": max(dgs10["observation_date"], dgs2["observation_date"])}
    if vix: tier_a["vix"] = vix
    if hy: tier_a["high_yield_spread_pct"] = hy

    cpi = _yoy(series_data.get("CPIAUCSL", []), target, lag_days=45)
    unemployment = _last_value(series_data.get("UNRATE", []), target, lag_days=21)
    gdp = _yoy(series_data.get("GDPC1", []), target, lag_days=120)
    liquidity = _yoy(series_data.get("WALCL", []), target, lag_days=14)
    tier_b = {
        "cpi_yoy_pct": cpi,
        "unemployment_pct": unemployment,
        "real_gdp_yoy_pct": gdp,
        "fed_balance_sheet_yoy_pct": liquidity,
    }
    tier_b = {key: value for key, value in tier_b.items() if value is not None}
    return {
        "date": target.isoformat(),
        "tier_a_backtest_eligible": tier_a,
        "tier_a_dimensions_ready": len(tier_a),
        "tier_b_context_only": tier_b,
        "tier_b_dimensions_ready": len(tier_b),
        "point_in_time_policy": {
            "tier_a": "MARKET_OBSERVABLE_OR_POLICY_SERIES_ELIGIBLE_FOR_NORMALIZATION",
            "tier_b": "CONTEXT_ONLY_CURRENT_HISTORY_NOT_REVISION_VINTAGE_SAFE",
            "future_leakage_guard": "ONLY_OBSERVATIONS_AT_OR_BEFORE_EFFECTIVE_TARGET_DATE",
        },
    }


def _distance(left: dict[str, Any], right: dict[str, Any]) -> float | None:
    total = 0.0
    used = 0.0
    for key, scale in SCALES.items():
        lv = _float((left.get(key) or {}).get("value") if isinstance(left.get(key), dict) else None)
        rv = _float((right.get(key) or {}).get("value") if isinstance(right.get(key), dict) else None)
        if lv is None or rv is None:
            continue
        weight = WEIGHTS[key]
        total += weight * abs(lv - rv) / scale
        used += weight
    if used <= 0:
        return None
    return total / used


def normalize_study(study: dict[str, Any], series_data: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    current_date = _parse_date(study.get("as_of_date"))
    symbol = str(study.get("symbol") or "")
    if current_date is None:
        return {"symbol": symbol, "status": "INVALID_STUDY_DATE", "macro_normalized_analogs": []}
    current = macro_snapshot(current_date, series_data)
    ranked: list[dict[str, Any]] = []
    for analog in study.get("analogs", []) if isinstance(study.get("analogs"), list) else []:
        analog_date = _parse_date(analog.get("date")) if isinstance(analog, dict) else None
        if analog_date is None:
            continue
        snapshot = macro_snapshot(analog_date, series_data)
        distance = _distance(current["tier_a_backtest_eligible"], snapshot["tier_a_backtest_eligible"])
        if distance is None or min(current["tier_a_dimensions_ready"], snapshot["tier_a_dimensions_ready"]) < 3:
            continue
        ranked.append({
            "date": analog_date.isoformat(),
            "macro_distance": round(distance, 4),
            "macro_similarity_score": round(max(0.0, 100.0 * (1.0 - min(distance, 1.0))), 1),
            "price_similarity_score": analog.get("similarity_score"),
            "forward_returns": analog.get("forward_returns") if isinstance(analog.get("forward_returns"), dict) else {},
            "macro_snapshot": snapshot,
        })
    ranked.sort(key=lambda row: row["macro_distance"])
    top = ranked[:6]
    return {
        "symbol": symbol,
        "label": study.get("label"),
        "status": "MACRO_NORMALIZED_ANALOGS_READY" if top else "INSUFFICIENT_MACRO_OVERLAP",
        "as_of_date": current_date.isoformat(),
        "current_macro_snapshot": current,
        "macro_normalized_analogs": top,
        "candidate_count": len(ranked),
        "normalization_method": "TIER_A_MARKET_OBSERVABLE_DISTANCE_NO_FUTURE_DATED_OBSERVATIONS",
        "tier_b_usage": "CONTEXT_ONLY_NOT_USED_IN_ANALOG_RANKING",
    }


def build_library(*, historical: dict[str, Any], series_data: dict[str, list[dict[str, Any]]], provider_meta: dict[str, dict[str, Any]]) -> dict[str, Any]:
    studies = [row for row in (historical.get("studies") or []) if isinstance(row, dict) and row.get("status") == "ANALOG_STUDY_READY"]
    normalized = [normalize_study(study, series_data) for study in studies]
    ready = sum(1 for row in normalized if row.get("status") == "MACRO_NORMALIZED_ANALOGS_READY")
    tier_a_series_ready = sum(1 for key in ("DFF", "DGS2", "DGS10", "VIXCLS", "BAMLH0A0HYM2") if series_data.get(key))
    tier_b_series_ready = sum(1 for key in ("CPIAUCSL", "UNRATE", "GDPC1", "WALCL") if series_data.get(key))
    errors = [f"{key}: {meta.get('error')}" for key, meta in provider_meta.items() if meta.get("error") and not series_data.get(key)]
    status = "HISTORICAL_MACRO_REGIME_LIBRARY_ACTIVE" if ready > 0 and tier_a_series_ready >= 4 else ("HISTORICAL_MACRO_REGIME_LIBRARY_DEGRADED" if errors else "HISTORICAL_MACRO_REGIME_LIBRARY_WARM_UP")
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _utc_now(),
        "status": status,
        "mode": "TWENTY_FOUR_SEVEN_READ_ONLY_MACRO_RESEARCH",
        "series_registry": [{"series_id": key, **meta, "rows": len(series_data.get(key, [])), "provider": provider_meta.get(key, {}).get("provider"), "provider_error": provider_meta.get(key, {}).get("error")} for key, meta in SERIES.items()],
        "coverage": {
            "tier_a_series_ready": tier_a_series_ready,
            "tier_a_series_required_for_active": 4,
            "tier_b_context_series_ready": tier_b_series_ready,
            "normalized_symbols_ready": ready,
            "price_analog_studies_seen": len(studies),
            "revision_policy": "TIER_B_REVISED_MACRO_SERIES_CONTEXT_ONLY_UNTIL_POINT_IN_TIME_VINTAGE_SOURCE_EXISTS",
        },
        "normalized_studies": normalized,
        "pipeline": [
            {"stage": "POLICY_RATES", "state": "ACTIVE" if series_data.get("DFF") and series_data.get("DGS10") else "MEASUREMENT_GAP"},
            {"stage": "YIELD_CURVE", "state": "ACTIVE" if series_data.get("DGS2") and series_data.get("DGS10") else "MEASUREMENT_GAP"},
            {"stage": "VOLATILITY", "state": "ACTIVE" if series_data.get("VIXCLS") else "MEASUREMENT_GAP"},
            {"stage": "CREDIT", "state": "ACTIVE" if series_data.get("BAMLH0A0HYM2") else "MEASUREMENT_GAP"},
            {"stage": "INFLATION_GROWTH", "state": "CONTEXT_ONLY" if tier_b_series_ready >= 2 else "MEASUREMENT_GAP", "note": "Current FRED history is not treated as revision-vintage-safe backtest truth."},
            {"stage": "MACRO_NORMALIZED_ANALOGS", "state": "ACTIVE" if ready else "WARM_UP"},
        ],
        "research_summary": {"normalized_symbols_ready": ready, "tier_a_series_ready": tier_a_series_ready, "tier_b_series_ready": tier_b_series_ready, "errors": errors[:12]},
        "measurement_plan": {
            "comparison": "PRICE_ONLY_VS_TIER_A_MACRO_NORMALIZED_ANALOGS",
            "future_metric": "Measure whether macro-normalized analog evidence improves mature 9J outcomes before any production weighting proposal.",
        },
        "safety": {
            "read_only_research": True,
            "advisory_only": True,
            "auto_generate_trades": False,
            "auto_change_thresholds": False,
            "auto_change_agent_weights": False,
            "auto_change_model_routing": False,
            "auto_change_portfolio_exposure": False,
            "provider_change_authority": False,
            "broker_connection_authority": False,
            "capital_authority": False,
            "trade_execution_permission": False,
            "live_execution": False,
            "human_approval_required": True,
        },
    }


def run_cycle(*, historical_dir: Path, macro_dir: Path) -> dict[str, Any]:
    historical = _read_json(historical_dir / "latest_historical_market_intelligence.json")
    series_data: dict[str, list[dict[str, Any]]] = {}
    provider_meta: dict[str, dict[str, Any]] = {}
    for series_id in SERIES:
        rows, meta = _fetch_series(series_id, macro_dir)
        series_data[series_id] = rows
        provider_meta[series_id] = meta
    payload = build_library(historical=historical, series_data=series_data, provider_meta=provider_meta)
    _atomic_write(macro_dir / "latest_historical_macro_regime_library.json", payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one governed Batch 10K historical macro/regime normalization cycle.")
    parser.add_argument("--historical-dir", default=str(DEFAULT_HISTORICAL_DIR))
    parser.add_argument("--macro-dir", default=str(DEFAULT_MACRO_DIR))
    parser.add_argument("--stdout", action="store_true")
    args = parser.parse_args()
    payload = run_cycle(historical_dir=Path(args.historical_dir).expanduser(), macro_dir=Path(args.macro_dir).expanduser())
    output = payload if args.stdout else {"status": payload.get("status"), **(payload.get("research_summary") or {}), "live_execution": False}
    print(json.dumps(output, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
