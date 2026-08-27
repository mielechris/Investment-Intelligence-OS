from __future__ import annotations

import hashlib
import json
import math
import os
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode
from uuid import uuid4

import grok_provider
import kimi_provider
import kimi_swarm_bridge
from batch8c_production_inputs import current_strict_governed_universe
from factory_genericization import resolve_case_profile
from ledger import DB_PATH, get_object, latest_object, record_event, record_object, utc_now
from opportunity_acquisition import (
    OPPORTUNITY_LEDGER_CASE,
    promote_candidate,
    score_candidate,
)
from paper_portfolio_validation import _candidate_case_ids
from provider_hardening import _json_request, fetch_google_news_rss, fetch_market_quote


POLICY_VERSION = "batch9e-high-speed-market-radar-v1"
RADAR_CASE_ID = "high_speed_market_radar"
STATE_ID = "high_speed_market_radar_state_v1"
STATE_TYPE = "high_speed_market_radar_state"
CYCLE_TYPE = "high_speed_market_radar_cycle"
MODEL_CONTEXT_TYPE = "high_speed_market_model_context"
SWARM_REQUEST_TYPE = "kimi_swarm_research_request"

SCREENER_IDS = (
    "day_gainers",
    "day_losers",
    "most_actives",
)
SCREENER_COUNT = max(25, min(int(os.getenv("IIOS_9E_SCREENER_COUNT", "100")), 100))
GROK_BATCH_SIZE = max(10, min(int(os.getenv("IIOS_9E_GROK_BATCH_SIZE", "35")), 50))
GROK_MAX_BATCHES = max(1, min(int(os.getenv("IIOS_9E_GROK_MAX_BATCHES", "2")), 4))
KIMI_FINALIST_COUNT = max(4, min(int(os.getenv("IIOS_9E_KIMI_FINALISTS", "12")), 24))
KIMI_WORKERS = max(1, min(int(os.getenv("IIOS_9E_KIMI_WORKERS", "4")), 8))
PROMOTION_EVIDENCE_COUNT = max(3, min(int(os.getenv("IIOS_9E_PROMOTION_EVIDENCE_COUNT", "8")), 15))
MAX_PROMOTIONS_PER_CYCLE = max(1, min(int(os.getenv("IIOS_9E_MAX_PROMOTIONS", "5")), 5))
MAX_AGENT_CASES_PER_CYCLE = max(1, min(int(os.getenv("IIOS_9E_MAX_AGENT_CASES", "2")), 2))
RECENT_CASE_COOLDOWN_HOURS = max(1, min(int(os.getenv("IIOS_9E_RECENT_CASE_COOLDOWN_HOURS", "12")), 72))
DEEP_REFRESH_MINUTES = max(5, min(int(os.getenv("IIOS_9E_DEEP_REFRESH_MINUTES", "15")), 120))


def _safe_float(value: Any, default: float | None = None) -> float | None:
    if isinstance(value, dict) and "raw" in value:
        value = value.get("raw")
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(number):
        return default
    return number


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


def _strict_universe() -> tuple[list[str], dict[str, str]]:
    governed = current_strict_governed_universe()
    if not isinstance(governed, dict):
        raise RuntimeError("STRICT_GOVERNED_UNIVERSE_UNAVAILABLE")
    if governed.get("verified_complete") is not True or governed.get("strict_membership") is not True:
        raise RuntimeError("STRICT_GOVERNED_UNIVERSE_NOT_VERIFIED")

    raw = governed.get("symbols") or []
    symbols: list[str] = []
    aliases: dict[str, str] = {}
    for row in raw:
        symbol = str(row.get("ticker") if isinstance(row, dict) else row or "").strip().upper()
        if not symbol:
            continue
        if symbol not in symbols:
            symbols.append(symbol)
        aliases[_canonical_symbol(symbol)] = symbol

    if not symbols:
        raise RuntimeError("STRICT_GOVERNED_UNIVERSE_EMPTY")
    return symbols, aliases


