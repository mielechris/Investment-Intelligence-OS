#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import subprocess
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

SCHEMA_VERSION = "batch10j-historical-event-reconstruction-v1"
DEFAULT_HISTORICAL_DIR = Path.home() / "Library" / "Application Support" / "IIOS" / "historical-research"
DEFAULT_EVENT_DIR = Path.home() / "Library" / "Application Support" / "IIOS" / "historical-event-reconstruction"
SYSTEM_CURL = Path("/usr/bin/curl")
MIN_GDELT_DATE = date(2015, 2, 19)
HISTORICAL_CACHE_SECONDS = 180 * 24 * 60 * 60
CURRENT_CACHE_SECONDS = 30 * 60
ANALOGS_PER_SYMBOL = 4

EVENT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "MONETARY_POLICY_RATES": ("federal reserve", "fed ", "interest rate", "rate cut", "rate hike", "powell", "fomc", "yield"),
    "INFLATION_GROWTH_MACRO": ("inflation", "cpi", "pce", "jobs report", "payroll", "unemployment", "gdp", "recession", "economic growth"),
    "GEOPOLITICAL_CONFLICT": ("war", "invasion", "missile", "military", "sanction", "geopolitical", "conflict", "ceasefire"),
    "REGULATORY_POLICY": ("regulation", "regulator", "antitrust", "tariff", "executive order", "congress", "senate", "sec ", "doj ", "policy"),
    "COMMODITY_ENERGY": ("oil", "crude", "opec", "natural gas", "energy prices", "commodity", "copper", "gold"),
    "LIQUIDITY_CREDIT": ("credit", "bank failure", "liquidity", "debt ceiling", "default", "bond market", "funding stress", "banking crisis"),
    "EARNINGS_CORPORATE": ("earnings", "revenue", "profit", "guidance", "forecast", "merger", "acquisition", "buyback", "dividend"),
    "TECHNOLOGY_PRODUCT": ("ai ", "artificial intelligence", "chip", "semiconductor", "technology", "product launch", "data center"),
    "WEATHER_NATURAL_DISASTER": ("hurricane", "wildfire", "earthquake", "storm", "flood", "drought", "weather"),
    "HEALTH_BIO": ("pandemic", "covid", "vaccine", "drug trial", "fda", "health emergency"),
    "MARKET_POSITIONING_TECHNICAL": ("selloff", "rally", "short squeeze", "options", "volatility", "vix", "rebalancing", "technical"),
}

QUERY_BY_SYMBOL = {
    "^SPX": '("S&P 500" OR "US stocks" OR "Wall Street")',
    "SPY": '("S&P 500" OR "US stocks" OR "Wall Street")',
    "^DJI": '("Dow Jones" OR "US stocks" OR "Wall Street")',
    "^NDQ": '("Nasdaq Composite" OR Nasdaq OR "technology stocks")',
    "QQQ": '(Nasdaq OR "technology stocks" OR "growth stocks")',
    "IWM": '("Russell 2000" OR "small cap stocks" OR "small-cap stocks")',
    "SMH": '(semiconductor OR chip OR "chip stocks")',
    "XLF": '("financial stocks" OR banks OR banking)',
    "XLE": '("energy stocks" OR oil OR crude)',
}


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


