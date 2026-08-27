#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND = REPO_ROOT / "BACK END" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from batch9d_model_brains import build_model_brains  # noqa: E402
from factory_intelligence_ui import build_case_detail, build_overview  # noqa: E402
from governed_paper_execution_api import build_paper_fund_operations  # noqa: E402
from ledger import get_object  # noqa: E402


app = FastAPI(
    title="IIOS Batch 9D Family Network Read-Only Preview API",
    version="9D-preview",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5191",
        "http://localhost:5191",
    ],
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["Accept", "Content-Type"],
)


def _case_model_research_gate(case_id: str) -> dict[str, Any]:
    """Return truthful case-specific 9E Grok/Gemini research state.

    Older Batch8/9D case details expose a Kimi research gate. The active Batch9E
    architecture instead stores Grok/Gemini ranking context on the source
    opportunity candidate. This adapter never treats provider configuration or
    global model activity as proof that one specific case was researched.
    """
    case = get_object(case_id) or {}
    candidate_id = str(case.get("source_candidate_id") or "").strip()
    candidate = get_object(candidate_id) if candidate_id else None
    candidate = candidate if isinstance(candidate, dict) else {}
    context = candidate.get("external_model_context")
    context = context if isinstance(context, dict) else {}

    grok = context.get("grok")
    gemini = context.get("gemini")
    grok_present = isinstance(grok, dict) and bool(grok)
    gemini_present = isinstance(gemini, dict) and bool(gemini)

    if grok_present and gemini_present:
        status = "COMPLETE"
        label = "Grok + Gemini research context recorded for this case"
    elif grok_present or gemini_present:
        status = "PARTIAL"
        provider = "Grok" if grok_present else "Gemini"
        label = f"Only {provider} research context recorded for this case"
    else:
        status = "PENDING"
        label = "No case-specific Grok + Gemini research context recorded yet"

    return {
        "key": "GROK_GEMINI_RESEARCH",
        "status": status,
        "label": label,
        "object_id": candidate_id or None,
        "grok_present": grok_present,
        "gemini_present": gemini_present,
        "context_only": True,
        "qualification_evidence": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }


def _modernize_case_detail(detail: dict[str, Any], case_id: str) -> dict[str, Any]:
    journey = detail.get("journey")
    journey = list(journey) if isinstance(journey, list) else []
    filtered = [
        row
        for row in journey
        if not (
            isinstance(row, dict)
            and str(row.get("key") or "").upper() == "KIMI_RESEARCH"
        )
    ]
    gate = _case_model_research_gate(case_id)
    insert_at = 1 if filtered else 0
    filtered.insert(insert_at, gate)
    return {
        **detail,
        "journey": filtered,
        "active_external_research": {
            "architecture": "GROK_PLUS_GEMINI",
            "grok": "THE_WIRE",
            "gemini": "THE_BOOKS",
            "legacy_kimi_critical_path": False,
            "context_only": True,
            "trade_execution_permission": False,
            "live_execution": False,
        },
    }


@app.get("/health")
def health():
    return {
        "status": "ok",
        "mode": "BATCH_9D_READ_ONLY_PREVIEW",
        "scheduler_started": False,
        "paper_order_route_exposed": False,
        "broker_connected": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }


@app.get("/paper-fund/operations")
def paper_fund_operations():
    return build_paper_fund_operations()


@app.get("/family-network/model-brains")
def family_network_model_brains():
    return build_model_brains()


@app.get("/experience/factory-intelligence/overview")
def factory_overview():
    return build_overview()


@app.get("/experience/factory-intelligence/case/{case_id}")
def factory_case(case_id: str):
    try:
        detail = build_case_detail(case_id)
        return _modernize_case_detail(detail, case_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
