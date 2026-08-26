from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Body, HTTPException

import kimi_provider
import kimi_swarm_bridge
from institutional_research_intelligence import institutional_research_evidence
from judgment_bank_integration import build_judgment_context
from ledger import DB_PATH, get_object, latest_object, list_objects, record_event, record_object, utc_now
from macro_policy_intelligence import market_policy_evidence
from thesis_integrity_v2 import thesis_integrity_evidence


router = APIRouter()
KIMI_FACTORY_CASE = "kimi_research_factory"
MAX_DOCUMENTS = 100
MAX_CHARS_PER_DOCUMENT = 180_000
MAX_TOTAL_INPUT_CHARS = 2_400_000
MAX_PARALLEL_WORKERS = max(1, min(int(os.getenv("IIOS_KIMI_MAX_PARALLEL_WORKERS", "4")), 12))


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


def _list(value: Any, limit: int = 20) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(x).strip() for x in value if str(x).strip()][:limit]


def _float(value: Any, default: float = 0.5) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return default


def _document(value: Any, index: int) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    title = str(value.get("title") or f"Document {index + 1}").strip()
    content = str(value.get("content") or value.get("report_text") or "").strip()
    if not content:
        return None
    content = content[:MAX_CHARS_PER_DOCUMENT]
    return {
        "document_id": str(value.get("document_id") or f"doc_{index + 1}"),
        "institution": str(value.get("institution") or value.get("source") or "UNKNOWN").strip(),
        "title": title,
        "published_at": str(value.get("published_at") or "").strip() or None,
        "source_url": value.get("source_url") or value.get("url"),
        "access_tier": str(value.get("access_tier") or "AUTHORIZED_OR_PUBLIC").upper(),
        "content": content,
        "content_hash": hashlib.sha256(content.encode("utf-8")).hexdigest(),
        "char_count": len(content),
    }


def normalize_documents(values: Any) -> list[dict[str, Any]]:
    if not isinstance(values, list):
        return []
    docs: list[dict[str, Any]] = []
    total = 0
    for index, value in enumerate(values[:MAX_DOCUMENTS]):
        doc = _document(value, index)
        if not doc:
            continue
        remaining = MAX_TOTAL_INPUT_CHARS - total
        if remaining <= 0:
            break
        if doc["char_count"] > remaining:
            doc["content"] = doc["content"][:remaining]
            doc["char_count"] = len(doc["content"])
            doc["content_hash"] = hashlib.sha256(doc["content"].encode("utf-8")).hexdigest()
        total += doc["char_count"]
        docs.append(doc)
    return docs


def document_manifest(doc: dict[str, Any]) -> dict[str, Any]:
    return {
        "document_id": doc.get("document_id"),
        "institution": doc.get("institution"),
        "title": doc.get("title"),
        "published_at": doc.get("published_at"),
        "source_url": doc.get("source_url"),
        "access_tier": doc.get("access_tier"),
        "content_hash": doc.get("content_hash"),
        "char_count": doc.get("char_count"),
        "full_text_persisted": False,
    }


def _normalize_sector_views(values: Any) -> list[dict[str, Any]]:
    output = []
    for value in values if isinstance(values, list) else []:
        if not isinstance(value, dict):
            continue
        sector = str(value.get("sector") or "").strip().upper().replace(" ", "_")
        if not sector:
            continue
        sentiment = str(value.get("sentiment") or "MIXED").upper()
        if sentiment not in {"FAVORABLE", "MIXED", "UNFAVORABLE"}:
            sentiment = "MIXED"
        output.append(
            {
                "sector": sector,
                "sentiment": sentiment,
                "conviction": _float(value.get("conviction")),
                "drivers": _list(value.get("drivers"), 10),
                "risks": _list(value.get("risks"), 10),
                "tickers": [x.upper() for x in _list(value.get("tickers"), 25)],
            }
        )
    return output[:25]


def normalize_worker_output(value: Any, doc: dict[str, Any]) -> dict[str, Any]:
    value = value if isinstance(value, dict) else {}
    citations = []
    for row in value.get("citations") or []:
        if not isinstance(row, dict):
            continue
        citations.append(
            {
                "source_title": str(row.get("source_title") or doc.get("title") or "").strip(),
                "source_url": row.get("source_url") or doc.get("source_url"),
                "section_locator": str(row.get("section_locator") or "").strip()[:300],
                "supports": str(row.get("supports") or "").strip()[:800],
            }
        )
    return {
        "document_id": doc.get("document_id"),
        "institution": doc.get("institution"),
        "title": doc.get("title"),
        "summary": str(value.get("summary") or "").strip()[:5000],
        "sector_views": _normalize_sector_views(value.get("sector_views")),
        "key_assumptions": _list(value.get("key_assumptions"), 20),
        "catalysts": _list(value.get("catalysts"), 20),
        "risks": _list(value.get("risks"), 20),
        "falsifiers": _list(value.get("falsifiers"), 20),
        "open_questions": _list(value.get("open_questions"), 20),
        "citations": citations[:20],
        "confidence": _float(value.get("confidence")),
        "full_text_persisted": False,
    }