def _rows(value: Any) -> list[dict[str, Any]]:
    return [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []


def _parse_date(value: Any) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return date.fromisoformat(text[:10])
        except ValueError:
            return None


def _curl_json(url: str) -> dict[str, Any]:
    command = str(SYSTEM_CURL if SYSTEM_CURL.exists() else "curl")
    result = subprocess.run(
        [
            command,
            "--fail",
            "--silent",
            "--show-error",
            "--location",
            "--connect-timeout",
            "10",
            "--max-time",
            "45",
            "--user-agent",
            "Investment-Intelligence-OS/1.0 historical-event-reconstruction",
            url,
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "curl failed").strip()
        raise RuntimeError(f"system curl failed ({result.returncode}): {detail[:800]}")
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("historical event provider returned non-JSON content") from exc
    if not isinstance(value, dict):
        raise RuntimeError("historical event provider returned non-object JSON")
    return value


def _query_for(symbol: str, label: str) -> str:
    if symbol in QUERY_BY_SYMBOL:
        return QUERY_BY_SYMBOL[symbol]
    cleaned = " ".join(str(label or symbol).replace('"', " ").split())
    return f'("{cleaned}" OR "{symbol}")'


def _gdelt_url(symbol: str, label: str, center: date, span_days: int) -> str:
    start = center - timedelta(days=span_days)
    end = center + timedelta(days=span_days)
    params = {
        "query": _query_for(symbol, label),
        "mode": "artlist",
        "format": "json",
        "sort": "datedesc",
        "maxrecords": "40",
        "startdatetime": start.strftime("%Y%m%d000000"),
        "enddatetime": end.strftime("%Y%m%d235959"),
    }
    return "https://api.gdeltproject.org/api/v2/doc/doc?" + urlencode(params)


def _cache_key(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:24]


def _fetch_articles(
    *,
    symbol: str,
    label: str,
    center: date,
    event_dir: Path,
    span_days: int = 2,
    current: bool = False,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if center < MIN_GDELT_DATE:
        return [], {
            "provider": "GDELT_DOC_2",
            "status": "OUTSIDE_MODERN_NEWS_CORPUS_COVERAGE",
            "coverage_start": MIN_GDELT_DATE.isoformat(),
            "error": None,
            "cache_hit": False,
        }
    url = _gdelt_url(symbol, label, center, span_days)
    cache_dir = event_dir / "provider-cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / f"{_cache_key(url)}.json"
    ttl = CURRENT_CACHE_SECONDS if current else HISTORICAL_CACHE_SECONDS
    if cache_path.exists() and (time.time() - cache_path.stat().st_mtime) <= ttl:
        payload = _read_json(cache_path)
        articles = _rows(payload.get("articles"))
        return articles, {"provider": "GDELT_DOC_2", "status": "OK", "error": None, "cache_hit": True, "url": url}
    try:
        payload = _curl_json(url)
        normalized: list[dict[str, Any]] = []
        seen: set[str] = set()
        for article in _rows(payload.get("articles")):
            title = str(article.get("title") or "").strip()
            article_url = str(article.get("url") or "").strip()
            if not title:
                continue
            key = article_url or title.lower()
            if key in seen:
                continue
            seen.add(key)
            normalized.append({
                "title": title,
                "url": article_url or None,
                "domain": article.get("domain"),
                "seen_at": article.get("seendate"),
                "language": article.get("language"),
                "source_country": article.get("sourcecountry"),
            })
        _atomic_write(cache_path, {"generated_at": _utc_now(), "provider": "GDELT_DOC_2", "url": url, "articles": normalized})
        return normalized, {"provider": "GDELT_DOC_2", "status": "OK", "error": None, "cache_hit": False, "url": url}
    except Exception as exc:  # noqa: BLE001 - fail closed into explicit evidence gap
        if cache_path.exists():
            payload = _read_json(cache_path)
            articles = _rows(payload.get("articles"))
            if articles:
                return articles, {"provider": "GDELT_DOC_2", "status": "STALE_VERIFIED_CACHE", "error": str(exc)[:800], "cache_hit": True, "url": url}
        return [], {"provider": "GDELT_DOC_2", "status": "PROVIDER_ERROR", "error": f"{type(exc).__name__}: {exc}"[:800], "cache_hit": False, "url": url}


def classify_event_context(articles: list[dict[str, Any]]) -> dict[str, Any]:
    if not articles:
        return {
            "status": "NO_GOVERNED_EVENT_EVIDENCE",
            "candidate_event_type": None,
            "association_confidence_pct": 0.0,
            "article_count": 0,
            "event_type_scores": {},
            "causal_claim": False,
        }
    scores: dict[str, int] = {key: 0 for key in EVENT_KEYWORDS}
    supporting: dict[str, list[str]] = {key: [] for key in EVENT_KEYWORDS}
    for article in articles:
        title = str(article.get("title") or "").lower()
        for event_type, keywords in EVENT_KEYWORDS.items():
            hits = sum(1 for keyword in keywords if keyword in title)
            if hits:
                scores[event_type] += hits
                if len(supporting[event_type]) < 4:
                    supporting[event_type].append(str(article.get("title") or ""))
    nonzero = {key: value for key, value in scores.items() if value > 0}
    if not nonzero:
        return {
            "status": "ASSOCIATED_EVENT_EVIDENCE_UNCLASSIFIED",
            "candidate_event_type": "OTHER_UNCLASSIFIED",
            "association_confidence_pct": 15.0,
            "article_count": len(articles),
            "event_type_scores": {},
            "supporting_headlines": [str(row.get("title") or "") for row in articles[:4]],
            "causal_claim": False,
        }
    ranked = sorted(nonzero.items(), key=lambda item: item[1], reverse=True)
    top_type, top_score = ranked[0]
    total = sum(nonzero.values())
    dominance = top_score / total if total else 0.0
    breadth = min(1.0, len(articles) / 6.0)
    confidence = round(100.0 * dominance * (0.55 + 0.45 * breadth), 1)
    status = "EVENT_CONTEXT_READY" if len(articles) >= 3 and confidence >= 45.0 else "ASSOCIATED_EVENT_EVIDENCE_PARTIAL"
    return {
        "status": status,
        "candidate_event_type": top_type,
        "association_confidence_pct": confidence,
        "article_count": len(articles),
        "event_type_scores": nonzero,
        "supporting_headlines": supporting.get(top_type, [])[:4],
        "causal_claim": False,
    }


def _median(values: list[float]) -> float | None:
    return round(statistics.median(values), 2) if values else None


def _event_match_summary(current: dict[str, Any], analogs: list[dict[str, Any]]) -> dict[str, Any]:
    current_type = current.get("candidate_event_type") if current.get("status") == "EVENT_CONTEXT_READY" else None
    matched = [row for row in analogs if current_type and row.get("event_context", {}).get("candidate_event_type") == current_type and row.get("event_context", {}).get("status") == "EVENT_CONTEXT_READY"]
    summary: dict[str, Any] = {
        "current_event_type": current_type,
        "current_event_context_ready": bool(current_type),
        "analog_count": len(analogs),
        "event_matched_analog_count": len(matched),
        "event_matching_state": "MEASURED" if current_type else "CURRENT_EVENT_CONTEXT_NOT_READY",
    }
    for horizon in (1, 5, 20, 60):
        key = f"fwd_{horizon}d_pct"
        values: list[float] = []
        for row in matched:
            try:
                values.append(float((row.get("forward_returns") or {}).get(key)))
            except (TypeError, ValueError):
                pass
        summary[f"event_matched_{horizon}d_median_pct"] = _median(values)
        summary[f"event_matched_{horizon}d_sample"] = len(values)
    return summary


def reconstruct_study(study: dict[str, Any], event_dir: Path) -> dict[str, Any]:
    symbol = str(study.get("symbol") or "").strip()
    label = str(study.get("label") or symbol)
    as_of = _parse_date(study.get("as_of_date"))
    if not symbol or as_of is None:
        return {"symbol": symbol or None, "label": label, "status": "INVALID_10H_STUDY", "analogs": []}
    current_articles, current_provider = _fetch_articles(symbol=symbol, label=label, center=as_of, event_dir=event_dir, span_days=2, current=True)
    current_context = classify_event_context(current_articles)
    current_context["provider"] = current_provider
    reconstructed: list[dict[str, Any]] = []
    errors: list[str] = []
    for analog in _rows(study.get("analogs"))[:ANALOGS_PER_SYMBOL]:
        analog_date = _parse_date(analog.get("date"))
        if analog_date is None:
            continue
        articles, provider = _fetch_articles(symbol=symbol, label=label, center=analog_date, event_dir=event_dir, span_days=2, current=False)
        context = classify_event_context(articles)
        context["provider"] = provider
        if provider.get("error"):
            errors.append(f"{analog_date.isoformat()}: {provider.get('error')}")
        reconstructed.append({
            "date": analog_date.isoformat(),
            "similarity_score": analog.get("similarity_score"),
            "forward_returns": analog.get("forward_returns") if isinstance(analog.get("forward_returns"), dict) else {},
            "event_context": context,
        })
    match_summary = _event_match_summary(current_context, reconstructed)
    ready_contexts = sum(1 for row in reconstructed if (row.get("event_context") or {}).get("status") == "EVENT_CONTEXT_READY")
    status = "EVENT_RECONSTRUCTION_READY" if reconstructed and ready_contexts > 0 else ("EVENT_RECONSTRUCTION_PARTIAL" if reconstructed else "EVENT_RECONSTRUCTION_WAITING")
    return {
        "symbol": symbol,
        "label": label,
        "status": status,
        "as_of_date": as_of.isoformat(),
        "price_analog_method": study.get("method"),
        "current_event_context": current_context,
        "analogs": reconstructed,
        "analog_event_contexts_ready": ready_contexts,
        "event_match_summary": match_summary,
        "errors": errors[:8],
        "truth_contract": "ASSOCIATED_EVENT_EVIDENCE_NOT_CAUSAL_PROOF",
    }


def run_cycle(*, historical_dir: Path, event_dir: Path, symbols_per_cycle: int = 1) -> dict[str, Any]:
    historical = _read_json(historical_dir / "latest_historical_market_intelligence.json")
    studies = [row for row in _rows(historical.get("studies")) if row.get("status") == "ANALOG_STUDY_READY"]
    prior = _read_json(event_dir / "latest_historical_event_reconstruction.json")
    prior_by_symbol = {str(row.get("symbol")): row for row in _rows(prior.get("reconstructions")) if row.get("symbol")}
    cursor = int((prior.get("cycle") or {}).get("next_cursor") or 0) if isinstance(prior.get("cycle"), dict) else 0
    if studies:
        cursor %= len(studies)
    batch = [studies[(cursor + index) % len(studies)] for index in range(min(max(1, symbols_per_cycle), len(studies)))] if studies else []
    processed: list[str] = []
    errors: list[str] = []
    for study in batch:
        reconstruction = reconstruct_study(study, event_dir)
        symbol = str(reconstruction.get("symbol") or "")
        if symbol:
            prior_by_symbol[symbol] = reconstruction
            processed.append(symbol)
        errors.extend(str(value) for value in _rows(reconstruction.get("errors")))
        if isinstance(reconstruction.get("errors"), list):
            errors.extend(str(value) for value in reconstruction.get("errors") if value)
    next_cursor = (cursor + len(batch)) % len(studies) if studies else 0
    reconstructions = sorted(prior_by_symbol.values(), key=lambda row: str(row.get("symbol") or ""))
    ready = sum(1 for row in reconstructions if row.get("status") == "EVENT_RECONSTRUCTION_READY")
    current_ready = sum(1 for row in reconstructions if (row.get("current_event_context") or {}).get("status") == "EVENT_CONTEXT_READY")
    analog_contexts = sum(int(row.get("analog_event_contexts_ready") or 0) for row in reconstructions)
    status = "HISTORICAL_EVENT_RECONSTRUCTION_ACTIVE" if ready else ("HISTORICAL_EVENT_RECONSTRUCTION_DEGRADED" if errors else "HISTORICAL_EVENT_RECONSTRUCTION_WARM_UP")
    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _utc_now(),
        "status": status,
        "mode": "TWENTY_FOUR_SEVEN_READ_ONLY_EVENT_RESEARCH",
        "cycle": {
            "cycle_id": f"10J-{int(time.time())}",
            "cycle_count": int((prior.get("cycle") or {}).get("cycle_count") or 0) + 1 if isinstance(prior.get("cycle"), dict) else 1,
            "queue_size": len(studies),
            "processed_symbols": processed,
            "next_cursor": next_cursor,
            "symbols_per_cycle": symbols_per_cycle,
            "error_count": len(errors),
        },
        "coverage": {
            "provider": "GDELT_DOC_2",
            "modern_news_corpus_start": MIN_GDELT_DATE.isoformat(),
            "price_analog_studies_available": len(studies),
            "symbols_reconstructed": len(reconstructions),
            "symbols_ready": ready,
            "current_event_contexts_ready": current_ready,
            "analog_event_contexts_ready": analog_contexts,
            "coverage_policy": "NEVER_BACKFILL_OR_INFER_EVENT_CONTEXT_WHEN_PROVIDER_EVIDENCE_IS_ABSENT",
        },
        "reconstructions": reconstructions,
        "research_summary": {
            "symbols_known": len(studies),
            "symbols_reconstructed": len(reconstructions),
            "symbols_ready": ready,
            "current_contexts_ready": current_ready,
            "analog_contexts_ready": analog_contexts,
            "errors": errors[:12],
        },
        "measurement_plan": {
            "comparison": "PRICE_ONLY_ANALOGS_VS_EVENT_MATCHED_ANALOGS",
            "future_metric": "Compare event-matched analog usefulness against mature 9J outcomes before any weighting proposal.",
            "causal_language_policy": "Candidate associated event type only; headlines near a date do not prove market causality.",
        },
        "safety": {
            "read_only_research": True,
            "advisory_only": True,
            "causal_claim_authority": False,
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
    _atomic_write(event_dir / "latest_historical_event_reconstruction.json", payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one governed Batch 10J historical event-reconstruction cycle.")
    parser.add_argument("--historical-dir", default=str(DEFAULT_HISTORICAL_DIR))
    parser.add_argument("--event-dir", default=str(DEFAULT_EVENT_DIR))
    parser.add_argument("--symbols-per-cycle", type=int, default=1)
    parser.add_argument("--stdout", action="store_true")
    args = parser.parse_args()
    payload = run_cycle(
        historical_dir=Path(args.historical_dir).expanduser(),
        event_dir=Path(args.event_dir).expanduser(),
        symbols_per_cycle=max(1, min(args.symbols_per_cycle, 4)),
    )
    output = payload if args.stdout else {
        "status": payload.get("status"),
        "processed": (payload.get("cycle") or {}).get("processed_symbols"),
        "symbols_ready": (payload.get("research_summary") or {}).get("symbols_ready"),
        "live_execution": False,
    }
    print(json.dumps(output, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
