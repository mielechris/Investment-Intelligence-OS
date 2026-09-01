#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import io
import json
import math
import os
import sqlite3
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, time as dt_time, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config" / "iios_batch10m7_nightly_market_reconstruction.json"
ET = ZoneInfo("America/New_York")
SYSTEM_CURL = Path("/usr/bin/curl")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def expand(value: str) -> Path:
    return Path(os.path.expanduser(value)).resolve()


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    tmp.replace(path)


def connect_ro(path: Path) -> sqlite3.Connection:
    if not path.exists():
        raise RuntimeError(f"live ledger missing: {path}")
    uri = f"file:{path}?mode=ro"
    db = sqlite3.connect(uri, uri=True, timeout=20)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA query_only=ON")
    return db


def parse_json(raw: Any) -> dict[str, Any]:
    try:
        value = json.loads(str(raw or "{}"))
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def tables(db: sqlite3.Connection) -> set[str]:
    return {str(row[0]) for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}


def normalize_symbol(value: Any) -> str:
    text = str(value or "").strip().upper()
    if not text or len(text) > 12 or " " in text:
        return ""
    allowed = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-^")
    return text if all(ch in allowed for ch in text) else ""


def recursive_symbol_lists(value: Any) -> list[list[str]]:
    found: list[list[str]] = []
    if isinstance(value, list):
        symbols = [normalize_symbol(x.get("ticker") or x.get("symbol") if isinstance(x, dict) else x) for x in value]
        clean = [x for x in symbols if x]
        if len(clean) >= 20:
            found.append(clean)
        for item in value:
            found.extend(recursive_symbol_lists(item))
    elif isinstance(value, dict):
        for key, item in value.items():
            if str(key).lower() in {"symbols", "tickers", "members", "universe", "constituents"} and isinstance(item, list):
                symbols = [normalize_symbol(x.get("ticker") or x.get("symbol") if isinstance(x, dict) else x) for x in item]
                clean = [x for x in symbols if x]
                if clean:
                    found.append(clean)
            found.extend(recursive_symbol_lists(item))
    return found


def extract_verified_universe(db: sqlite3.Connection, minimum: int, maximum: int) -> tuple[list[str], dict[str, Any]]:
    if "ledger_objects" not in tables(db):
        return [], {"status": "LEDGER_OBJECTS_TABLE_MISSING"}
    rows = db.execute(
        "SELECT object_type,payload_json,created_at FROM ledger_objects "
        "WHERE lower(object_type) LIKE '%universe%' OR payload_json LIKE '%strict_membership%' "
        "ORDER BY created_at DESC LIMIT 400"
    ).fetchall()
    candidates: list[tuple[int, list[str], dict[str, Any], str, str]] = []
    for row in rows:
        payload = parse_json(row["payload_json"])
        strict = payload.get("strict_membership")
        verified = payload.get("verified_complete")
        if strict is False or verified is False:
            continue
        for symbols in recursive_symbol_lists(payload):
            unique = list(dict.fromkeys(symbols))
            if minimum <= len(unique) <= maximum:
                candidates.append((len(unique), unique, payload, str(row["object_type"]), str(row["created_at"] or "")))
    if not candidates:
        return [], {"status": "NO_VERIFIED_GOVERNED_UNIVERSE_IN_LEDGER", "minimum": minimum, "maximum": maximum}
    candidates.sort(key=lambda x: (x[4], x[0]), reverse=True)
    count, symbols, payload, object_type, created_at = candidates[0]
    return symbols, {
        "status": "VERIFIED_GOVERNED_UNIVERSE",
        "count": count,
        "source_object_type": object_type,
        "source_created_at": created_at,
        "strict_membership": payload.get("strict_membership"),
        "verified_complete": payload.get("verified_complete"),
    }


def session_bounds_utc(session_date: date) -> tuple[datetime, datetime]:
    start = datetime.combine(session_date, dt_time(9, 30), tzinfo=ET).astimezone(timezone.utc)
    end = datetime.combine(session_date, dt_time(16, 0), tzinfo=ET).astimezone(timezone.utc)
    return start, end


