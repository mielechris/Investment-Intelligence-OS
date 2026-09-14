from __future__ import annotations

import json
import sqlite3
import tempfile
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Body, HTTPException

import grok_ab_benchmark as ab
import source_ingestion
from evidence_engine import build_packet
from ledger import get_object, latest_object, record_event, record_object, utc_now
from orchestration_ab_benchmark import snapshot_ledger
from provider_hardening import fetch_market_quote


router = APIRouter()
REUSE_MODE = "REUSE_LATEST_VALIDATED_GROK_CONTEXT"
FRESH_BASE_EVIDENCE_MODE = "FRESH_PUBLIC_EVIDENCE_TEMP_SNAPSHOT_ONLY"


def validated_latest_context(case_id: str) -> dict[str, Any]:
    context = latest_object("grok_social_context", case_id=case_id) or {}
    checks = {
        "context_exists": bool(context),
        "verified_citations_present": int(context.get("citation_count") or 0) > 0,
        "admitted_context_present": int(context.get("admitted_count") or 0) > 0,
        "agent_context_present": isinstance(context.get("items_by_agent"), dict),
        "not_qualification_evidence": context.get("qualification_evidence") is False,
        "no_capital_authority": context.get("capital_authority") is False,
        "no_paper_order_permission": context.get("paper_order_permission") is False,
        "no_trade_execution_permission": context.get("trade_execution_permission") is False,
        "no_live_execution": context.get("live_execution") is False,
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise ValueError("Latest Grok context is not reusable: " + ", ".join(failed))
    return context


def _default_refresh_sources(topic: str) -> list[dict[str, Any]]:
    query = str(topic or "")[:180].strip()
    return [
        {"source": "gdelt_news", "params": {"query": query, "limit": 12, "timespan": "24h"}},
        {"source": "fred_series", "params": {"series_id": "DGS10", "limit": 4}},
    ]


def build_fresh_base_evidence(case_id: str) -> dict[str, Any]:
    """Fetch one fresh public IIOS packet for both A/B arms without mutating the live case."""
    case = get_object(case_id)
    if not case:
        raise ValueError("Unknown case_id")
    profile = latest_object("monitor_profile", case_id=case_id) or {}
    source_requests = (
        profile.get("source_requests")
        if isinstance(profile.get("source_requests"), list) and profile.get("source_requests")
        else _default_refresh_sources(str(case.get("topic") or ""))
    )
    ingestion = source_ingestion.ingest_sources(source_requests)
    ticker = str(profile.get("ticker") or "").strip()
    quote = fetch_market_quote(ticker) if ticker else {
        "status": "skipped",
        "items": [],
        "current_price": None,
        "provider": None,
        "error": None,
    }
    evidence = list(ingestion.get("evidence_items") or []) + list(quote.get("items") or [])
    packet = build_packet(evidence)
    flags = list((packet.get("summary") or {}).get("critical_flags") or [])
    if not packet.get("items"):
        raise ValueError("Fresh A/B evidence refresh returned no evidence")
    if "ALL_EVIDENCE_STALE" in flags:
        raise ValueError("Fresh A/B evidence refresh is still all stale")
    return {
        "mode": FRESH_BASE_EVIDENCE_MODE,
        "packet": packet,
        "source_requests": source_requests,
        "successful_sources": ingestion.get("successful_sources"),
        "failed_sources": ingestion.get("failed_sources"),
        "quote_status": quote.get("status"),
        "quote_provider": quote.get("provider"),
        "ticker": ticker or None,
        "live_case_evidence_mutated": False,
        "new_xai_search_calls": 0,
        "created_at": utc_now(),
    }


def patch_snapshot_case_evidence(db_path: Path, case_id: str, packet: dict[str, Any]) -> None:
    """Replace case evidence only inside an isolated A/B SQLite snapshot."""
    connection = sqlite3.connect(Path(db_path), timeout=30)
    try:
        row = connection.execute(
            "SELECT payload_json FROM ledger_objects WHERE object_id = ? AND object_type = 'case'",
            (case_id,),
        ).fetchone()
        if not row:
            raise ValueError("Case missing from A/B ledger snapshot")
        case = json.loads(row[0])
        case["evidence"] = list(packet.get("items") or [])
        case["evidence_summary"] = dict(packet.get("summary") or {})
        case["ab_base_evidence_mode"] = FRESH_BASE_EVIDENCE_MODE
        connection.execute(
            "UPDATE ledger_objects SET payload_json = ? WHERE object_id = ? AND object_type = 'case'",
            (json.dumps(case, default=str, separators=(",", ":")), case_id),
        )
        connection.commit()
    finally:
        connection.close()


def run_reused_context_ab(
    case_id: str,
    *,
    runs: int = 1,
    refresh_base_evidence: bool = False,
    persist: bool = True,
) -> dict[str, Any]:
    case = get_object(case_id)
    if not case:
        raise ValueError("Unknown case_id")

    grok_context = validated_latest_context(case_id)
    fresh_base = build_fresh_base_evidence(case_id) if refresh_base_evidence else None
    run_count = ab.normalize_runs(runs)
    source_db = Path(ab.DB_PATH).expanduser().resolve()
    baseline_signatures: list[dict[str, Any]] = []
    grok_signatures: list[dict[str, Any]] = []

    with tempfile.TemporaryDirectory(prefix="iios_grok_ab_reuse_") as tempdir:
        root = Path(tempdir)
        context_path = root / "grok_context.json"
        context_path.write_text(
            json.dumps({"items_by_agent": grok_context.get("items_by_agent") or {}}, default=str),
            encoding="utf-8",
        )
        for index in range(run_count):
            baseline_db = root / f"baseline_{index}.db"
            grok_db = root / f"grok_{index}.db"
            snapshot_ledger(source_db, baseline_db)
            snapshot_ledger(source_db, grok_db)
            if fresh_base:
                patch_snapshot_case_evidence(baseline_db, case_id, fresh_base["packet"])
                patch_snapshot_case_evidence(grok_db, case_id, fresh_base["packet"])
            baseline_signatures.append(ab.quality_signature(ab._run_child(case_id, baseline_db)))
            grok_signatures.append(
                ab.quality_signature(ab._run_child(case_id, grok_db, context_path=context_path))
            )

    comparison = ab.compare_ab(baseline_signatures, grok_signatures, grok_context)
    result_id = f"grok_ab_{uuid4().hex}"
    result = {
        "grok_ab_result_id": result_id,
        "case_id": case_id,
        "runs_per_arm": run_count,
        "context_mode": REUSE_MODE,
        "base_evidence_mode": fresh_base.get("mode") if fresh_base else "ORIGINAL_CASE_EVIDENCE",
        "base_evidence_refresh": ({
            "evidence_count": (fresh_base.get("packet") or {}).get("summary", {}).get("evidence_count"),
            "critical_flags": (fresh_base.get("packet") or {}).get("summary", {}).get("critical_flags"),
            "successful_sources": fresh_base.get("successful_sources"),
            "failed_sources": fresh_base.get("failed_sources"),
            "quote_status": fresh_base.get("quote_status"),
            "quote_provider": fresh_base.get("quote_provider"),
            "ticker": fresh_base.get("ticker"),
            "live_case_evidence_mutated": False,
        } if fresh_base else None),
        "reused_grok_social_context_id": grok_context.get("grok_social_context_id"),
        "new_xai_search_calls": 0,
        "ledger_isolation": "temporary_snapshot_per_arm",
        "grok_context_fixed_across_paired_runs": True,
        "baseline_runs": baseline_signatures,
        "grok_runs": grok_signatures,
        "grok_context_summary": {
            "summary": grok_context.get("summary"),
            "admitted_count": grok_context.get("admitted_count"),
            "quarantined_count": grok_context.get("quarantined_count"),
            "citation_count": grok_context.get("citation_count"),
            "usage": grok_context.get("usage"),
        },
        "comparison": comparison,
        "automatic_architecture_promotion": False,
        "research_only": True,
        "paper_mode": True,
        "auto_trade_authority": False,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
        "created_at": utc_now(),
    }
    if persist:
        record_object(
            result_id,
            "grok_ab_result",
            case_id,
            result,
            parent_id=case_id,
            topic=case.get("topic"),
        )
        record_event(
            case_id,
            "GROK_AB_EXPERIMENT_COMPLETE",
            entity_id=result_id,
            payload={
                "context_mode": REUSE_MODE,
                "base_evidence_mode": result["base_evidence_mode"],
                "new_xai_search_calls": 0,
                "experiment_valid": comparison.get("experiment_valid"),
                "recommendation": comparison.get("recommendation"),
                "architecture_promotion_eligible": False,
                "trade_execution_permission": False,
            },
        )
    return result


@router.get("/grok/ab-reuse/plan")
def grok_ab_reuse_plan():
    return {
        "mode": REUSE_MODE,
        "new_xai_search_calls": 0,
        "same_case": True,
        "same_ledger_snapshot": True,
        "same_iios_orchestration_profile": "baseline",
        "requires_existing_verified_context": True,
        "fresh_base_evidence_option": True,
        "fresh_base_evidence_live_case_mutation": False,
        "fresh_base_evidence_same_packet_for_both_arms": True,
        "architecture_promotion_automatic": False,
        "paper_mode": True,
        "auto_trade_authority": False,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }


@router.post("/grok/ab-reuse/{case_id}/run")
def run_grok_ab_reuse_route(case_id: str, request: dict[str, Any] = Body(default={})):
    try:
        return run_reused_context_ab(
            case_id,
            runs=ab.normalize_runs(request.get("runs") or 1),
            refresh_base_evidence=bool(request.get("refresh_base_evidence", False)),
            persist=True,
        )
    except ValueError as exc:
        status = 404 if "Unknown case_id" in str(exc) else 409
        raise HTTPException(status_code=status, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)[:1000])
