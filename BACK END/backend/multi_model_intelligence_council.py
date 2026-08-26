from __future__ import annotations

import json
import sqlite3
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Body, HTTPException

import grok_provider
from ledger import DB_PATH, get_object, latest_object, list_objects, record_event, record_object, utc_now
from macro_policy_intelligence import market_policy_evidence
from institutional_research_intelligence import institutional_research_evidence

router = APIRouter()
COUNCIL_TYPE = "multi_model_council_packet"
STANCE_SCORE = {"UNFAVORABLE": -1.0, "MIXED": 0.0, "FAVORABLE": 1.0}


def _rows(object_type: str, limit: int = 1000) -> list[dict[str, Any]]:
    db = sqlite3.connect(DB_PATH, timeout=30)
    db.row_factory = sqlite3.Row
    try:
        rows = db.execute(
            "SELECT payload_json FROM ledger_objects WHERE object_type=? ORDER BY created_at DESC LIMIT ?",
            (object_type, limit),
        ).fetchall()
    finally:
        db.close()
    return [json.loads(row["payload_json"]) for row in rows]


def normalize_stance(value: Any) -> str:
    text = str(value or "").strip().upper().replace(" ", "_")
    aliases = {
        "BULLISH": "FAVORABLE",
        "POSITIVE": "FAVORABLE",
        "BUY": "FAVORABLE",
        "BEARISH": "UNFAVORABLE",
        "NEGATIVE": "UNFAVORABLE",
        "NO_TRADE": "UNFAVORABLE",
        "NEUTRAL": "MIXED",
        "WATCH": "MIXED",
    }
    text = aliases.get(text, text)
    return text if text in STANCE_SCORE else "MIXED"


def _confidence(value: Any, default: float = 0.5) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return default


def _list(value: Any, limit: int = 20) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(x).strip() for x in value if str(x).strip()][:limit]


def _iios_view(case_id: str) -> dict[str, Any]:
    decision = latest_object("committee_decision", case_id=case_id)
    if not decision:
        return {
            "model": "IIOS_OPENAI_CORE",
            "status": "UNAVAILABLE",
            "stance": "MIXED",
            "confidence": 0.0,
            "summary": "No governed IIOS committee decision is available yet.",
            "citation_count": 0,
        }
    disposition = str(decision.get("disposition") or decision.get("recommendation") or "WATCH")
    return {
        "model": "IIOS_OPENAI_CORE",
        "status": "AVAILABLE",
        "stance": normalize_stance(disposition),
        "confidence": _confidence(decision.get("confidence"), 0.5),
        "summary": str(decision.get("summary") or decision.get("headline") or disposition)[:5000],
        "drivers": _list(decision.get("drivers") or decision.get("supporting_reasons"), 15),
        "risks": _list(decision.get("risks") or decision.get("dissent"), 15),
        "citation_count": len(decision.get("evidence_refs") or []),
        "source_object_id": decision.get("committee_decision_id"),
        "governed_decision_source": True,
    }