def payload_ticker(payload: dict[str, Any]) -> str:
    for key in ("ticker", "symbol"):
        symbol = normalize_symbol(payload.get(key))
        if symbol:
            return symbol
    for key in ("case", "opportunity", "candidate", "input"):
        nested = payload.get(key)
        if isinstance(nested, dict):
            symbol = payload_ticker(nested)
            if symbol:
                return symbol
    topic = str(payload.get("topic") or "")
    if "(" in topic and ")" in topic:
        symbol = normalize_symbol(topic.rsplit("(", 1)[-1].split(")", 1)[0])
        if symbol:
            return symbol
    return ""


def live_session_observations(db: sqlite3.Connection, session_date: date) -> dict[str, Any]:
    start, end = session_bounds_utc(session_date)
    detected: set[str] = set()
    events: list[dict[str, Any]] = []
    tbls = tables(db)
    if "ledger_objects" in tbls:
        rows = db.execute(
            "SELECT object_type,case_id,payload_json,created_at FROM ledger_objects "
            "WHERE created_at>=? AND created_at<=? ORDER BY created_at",
            (start.isoformat(), end.isoformat()),
        ).fetchall()
        for row in rows:
            typ = str(row["object_type"] or "")
            payload = parse_json(row["payload_json"])
            symbol = payload_ticker(payload)
            if symbol and ("case" in typ.lower() or "opportun" in typ.lower() or "promotion" in typ.lower()):
                detected.add(symbol)
            if symbol and len(events) < 500:
                events.append({"at": row["created_at"], "type": typ, "case_id": row["case_id"], "ticker": symbol})
    for event_table in ("ledger_events", "events"):
        if event_table not in tbls:
            continue
        columns = {str(r[1]) for r in db.execute(f"PRAGMA table_info({event_table})").fetchall()}
        time_col = "created_at" if "created_at" in columns else "event_at" if "event_at" in columns else None
        type_col = "event_type" if "event_type" in columns else "type" if "type" in columns else None
        payload_col = "payload_json" if "payload_json" in columns else "payload" if "payload" in columns else None
        if not (time_col and type_col and payload_col):
            continue
        rows = db.execute(
            f"SELECT {type_col} AS typ,{payload_col} AS payload,{time_col} AS at FROM {event_table} WHERE {time_col}>=? AND {time_col}<=? ORDER BY {time_col}",
            (start.isoformat(), end.isoformat()),
        ).fetchall()
        for row in rows:
            payload = parse_json(row["payload"])
            symbol = payload_ticker(payload)
            typ = str(row["typ"] or "")
            if symbol and ("PROMOT" in typ.upper() or "CASE" in typ.upper() or "OPPORT" in typ.upper()):
                detected.add(symbol)
    return {
        "session_start_utc": start.isoformat(),
        "session_end_utc": end.isoformat(),
        "live_detected_tickers": sorted(detected),
        "live_detected_count": len(detected),
        "sample_events": events[-100:],
    }


def curl_text(url: str, timeout: int) -> str:
    command = str(SYSTEM_CURL if SYSTEM_CURL.exists() else "curl")
    result = subprocess.run(
        [command, "--fail", "--silent", "--show-error", "--location", "--connect-timeout", "6", "--max-time", str(timeout), "--user-agent", "Investment-Intelligence-OS/1.0 nightly-backfill", url],
        text=True, capture_output=True, check=False,
    )
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout or "provider error")[:500])
    return result.stdout


def stooq_symbol(symbol: str) -> str:
    text = symbol.lower()
    if text.startswith("^"):
        return text
    if "." in text:
        text = text.replace(".", "-")
    return text if text.endswith(".us") else text + ".us"


def parse_daily_csv(text: str, session_date: str) -> dict[str, Any] | None:
    rows: list[dict[str, Any]] = []
    for row in csv.DictReader(io.StringIO(text)):
        d = str(row.get("Date") or row.get("date") or "")
        try:
            close = float(row.get("Close") or row.get("close"))
        except Exception:
            continue
        if not math.isfinite(close) or close <= 0:
            continue
        rows.append({"date": d, "close": close})
    rows.sort(key=lambda x: x["date"])
    idx = next((i for i, row in enumerate(rows) if row["date"] == session_date), None)
    if idx is None or idx < 1:
        return None
    prev = rows[idx - 1]["close"]
    close = rows[idx]["close"]
    if prev <= 0:
        return None
    return {"session_close": close, "previous_close": prev, "move_pct": round((close / prev - 1) * 100.0, 4), "previous_date": rows[idx - 1]["date"]}