def normalize_synthesis(value: Any) -> dict[str, Any]:
    value = value if isinstance(value, dict) else {}
    disagreements = []
    for row in value.get("disagreements") or []:
        if not isinstance(row, dict):
            continue
        disagreements.append(
            {
                "topic": str(row.get("topic") or "").strip()[:500],
                "side_a": str(row.get("side_a") or "").strip()[:1000],
                "side_b": str(row.get("side_b") or "").strip()[:1000],
                "assumption_causing_divergence": str(row.get("assumption_causing_divergence") or "").strip()[:1200],
                "what_would_resolve_it": str(row.get("what_would_resolve_it") or "").strip()[:1200],
            }
        )
    return {
        "executive_summary": str(value.get("executive_summary") or "").strip()[:8000],
        "consensus": _list(value.get("consensus"), 30),
        "disagreements": disagreements[:30],
        "sector_matrix": _normalize_sector_views(value.get("sector_matrix")),
        "assumption_conflicts": _list(value.get("assumption_conflicts"), 30),
        "company_divergences": _list(value.get("company_divergences"), 30),
        "open_questions": _list(value.get("open_questions"), 30),
        "recommended_followup_research": _list(value.get("recommended_followup_research"), 30),
        "confidence": _float(value.get("confidence")),
    }


def _worker_prompt(doc: dict[str, Any], objective: str) -> tuple[str, str]:
    system = (
        "You are Kimi operating as a research analyst inside IIOS. Analyze only the supplied source. "
        "Separate sourced facts from inference. Do not recommend or execute a trade. Do not reproduce long passages. "
        "Return JSON only with keys: summary, sector_views, key_assumptions, catalysts, risks, falsifiers, "
        "open_questions, citations, confidence. sector_views items use sector, sentiment FAVORABLE|MIXED|UNFAVORABLE, "
        "conviction 0..1, drivers, risks, tickers. citations must use source_title/source_url/section_locator/supports and "
        "must paraphrase rather than quote copyrighted text."
    )
    user = json.dumps(
        {
            "objective": objective,
            "source": {
                "institution": doc.get("institution"),
                "title": doc.get("title"),
                "published_at": doc.get("published_at"),
                "source_url": doc.get("source_url"),
                "access_tier": doc.get("access_tier"),
            },
            "document_text": doc.get("content"),
        },
        ensure_ascii=False,
    )
    return system, user


def _analyze_one(doc: dict[str, Any], objective: str, use_web_search: bool) -> dict[str, Any]:
    system, user = _worker_prompt(doc, objective)
    result = (
        kimi_provider.research_json_with_web_search(system=system, user=user)
        if use_web_search
        else kimi_provider.chat_json(system=system, user=user)
    )
    return {
        "status": result.get("status"),
        "model": result.get("model"),
        "usage": result.get("usage") or {},
        "analysis": normalize_worker_output(result.get("output"), doc),
    }


def _synthesize(worker_results: list[dict[str, Any]], objective: str) -> dict[str, Any]:
    payload = [row.get("analysis") for row in worker_results if row.get("status") == "CAPTURED"]
    system = (
        "You are Kimi serving as a cross-report synthesis analyst inside IIOS. Reconcile normalized research analyses. "
        "Preserve disagreement; do not average away dissent. Identify assumptions that cause institutions to diverge. "
        "Do not make a trade recommendation. Return JSON only with keys: executive_summary, consensus, disagreements, "
        "sector_matrix, assumption_conflicts, company_divergences, open_questions, recommended_followup_research, confidence."
    )
    user = json.dumps({"objective": objective, "normalized_research": payload}, ensure_ascii=False)
    result = kimi_provider.chat_json(system=system, user=user, max_completion_tokens=8000)
    return {
        "status": result.get("status"),
        "model": result.get("model"),
        "usage": result.get("usage") or {},
        "analysis": normalize_synthesis(result.get("output")),
    }


