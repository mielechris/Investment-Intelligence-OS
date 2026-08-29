#!/usr/bin/env python3
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

SCHEMA_VERSION="batch10f-institutional-investment-firm-os-v1"


def build_firm_os(*,readiness:dict[str,Any],qualification:dict[str,Any],portfolio:dict[str,Any],regime:dict[str,Any],generated_at:datetime|None=None)->dict[str,Any]:
    modules=[
        ("MARKET_OBSERVATION","9A/9E/9G/9H","Observe market, independent benchmark and telemetry"),
        ("RESEARCH_DEBATE","8 agents + 9M/9N","Research, debate, replay and provenance"),
        ("DECISION_RISK","Committee + Risk","Governed decision and deterministic risk inspection"),
        ("PAPER_EXECUTION","9B + paper portfolio","Paper-only execution and accounting"),
        ("OUTCOME_LEARNING","9J + 9O","Outcome memory and daily factory episode"),
        ("CONTINUOUS_IMPROVEMENT","9P/9Q","Advisory improvement and shadow experimentation"),
        ("DATA_GOVERNANCE","9R","Measured-gap source expansion and licensing gates"),
        ("PERFORMANCE_REGIME","9S/9T","Agent performance and market-regime intelligence"),
        ("OPERATING_CONTROL","10A/10B/10C","Unified browser, paper qualification, portfolio intelligence"),
        ("CAPITAL_PRESERVATION","10D/10E","Stress lab and governed readiness dossier"),
    ]
    institutional_gaps=[
        "independent legal/compliance governance and documented jurisdictional scope",
        "live broker/custodian integration, permissions segregation and reconciliation",
        "production market-data licensing, entitlement inventory and audit rights",
        "formal human roles, escalation matrix, incident response and business continuity",
        "tax/accounting reporting controls and external statement reconciliation",
        "security review, secrets management, disaster recovery and retention policy",
        "validated capacity, liquidity, market-impact and execution-quality measurement",
        "formal investment mandate, risk appetite and capital-allocation policy approved by humans",
    ]
    return {
        "schema_version":SCHEMA_VERSION,"generated_at":(generated_at or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat(),
        "status":"INSTITUTIONAL_OS_ARCHITECTURE_READY_LIVE_CAPITAL_NOT_AUTHORIZED",
        "operating_loop":["Observe market","Discover opportunities","Research","Debate","Decide","Risk inspect","Paper test","Measure outcome","Grade decision","Learn","Identify weaknesses","Recommend upgrades","Shadow-test upgrades","Human approves","Improve factory","Repeat"],
        "modules":[{"room":room,"systems":systems,"purpose":purpose} for room,systems,purpose in modules],
        "current_state":{"capital_readiness":readiness.get("status"),"paper_qualification":qualification.get("status"),"paper_positions":portfolio.get("position_count"),"regime_label":regime.get("regime_label")},
        "institutionalization_gaps":institutional_gaps,
        "governance_principles":["Evidence before authority","Persisted lineage before attribution","Shadow before production","Human approval before material configuration change","Paper qualification before capital-readiness review","Capital preservation before return maximization","No silent degradation: WAITING and MEASUREMENT GAP remain visible"],
        "safety":{"architecture_only":True,"institutional_label_does_not_imply_regulatory_status":True,"auto_enable_live":False,"broker_connection_authority":False,"capital_authority":False,"trade_execution_permission":False,"live_execution":False,"human_approval_required":True}
    }