def _yahoo_screener(scr_id: str, count: int = SCREENER_COUNT) -> list[dict[str, Any]]:
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
                provider="yahoo_9e_market_radar",
                minimum_interval_seconds=0.18,
                retries=1,
                cache_ttl_seconds=120,
            )
            result = ((payload.get("finance") or {}).get("result") or [None])[0]
            quotes = result.get("quotes") if isinstance(result, dict) else None
            if isinstance(quotes, list):
                return [row for row in quotes if isinstance(row, dict)]
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{host}:{type(exc).__name__}:{exc}")
    raise RuntimeError(" | ".join(errors) or f"Yahoo screener unavailable: {scr_id}")


def _radar_score(row: dict[str, Any], appearances: set[str]) -> tuple[float, list[str]]:
    change = abs(_safe_float(row.get("regularMarketChangePercent"), 0.0) or 0.0)
    volume = _safe_float(row.get("regularMarketVolume"), 0.0) or 0.0
    avg_volume = (
        _safe_float(row.get("averageDailyVolume3Month"))
        or _safe_float(row.get("averageDailyVolume10Day"))
        or 0.0
    )
    ratio = (volume / avg_volume) if volume > 0 and avg_volume > 0 else 0.0

    score = 10.0
    reasons: list[str] = []
    score += min(change * 5.0, 35.0)
    if change >= 2.0:
        reasons.append("MATERIAL_PRICE_MOVE")
    if change >= 5.0:
        reasons.append("LARGE_PRICE_MOVE")

    if ratio > 0:
        score += min(max(ratio - 0.75, 0.0) * 18.0, 25.0)
        if ratio >= 1.5:
            reasons.append("ELEVATED_VOLUME")
        if ratio >= 2.5:
            reasons.append("UNUSUAL_VOLUME")

    if "most_actives" in appearances:
        score += 10.0
        reasons.append("MOST_ACTIVE")
    if "day_gainers" in appearances:
        score += 6.0
        reasons.append("DAY_GAINER")
    if "day_losers" in appearances:
        score += 6.0
        reasons.append("DAY_LOSER")
    if len(appearances) >= 2:
        score += 8.0
        reasons.append("MULTI_SCREENER_CONSENSUS")

    market_cap = _safe_float(row.get("marketCap"), 0.0) or 0.0
    if market_cap >= 10_000_000_000:
        score += 4.0
        reasons.append("LARGE_CAP_LIQUIDITY")

    return round(max(0.0, min(100.0, score)), 2), reasons


def fast_market_sweep() -> dict[str, Any]:
    symbols, aliases = _strict_universe()
    collected: dict[str, dict[str, Any]] = {}
    provider_errors: list[str] = []

    for screener_id in SCREENER_IDS:
        try:
            rows = _yahoo_screener(screener_id)
        except Exception as exc:  # noqa: BLE001
            provider_errors.append(f"{screener_id}:{type(exc).__name__}:{exc}")
            continue

        for row in rows:
            yahoo_symbol = str(row.get("symbol") or "").strip().upper()
            governed_symbol = aliases.get(_canonical_symbol(yahoo_symbol))
            if not governed_symbol:
                continue
            item = collected.setdefault(
                governed_symbol,
                {
                    "ticker": governed_symbol,
                    "company": str(row.get("shortName") or row.get("longName") or governed_symbol),
                    "screeners": set(),
                    "quote": row,
                },
            )
            item["screeners"].add(screener_id)
            # Prefer the row with the richest data.
            if len(row) > len(item.get("quote") or {}):
                item["quote"] = row

    ranked: list[dict[str, Any]] = []
    for ticker, item in collected.items():
        score, reasons = _radar_score(item.get("quote") or {}, item["screeners"])
        quote = item.get("quote") or {}
        ranked.append(
            {
                "ticker": ticker,
                "company": item["company"],
                "radar_score": score,
                "radar_reason_codes": reasons,
                "screeners": sorted(item["screeners"]),
                "current_price": _safe_float(quote.get("regularMarketPrice")),
                "change_pct": _safe_float(quote.get("regularMarketChangePercent")),
                "volume": _safe_float(quote.get("regularMarketVolume")),
                "average_volume": (
                    _safe_float(quote.get("averageDailyVolume3Month"))
                    or _safe_float(quote.get("averageDailyVolume10Day"))
                ),
                "market_cap": _safe_float(quote.get("marketCap")),
                "strict_governed_universe": True,
            }
        )

    ranked.sort(key=lambda row: float(row.get("radar_score") or 0.0), reverse=True)
    return {
        "governed_universe_count": len(symbols),
        "screener_hit_count": len(ranked),
        "candidates": ranked,
        "provider_errors": provider_errors,
        "strict_membership": True,
    }