def _persist_packet(
    *,
    case_id: str,
    objective: str,
    documents: list[dict[str, Any]],
    workers: list[dict[str, Any]],
    synthesis: dict[str, Any],
    execution_mode: str,
    use_web_search: bool,
) -> dict[str, Any]:
    packet_id = f"kimi_research_{uuid4().hex}"
    packet = {
        "kimi_research_packet_id": packet_id,
        "case_id": case_id,
        "objective": objective,
        "execution_mode": execution_mode,
        "use_kimi_formula_web_search": use_web_search,
        "provider_model": synthesis.get("model") or next((x.get("model") for x in workers if x.get("model")), None),
        "document_manifest": [document_manifest(doc) for doc in documents],
        "document_count": len(documents),
        "worker_results": workers,
        "synthesis": synthesis.get("analysis") or {},
        "provider_status": kimi_provider.configuration_status(),
        "native_swarm_status": kimi_swarm_bridge.configuration_status(),
        "full_report_persisted": False,
        "normalized_analysis_only": True,
        "licensing_note": "Full source text is used ephemerally for authorized analysis and is not persisted by this Kimi layer.",
        "untrusted_model_output": True,
        "requires_independent_corroboration": True,
        "context_only": True,
        "qualification_evidence": False,
        "gap_resolution_eligible": False,
        "fact_resolution_authority": False,
        "committee_override": False,
        "capital_authority": False,
        "trade_signal": False,
        "auto_trade_authority": False,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
        "created_at": utc_now(),
    }
    record_object(packet_id, "kimi_research_packet", case_id, packet, topic=objective)
    record_event(
        case_id,
        "KIMI_RESEARCH_COMPLETE",
        entity_id=packet_id,
        payload={
            "document_count": len(documents),
            "execution_mode": execution_mode,
            "worker_success_count": sum(1 for x in workers if x.get("status") == "CAPTURED"),
            "trade_execution_permission": False,
        },
    )
    return packet


def run_research(request: dict[str, Any]) -> dict[str, Any]:
    objective = str(request.get("objective") or "Cross-source investment research synthesis").strip()
    case_id = str(request.get("case_id") or KIMI_FACTORY_CASE).strip()
    documents = normalize_documents(request.get("documents"))
    use_web_search = request.get("use_web_search") is True

    if not documents:
        raise ValueError("At least one document with content is required")
    provider = kimi_provider.configuration_status()
    if not provider.get("configured"):
        return {
            "status": "PROVIDER_NOT_CONFIGURED",
            "provider_status": provider,
            "document_manifest": [document_manifest(doc) for doc in documents],
            "full_report_persisted": False,
            "context_only": True,
            "trade_execution_permission": False,
            "live_execution": False,
        }

    workers: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=min(MAX_PARALLEL_WORKERS, len(documents))) as pool:
        future_map = {
            pool.submit(_analyze_one, doc, objective, use_web_search): doc
            for doc in documents
        }
        for future in as_completed(future_map):
            doc = future_map[future]
            try:
                row = future.result()
            except Exception as exc:
                row = {
                    "status": "FAILED",
                    "model": None,
                    "usage": {},
                    "analysis": {
                        "document_id": doc.get("document_id"),
                        "institution": doc.get("institution"),
                        "title": doc.get("title"),
                        "error": f"{type(exc).__name__}: {exc}",
                        "full_text_persisted": False,
                    },
                }
            workers.append(row)

    successes = [row for row in workers if row.get("status") == "CAPTURED"]
    if not successes:
        return {
            "status": "FAILED",
            "worker_results": workers,
            "provider_status": provider,
            "document_manifest": [document_manifest(doc) for doc in documents],
            "full_report_persisted": False,
            "context_only": True,
            "trade_execution_permission": False,
            "live_execution": False,
        }

    synthesis = _synthesize(successes, objective)
    packet = _persist_packet(
        case_id=case_id,
        objective=objective,
        documents=documents,
        workers=workers,
        synthesis=synthesis,
        execution_mode="IIOS_PARALLEL_KIMI_API",
        use_web_search=use_web_search,
    )
    return {"status": "COMPLETE", "packet": packet}


def case_context_documents(case_id: str) -> list[dict[str, Any]]:
    case = get_object(case_id)
    if not case:
        raise ValueError("Unknown case_id")
    evidence = []
    evidence.extend(institutional_research_evidence(case_id))
    evidence.extend(market_policy_evidence(case_id))
    evidence.extend(thesis_integrity_evidence(case_id))
    try:
        judgment = build_judgment_context(case_id)
        evidence.extend(judgment.get("context_items") or [])
    except Exception:
        pass
    committee = latest_object("committee_decision", case_id=case_id)
    if committee:
        evidence.append(
            {
                "source": "IIOS Investment Committee",
                "title": committee.get("headline"),
                "claim": committee.get("summary"),
                "dissent": committee.get("dissent"),
                "required_evidence": committee.get("required_evidence"),
                "context_only": True,
            }
        )
    return [
        {
            "document_id": f"iios_case_context_{case_id}",
            "institution": "IIOS GOVERNED CONTEXT",
            "title": str(case.get("topic") or case_id),
            "source_url": f"iios://case/{case_id}",
            "access_tier": "GOVERNED_IIOS_CONTEXT",
            "content": json.dumps(evidence, ensure_ascii=False, default=str),
        }
    ]


