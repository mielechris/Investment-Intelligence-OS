#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "batch10l-benchmark-alpha-attribution-v1"
DEFAULT_TELEMETRY_DIR = Path.home() / "Library" / "Application Support" / "IIOS" / "telemetry"
DEFAULT_RESEARCH_DIR = Path.home() / "Library" / "Application Support" / "IIOS" / "historical-research"
DEFAULT_BENCHMARK_DIR = Path.home() / "Library" / "Application Support" / "IIOS" / "benchmark-alpha"


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
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_date(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        try:
            return datetime.strptime(text[:10], "%Y-%m-%d").date().isoformat()
        except ValueError:
            return None


def _history_path(research_dir: Path, symbol: str) -> Path:
    safe = symbol.replace("^", "INDEX_").replace("/", "_").replace(".", "_")
    verified = research_dir / "datasets" / "verified-history" / f"{safe}.csv"
    if verified.exists():
        return verified
    return research_dir / "datasets" / "stooq" / f"{safe}.csv"


def _load_closes(path: Path) -> list[tuple[str, float]]:
    if not path.exists():
        return []
    rows: list[tuple[str, float]] = []
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                dt = str(row.get("Date") or row.get("date") or "").strip()
                raw = row.get("Close") or row.get("close")
                try:
                    close = float(raw)
                except (TypeError, ValueError):
                    continue
                if dt and close > 0:
                    rows.append((dt, close))
    except OSError:
        return []
    rows.sort(key=lambda item: item[0])
    return rows


def _close_at_or_before(rows: list[tuple[str, float]], target: str) -> tuple[str, float] | None:
    chosen = None
    for dt, close in rows:
        if dt > target:
            break
        chosen = (dt, close)
    return chosen


def _benchmark_return(rows: list[tuple[str, float]], start_date: str) -> dict[str, Any]:
    if not rows:
        return {"status": "PRICE_HISTORY_UNAVAILABLE"}
    start = _close_at_or_before(rows, start_date)
    end = rows[-1]
    if start is None or start[1] <= 0:
        return {"status": "NO_PRICE_AT_OR_BEFORE_INCEPTION"}
    ret = (end[1] / start[1] - 1.0) * 100.0
    return {
        "status": "MEASURED",
        "start_date": start[0],
        "end_date": end[0],
        "start_close": round(start[1], 6),
        "end_close": round(end[1], 6),
        "return_pct": round(ret, 4),
    }


def _ensure_inception(benchmark_dir: Path, telemetry: dict[str, Any]) -> dict[str, Any]:
    path = benchmark_dir / "inception.json"
    existing = _read_json(path)
    if existing.get("start_date") and existing.get("initial_nav") is not None:
        return existing
    fund = telemetry.get("paper_fund") if isinstance(telemetry.get("paper_fund"), dict) else {}
    generated = _parse_date(telemetry.get("generated_at")) or datetime.now(timezone.utc).date().isoformat()
    initial_nav = _float(fund.get("nav")) or _float(fund.get("cash")) or 10000.0
    payload = {
        "created_at": _utc_now(),
        "start_date": generated,
        "initial_nav": round(initial_nav, 2),
        "policy": "PERSIST_ONCE_AND_NEVER_RETROACTIVELY_MOVE_BENCHMARK_INCEPTION",
    }
    _atomic_write(path, payload)
    return payload


def build_attribution(*, telemetry: dict[str, Any], research_dir: Path, benchmark_dir: Path) -> dict[str, Any]:
    fund = telemetry.get("paper_fund") if isinstance(telemetry.get("paper_fund"), dict) else {}
    inception = _ensure_inception(benchmark_dir, telemetry)
    start_date = str(inception["start_date"])
    initial_nav = float(inception["initial_nav"])
    current_nav = _float(fund.get("nav")) or initial_nav
    iios_return = ((current_nav / initial_nav) - 1.0) * 100.0 if initial_nav > 0 else None

    spy = _benchmark_return(_load_closes(_history_path(research_dir, "SPY")), start_date)
    qqq = _benchmark_return(_load_closes(_history_path(research_dir, "QQQ")), start_date)
    cash = {"status": "MEASURED", "start_date": start_date, "end_date": datetime.now(timezone.utc).date().isoformat(), "return_pct": 0.0, "note": "Zero-yield cash control; not represented as a T-bill total-return series."}

    measured_returns = [x.get("return_pct") for x in (spy, qqq) if x.get("status") == "MEASURED" and isinstance(x.get("return_pct"), (int, float))]
    mechanical_return = round(sum(measured_returns) / len(measured_returns), 4) if len(measured_returns) == 2 else None
    mechanical = {
        "status": "MEASURED" if mechanical_return is not None else "WAITING_FOR_SPY_AND_QQQ",
        "method": "STATIC_50_50_SPY_QQQ_BUY_AND_HOLD_RETURN_AVERAGE",
        "return_pct": mechanical_return,
        "allocation_authority": False,
    }

    controls = {"SPY": spy, "QQQ": qqq, "CASH_ZERO": cash, "MECHANICAL_50_50_SPY_QQQ": mechanical}
    comparable = {k: v for k, v in controls.items() if isinstance(v.get("return_pct"), (int, float))}
    excess = {k: round(float(iios_return or 0.0) - float(v["return_pct"]), 4) for k, v in comparable.items()} if iios_return is not None else {}
    transaction_count = int(fund.get("transaction_count") or 0)
    measurement_contract_ready = spy.get("status") == "MEASURED" and qqq.get("status") == "MEASURED"
    status = "BENCHMARK_ALPHA_ATTRIBUTION_ACTIVE" if measurement_contract_ready else "BENCHMARK_ALPHA_ATTRIBUTION_WARM_UP"

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _utc_now(),
        "status": status,
        "measurement_contract_ready": measurement_contract_ready,
        "inception": inception,
        "paper": {
            "initial_nav": initial_nav,
            "current_nav": current_nav,
            "return_pct": round(iios_return, 4) if iios_return is not None else None,
            "transaction_count": transaction_count,
            "max_drawdown_pct": _float(fund.get("max_drawdown_pct")),
        },
        "controls": controls,
        "excess_return_pct": excess,
        "interpretation": "Benchmark infrastructure can be active before the paper sample is mature. Edge claims remain prohibited until governed qualification and sufficient outcomes exist.",
        "measurement_gaps": [
            "risk-adjusted alpha requires a persisted daily paper NAV/equity curve",
            "cash control is zero-yield cash until a governed T-bill total-return series is available",
            "statistical significance requires a mature governed paper sample",
        ],
        "safety": {
            "measurement_only": True,
            "benchmark_only": True,
            "auto_change_allocation": False,
            "auto_change_strategy": False,
            "capital_authority": False,
            "broker_connection_authority": False,
            "trade_execution_permission": False,
            "live_execution": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build governed Batch 10L benchmark/control-portfolio attribution.")
    parser.add_argument("--telemetry-dir", default=str(DEFAULT_TELEMETRY_DIR))
    parser.add_argument("--research-dir", default=str(DEFAULT_RESEARCH_DIR))
    parser.add_argument("--benchmark-dir", default=str(DEFAULT_BENCHMARK_DIR))
    args = parser.parse_args()
    telemetry_dir = Path(args.telemetry_dir).expanduser()
    research_dir = Path(args.research_dir).expanduser()
    benchmark_dir = Path(args.benchmark_dir).expanduser()
    payload = build_attribution(telemetry=_read_json(telemetry_dir / "latest.json"), research_dir=research_dir, benchmark_dir=benchmark_dir)
    _atomic_write(benchmark_dir / "latest_benchmark_alpha_attribution.json", payload)
    print(json.dumps({"status": payload["status"], "measurement_contract_ready": payload["measurement_contract_ready"], "paper_return_pct": payload["paper"]["return_pct"], "live_execution": False}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