def fetch_move(symbol: str, session_date: date, timeout: int, stooq_primary: bool, yahoo_fallback: bool) -> dict[str, Any]:
    date1 = (session_date - timedelta(days=10)).strftime("%Y%m%d")
    date2 = session_date.strftime("%Y%m%d")
    errors: list[str] = []
    if stooq_primary:
        try:
            url = f"https://stooq.com/q/d/l/?s={quote_plus(stooq_symbol(symbol))}&d1={date1}&d2={date2}&i=d"
            parsed = parse_daily_csv(curl_text(url, timeout), session_date.isoformat())
            if parsed:
                return {"ticker": symbol, "provider": "Stooq", **parsed, "status": "READY"}
            errors.append("Stooq: session row unavailable")
        except Exception as exc:
            errors.append(f"Stooq: {type(exc).__name__}: {exc}")
    if yahoo_fallback:
        try:
            normalized = symbol.replace(".", "-")
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{quote_plus(normalized)}?range=1mo&interval=1d&events=history&includeAdjustedClose=true"
            value = json.loads(curl_text(url, timeout))
            result = (((value.get("chart") or {}).get("result") or [None])[0])
            if isinstance(result, dict):
                stamps = result.get("timestamp") or []
                closes = (((result.get("indicators") or {}).get("quote") or [{}])[0]).get("close") or []
                rows = []
                for i, stamp in enumerate(stamps):
                    if i >= len(closes) or closes[i] is None:
                        continue
                    rows.append({"date": datetime.fromtimestamp(float(stamp), timezone.utc).date().isoformat(), "close": float(closes[i])})
                text = "Date,Close\n" + "\n".join(f"{r['date']},{r['close']}" for r in rows)
                parsed = parse_daily_csv(text, session_date.isoformat())
                if parsed:
                    return {"ticker": symbol, "provider": "Yahoo Finance", **parsed, "status": "READY"}
            errors.append("Yahoo Finance: session row unavailable")
        except Exception as exc:
            errors.append(f"Yahoo Finance: {type(exc).__name__}: {exc}")
    return {"ticker": symbol, "status": "UNAVAILABLE", "error": " | ".join(errors)[:1000]}


def mover_sweep(symbols: list[str], session_date: date, cfg: dict[str, Any]) -> dict[str, Any]:
    max_workers = max(1, min(int(cfg.get("max_workers") or 12), 24))
    timeout = max(5, min(int(cfg.get("provider_timeout_seconds") or 20), 60))
    rows: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(fetch_move, symbol, session_date, timeout, bool(cfg.get("stooq_primary", True)), bool(cfg.get("yahoo_fallback", True))): symbol for symbol in symbols}
        for future in as_completed(futures):
            try:
                rows.append(future.result())
            except Exception as exc:
                rows.append({"ticker": futures[future], "status": "UNAVAILABLE", "error": f"{type(exc).__name__}: {exc}"[:800]})
    ready = [r for r in rows if r.get("status") == "READY" and isinstance(r.get("move_pct"), (int, float))]
    ready.sort(key=lambda r: abs(float(r["move_pct"])), reverse=True)
    threshold = float(cfg.get("absolute_move_threshold_pct") or 3.0)
    limit = max(1, min(int(cfg.get("top_movers_limit") or 30), 100))
    material = [r for r in ready if abs(float(r["move_pct"])) >= threshold][:limit]
    return {
        "requested_count": len(symbols),
        "ready_count": len(ready),
        "unavailable_count": len(rows) - len(ready),
        "coverage_pct": round(len(ready) / len(symbols) * 100.0, 2) if symbols else 0.0,
        "threshold_pct": threshold,
        "material_movers": material,
        "material_mover_count": len(material),
        "provider_counts": {p: sum(1 for r in ready if r.get("provider") == p) for p in sorted({str(r.get("provider")) for r in ready})},
        "errors_sample": [r for r in rows if r.get("status") != "READY"][:25],
    }