def run_case_research(case_id: str, request: dict[str, Any] | None = None) -> dict[str, Any]:
    request = dict(request or {})
    request["case_id"] = case_id
    request.setdefault("objective", f"Synthesize governed IIOS context for case {case_id}; surface consensus, dissent, assumption conflicts and missing research.")
    request["documents"] = case_context_documents(case_id)
    return run_research(request)


def run_native_swarm_research(request: dict[str, Any]) -> dict[str, Any]:
    objective = str(request.get("objective") or "Parallel research synthesis").strip()
    items = request.get("items") if isinstance(request.get("items"), list) else []
    clean_items = [str(x).strip()[:4000] for x in items if str(x).strip()][:128]
    if len(clean_items) < 2:
        raise ValueError("Native swarm requires at least two normalized research items")
    prompt = (
        "You are Kimi Agent Swarm operating as a research-only layer inside IIOS. "
        "Spawn parallel specialists as useful. Analyze each item independently, then reconcile consensus and disagreement. "
        "No trade recommendations, no order execution, no writes to the IIOS repository. Return a JSON object with keys "
        "executive_summary, consensus, disagreements, assumption_conflicts, open_questions, confidence.\n\n"
        f"OBJECTIVE: {objective}\nITEMS:\n" + "\n".join(f"[{i+1}] {x}" for i, x in enumerate(clean_items))
    )
    result = kimi_swarm_bridge.run_native_swarm(prompt=prompt, model=request.get("model"))
    if result.get("status") != "CAPTURED":
        return result
    try:
        parsed = json.loads(result.get("output_text") or "{}")
    except json.JSONDecodeError:
        parsed = {}
    normalized = normalize_synthesis(parsed)
    return {
        "status": "CAPTURED" if normalized.get("executive_summary") else "UNSTRUCTURED_OUTPUT",
        "analysis": normalized,
        "subagent_count": result.get("subagent_count"),
        "usage": result.get("usage") or {},
        "configuration": result.get("configuration"),
        "context_only": True,
        "qualification_evidence": False,
        "gap_resolution_eligible": False,
        "capital_authority": False,
        "trade_signal": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }


def kimi_research_evidence(case_id: str) -> list[dict[str, Any]]:
    rows = list_objects(case_id, "kimi_research_packet")
    output = []
    for packet in rows[-5:]:
        synthesis = packet.get("synthesis") or {}
        summary = str(synthesis.get("executive_summary") or "").strip()
        if not summary:
            continue
        output.append(
            {
                "source": "Kimi Research Intelligence",
                "source_type": "model_research_context",
                "evidence_type": "kimi_research_synthesis",
                "url": f"iios://kimi/{packet.get('kimi_research_packet_id')}",
                "title": "Kimi cross-report research synthesis",
                "claim": (
                    f"SUMMARY={summary[:2500]}; "
                    f"CONSENSUS={synthesis.get('consensus')}; "
                    f"DISAGREEMENTS={synthesis.get('disagreements')}; "
                    f"OPEN_QUESTIONS={synthesis.get('open_questions')}"
                ),
                "timestamp": packet.get("created_at"),
                "reliability_score": 0.55,
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
        )
    return output


def status() -> dict[str, Any]:
    packets = _rows("kimi_research_packet", 500)
    return {
        "name": "Kimi Research & Swarm Intelligence Layer",
        "provider": kimi_provider.configuration_status(),
        "native_swarm": kimi_swarm_bridge.configuration_status(),
        "packet_count": len(packets),
        "latest_packet": packets[0] if packets else None,
        "deep_research_api_claimed": False,
        "deep_research_via_k3_orchestration": True,
        "full_report_persistence": False,
        "context_only_default": True,
        "qualification_evidence_default": False,
        "gap_resolution_eligible_default": False,
        "auto_trade_authority": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }


@router.get("/intelligence/kimi/status")
def get_status():
    return status()


@router.post("/intelligence/kimi/research/run")
def run_research_api(request: dict[str, Any] = Body(...)):
    try:
        return run_research(request)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"{type(exc).__name__}: {exc}")


@router.post("/intelligence/kimi/case/{case_id}/run")
def run_case_api(case_id: str, request: dict[str, Any] = Body(default={})):
    try:
        return run_case_research(case_id, request)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"{type(exc).__name__}: {exc}")


@router.get("/intelligence/kimi/case/{case_id}")
def get_case_context(case_id: str):
    return {
        "case_id": case_id,
        "evidence": kimi_research_evidence(case_id),
        "latest_packet": latest_object("kimi_research_packet", case_id=case_id),
        "context_only": True,
        "trade_execution_permission": False,
        "live_execution": False,
    }


@router.post("/intelligence/kimi/native-swarm/run")
def run_native_swarm_api(request: dict[str, Any] = Body(...)):
    try:
        return run_native_swarm_research(request)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"{type(exc).__name__}: {exc}")
