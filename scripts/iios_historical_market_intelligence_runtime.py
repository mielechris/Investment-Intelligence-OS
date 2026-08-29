#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

import iios_historical_market_intelligence as core

SYSTEM_CURL = Path("/usr/bin/curl")
CACHE_TTL_SECONDS = 6 * 60 * 60
MIN_USABLE_ROWS = 100
USER_AGENT = "Investment-Intelligence-OS/1.0 historical-research"


def _curl_text(url: str) -> str:
    if not SYSTEM_CURL.exists():
        raise RuntimeError("macOS system curl is unavailable")
    result = subprocess.run(
        [
            str(SYSTEM_CURL),
            "--fail",
            "--silent",
            "--show-error",
            "--location",
            "--connect-timeout",
            "10",
            "--max-time",
            "45",
            "--user-agent",
            USER_AGENT,
            url,
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "curl failed").strip()
        raise RuntimeError(f"system curl failed ({result.returncode}): {detail[:800]}")
    return result.stdout


def _stooq_history(symbol: str) -> tuple[str, str, str]:
    normalized = core._stooq_symbol(symbol)
    url = f"https://stooq.com/q/d/l/?s={quote_plus(normalized)}&i=d"
    text = _curl_text(url)
    rows = core._parse_history_csv(text)
    if len(rows) < MIN_USABLE_ROWS:
        raise ValueError(f"Stooq returned only {len(rows)} usable rows")
    return text, url, "Stooq"


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _yahoo_json_to_csv(payload: dict[str, Any]) -> str:
    result = (((payload.get("chart") or {}).get("result") or [None])[0])
    if not isinstance(result, dict):
        raise ValueError("Yahoo chart returned no result")
    timestamps = result.get("timestamp") or []
    quote_rows = ((result.get("indicators") or {}).get("quote") or [{}])[0]
    if not isinstance(quote_rows, dict):
        raise ValueError("Yahoo chart returned no quote rows")
    opens = quote_rows.get("open") or []
    highs = quote_rows.get("high") or []
    lows = quote_rows.get("low") or []
    closes = quote_rows.get("close") or []
    volumes = quote_rows.get("volume") or []
    lines = ["Date,Open,High,Low,Close,Volume"]
    for index, stamp in enumerate(timestamps):
        if index >= len(closes):
            break
        close = _finite(closes[index])
        if close is None or close <= 0:
            continue
        date = datetime.fromtimestamp(float(stamp), tz=timezone.utc).date().isoformat()

        def item(values: list[Any]) -> str:
            if index >= len(values):
                return ""
            value = _finite(values[index])
            return "" if value is None else str(value)

        lines.append(
            ",".join(
                [date, item(opens), item(highs), item(lows), str(close), item(volumes)]
            )
        )
    if len(lines) - 1 < MIN_USABLE_ROWS:
        raise ValueError(f"Yahoo returned only {len(lines) - 1} usable rows")
    return "\n".join(lines) + "\n"


def _yahoo_history(symbol: str) -> tuple[str, str, str]:
    normalized = core._normalize_symbol(symbol)
    url = (
        "https://query1.finance.yahoo.com/v8/finance/chart/"
        f"{quote_plus(normalized)}?range=max&interval=1d&events=history&includeAdjustedClose=true"
    )
    payload = json.loads(_curl_text(url))
    return _yahoo_json_to_csv(payload), url, "Yahoo Finance"


def _fetch_history(symbol: str) -> tuple[str, str, str]:
    errors: list[str] = []
    for provider, fetcher in (("Stooq", _stooq_history), ("Yahoo Finance", _yahoo_history)):
        try:
            return fetcher(symbol)
        except Exception as exc:  # noqa: BLE001 - provider fallback is intentional
            errors.append(f"{provider}: {type(exc).__name__}: {exc}")
    raise RuntimeError(" | ".join(errors))


def _safe_name(symbol: str) -> str:
    return symbol.replace("^", "INDEX_").replace("/", "_").replace(".", "_")


def _load_or_refresh_history(
    symbol: str,
    research_dir: Path,
    now: float | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    now_value = time.time() if now is None else now
    cache_dir = research_dir / "datasets" / "verified-history"
    cache_dir.mkdir(parents=True, exist_ok=True)
    safe = _safe_name(symbol)
    csv_path = cache_dir / f"{safe}.csv"
    meta_path = cache_dir / f"{safe}.meta.json"
    meta = core._read_json(meta_path)
    cached_rows: list[dict[str, Any]] = []
    if csv_path.exists():
        try:
            cached_rows = core._parse_history_csv(csv_path.read_text(encoding="utf-8"))
        except OSError:
            cached_rows = []
    cache_fresh = (
        len(cached_rows) >= MIN_USABLE_ROWS
        and csv_path.exists()
        and (now_value - csv_path.stat().st_mtime) <= CACHE_TTL_SECONDS
    )
    if cache_fresh:
        return cached_rows, {
            "provider": meta.get("provider") or "VERIFIED_CACHE",
            "source_url": meta.get("source_url"),
            "provider_fetch": False,
            "cache_hit": True,
            "error": None,
        }

    try:
        text, source_url, provider = _fetch_history(symbol)
        rows = core._parse_history_csv(text)
        if len(rows) < MIN_USABLE_ROWS:
            raise ValueError(f"provider history parsed to only {len(rows)} usable rows")
        temporary = csv_path.with_suffix(".tmp.csv")
        temporary.write_text(text, encoding="utf-8")
        temporary.replace(csv_path)
        core._atomic_write(
            meta_path,
            {
                "symbol": symbol,
                "provider": provider,
                "source_url": source_url,
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "row_count": len(rows),
                "tls_policy": "SYSTEM_TRUST_VERIFIED_NO_INSECURE_FLAG",
            },
        )
        return rows, {
            "provider": provider,
            "source_url": source_url,
            "provider_fetch": True,
            "cache_hit": False,
            "error": None,
        }
    except Exception as exc:  # noqa: BLE001 - stale verified cache may still be useful
        if len(cached_rows) >= MIN_USABLE_ROWS:
            return cached_rows, {
                "provider": meta.get("provider") or "VERIFIED_CACHE",
                "source_url": meta.get("source_url"),
                "provider_fetch": False,
                "cache_hit": True,
                "error": f"refresh failed; using verified cache: {type(exc).__name__}: {exc}",
            }
        return [], {
            "provider": None,
            "source_url": None,
            "provider_fetch": False,
            "cache_hit": False,
            "error": f"{type(exc).__name__}: {exc}",
        }


def install_runtime_patch() -> None:
    core._load_or_refresh_history = _load_or_refresh_history


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one verified Batch 10H historical research cycle using macOS system trust.")
    parser.add_argument("--state-dir", default=str(core.DEFAULT_STATE_DIR))
    parser.add_argument("--telemetry-dir", default=str(core.DEFAULT_TELEMETRY_DIR))
    parser.add_argument("--research-dir", default=str(core.DEFAULT_RESEARCH_DIR))
    parser.add_argument("--targets-per-cycle", type=int, default=3)
    parser.add_argument("--stdout", action="store_true")
    args = parser.parse_args()
    install_runtime_patch()
    payload = core.run_cycle(
        state_dir=Path(args.state_dir).expanduser(),
        telemetry_dir=Path(args.telemetry_dir).expanduser(),
        research_dir=Path(args.research_dir).expanduser(),
        targets_per_cycle=max(1, min(args.targets_per_cycle, 12)),
    )
    if args.stdout:
        print(json.dumps(payload, indent=2, sort_keys=True, default=str))
    else:
        print(
            json.dumps(
                {
                    "status": payload.get("status"),
                    "processed": (payload.get("cycle") or {}).get("processed_symbols"),
                    "studies_ready": (payload.get("research_summary") or {}).get("studies_ready"),
                    "runtime_tls": "MACOS_SYSTEM_TRUST_VERIFIED",
                    "live_execution": False,
                },
                sort_keys=True,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