def run_command(args: list[str], cwd: Path, env: dict[str, str] | None = None, timeout: int = 900) -> dict[str, Any]:
    started = time.perf_counter()
    result = subprocess.run(args, cwd=str(cwd), text=True, capture_output=True, check=False, env=env, timeout=timeout)
    return {"returncode": result.returncode, "seconds": round(time.perf_counter() - started, 3), "stdout": (result.stdout or "")[-4000:], "stderr": (result.stderr or "")[-4000:]}


def run_historical_stack(config: dict[str, Any], session_root: Path, movers: list[dict[str, Any]], python: Path) -> dict[str, Any]:
    worktrees = {k: expand(v) for k, v in (config.get("historical_worktrees") or {}).items()}
    missing = [k for k in ("10h", "10j", "10k") if not worktrees.get(k) or not worktrees[k].exists()]
    if missing:
        return {"status": "HISTORICAL_DEPENDENCY_MISSING", "missing": missing}
    state_dir = session_root / "isolated-state"
    telemetry_dir = session_root / "isolated-telemetry"
    historical_dir = session_root / "historical-research"
    event_dir = session_root / "historical-event-reconstruction"
    macro_dir = session_root / "historical-macro-regime"
    state_dir.mkdir(parents=True, exist_ok=True); telemetry_dir.mkdir(parents=True, exist_ok=True)
    opportunities = [{"ticker": r["ticker"], "symbol": r["ticker"], "company": r["ticker"], "move_pct": r["move_pct"], "backfill": True} for r in movers]
    write_json(state_dir / "latest_market_validation.json", {"status": "RETROSPECTIVE_BACKFILL_INPUT", "input": {"opportunities": opportunities}, "truth": {"counts_as_live_detection": False, "eligible_for_9h_live_score": False}})
    write_json(telemetry_dir / "latest.json", {"paper_fund": {"positions": []}, "source": {"mode": "RETROSPECTIVE_ISOLATED_INPUT"}})
    hcfg = config.get("historical_research") or {}
    h10 = worktrees["10h"] / "scripts" / "iios_historical_market_intelligence_runtime.py"
    j10 = worktrees["10j"] / "scripts" / "iios_historical_event_reconstruction_runtime.py"
    k10 = worktrees["10k"] / "scripts" / "iios_historical_macro_regime_library.py"
    for path in (h10, j10, k10):
        if not path.exists():
            return {"status": "HISTORICAL_ENGINE_FILE_MISSING", "path": str(path)}
    env10h = dict(os.environ); env10h["PYTHONPATH"] = str(worktrees["10h"] / "scripts")
    cycles_10h = max(1, math.ceil((9 + len(opportunities)) / max(1, int(hcfg.get("10h_targets_per_cycle") or 12))))
    runs10h = []
    for _ in range(cycles_10h):
        runs10h.append(run_command([str(python), str(h10), "--state-dir", str(state_dir), "--telemetry-dir", str(telemetry_dir), "--research-dir", str(historical_dir), "--targets-per-cycle", str(int(hcfg.get("10h_targets_per_cycle") or 12))], worktrees["10h"], env10h))
    env10j = dict(os.environ); env10j["PYTHONPATH"] = str(worktrees["10j"] / "scripts")
    cycles_10j = max(1, math.ceil(min(len(opportunities), int(hcfg.get("top_movers_for_deep_reconstruction") or 24)) / max(1, int(hcfg.get("10j_symbols_per_cycle") or 8))))
    runs10j = []
    for _ in range(cycles_10j):
        runs10j.append(run_command([str(python), str(j10), "--historical-dir", str(historical_dir), "--event-dir", str(event_dir), "--symbols-per-cycle", str(int(hcfg.get("10j_symbols_per_cycle") or 8))], worktrees["10j"], env10j))
    env10k = dict(os.environ); env10k["PYTHONPATH"] = str(worktrees["10k"] / "scripts")
    run10k = run_command([str(python), str(k10), "--historical-dir", str(historical_dir), "--macro-dir", str(macro_dir)], worktrees["10k"], env10k)
    artifacts = {
        "10h": read_json(historical_dir / "latest_historical_market_intelligence.json"),
        "10j": read_json(event_dir / "latest_historical_event_reconstruction.json"),
        "10k": read_json(macro_dir / "latest_historical_macro_regime_library.json"),
    }
    successful = all(r.get("returncode") == 0 for r in runs10h + runs10j + [run10k])
    return {"status": "HISTORICAL_STACK_COMPLETE" if successful else "HISTORICAL_STACK_PARTIAL", "10h_runs": runs10h, "10j_runs": runs10j, "10k_run": run10k, "artifacts": artifacts, "isolated_directories": {"historical": str(historical_dir), "events": str(event_dir), "macro": str(macro_dir)}}


