#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import date, datetime, time as dt_time, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import iios_historical_event_reconstruction as core

DOC_SEARCH_START = date(2017, 1, 1)
EVENT_ANALOGS_PER_SYMBOL = 4


def _bounded_gdelt_url(symbol: str, label: str, center: date, span_days: int) -> str:
    now = datetime.now(timezone.utc)
    start_date = max(DOC_SEARCH_START, center - timedelta(days=span_days))
    requested_end = datetime.combine(center + timedelta(days=span_days), dt_time(23, 59, 59), tzinfo=timezone.utc)
    end_dt = min(requested_end, now)
    start_dt = datetime.combine(start_date, dt_time(0, 0, 0), tzinfo=timezone.utc)
    if start_dt > end_dt:
        start_dt = max(datetime.combine(DOC_SEARCH_START, dt_time(0, 0, 0), tzinfo=timezone.utc), end_dt - timedelta(days=max(1, span_days * 2)))
    params = {
        "query": core._query_for(symbol, label),
        "mode": "artlist",
        "format": "json",
        "sort": "datedesc",
        "maxrecords": "40",
        "startdatetime": start_dt.strftime("%Y%m%d%H%M%S"),
        "enddatetime": end_dt.strftime("%Y%m%d%H%M%S"),
    }
    return "https://api.gdeltproject.org/api/v2/doc/doc?" + urlencode(params)


def _eligible_event_analogs(study: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    all_analogs = core._rows(study.get("analogs"))
    inside: list[dict[str, Any]] = []
    outside: list[dict[str, Any]] = []
    for analog in all_analogs:
        analog_date = core._parse_date(analog.get("date"))
        if analog_date is not None and analog_date >= DOC_SEARCH_START:
            inside.append(analog)
        else:
            outside.append(analog)
    selected = inside[:EVENT_ANALOGS_PER_SYMBOL]
    if not selected:
        selected = outside[:EVENT_ANALOGS_PER_SYMBOL]
    return selected, {
        "price_analogs_available": len(all_analogs),
        "inside_doc_corpus": len(inside),
        "outside_doc_corpus": len(outside),
        "selected_for_event_reconstruction": len(selected),
        "selection_policy": "PREFER_BEST_PRICE_ANALOGS_INSIDE_GDELT_DOC_SEARCH_COVERAGE",
        "doc_search_start": DOC_SEARCH_START.isoformat(),
    }


def _reconstruct_study(study: dict[str, Any], event_dir: Path) -> dict[str, Any]:
    selected, selection = _eligible_event_analogs(study)
    scoped = dict(study)
    scoped["analogs"] = selected
    result = _ORIGINAL_RECONSTRUCT_STUDY(scoped, event_dir)
    result["event_analog_selection"] = selection
    return result


_ORIGINAL_RECONSTRUCT_STUDY = core.reconstruct_study


def install_runtime_patch() -> None:
    core.MIN_GDELT_DATE = DOC_SEARCH_START
    core.ANALOGS_PER_SYMBOL = EVENT_ANALOGS_PER_SYMBOL
    core._gdelt_url = _bounded_gdelt_url
    core.reconstruct_study = _reconstruct_study


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Batch 10J with truthful GDELT DOC coverage and bounded current windows.")
    parser.add_argument("--historical-dir", default=str(core.DEFAULT_HISTORICAL_DIR))
    parser.add_argument("--event-dir", default=str(core.DEFAULT_EVENT_DIR))
    parser.add_argument("--symbols-per-cycle", type=int, default=1)
    parser.add_argument("--stdout", action="store_true")
    args = parser.parse_args()
    install_runtime_patch()
    payload = core.run_cycle(
        historical_dir=Path(args.historical_dir).expanduser(),
        event_dir=Path(args.event_dir).expanduser(),
        symbols_per_cycle=max(1, min(args.symbols_per_cycle, 4)),
    )
    import json
    output = payload if args.stdout else {
        "status": payload.get("status"),
        "processed": (payload.get("cycle") or {}).get("processed_symbols"),
        "symbols_ready": (payload.get("research_summary") or {}).get("symbols_ready"),
        "current_contexts_ready": (payload.get("research_summary") or {}).get("current_contexts_ready"),
        "analog_contexts_ready": (payload.get("research_summary") or {}).get("analog_contexts_ready"),
        "doc_search_start": DOC_SEARCH_START.isoformat(),
        "live_execution": False,
    }
    print(json.dumps(output, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
