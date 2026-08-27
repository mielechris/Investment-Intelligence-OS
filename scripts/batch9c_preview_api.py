#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND = REPO_ROOT / "BACK END" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from factory_intelligence_ui import build_case_detail, build_overview  # noqa: E402
from governed_paper_execution_api import build_paper_fund_operations  # noqa: E402


app = FastAPI(
    title="IIOS Batch 9C Read-Only Preview API",
    version="9C-preview",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5190",
        "http://localhost:5190",
    ],
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["Accept", "Content-Type"],
)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "mode": "BATCH_9C_READ_ONLY_PREVIEW",
        "scheduler_started": False,
        "paper_order_route_exposed": False,
        "broker_connected": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }


@app.get("/paper-fund/operations")
def paper_fund_operations():
    return build_paper_fund_operations()


@app.get("/experience/factory-intelligence/overview")
def factory_overview():
    return build_overview()


@app.get("/experience/factory-intelligence/case/{case_id}")
def factory_case(case_id: str):
    try:
        return build_case_detail(case_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