def select_session_date(now_et: datetime, override: str | None) -> date:
    if override:
        return date.fromisoformat(override)
    candidate = now_et.date()
    while candidate.weekday() >= 5:
        candidate -= timedelta(days=1)
    return candidate


def post_close_allowed(now_et: datetime, config: dict[str, Any], session_date: date, force: bool) -> bool:
    if force:
        return True
    if session_date != now_et.date():
        return True
    hour, minute = [int(x) for x in str(config.get("post_close_not_before_et") or "16:30").split(":", 1)]
    return now_et.time() >= dt_time(hour, minute)


def resolve_python(config: dict[str, Any]) -> Path:
    for candidate in config.get("backend_python_candidates") or []:
        path = expand(str(candidate))
        if path.exists() and os.access(path, os.X_OK):
            return path
    return Path(sys.executable)


def build_report(config: dict[str, Any], session_date: date, universe_meta: dict[str, Any], live: dict[str, Any], sweep: dict[str, Any], historical: dict[str, Any]) -> dict[str, Any]:
    live_set = set(live.get("live_detected_tickers") or [])
    movers = sweep.get("material_movers") or []
    retrospective = {str(r.get("ticker")) for r in movers if r.get("ticker")}
    missed = sorted(retrospective - live_set)
    caught = sorted(retrospective & live_set)
    coverage = float(sweep.get("coverage_pct") or 0.0)
    universe_count = int(universe_meta.get("count") or 0)
    hist_ok = historical.get("status") == "HISTORICAL_STACK_COMPLETE"
    status = "BACKFILL_COMPLETE" if universe_count >= int((config.get("mover_sweep") or {}).get("min_verified_universe") or 400) and coverage >= 90.0 and hist_ok else "BACKFILL_PARTIAL"
    truth = dict(config.get("truth_contract") or {})
    return {
        "schema_version": config.get("schema_version"),
        "generated_at": now_iso(),
        "status": status,
        "session_date": session_date.isoformat(),
        "detection_mode": "RETROSPECTIVE_BACKFILL",
        "truth": truth,
        "universe": universe_meta,
        "live_observation": live,
        "retrospective_market_sweep": sweep,
        "comparison": {
            "material_movers_reconstructed": len(retrospective),
            "material_movers_seen_live": caught,
            "material_movers_seen_live_count": len(caught),
            "missed_live_but_found_retrospectively": missed,
            "missed_live_but_found_retrospectively_count": len(missed),
            "interpretation": "RETROSPECTIVE DIFFERENCE ONLY. A backfilled mover is not a live 9H detection hit and is not automatically a trade that IIOS should have made."
        },
        "historical_stack": historical,
        "learning_contract": {
            "eligible_for_10m2_measurement": True,
            "eligible_for_9j_outcome_learning": True,
            "eligible_for_9h_live_detection_score": False,
            "official_9h_score_impact": "NONE",
            "automatic_threshold_change": False,
            "automatic_model_routing_change": False,
            "human_review_required_for_material_changes": True,
        },
        "causality_warning": "10J event/news results are associated context, not proof that a headline caused a market move.",
        "safety": config.get("safety") or {},
    }


