from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any
from uuid import uuid4

import grok_provider
import kimi_provider
import kimi_rapid_research
import kimi_swarm_bridge
import high_speed_market_radar as core
from ledger import latest_object, record_event, record_object, utc_now
from opportunity_acquisition import promote_candidate


def run_parallel_high_speed_cycle(
    *,
    enable_grok: bool = True,
    enable_kimi: bool = True,
    enable_promotions: bool = True,
    promotion_limit: int = core.MAX_PROMOTIONS_PER_CYCLE,
    force_model_refresh: bool = False,
) -> dict[str, Any]:
    """Run 9E with Grok and Kimi concurrently so neither blocks the other."""
    started = time.perf_counter()
    cycle_id = f"high_speed_radar_{uuid4().hex}"
    sweep = core.fast_market_sweep()
    sweep_rows = sweep.get("candidates") or []
    fingerprint = core._deep_fingerprint(sweep_rows)

    grok_status = grok_provider.configuration_status()
    kimi_status = kimi_provider.configuration_status()
    models_requested = bool(enable_grok or enable_kimi)

    reuse_packet = latest_object(core.MODEL_CONTEXT_TYPE, case_id=core.RADAR_CASE_ID) or {}
    reuse = False
    if models_requested and not force_model_refresh and core._can_reuse_deep_context(fingerprint):
        grok_reuse_ok = (
            not enable_grok
            or reuse_packet.get("grok_execution_satisfied") is True
        )
        kimi_reuse_ok = (
            not enable_kimi
            or reuse_packet.get("kimi_execution_satisfied") is True
        )
        reuse = bool(grok_reuse_ok and kimi_reuse_ok)

    grok: dict[str, dict[str, Any]] = {}
    kimi: dict[str, dict[str, Any]] = {}
    kimi_diagnostics: dict[str, str] = {}
    provider_errors: dict[str, str] = {}
    deep_started = time.perf_counter()
    grok_execution_satisfied = False
    kimi_execution_satisfied = False

    if reuse:
        grok = reuse_packet.get("grok") if isinstance(reuse_packet.get("grok"), dict) else {}
        kimi = reuse_packet.get("kimi") if isinstance(reuse_packet.get("kimi"), dict) else {}
        kimi_diagnostics = (
            dict(reuse_packet.get("kimi_diagnostics") or {})
            if isinstance(reuse_packet.get("kimi_diagnostics"), dict)
            else {}
        )
        provider_errors = (
            dict(reuse_packet.get("provider_errors") or {})
            if isinstance(reuse_packet.get("provider_errors"), dict)
            else {}
        )
        grok_execution_satisfied = (
            not enable_grok
            or reuse_packet.get("grok_execution_satisfied") is True
        )
        kimi_execution_satisfied = (
            not enable_kimi
            or reuse_packet.get("kimi_execution_satisfied") is True
        )
    else:
        grok_input = sweep_rows[: core.GROK_BATCH_SIZE * core.GROK_MAX_BATCHES]
        kimi_input = sweep_rows[: core.KIMI_FINALIST_COUNT]

        if enable_grok and not grok_status.get("configured"):
            provider_errors["grok"] = "PROVIDER_NOT_CONFIGURED"
        if enable_kimi and not kimi_status.get("configured"):
            provider_errors["kimi"] = "PROVIDER_NOT_CONFIGURED"

        with ThreadPoolExecutor(max_workers=2) as pool:
            grok_future = (
                pool.submit(core._run_grok_wire, grok_input)
                if enable_grok and grok_status.get("configured") and grok_input
                else None
            )
            kimi_future = (
                pool.submit(
                    kimi_rapid_research.run_kimi_rapid_research,
                    kimi_input,
                    max_workers=core.KIMI_WORKERS,
                )
                if enable_kimi and kimi_status.get("configured") and kimi_input
                else None
            )

            if grok_future is not None:
                try:
                    grok = grok_future.result()
                except Exception as exc:  # noqa: BLE001
                    provider_errors["grok"] = f"{type(exc).__name__}: {exc}"

            if kimi_future is not None:
                try:
                    kimi, kimi_diagnostics = kimi_future.result()
                except Exception as exc:  # noqa: BLE001
                    provider_errors["kimi"] = f"{type(exc).__name__}: {exc}"

        if enable_grok and grok_status.get("configured") and grok_input and not grok:
            provider_errors.setdefault("grok", "NO_CANDIDATES_RETURNED")
        if enable_kimi and kimi_status.get("configured") and kimi_input and not kimi:
            provider_errors.setdefault("kimi", "NO_CANDIDATES_RETURNED")

        grok_execution_satisfied = bool(
            not enable_grok
            or (
                grok_status.get("configured") is True
                and bool(grok)
                and "grok" not in provider_errors
            )
        )
        kimi_execution_satisfied = bool(
            not enable_kimi
            or (
                kimi_status.get("configured") is True
                and bool(kimi)
                and "kimi" not in provider_errors
            )
        )

        if models_requested:
            model_packet_id = f"high_speed_model_context_{uuid4().hex}"
            model_packet = {
                "high_speed_market_model_context_id": model_packet_id,
                "deep_fingerprint": fingerprint,
                "grok_requested": bool(enable_grok),
                "kimi_requested": bool(enable_kimi),
                "grok_execution_satisfied": grok_execution_satisfied,
                "kimi_execution_satisfied": kimi_execution_satisfied,
                "model_execution_satisfied": bool(
                    grok_execution_satisfied and kimi_execution_satisfied
                ),
                "force_model_refresh": bool(force_model_refresh),
                "grok": grok,
                "kimi": kimi,
                "kimi_diagnostics": kimi_diagnostics,
                "provider_errors": provider_errors,
                "grok_provider": grok_status,
                "kimi_provider": kimi_status,
                "kimi_swarm_provider": kimi_swarm_bridge.configuration_status(),
                "model_execution_mode": "GROK_AND_KIMI_PARALLEL",
                "grok_x_search": True,
                "grok_web_search": True,
                "kimi_formula_web_search": True,
                "kimi_high_reasoning": True,
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
                topic="HIGH_SPEED_MODEL_CONTEXT",
            )

    model_execution_satisfied = bool(
        models_requested
        and grok_execution_satisfied
        and kimi_execution_satisfied
    )
    deep_duration = round(time.perf_counter() - deep_started, 3)
    ranked = core._combine_rank(sweep_rows, grok, kimi)
    candidates = core._build_promotion_candidates(ranked, cycle_id)

    promotions: list[dict[str, Any]] = []
    if enable_promotions:
        for candidate in candidates:
            if len(promotions) >= max(0, min(int(promotion_limit), core.MAX_PROMOTIONS_PER_CYCLE)):
                break
            if candidate.get("eligible_for_promotion") is not True:
                continue
            try:
                promotions.append(
                    promote_candidate(str(candidate["opportunity_candidate_id"]))
                )
            except Exception:  # noqa: BLE001
                continue

    swarm_requests = core._queue_swarm(promotions, ranked)
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
        "policy_version": core.POLICY_VERSION,
        "last_cycle_id": cycle_id,
        "last_cycle_completed_at": completed_at,
        "deep_research_completed_at": deep_research_completed_at,
        "deep_fingerprint": fingerprint,
        "deep_context_reused": reuse,
        "model_refresh_forced": bool(force_model_refresh),
        "models_requested": models_requested,
        "grok_requested": bool(enable_grok),
        "kimi_requested": bool(enable_kimi),
        "grok_configured": grok_status.get("configured") is True,
        "kimi_configured": kimi_status.get("configured") is True,
        "grok_execution_satisfied": grok_execution_satisfied,
        "kimi_execution_satisfied": kimi_execution_satisfied,
        "model_execution_satisfied": model_execution_satisfied,
        "model_execution_mode": "GROK_AND_KIMI_PARALLEL",
        "governed_universe_count": sweep.get("governed_universe_count"),
        "screener_hit_count": sweep.get("screener_hit_count"),
        "grok_candidate_count": len(grok),
        "kimi_candidate_count": len(kimi),
        "kimi_diagnostics": kimi_diagnostics,
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
        "swarm_request_count": len(swarm_requests),
        "swarm_request_ids": swarm_requests,
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
    record_object(
        core.STATE_ID,
        core.STATE_TYPE,
        core.RADAR_CASE_ID,
        state,
        topic="HIGH_SPEED_MARKET_RADAR",
    )

    cycle = {
        "high_speed_market_radar_cycle_id": cycle_id,
        **state,
        "fast_sweep": sweep,
        "ranked_candidates": ranked[:40],
        "promotion_candidates": candidates,
        "created_at": completed_at,
    }
    record_object(
        cycle_id,
        core.CYCLE_TYPE,
        core.RADAR_CASE_ID,
        cycle,
        topic="HIGH_SPEED_MARKET_RADAR",
    )
    record_event(
        core.RADAR_CASE_ID,
        "HIGH_SPEED_MARKET_RADAR_COMPLETE",
        entity_id=cycle_id,
        payload={
            "governed_universe_count": state["governed_universe_count"],
            "screener_hit_count": state["screener_hit_count"],
            "grok_candidate_count": state["grok_candidate_count"],
            "kimi_candidate_count": state["kimi_candidate_count"],
            "promoted_case_count": state["promoted_case_count"],
            "deep_context_reused": reuse,
            "model_execution_satisfied": state["model_execution_satisfied"],
            "model_execution_mode": state["model_execution_mode"],
            "trade_execution_permission": False,
        },
    )
    return cycle