def _stance_from_matrix(matrix: Any) -> tuple[str, float]:
    rows = matrix if isinstance(matrix, list) else []
    scored: list[tuple[float, float]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        stance = normalize_stance(row.get("sentiment"))
        conviction = _confidence(row.get("conviction"), 0.5)
        scored.append((STANCE_SCORE[stance], conviction))
    if not scored:
        return "MIXED", 0.5
    denominator = sum(weight for _, weight in scored) or 1.0
    score = sum(value * weight for value, weight in scored) / denominator
    stance = "FAVORABLE" if score >= 0.25 else "UNFAVORABLE" if score <= -0.25 else "MIXED"
    return stance, min(1.0, max(0.25, abs(score)))


def _kimi_view(case_id: str) -> dict[str, Any]:
    packet = latest_object("kimi_research_packet", case_id=case_id)
    if not packet:
        return {
            "model": "KIMI_RESEARCH",
            "status": "UNAVAILABLE",
            "stance": "MIXED",
            "confidence": 0.0,
            "summary": "No Kimi research packet is available for this case yet.",
            "citation_count": 0,
        }
    synthesis = packet.get("synthesis") or {}
    stance, inferred_confidence = _stance_from_matrix(synthesis.get("sector_matrix"))
    citations = 0
    for worker in packet.get("worker_results") or []:
        analysis = worker.get("analysis") if isinstance(worker, dict) else None
        if isinstance(analysis, dict):
            citations += len(analysis.get("citations") or [])
    return {
        "model": "KIMI_RESEARCH",
        "status": "AVAILABLE",
        "stance": stance,
        "confidence": _confidence(synthesis.get("confidence"), inferred_confidence),
        "summary": str(synthesis.get("executive_summary") or "")[:5000],
        "consensus": _list(synthesis.get("consensus"), 20),
        "disagreements": synthesis.get("disagreements") if isinstance(synthesis.get("disagreements"), list) else [],
        "risks": _list(synthesis.get("open_questions"), 20),
        "citation_count": citations,
        "source_object_id": packet.get("kimi_research_packet_id"),
        "untrusted_model_output": True,
    }


def _grok_context(case_id: str, kimi_view: dict[str, Any], iios_view: dict[str, Any]) -> dict[str, Any]:
    case = get_object(case_id) or {}
    institutional = institutional_research_evidence(case_id)[:12]
    policy = market_policy_evidence(case_id)[:8]
    return {
        "case_id": case_id,
        "topic": case.get("topic"),
        "ticker": case.get("ticker"),
        "iios_core": iios_view,
        "kimi_research": kimi_view,
        "institutional_context": institutional,
        "policy_context": policy,
    }


def normalize_grok_output(value: Any, citations: list[str] | None = None) -> dict[str, Any]:
    value = value if isinstance(value, dict) else {}
    return {
        "model": "GROK_NARRATIVE",
        "status": "AVAILABLE",
        "stance": normalize_stance(value.get("stance")),
        "confidence": _confidence(value.get("confidence"), 0.5),
        "summary": str(value.get("summary") or "")[:5000],
        "narrative_drivers": _list(value.get("narrative_drivers"), 20),
        "crowding_hype_signals": _list(value.get("crowding_hype_signals"), 20),
        "catalysts": _list(value.get("catalysts"), 20),
        "risks": _list(value.get("risks"), 20),
        "contradictions": _list(value.get("contradictions"), 20),
        "evidence_needed": _list(value.get("evidence_needed"), 20),
        "citation_urls": list(dict.fromkeys(citations or []))[:50],
        "citation_count": len(list(dict.fromkeys(citations or []))),
        "untrusted_model_output": True,
    }


def _grok_view(case_id: str, kimi_view: dict[str, Any], iios_view: dict[str, Any]) -> dict[str, Any]:
    status = grok_provider.configuration_status()
    if not status.get("configured"):
        return {
            "model": "GROK_NARRATIVE",
            "status": "PROVIDER_NOT_CONFIGURED",
            "stance": "MIXED",
            "confidence": 0.0,
            "summary": "Grok provider credential is not configured; no narrative view was invented.",
            "citation_count": 0,
            "provider_status": status,
        }

    system = (
        "You are Grok operating as the real-time narrative and crowd-intelligence analyst inside IIOS. "
        "Use X Search and Web Search to identify current narrative, crowding/hype, catalysts, contradictions and emerging risks. "
        "Do not issue a trade recommendation and do not treat social consensus as fact. Return JSON only with keys: "
        "stance (FAVORABLE|MIXED|UNFAVORABLE), confidence 0..1, summary, narrative_drivers, crowding_hype_signals, "
        "catalysts, risks, contradictions, evidence_needed."
    )
    user = json.dumps(_grok_context(case_id, kimi_view, iios_view), ensure_ascii=False, default=str)[:120000]
    result = grok_provider.research_json(system=system, user=user, use_x_search=True, use_web_search=True)
    view = normalize_grok_output(result.get("output"), result.get("citations") or [])
    view["provider_model"] = result.get("model")
    view["latency_ms"] = result.get("latency_ms")
    view["usage"] = result.get("usage") or {}
    view["x_search_enabled"] = result.get("x_search_enabled") is True
    view["web_search_enabled"] = result.get("web_search_enabled") is True
    return view


def reconcile_views(views: list[dict[str, Any]]) -> dict[str, Any]:
    available = [v for v in views if v.get("status") == "AVAILABLE" and v.get("stance") in STANCE_SCORE]
    if not available:
        return {
            "available_model_count": 0,
            "consensus_stance": "MIXED",
            "consensus_score": 0.0,
            "divergence_score": 0.0,
            "directional_conflict": False,
            "skeptic_escalation_recommended": False,
        }

    scores = [STANCE_SCORE[str(v["stance"])] for v in available]
    confidences = [_confidence(v.get("confidence"), 0.5) for v in available]
    denominator = sum(confidences) or float(len(available))
    weighted = sum(score * confidence for score, confidence in zip(scores, confidences)) / denominator
    consensus = "FAVORABLE" if weighted >= 0.25 else "UNFAVORABLE" if weighted <= -0.25 else "MIXED"

    if len(scores) < 2:
        divergence = 0.0
    else:
        distances = []
        for i in range(len(scores)):
            for j in range(i + 1, len(scores)):
                distances.append(abs(scores[i] - scores[j]) / 2.0)
        divergence = sum(distances) / len(distances) if distances else 0.0

    directional_conflict = min(scores) < 0 < max(scores)
    escalation = directional_conflict or divergence >= 0.5
    return {
        "available_model_count": len(available),
        "consensus_stance": consensus,
        "consensus_score": round(weighted, 4),
        "divergence_score": round(divergence, 4),
        "directional_conflict": directional_conflict,
        "skeptic_escalation_recommended": escalation,
    }


def _observations(views: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for view in views:
        output.append(
            {
                "model": view.get("model"),
                "status": view.get("status"),
                "stance": view.get("stance"),
                "confidence": view.get("confidence"),
                "citation_count": int(view.get("citation_count") or 0),
                "latency_ms": view.get("latency_ms"),
                "usage": view.get("usage") or {},
                "universal_weight": None,
                "task_specific_weighting_deferred_to_calibration": True,
            }
        )
    return output


def run_council(case_id: str, request: dict[str, Any] | None = None) -> dict[str, Any]:
    if not get_object(case_id):
        raise ValueError("Unknown case_id")
    request = dict(request or {})
    iios = _iios_view(case_id)
    kimi = _kimi_view(case_id)
    if request.get("run_grok", True):
        try:
            grok = _grok_view(case_id, kimi, iios)
        except Exception as exc:
            grok = {
                "model": "GROK_NARRATIVE",
                "status": "PROVIDER_ERROR",
                "stance": "MIXED",
                "confidence": 0.0,
                "summary": f"{type(exc).__name__}: {exc}"[:1500],
                "citation_count": 0,
            }
    else:
        grok = {
            "model": "GROK_NARRATIVE",
            "status": "SKIPPED",
            "stance": "MIXED",
            "confidence": 0.0,
            "summary": "Grok live narrative run skipped by request.",
            "citation_count": 0,
        }

    views = [iios, kimi, grok]
    reconciliation = reconcile_views(views)
    packet_id = f"multi_model_council_{uuid4().hex}"
    packet = {
        "multi_model_council_packet_id": packet_id,
        "case_id": case_id,
        "views": views,
        "reconciliation": reconciliation,
        "model_observations": _observations(views),
        "model_weighting_mode": "NO_UNIVERSAL_WEIGHT_UNTIL_TASK_CALIBRATION",
        "skeptic_escalation_recommended": reconciliation["skeptic_escalation_recommended"],
        "skeptic_escalation_reason": (
            "MODEL_DIRECTIONAL_DIVERGENCE" if reconciliation["directional_conflict"] else
            "MODEL_DISAGREEMENT" if reconciliation["skeptic_escalation_recommended"] else None
        ),
        "governed_iios_committee_remains_authoritative": True,
        "committee_override": False,
        "risk_override": False,
        "context_only": True,
        "qualification_evidence": False,
        "gap_resolution_eligible": False,
        "fact_resolution_authority": False,
        "capital_authority": False,
        "trade_signal": False,
        "auto_trade_authority": False,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
        "created_at": utc_now(),
    }
    record_object(packet_id, COUNCIL_TYPE, case_id, packet, topic="multi-model-intelligence-council")
    record_event(
        case_id,
        "MULTI_MODEL_COUNCIL_COMPLETE",
        entity_id=packet_id,
        payload={
            "available_model_count": reconciliation["available_model_count"],
            "divergence_score": reconciliation["divergence_score"],
            "skeptic_escalation_recommended": reconciliation["skeptic_escalation_recommended"],
            "trade_execution_permission": False,
        },
    )
    return packet


def council_evidence(case_id: str) -> list[dict[str, Any]]:
    packet = latest_object(COUNCIL_TYPE, case_id=case_id)
    if not packet:
        return []
    reconciliation = packet.get("reconciliation") or {}
    return [
        {
            "source": "IIOS Multi-Model Intelligence Council",
            "source_type": "multi_model_context",
            "evidence_type": "model_disagreement_context",
            "url": f"iios://multi-model/{packet.get('multi_model_council_packet_id')}",
            "title": "IIOS / Kimi / Grok model comparison",
            "claim": (
                f"consensus={reconciliation.get('consensus_stance')}; "
                f"divergence={reconciliation.get('divergence_score')}; "
                f"skeptic_escalation={packet.get('skeptic_escalation_recommended')}"
            ),
            "timestamp": packet.get("created_at"),
            "reliability_score": 0.45,
            "untrusted_model_output": True,
            "requires_independent_corroboration": True,
            "context_only": True,
            "qualification_evidence": False,
            "gap_resolution_eligible": False,
            "fact_resolution_authority": False,
            "capital_authority": False,
            "trade_signal": False,
            "trade_execution_permission": False,
        }
    ]


def status() -> dict[str, Any]:
    rows = _rows(COUNCIL_TYPE, 1000)
    return {
        "name": "IIOS Multi-Model Intelligence Council",
        "packet_count": len(rows),
        "latest_packet": rows[0] if rows else None,
        "models": {
            "iios_openai_core": {"role": "GOVERNED_CORE", "provider_required": False},
            "kimi": {"role": "DEEP_RESEARCH", "provider_required_for_live": True},
            "grok": {"role": "REALTIME_NARRATIVE_X_WEB", "provider": grok_provider.configuration_status()},
        },
        "universal_model_weighting": False,
        "skeptic_escalation_on_divergence": True,
        "committee_override": False,
        "risk_override": False,
        "context_only_default": True,
        "auto_trade_authority": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }


@router.get("/intelligence/multi-model-council/status")
def get_status():
    return status()


@router.get("/intelligence/multi-model-council/case/{case_id}")
def get_case(case_id: str):
    return {
        "case_id": case_id,
        "latest_packet": latest_object(COUNCIL_TYPE, case_id=case_id),
        "context": council_evidence(case_id),
        "trade_execution_permission": False,
        "live_execution": False,
    }


@router.post("/intelligence/multi-model-council/case/{case_id}/run")
def run_case(case_id: str, request: dict[str, Any] = Body(default={})):
    try:
        return run_council(case_id, request)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