def run(config: dict[str, Any], *, session_override: str | None = None, force: bool = False) -> dict[str, Any]:
    now_et = datetime.now(ET)
    session_date = select_session_date(now_et, session_override)
    output_root = expand(str(config.get("output_root") or "~/Library/Application Support/IIOS/nightly-reconstruction"))
    session_root = output_root / "sessions" / session_date.isoformat()
    latest = output_root / "latest_nightly_reconstruction.json"
    final = session_root / "nightly_reconstruction.json"
    if final.exists() and not force:
        payload = read_json(final)
        payload["scheduled_action"] = "SKIPPED_ALREADY_RECONSTRUCTED"
        write_json(latest, payload)
        return payload
    if not post_close_allowed(now_et, config, session_date, force):
        payload = {"schema_version": config.get("schema_version"), "generated_at": now_iso(), "status": "WAITING_FOR_POST_CLOSE", "session_date": session_date.isoformat(), "truth": config.get("truth_contract") or {}, "safety": config.get("safety") or {}}
        write_json(latest, payload)
        return payload
    ledger = expand(str(config.get("live_ledger_path") or ""))
    db = connect_ro(ledger)
    try:
        sweep_cfg = config.get("mover_sweep") or {}
        symbols, universe_meta = extract_verified_universe(db, int(sweep_cfg.get("min_verified_universe") or 400), int(sweep_cfg.get("max_verified_universe") or 700))
        live = live_session_observations(db, session_date)
    finally:
        db.close()
    if not symbols:
        payload = {"schema_version": config.get("schema_version"), "generated_at": now_iso(), "status": "BACKFILL_INCOMPLETE", "session_date": session_date.isoformat(), "reason": "VERIFIED_GOVERNED_UNIVERSE_UNAVAILABLE", "universe": universe_meta, "live_observation": live, "truth": config.get("truth_contract") or {}, "safety": config.get("safety") or {}}
        write_json(final, payload); write_json(latest, payload); return payload
    sweep = mover_sweep(symbols, session_date, sweep_cfg)
    movers = list(sweep.get("material_movers") or [])[: int((config.get("historical_research") or {}).get("top_movers_for_deep_reconstruction") or 24)]
    historical = run_historical_stack(config, session_root, movers, resolve_python(config))
    payload = build_report(config, session_date, universe_meta, live, sweep, historical)
    write_json(final, payload); write_json(latest, payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="IIOS Batch 10M.7 Nightly Market Reconstruction")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--session-date")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--stdout", action="store_true")
    args = parser.parse_args()
    config = read_json(expand(args.config))
    if not config:
        raise SystemExit("10M.7 config missing or invalid")
    output_root = expand(str(config.get("output_root") or "~/Library/Application Support/IIOS/nightly-reconstruction"))
    latest = output_root / "latest_nightly_reconstruction.json"
    if args.status:
        if not latest.exists():
            print(f"No nightly reconstruction artifact yet: {latest}")
            return 1
        print(latest.read_text(encoding="utf-8"))
        return 0
    try:
        payload = run(config, session_override=args.session_date, force=args.force)
    except Exception as exc:
        payload = {"schema_version": config.get("schema_version"), "generated_at": now_iso(), "status": "BACKFILL_INCOMPLETE", "reason": f"{type(exc).__name__}: {exc}"[:3000], "truth": config.get("truth_contract") or {}, "safety": config.get("safety") or {}}
        write_json(latest, payload)
    if args.stdout:
        print(json.dumps(payload, indent=2, sort_keys=True, default=str))
    else:
        print(json.dumps({"status": payload.get("status"), "session_date": payload.get("session_date"), "universe_count": (payload.get("universe") or {}).get("count"), "sweep_coverage_pct": (payload.get("retrospective_market_sweep") or {}).get("coverage_pct"), "material_movers": (payload.get("retrospective_market_sweep") or {}).get("material_mover_count"), "missed_live_but_backfilled": (payload.get("comparison") or {}).get("missed_live_but_found_retrospectively_count"), "official_9h_score_impact": ((payload.get("learning_contract") or {}).get("official_9h_score_impact") or (payload.get("truth") or {}).get("official_9h_score_impact")), "live_execution": False}, sort_keys=True))
    return 0 if payload.get("status") in {"BACKFILL_COMPLETE", "BACKFILL_PARTIAL", "WAITING_FOR_POST_CLOSE"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
