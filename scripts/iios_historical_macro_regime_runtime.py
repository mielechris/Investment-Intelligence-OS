#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import io
import json
import math
import subprocess
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import iios_historical_macro_regime_library as core

SYSTEM_CURL = Path("/usr/bin/curl")
TREASURY_XML = "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml?data=daily_treasury_yield_curve&field_tdr_date_value={year}"
CBOE_VIX_CSV = "https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv"
TREASURY_START_YEAR = 1990
MAX_PROVIDER_WORKERS = 6
CACHE_TTL_SECONDS = 6 * 60 * 60

SCALES = {
    "front_end_2y_pct": 2.5,
    "long_rate_10y_pct": 2.5,
    "curve_10y2y_pct": 2.0,
    "vix": 20.0,
}
WEIGHTS = {
    "front_end_2y_pct": 1.0,
    "long_rate_10y_pct": 0.8,
    "curve_10y2y_pct": 1.1,
    "vix": 1.0,
}


def _curl_text(url: str, *, max_time: int = 30) -> str:
    command = str(SYSTEM_CURL if SYSTEM_CURL.exists() else "curl")
    result = subprocess.run(
        [
            command,
            "--http1.1",
            "--fail",
            "--silent",
            "--show-error",
            "--location",
            "--connect-timeout",
            "8",
            "--max-time",
            str(max_time),
            "--retry",
            "1",
            "--retry-delay",
            "1",
            "--retry-all-errors",
            "--user-agent",
            "Investment-Intelligence-OS/1.0 macro-regime-direct",
            url,
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "curl failed").strip()
        raise RuntimeError(f"verified HTTP/1.1 fetch failed ({result.returncode}): {detail[:800]}")
    return result.stdout


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].upper()