def _grok_batch_prompt(rows: list[dict[str, Any]]) -> tuple[str, str]:
    system = (
        "You are Grok operating as IIOS's pre-case real-time Wire Room. Use X Search and Web Search at full useful capability "
        "to identify breaking narratives, verified catalysts, management comments, policy/regulatory developments, crowding, hype, "
        "contradictions, and reasons attention may be temporary. Do not recommend a trade. Treat social claims as unverified until "
        "corroborated. Return JSON only with key ranked_candidates. Each item must contain ticker, attention_score 0..100, "
        "narrative, catalysts, contradictions, crowding_signals, evidence_needed. Only include supplied tickers."
    )
    user = json.dumps(
        {
            "objective": "Find which radar names deserve immediate governed research, not which names to buy.",
            "candidates": rows,
        },
        ensure_ascii=False,
        default=str,
    )
    return system, user


def _run_grok_wire(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    if not grok_provider.configuration_status().get("configured"):
        return {}
    chunks = [rows[index : index + GROK_BATCH_SIZE] for index in range(0, len(rows), GROK_BATCH_SIZE)]
    chunks = chunks[:GROK_MAX_BATCHES]
    output: dict[str, dict[str, Any]] = {}

    def one(chunk: list[dict[str, Any]]) -> dict[str, Any]:
        system, user = _grok_batch_prompt(chunk)
        return grok_provider.research_json(
            system=system,
            user=user,
            use_x_search=True,
            use_web_search=True,
        )

    with ThreadPoolExecutor(max_workers=min(2, len(chunks) or 1)) as pool:
        futures = [pool.submit(one, chunk) for chunk in chunks]
        for future in as_completed(futures):
            try:
                result = future.result()
            except Exception as exc:  # noqa: BLE001
                continue
            payload = result.get("output") or {}
            for row in payload.get("ranked_candidates") or []:
                if not isinstance(row, dict):
                    continue
                ticker = str(row.get("ticker") or "").strip().upper()
                if not ticker:
                    continue
                output[ticker] = {
                    "attention_score": max(0.0, min(100.0, float(row.get("attention_score") or 0.0))),
                    "narrative": str(row.get("narrative") or "")[:2000],
                    "catalysts": [str(x)[:500] for x in row.get("catalysts") or []][:12],
                    "contradictions": [str(x)[:500] for x in row.get("contradictions") or []][:12],
                    "crowding_signals": [str(x)[:500] for x in row.get("crowding_signals") or []][:12],
                    "evidence_needed": [str(x)[:500] for x in row.get("evidence_needed") or []][:12],
                    "citations": result.get("citations") or [],
                    "provider_model": result.get("model"),
                    "latency_ms": result.get("latency_ms"),
                    "usage": result.get("usage") or {},
                    "context_only": True,
                }
    return output


def _kimi_prompt(row: dict[str, Any]) -> tuple[str, str]:
    system = (
        "You are Kimi K3 operating as IIOS's rapid pre-case due-diligence research crew. Use Formula Web Search when available and "
        "high reasoning to investigate the supplied company. Verify the catalyst, identify primary/credible sources, separate fact from "
        "inference, test whether the move appears structural or temporary, and list missing evidence. Do not recommend a trade. Return "
        "JSON only with keys: ticker, research_score 0..100, verified_catalysts, counterevidence, primary_sources_found, open_questions, "
        "research_summary, complexity_score 0..100."
    )
    user = json.dumps(row, ensure_ascii=False, default=str)
    return system, user


def _run_kimi_research(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    if not kimi_provider.configuration_status().get("configured"):
        return {}
    finalists = rows[:KIMI_FINALIST_COUNT]
    output: dict[str, dict[str, Any]] = {}

    def one(row: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        system, user = _kimi_prompt(row)
        result = kimi_provider.research_json_with_web_search(
            system=system,
            user=user,
            max_tool_rounds=6,
            max_completion_tokens=6000,
        )
        return str(row.get("ticker") or "").upper(), result

    with ThreadPoolExecutor(max_workers=min(KIMI_WORKERS, len(finalists) or 1)) as pool:
        futures = [pool.submit(one, row) for row in finalists]
        for future in as_completed(futures):
            try:
                ticker, result = future.result()
            except Exception:  # noqa: BLE001
                continue
            value = result.get("output") or {}
            if not isinstance(value, dict):
                continue
            output[ticker] = {
                "research_score": max(0.0, min(100.0, float(value.get("research_score") or 0.0))),
                "verified_catalysts": [str(x)[:700] for x in value.get("verified_catalysts") or []][:15],
                "counterevidence": [str(x)[:700] for x in value.get("counterevidence") or []][:15],
                "primary_sources_found": [str(x)[:700] for x in value.get("primary_sources_found") or []][:15],
                "open_questions": [str(x)[:700] for x in value.get("open_questions") or []][:15],
                "research_summary": str(value.get("research_summary") or "")[:3500],
                "complexity_score": max(0.0, min(100.0, float(value.get("complexity_score") or 0.0))),
                "provider_model": result.get("model"),
                "usage": result.get("usage") or {},
                "tool_calls_used": result.get("tool_calls_used"),
                "context_only": True,
            }
    return output


def _recent_case_tickers() -> set[str]:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=RECENT_CASE_COOLDOWN_HOURS)
    output: set[str] = set()
    for case_id in _candidate_case_ids():
        try:
            case = get_object(case_id) or {}
            created = _parse_time(case.get("created_at"))
            if created is None or created < cutoff:
                continue
            profile = resolve_case_profile(case_id)
            ticker = str(profile.get("ticker") or "").strip().upper()
            if ticker:
                output.add(ticker)
        except Exception:  # noqa: BLE001
            continue
    return output


def _combine_rank(
    sweep_rows: list[dict[str, Any]],
    grok: dict[str, dict[str, Any]],
    kimi: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for row in sweep_rows:
        ticker = str(row.get("ticker") or "").upper()
        grok_row = grok.get(ticker) or {}
        kimi_row = kimi.get(ticker) or {}
        radar = float(row.get("radar_score") or 0.0)
        grok_score = float(grok_row.get("attention_score") or 0.0)
        kimi_score = float(kimi_row.get("research_score") or 0.0)

        available_weights = [(radar, 0.50)]
        if grok_row:
            available_weights.append((grok_score, 0.25))
        if kimi_row:
            available_weights.append((kimi_score, 0.25))
        total_weight = sum(weight for _, weight in available_weights) or 1.0
        rank_score = sum(score * weight for score, weight in available_weights) / total_weight

        output.append(
            {
                **row,
                "grok": grok_row,
                "kimi": kimi_row,
                "rank_score": round(rank_score, 2),
                "ranking_only": True,
                "external_model_context_is_qualification_evidence": False,
            }
        )
    output.sort(key=lambda row: float(row.get("rank_score") or 0.0), reverse=True)
    return output


def _deep_fingerprint(rows: list[dict[str, Any]]) -> str:
    compact = [
        {
            "ticker": row.get("ticker"),
            "change_bucket": round((float(row.get("change_pct") or 0.0)) * 2.0) / 2.0,
            "screeners": row.get("screeners") or [],
        }
        for row in rows[:50]
    ]
    return hashlib.sha256(json.dumps(compact, sort_keys=True).encode("utf-8")).hexdigest()


def _can_reuse_deep_context(fingerprint: str) -> bool:
    state = latest_object(STATE_TYPE, case_id=RADAR_CASE_ID) or {}
    if state.get("deep_fingerprint") != fingerprint:
        return False
    completed = _parse_time(state.get("deep_research_completed_at"))
    return bool(
        completed
        and datetime.now(timezone.utc) - completed < timedelta(minutes=DEEP_REFRESH_MINUTES)
    )


def _rows_by_type(object_type: str, limit: int = 100) -> list[dict[str, Any]]:
    db = sqlite3.connect(DB_PATH, timeout=30)
    db.row_factory = sqlite3.Row
    try:
        rows = db.execute(
            "SELECT payload_json FROM ledger_objects WHERE object_type=? ORDER BY created_at DESC LIMIT ?",
            (object_type, max(1, min(int(limit), 1000))),
        ).fetchall()
    finally:
        db.close()
    output: list[dict[str, Any]] = []
    for row in rows:
        try:
            value = json.loads(row["payload_json"])
        except Exception:  # noqa: BLE001
            continue
        if isinstance(value, dict):
            output.append(value)
    return output


def _reuse_model_context() -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    packet = latest_object(MODEL_CONTEXT_TYPE, case_id=RADAR_CASE_ID) or {}
    grok = packet.get("grok") if isinstance(packet.get("grok"), dict) else {}
    kimi = packet.get("kimi") if isinstance(packet.get("kimi"), dict) else {}
    return grok, kimi


def _build_promotion_candidates(
    ranked: list[dict[str, Any]],
    scan_id: str,
    *,
    evidence_limit: int = PROMOTION_EVIDENCE_COUNT,
) -> list[dict[str, Any]]:
    recent_tickers = _recent_case_tickers()
    output: list[dict[str, Any]] = []

    for row in ranked[:evidence_limit]:
        ticker = str(row.get("ticker") or "").upper()
        company = str(row.get("company") or ticker)
        quote = fetch_market_quote(ticker)
        try:
            news = fetch_google_news_rss(
                {
                    "query": f'"{company}" {ticker} stock',
                    "limit": 8,
                }
            )
        except Exception as exc:  # noqa: BLE001
            news = []
            news_error = f"{type(exc).__name__}: {exc}"
        else:
            news_error = None

        scored = score_candidate(ticker=ticker, quote=quote, news_items=news)
        blocked_recent = ticker in recent_tickers
        eligible = scored.get("eligible_for_promotion") is True and not blocked_recent
        reasons = list(scored.get("reason_codes") or [])
        if blocked_recent:
            reasons.append("RECENT_GOVERNED_CASE_EXISTS")

        candidate_id = f"opportunity_{uuid4().hex}"
        evidence = list(quote.get("items") or []) + list(news)
        candidate = {
            "opportunity_candidate_id": candidate_id,
            "opportunity_scan_id": scan_id,
            "ticker": ticker,
            "label": company,
            "query": f"{company} {ticker}",
            **scored,
            "eligible_for_promotion": eligible,
            "reason_codes": reasons,
            "score": scored.get("score"),
            "radar_rank_score": row.get("rank_score"),
            "radar_score": row.get("radar_score"),
            "grok_attention_score": (row.get("grok") or {}).get("attention_score"),
            "kimi_research_score": (row.get("kimi") or {}).get("research_score"),
            "current_price": quote.get("current_price"),
            "quote_provider": quote.get("provider"),
            "quote_error": quote.get("error"),
            "news_error": news_error,
            "evidence": evidence,
            "evidence_count": len(evidence),
            "external_model_context": {
                "grok": row.get("grok") or {},
                "kimi": row.get("kimi") or {},
                "context_only": True,
                "qualification_evidence": False,
                "fact_resolution_authority": False,
            },
            "promoted_case_id": None,
            "created_by": "BATCH_9E_HIGH_SPEED_MARKET_RADAR",
            "created_at": utc_now(),
            "paper_mode": True,
            "trade_signal": False,
            "auto_trade_authority": False,
            "paper_order_permission": False,
            "trade_execution_permission": False,
            "live_execution": False,
        }
        record_object(
            candidate_id,
            "opportunity_candidate",
            OPPORTUNITY_LEDGER_CASE,
            candidate,
            topic=company,
        )
        output.append(candidate)

    output.sort(
        key=lambda row: float(row.get("radar_rank_score") or 0.0),
        reverse=True,
    )
    return output


def _queue_swarm(promotions: list[dict[str, Any]], ranked: list[dict[str, Any]]) -> list[str]:
    if not kimi_swarm_bridge.configuration_status().get("configured"):
        return []
    by_ticker = {str(row.get("ticker") or "").upper(): row for row in ranked}
    queued: list[str] = []
    for promotion in promotions[:2]:
        case = promotion.get("case") or {}
        candidate = promotion.get("candidate") or {}
        case_id = str(case.get("case_id") or "")
        ticker = str(candidate.get("ticker") or "").upper()
        row = by_ticker.get(ticker) or {}
        complexity = float(((row.get("kimi") or {}).get("complexity_score") or 0.0))
        if not case_id or complexity < 55.0:
            continue
        request_id = f"kimi_swarm_request_{uuid4().hex}"
        payload = {
            "kimi_swarm_research_request_id": request_id,
            "case_id": case_id,
            "ticker": ticker,
            "status": "QUEUED",
            "objective": (
                f"Deep independent investigation of {ticker}. Reconcile the radar, Grok Wire Room and Kimi K3 rapid-research context; "
                "seek primary sources and contradictions. Context only. Do not make a trade recommendation."
            ),
            "source_context": row,
            "repo_write_access_granted": False,
            "qualification_evidence": False,
            "capital_authority": False,
            "trade_execution_permission": False,
            "live_execution": False,
            "created_at": utc_now(),
        }
        record_object(request_id, SWARM_REQUEST_TYPE, case_id, payload, topic=ticker)
        queued.append(request_id)
    return queued


def run_high_speed_cycle(
    *,
    enable_grok: bool = True,
    enable_kimi: bool = True,
    enable_promotions: bool = True,
    promotion_limit: int = MAX_PROMOTIONS_PER_CYCLE,
) -> dict[str, Any]:
    started = time.perf_counter()
    cycle_id = f"high_speed_radar_{uuid4().hex}"
    sweep = fast_market_sweep()
    sweep_rows = sweep.get("candidates") or []
    fingerprint = _deep_fingerprint(sweep_rows)
    reuse = _can_reuse_deep_context(fingerprint)

    grok: dict[str, dict[str, Any]] = {}
    kimi: dict[str, dict[str, Any]] = {}
    deep_started = time.perf_counter()

    if reuse:
        grok, kimi = _reuse_model_context()
    else:
        grok_input = sweep_rows[: GROK_BATCH_SIZE * GROK_MAX_BATCHES]
        if enable_grok:
            grok = _run_grok_wire(grok_input)

        provisional = _combine_rank(sweep_rows, grok, {})
        if enable_kimi:
            kimi = _run_kimi_research(provisional)

        model_packet_id = f"high_speed_model_context_{uuid4().hex}"
        model_packet = {
            "high_speed_market_model_context_id": model_packet_id,
            "deep_fingerprint": fingerprint,
            "grok": grok,
            "kimi": kimi,
            "grok_provider": grok_provider.configuration_status(),
            "kimi_provider": kimi_provider.configuration_status(),
            "kimi_swarm_provider": kimi_swarm_bridge.configuration_status(),
            "context_only": True,
            "qualification_evidence": False,
            "committee_override": False,
            "risk_override": False,
            "capital_authority": False,
            "trade_execution_permission": False,
            "live_execution": False,
            "created_at": utc_now(),
        }
        record_object(model_packet_id, MODEL_CONTEXT_TYPE, RADAR_CASE_ID, model_packet)

    deep_duration = round(time.perf_counter() - deep_started, 3)
    ranked = _combine_rank(sweep_rows, grok, kimi)
    candidates = _build_promotion_candidates(ranked, cycle_id)

    promotions: list[dict[str, Any]] = []
    if enable_promotions:
        for candidate in candidates:
            if len(promotions) >= max(0, min(int(promotion_limit), MAX_PROMOTIONS_PER_CYCLE)):
                break
            if candidate.get("eligible_for_promotion") is not True:
                continue
            try:
                promotions.append(promote_candidate(str(candidate["opportunity_candidate_id"])))
            except Exception:  # noqa: BLE001
                continue

    swarm_requests = _queue_swarm(promotions, ranked)
    completed_at = utc_now()
    duration = round(time.perf_counter() - started, 3)
    state = {
        "high_speed_market_radar_state_id": STATE_ID,
        "policy_version": POLICY_VERSION,
        "last_cycle_id": cycle_id,
        "last_cycle_completed_at": completed_at,
        "deep_research_completed_at": completed_at if not reuse else (latest_object(STATE_TYPE, case_id=RADAR_CASE_ID) or {}).get("deep_research_completed_at"),
        "deep_fingerprint": fingerprint,
        "deep_context_reused": reuse,
        "governed_universe_count": sweep.get("governed_universe_count"),
        "screener_hit_count": sweep.get("screener_hit_count"),
        "grok_candidate_count": len(grok),
        "kimi_candidate_count": len(kimi),
        "promotion_candidate_count": len(candidates),
        "promoted_case_count": len(promotions),
        "promoted_cases": [
            {
                "case_id": (row.get("case") or {}).get("case_id"),
                "ticker": (row.get("candidate") or {}).get("ticker"),
                "score": (row.get("candidate") or {}).get("radar_rank_score"),
            }
            for row in promotions
        ],
        "swarm_request_count": len(swarm_requests),
        "swarm_request_ids": swarm_requests,
        "cycle_duration_seconds": duration,
        "deep_research_duration_seconds": deep_duration,
        "paper_mode": True,
        "trade_signal": False,
        "auto_trade_authority": False,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
        "created_at": completed_at,
    }
    record_object(STATE_ID, STATE_TYPE, RADAR_CASE_ID, state, topic="HIGH_SPEED_MARKET_RADAR")

    cycle = {
        "high_speed_market_radar_cycle_id": cycle_id,
        **state,
        "fast_sweep": sweep,
        "ranked_candidates": ranked[:40],
        "promotion_candidates": candidates,
        "created_at": completed_at,
    }
    record_object(cycle_id, CYCLE_TYPE, RADAR_CASE_ID, cycle, topic="HIGH_SPEED_MARKET_RADAR")
    record_event(
        RADAR_CASE_ID,
        "HIGH_SPEED_MARKET_RADAR_COMPLETE",
        entity_id=cycle_id,
        payload={
            "governed_universe_count": state["governed_universe_count"],
            "screener_hit_count": state["screener_hit_count"],
            "grok_candidate_count": state["grok_candidate_count"],
            "kimi_candidate_count": state["kimi_candidate_count"],
            "promoted_case_count": state["promoted_case_count"],
            "deep_context_reused": reuse,
            "trade_execution_permission": False,
        },
    )
    return cycle


def latest_status() -> dict[str, Any]:
    return {
        "state": latest_object(STATE_TYPE, case_id=RADAR_CASE_ID),
        "latest_cycle": latest_object(CYCLE_TYPE, case_id=RADAR_CASE_ID),
        "grok_provider": grok_provider.configuration_status(),
        "kimi_provider": kimi_provider.configuration_status(),
        "kimi_swarm_provider": kimi_swarm_bridge.configuration_status(),
        "policy_version": POLICY_VERSION,
        "paper_mode": True,
        "trade_execution_permission": False,
        "live_execution": False,
    }
