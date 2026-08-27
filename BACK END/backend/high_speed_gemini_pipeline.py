from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any
from uuid import uuid4

import gemini_provider
import gemini_rapid_research
import grok_provider
import high_speed_market_radar as core
from ledger import latest_object, record_event, record_object, utc_now
from opportunity_acquisition import OPPORTUNITY_LEDGER_CASE, promote_candidate, score_candidate
from provider_hardening import fetch_google_news_rss, fetch_market_quote


POLICY_VERSION = "batch9e-grok-gemini-high-speed-radar-v2"
MODEL_EXECUTION_MODE = "GROK_AND_GEMINI_PARALLEL"
GEMINI_DEEP_REQUEST_TYPE = "gemini_deep_research_request"
GEMINI_DEEP_COMPLEXITY_GATE = 65.0
MAX_GEMINI_DEEP_REQUESTS_PER_CYCLE = 2


def _combine_rank(
    sweep_rows: list[dict[str, Any]],
    grok: dict[str, dict[str, Any]],
    gemini: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for row in sweep_rows:
        ticker = str(row.get("ticker") or "").upper()
        grok_row = grok.get(ticker) or {}
        gemini_row = gemini.get(ticker) or {}
        radar_score = float(row.get("radar_score") or 0.0)
        grok_score = float(grok_row.get("attention_score") or 0.0)
        gemini_score = float(gemini_row.get("research_score") or 0.0)

        weighted: list[tuple[float, float]] = [(radar_score, 0.50)]
        if grok_row:
            weighted.append((grok_score, 0.25))
        if gemini_row:
            weighted.append((gemini_score, 0.25))
        total_weight = sum(weight for _, weight in weighted) or 1.0
        rank_score = sum(score * weight for score, weight in weighted) / total_weight

        output.append(
            {
                **row,
                "grok": grok_row,
                "gemini": gemini_row,
                "rank_score": round(rank_score, 2),
                "ranking_only": True,
                "external_model_context_is_qualification_evidence": False,
            }
        )
    output.sort(key=lambda row: float(row.get("rank_score") or 0.0), reverse=True)
    return output


def _build_promotion_candidates(
    ranked: list[dict[str, Any]],
    scan_id: str,
    *,
    evidence_limit: int = core.PROMOTION_EVIDENCE_COUNT,
) -> list[dict[str, Any]]:
    recent_tickers = core._recent_case_tickers()
    output: list[dict[str, Any]] = []

    for row in ranked[: max(1, min(int(evidence_limit), 15))]:
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
            news_error = None
        except Exception as exc:  # noqa: BLE001
            news = []
            news_error = f"{type(exc).__name__}: {exc}"

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
            "gemini_research_score": (row.get("gemini") or {}).get("research_score"),
            "current_price": quote.get("current_price"),
            "quote_provider": quote.get("provider"),
            "quote_error": quote.get("error"),
            "news_error": news_error,
            "evidence": evidence,
            "evidence_count": len(evidence),
            "external_model_context": {
                "grok": row.get("grok") or {},
                "gemini": row.get("gemini") or {},
                "context_only": True,
                "qualification_evidence": False,
                "fact_resolution_authority": False,
            },
            "promoted_case_id": None,
            "created_by": "BATCH_9E_GROK_GEMINI_HIGH_SPEED_RADAR",
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

    output.sort(key=lambda row: float(row.get("radar_rank_score") or 0.0), reverse=True)
    return output


def _queue_gemini_deep(
    promotions: list[dict[str, Any]],
    ranked: list[dict[str, Any]],
) -> list[str]:
    if not gemini_provider.configuration_status().get("configured"):
        return []
    by_ticker = {str(row.get("ticker") or "").upper(): row for row in ranked}
    queued: list[str] = []

    for promotion in promotions:
        if len(queued) >= MAX_GEMINI_DEEP_REQUESTS_PER_CYCLE:
            break
        case = promotion.get("case") or {}
        candidate = promotion.get("candidate") or {}
        case_id = str(case.get("case_id") or "")
        ticker = str(candidate.get("ticker") or "").upper()
        row = by_ticker.get(ticker) or {}
        complexity = float(((row.get("gemini") or {}).get("complexity_score") or 0.0))
        if not case_id or complexity < GEMINI_DEEP_COMPLEXITY_GATE:
            continue

        request_id = f"gemini_deep_request_{uuid4().hex}"
        request = {
            "gemini_deep_research_request_id": request_id,
            "case_id": case_id,
            "ticker": ticker,
            "status": "QUEUED",
            "objective": (
                f"Perform a deep independent source-grounded investigation of {ticker}. Reconcile the deterministic radar, "
                "Grok Wire Room, and Gemini Flash rapid research. Seek primary sources, contradictions, thesis risks, and what "
                "changed versus what was already known. Do not recommend or execute a trade."
            ),
            "source_context": row,
            "provider_model": gemini_provider.pro_model(),
            "context_only": True,
            "qualification_evidence": False,
            "fact_resolution_authority": False,
            "capital_authority": False,
            "trade_signal": False,
            "paper_order_permission": False,
            "trade_execution_permission": False,
            "live_execution": False,
            "created_at": utc_now(),
        }
        record_object(request_id, GEMINI_DEEP_REQUEST_TYPE, case_id, request, topic=ticker)
        queued.append(request_id)
    return queued


def run_parallel_high_speed_cycle(
    *,
    enable_grok: bool = True,
    enable_gemini: bool = True,
    enable_promotions: bool = True,
    promotion_limit: int = core.MAX_PROMOTIONS_PER_CYCLE,
    force_model_refresh: bool = False,
) -> dict[str, Any]:
    """Run 9E with Grok and Gemini concurrently; neither model receives decision authority."""
    started = time.perf_counter()
    cycle_id = f"high_speed_radar_{uuid4().hex}"
    sweep = core.fast_market_sweep()
    sweep_rows = sweep.get("candidates") or []
    fingerprint = core._deep_fingerprint(sweep_rows)

    grok_status = grok_provider.configuration_status()
    gemini_status = gemini_provider.configuration_status()
    models_requested = bool(enable_grok or enable_gemini)

    reuse_packet = latest_object(core.MODEL_CONTEXT_TYPE, case_id=core.RADAR_CASE_ID) or {}
    reuse = False
    if (
        models_requested
        and not force_model_refresh
        and reuse_packet.get("model_execution_mode") == MODEL_EXECUTION_MODE
        and core._can_reuse_deep_context(fingerprint)
    ):
        grok_reuse_ok = not enable_grok or reuse_packet.get("grok_execution_satisfied") is True
        gemini_reuse_ok = not enable_gemini or reuse_packet.get("gemini_execution_satisfied") is True
        reuse = bool(grok_reuse_ok and gemini_reuse_ok)

    grok: dict[str, dict[str, Any]] = {}
    gemini: dict[str, dict[str, Any]] = {}
    gemini_diagnostics: dict[str, str] = {}
    provider_errors: dict[str, str] = {}
    deep_started = time.perf_counter()
    grok_execution_satisfied = False
    gemini_execution_satisfied = False

    if reuse:
        grok = reuse_packet.get("grok") if isinstance(reuse_packet.get("grok"), dict) else {}
        gemini = reuse_packet.get("gemini") if isinstance(reuse_packet.get("gemini"), dict) else {}
        gemini_diagnostics = (
            dict(reuse_packet.get("gemini_diagnostics") or {})
            if isinstance(reuse_packet.get("gemini_diagnostics"), dict)
            else {}
        )
        provider_errors = (
            dict(reuse_packet.get("provider_errors") or {})
            if isinstance(reuse_packet.get("provider_errors"), dict)
            else {}
        )
        grok_execution_satisfied = not enable_grok or reuse_packet.get("grok_execution_satisfied") is True
        gemini_execution_satisfied = not enable_gemini or reuse_packet.get("gemini_execution_satisfied") is True
    else:
        grok_input = sweep_rows[: core.GROK_BATCH_SIZE * core.GROK_MAX_BATCHES]
        gemini_input = sweep_rows[: gemini_rapid_research.DEFAULT_FINALIST_COUNT]

        if enable_grok and not grok_status.get("configured"):
            provider_errors["grok"] = "PROVIDER_NOT_CONFIGURED"
        if enable_gemini and not gemini_status.get("configured"):
            provider_errors["gemini"] = "PROVIDER_NOT_CONFIGURED"

        with ThreadPoolExecutor(max_workers=2) as pool:
            grok_future = (
                pool.submit(core._run_grok_wire, grok_input)
                if enable_grok and grok_status.get("configured") and grok_input
                else None
            )
            gemini_future = (
                pool.submit(
                    gemini_rapid_research.run_gemini_rapid_research,
                    gemini_input,
                    finalist_count=gemini_rapid_research.DEFAULT_FINALIST_COUNT,
                    max_workers=gemini_rapid_research.DEFAULT_MAX_WORKERS,
                )
                if enable_gemini and gemini_status.get("configured") and gemini_input
                else None
            )

            if grok_future is not None:
                try:
                    grok = grok_future.result()
                except Exception as exc:  # noqa: BLE001
                    provider_errors["grok"] = f"{type(exc).__name__}: {exc}"[:2500]

            if gemini_future is not None:
                try:
                    gemini, gemini_diagnostics = gemini_future.result()
                except Exception as exc:  # noqa: BLE001
                    provider_errors["gemini"] = f"{type(exc).__name__}: {exc}"[:2500]

        if enable_grok and grok_status.get("configured") and grok_input and not grok:
            provider_errors.setdefault("grok", "NO_CANDIDATES_RETURNED")
        if enable_gemini and gemini_status.get("configured") and gemini_input and not gemini:
            provider_errors.setdefault("gemini", "NO_CANDIDATES_RETURNED")

        grok_execution_satisfied = bool(
            not enable_grok
            or (grok_status.get("configured") is True and bool(grok) and "grok" not in provider_errors)
        )
        gemini_execution_satisfied = bool(
            not enable_gemini
            or (
                gemini_status.get("configured") is True
                and bool(gemini)
                and "gemini" not in provider_errors
            )
        )

        if models_requested:
            model_packet_id = f"high_speed_model_context_{uuid4().hex}"
            model_packet = {
                "high_speed_market_model_context_id": model_packet_id,
                "policy_version": POLICY_VERSION,
                "deep_fingerprint": fingerprint,
                "grok_requested": bool(enable_grok),
                "gemini_requested": bool(enable_gemini),
                "grok_execution_satisfied": grok_execution_satisfied,
                "gemini_execution_satisfied": gemini_execution_satisfied,
                "model_execution_satisfied": bool(
                    grok_execution_satisfied and gemini_execution_satisfied
                ),
                "force_model_refresh": bool(force_model_refresh),
                "grok": grok,
                "gemini": gemini,
                "gemini_diagnostics": gemini_diagnostics,
                "provider_errors": provider_errors,
                "grok_provider": grok_status,
                "gemini_provider": gemini_status,
                "model_execution_mode": MODEL_EXECUTION_MODE,
                "grok_x_search": True,
                "grok_web_search": True,
                "gemini_google_search_grounding": True,
                "gemini_url_context": True,
                "gemini_structured_outputs": True,
                "context_only": True,
                "qualification_evidence": False,
                "committee_override": False,
                "risk_override": False,
                "capital_authority": False,
                "trade_execution_permission": False,
                "live_execution": False,
                "created_at": utc_now(),
            }
            record_object(
                model_packet_id,
                core.MODEL_CONTEXT_TYPE,
                core.RADAR_CASE_ID,
                model_packet,
                topic="HIGH_SPEED_GROK_GEMINI_MODEL_CONTEXT",
            )

    model_execution_satisfied = bool(
        models_requested and grok_execution_satisfied and gemini_execution_satisfied
    )
    deep_duration = round(time.perf_counter() - deep_started, 3)
    ranked = _combine_rank(sweep_rows, grok, gemini)
    candidates = _build_promotion_candidates(ranked, cycle_id)

    promotions: list[dict[str, Any]] = []
    if enable_promotions:
        for candidate in candidates:
            if len(promotions) >= max(0, min(int(promotion_limit), core.MAX_PROMOTIONS_PER_CYCLE)):
                break
            if candidate.get("eligible_for_promotion") is not True:
                continue
            try:
                promotions.append(promote_candidate(str(candidate["opportunity_candidate_id"])))
            except Exception:  # noqa: BLE001
                continue

    deep_requests = _queue_gemini_deep(promotions, ranked)
    completed_at = utc_now()
    duration = round(time.perf_counter() - started, 3)

    prior_state = latest_object(core.STATE_TYPE, case_id=core.RADAR_CASE_ID) or {}
    if reuse:
        deep_research_completed_at = prior_state.get("deep_research_completed_at")
    elif model_execution_satisfied:
        deep_research_completed_at = completed_at
    else:
        deep_research_completed_at = None

    state = {
        "high_speed_market_radar_state_id": core.STATE_ID,
        "policy_version": POLICY_VERSION,
        "last_cycle_id": cycle_id,
        "last_cycle_completed_at": completed_at,
        "deep_research_completed_at": deep_research_completed_at,
        "deep_fingerprint": fingerprint,
        "deep_context_reused": reuse,
        "model_refresh_forced": bool(force_model_refresh),
        "models_requested": models_requested,
        "grok_requested": bool(enable_grok),
        "gemini_requested": bool(enable_gemini),
        "grok_configured": grok_status.get("configured") is True,
        "gemini_configured": gemini_status.get("configured") is True,
        "grok_execution_satisfied": grok_execution_satisfied,
        "gemini_execution_satisfied": gemini_execution_satisfied,
        "model_execution_satisfied": model_execution_satisfied,
        "model_execution_mode": MODEL_EXECUTION_MODE,
        "governed_universe_count": sweep.get("governed_universe_count"),
        "screener_hit_count": sweep.get("screener_hit_count"),
        "grok_candidate_count": len(grok),
        "gemini_candidate_count": len(gemini),
        "gemini_diagnostics": gemini_diagnostics,
        "promotion_candidate_count": len(candidates),
        "promoted_case_count": len(promotions),
        "promoted_cases": [
            {
                "case_id": (row.get("case") or {}).get("case_id"),
                "ticker": (row.get("candidate") or {}).get("ticker"),
                "rank_score": (row.get("candidate") or {}).get("radar_rank_score"),
            }
            for row in promotions
        ],
        "gemini_deep_request_count": len(deep_requests),
        "gemini_deep_request_ids": deep_requests,
        "provider_errors": provider_errors,
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
    record_object(core.STATE_ID, core.STATE_TYPE, core.RADAR_CASE_ID, state, topic="HIGH_SPEED_MARKET_RADAR")

    cycle = {
        "high_speed_market_radar_cycle_id": cycle_id,
        **state,
        "fast_sweep": sweep,
        "ranked_candidates": ranked[:40],
        "promotion_candidates": candidates,
        "created_at": completed_at,
    }
    record_object(cycle_id, core.CYCLE_TYPE, core.RADAR_CASE_ID, cycle, topic="HIGH_SPEED_MARKET_RADAR")
    record_event(
        core.RADAR_CASE_ID,
        "HIGH_SPEED_GROK_GEMINI_RADAR_COMPLETE",
        entity_id=cycle_id,
        payload={
            "governed_universe_count": state["governed_universe_count"],
            "screener_hit_count": state["screener_hit_count"],
            "grok_candidate_count": state["grok_candidate_count"],
            "gemini_candidate_count": state["gemini_candidate_count"],
            "promoted_case_count": state["promoted_case_count"],
            "deep_context_reused": reuse,
            "model_execution_satisfied": state["model_execution_satisfied"],
            "model_execution_mode": state["model_execution_mode"],
            "trade_execution_permission": False,
        },
    )
    return cycle