def _parse_treasury_xml(text: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    root = ET.fromstring(text)
    two_year: list[dict[str, Any]] = []
    ten_year: list[dict[str, Any]] = []
    for entry in root.iter():
        if _local(entry.tag) != "ENTRY":
            continue
        fields: dict[str, str] = {}
        for node in entry.iter():
            if node.text and node.text.strip():
                fields[_local(node.tag)] = node.text.strip()
        raw_date = fields.get("NEW_DATE") or fields.get("DATE")
        if not raw_date:
            continue
        try:
            dt = datetime.fromisoformat(raw_date.replace("Z", "+00:00")).date()
        except ValueError:
            try:
                dt = datetime.strptime(raw_date[:10], "%Y-%m-%d").date()
            except ValueError:
                continue
        for target, names in (
            (two_year, ("BC_2YEAR", "BC_2_YEAR", "2YEAR")),
            (ten_year, ("BC_10YEAR", "BC_10_YEAR", "10YEAR")),
        ):
            raw = next((fields.get(name) for name in names if fields.get(name) not in {None, ""}), None)
            if raw is None:
                continue
            try:
                value = float(raw)
            except ValueError:
                continue
            if math.isfinite(value):
                target.append({"date": dt.isoformat(), "value": value})
    two_year.sort(key=lambda row: row["date"])
    ten_year.sort(key=lambda row: row["date"])
    return two_year, ten_year


def _parse_vix_csv(text: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    reader = csv.DictReader(io.StringIO(text))
    for raw in reader:
        raw_date = str(raw.get("DATE") or raw.get("Date") or "").strip()
        raw_close = str(raw.get("CLOSE") or raw.get("Close") or "").strip()
        if not raw_date or not raw_close:
            continue
        dt = None
        for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
            try:
                dt = datetime.strptime(raw_date, fmt).date()
                break
            except ValueError:
                pass
        if dt is None:
            continue
        try:
            value = float(raw_close)
        except ValueError:
            continue
        if math.isfinite(value):
            rows.append({"date": dt.isoformat(), "value": value})
    rows.sort(key=lambda row: row["date"])
    return rows


def _cached_text(path: Path, url: str, *, max_time: int = 30) -> tuple[str, bool]:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and (time.time() - path.stat().st_mtime) <= CACHE_TTL_SECONDS:
        return path.read_text(encoding="utf-8"), True
    try:
        text = _curl_text(url, max_time=max_time)
        path.write_text(text, encoding="utf-8")
        return text, False
    except Exception:
        if path.exists():
            return path.read_text(encoding="utf-8"), True
        raise


def _target_years(historical: dict[str, Any]) -> list[int]:
    years: set[int] = {datetime.now(timezone.utc).year}
    for study in historical.get("studies", []) if isinstance(historical.get("studies"), list) else []:
        if not isinstance(study, dict) or study.get("status") != "ANALOG_STUDY_READY":
            continue
        for raw in [study.get("as_of_date"), *[a.get("date") for a in study.get("analogs", []) if isinstance(a, dict)]]:
            dt = core._parse_date(raw)
            if dt and dt.year >= TREASURY_START_YEAR:
                years.add(dt.year)
                years.add(max(TREASURY_START_YEAR, dt.year - 1))
    return sorted(years)


def _fetch_treasury_year(year: int, macro_dir: Path) -> tuple[int, list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    cache = macro_dir / "datasets" / "treasury" / f"yield_curve_{year}.xml"
    url = TREASURY_XML.format(year=year)
    try:
        text, cache_hit = _cached_text(cache, url, max_time=25)
        two, ten = _parse_treasury_xml(text)
        if not two or not ten:
            raise ValueError(f"Treasury {year} XML missing usable 2Y/10Y rows")
        return year, two, ten, {"provider": "US_TREASURY_XML", "cache_hit": cache_hit, "error": None, "source_url": url}
    except Exception as exc:  # noqa: BLE001
        return year, [], [], {"provider": "US_TREASURY_XML", "cache_hit": False, "error": f"{type(exc).__name__}: {exc}", "source_url": url}


def _fetch_vix(macro_dir: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    cache = macro_dir / "datasets" / "cboe" / "VIX_History.csv"
    try:
        text, cache_hit = _cached_text(cache, CBOE_VIX_CSV, max_time=25)
        rows = _parse_vix_csv(text)
        if len(rows) < 100:
            raise ValueError(f"Cboe VIX returned only {len(rows)} usable rows")
        return rows, {"provider": "CBOE_VIX_HISTORY", "cache_hit": cache_hit, "error": None, "source_url": CBOE_VIX_CSV}
    except Exception as exc:  # noqa: BLE001
        return [], {"provider": "CBOE_VIX_HISTORY", "cache_hit": False, "error": f"{type(exc).__name__}: {exc}", "source_url": CBOE_VIX_CSV}


def _snapshot(target: date, series: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    two = core._last_value(series.get("UST2Y", []), target, max_age_days=7)
    ten = core._last_value(series.get("UST10Y", []), target, max_age_days=7)
    vix = core._last_value(series.get("VIX", []), target, max_age_days=7)
    dims: dict[str, Any] = {}
    if two:
        dims["front_end_2y_pct"] = two
    if ten:
        dims["long_rate_10y_pct"] = ten
    if two and ten:
        dims["curve_10y2y_pct"] = {
            "value": round(ten["value"] - two["value"], 3),
            "observation_date": max(ten["observation_date"], two["observation_date"]),
        }
    if vix:
        dims["vix"] = vix
    return {
        "date": target.isoformat(),
        "tier_a_backtest_eligible": dims,
        "tier_a_dimensions_ready": len(dims),
        "tier_b_context_only": {},
        "tier_b_dimensions_ready": 0,
        "point_in_time_policy": {
            "tier_a": "DIRECT_MARKET_OBSERVABLE_TREASURY_AND_CBOE_SERIES",
            "tier_b": "MEASUREMENT_GAP_NOT_USED_IN_ANALOG_RANKING",
            "future_leakage_guard": "ONLY_OBSERVATIONS_AT_OR_BEFORE_TARGET_DATE",
        },
    }


def _distance(left: dict[str, Any], right: dict[str, Any]) -> float | None:
    total = 0.0
    used = 0.0
    for key, scale in SCALES.items():
        lv = core._float((left.get(key) or {}).get("value") if isinstance(left.get(key), dict) else None)
        rv = core._float((right.get(key) or {}).get("value") if isinstance(right.get(key), dict) else None)
        if lv is None or rv is None:
            continue
        weight = WEIGHTS[key]
        total += weight * abs(lv - rv) / scale
        used += weight
    return (total / used) if used > 0 else None


def _normalize_study(study: dict[str, Any], series: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    current_date = core._parse_date(study.get("as_of_date"))
    symbol = str(study.get("symbol") or "")
    if current_date is None:
        return {"symbol": symbol, "status": "INVALID_STUDY_DATE", "macro_normalized_analogs": []}
    current = _snapshot(current_date, series)
    ranked: list[dict[str, Any]] = []
    for analog in study.get("analogs", []) if isinstance(study.get("analogs"), list) else []:
        if not isinstance(analog, dict):
            continue
        analog_date = core._parse_date(analog.get("date"))
        if analog_date is None or analog_date.year < TREASURY_START_YEAR:
            continue
        snap = _snapshot(analog_date, series)
        distance = _distance(current["tier_a_backtest_eligible"], snap["tier_a_backtest_eligible"])
        if distance is None or min(current["tier_a_dimensions_ready"], snap["tier_a_dimensions_ready"]) < 3:
            continue
        ranked.append({
            "date": analog_date.isoformat(),
            "macro_distance": round(distance, 4),
            "macro_similarity_score": round(max(0.0, 100.0 * (1.0 - min(distance, 1.0))), 1),
            "price_similarity_score": analog.get("similarity_score"),
            "forward_returns": analog.get("forward_returns") if isinstance(analog.get("forward_returns"), dict) else {},
            "macro_snapshot": snap,
        })
    ranked.sort(key=lambda row: row["macro_distance"])
    top = ranked[:6]
    return {
        "symbol": symbol,
        "label": study.get("label"),
        "status": "MACRO_NORMALIZED_ANALOGS_READY" if top else "INSUFFICIENT_DIRECT_MACRO_OVERLAP",
        "as_of_date": current_date.isoformat(),
        "current_macro_snapshot": current,
        "macro_normalized_analogs": top,
        "candidate_count": len(ranked),
        "normalization_method": "DIRECT_TREASURY_RATE_LEVEL_CURVE_AND_CBOE_VIX_NO_FUTURE_OBSERVATIONS",
        "tier_b_usage": "MEASUREMENT_GAP_NOT_USED_IN_ANALOG_RANKING",
    }


def _run_cycle_direct(*, historical_dir: Path, macro_dir: Path) -> dict[str, Any]:
    historical = core._read_json(historical_dir / "latest_historical_market_intelligence.json")
    years = _target_years(historical)
    two_rows: list[dict[str, Any]] = []
    ten_rows: list[dict[str, Any]] = []
    treasury_meta: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=min(MAX_PROVIDER_WORKERS, max(1, len(years))), thread_name_prefix="iios-10k-treasury") as pool:
        futures = {pool.submit(_fetch_treasury_year, year, macro_dir): year for year in years}
        for future in as_completed(futures):
            _, two, ten, meta = future.result()
            two_rows.extend(two)
            ten_rows.extend(ten)
            treasury_meta.append(meta)
    two_rows.sort(key=lambda row: row["date"])
    ten_rows.sort(key=lambda row: row["date"])
    vix_rows, vix_meta = _fetch_vix(macro_dir)
    series = {"UST2Y": two_rows, "UST10Y": ten_rows, "VIX": vix_rows}
    studies = [row for row in historical.get("studies", []) if isinstance(row, dict) and row.get("status") == "ANALOG_STUDY_READY"] if isinstance(historical.get("studies"), list) else []
    normalized = [_normalize_study(study, series) for study in studies]
    ready = sum(1 for row in normalized if row.get("status") == "MACRO_NORMALIZED_ANALOGS_READY")
    treasury_ok = bool(two_rows and ten_rows)
    vix_ok = bool(vix_rows)
    tier_a_series_ready = (2 if treasury_ok else 0) + (1 if vix_ok else 0)
    errors = [str(meta.get("error")) for meta in treasury_meta if meta.get("error")]
    if vix_meta.get("error"):
        errors.append(str(vix_meta.get("error")))
    status = "HISTORICAL_MACRO_REGIME_LIBRARY_ACTIVE" if ready > 0 and tier_a_series_ready >= 3 else ("HISTORICAL_MACRO_REGIME_LIBRARY_DEGRADED" if errors else "HISTORICAL_MACRO_REGIME_LIBRARY_WARM_UP")
    payload = {
        "schema_version": core.SCHEMA_VERSION,
        "generated_at": core._utc_now(),
        "status": status,
        "mode": "TWENTY_FOUR_SEVEN_READ_ONLY_MACRO_RESEARCH",
        "runtime_transport": "DIRECT_US_TREASURY_XML_PLUS_CBOE_VIX_VERIFIED_TLS",
        "series_registry": [
            {"series_id": "UST2Y", "name": "2-Year Treasury Par Yield", "family": "FRONT_END_RATE", "tier": "A", "rows": len(two_rows), "provider": "US_TREASURY_XML" if treasury_ok else None},
            {"series_id": "UST10Y", "name": "10-Year Treasury Par Yield", "family": "LONG_RATE_AND_CURVE", "tier": "A", "rows": len(ten_rows), "provider": "US_TREASURY_XML" if treasury_ok else None},
            {"series_id": "VIX", "name": "Cboe Volatility Index", "family": "VOLATILITY", "tier": "A", "rows": len(vix_rows), "provider": "CBOE_VIX_HISTORY" if vix_ok else None},
        ],
        "coverage": {
            "tier_a_series_ready": tier_a_series_ready,
            "tier_a_series_required_for_active": 3,
            "tier_a_dimensions": ["FRONT_END_2Y_RATE", "LONG_RATE_10Y", "10Y2Y_CURVE", "VIX"],
            "tier_b_context_series_ready": 0,
            "normalized_symbols_ready": ready,
            "price_analog_studies_seen": len(studies),
            "treasury_years_requested": years,
            "treasury_data_availability_start": str(TREASURY_START_YEAR),
            "revision_policy": "INFLATION_GROWTH_LIQUIDITY_REMAIN_MEASUREMENT_GAPS_UNTIL_POINT_IN_TIME_SAFE_DIRECT_SOURCES_ARE_ADDED",
        },
        "normalized_studies": normalized,
        "pipeline": [
            {"stage": "RATE_LEVEL", "state": "ACTIVE" if treasury_ok else "MEASUREMENT_GAP"},
            {"stage": "YIELD_CURVE", "state": "ACTIVE" if treasury_ok else "MEASUREMENT_GAP"},
            {"stage": "VOLATILITY", "state": "ACTIVE" if vix_ok else "MEASUREMENT_GAP"},
            {"stage": "CREDIT", "state": "MEASUREMENT_GAP"},
            {"stage": "INFLATION_GROWTH_LIQUIDITY", "state": "MEASUREMENT_GAP", "note": "Not used until point-in-time-safe direct sources are persisted."},
            {"stage": "MACRO_NORMALIZED_ANALOGS", "state": "ACTIVE" if ready else "WARM_UP"},
        ],
        "research_summary": {
            "normalized_symbols_ready": ready,
            "tier_a_series_ready": tier_a_series_ready,
            "tier_b_series_ready": 0,
            "errors": errors[:12],
        },
        "provider_diagnostics": {
            "treasury": {"years_requested": len(years), "year_fetches_ok": sum(1 for meta in treasury_meta if not meta.get("error")), "errors": [meta.get("error") for meta in treasury_meta if meta.get("error")][:8]},
            "cboe_vix": vix_meta,
            "fred": {"status": "NON_BLOCKING_DISABLED_AFTER_OBSERVED_RUNTIME_TIMEOUTS"},
        },
        "measurement_plan": {
            "comparison": "PRICE_ONLY_VS_DIRECT_RATE_CURVE_VOLATILITY_NORMALIZED_ANALOGS",
            "future_metric": "Measure whether direct-source macro/regime normalization improves mature 9J outcomes before any production weighting proposal.",
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
    core._atomic_write(macro_dir / "latest_historical_macro_regime_library.json", payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Batch 10K using direct Treasury + Cboe market-observable regime sources.")
    parser.add_argument("--historical-dir", default=str(core.DEFAULT_HISTORICAL_DIR))
    parser.add_argument("--macro-dir", default=str(core.DEFAULT_MACRO_DIR))
    parser.add_argument("--stdout", action="store_true")
    args = parser.parse_args()
    payload = _run_cycle_direct(historical_dir=Path(args.historical_dir).expanduser(), macro_dir=Path(args.macro_dir).expanduser())
    output = payload if args.stdout else {"status": payload.get("status"), **(payload.get("research_summary") or {}), "transport": payload.get("runtime_transport"), "live_execution": False}
    print(json.dumps(output, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
