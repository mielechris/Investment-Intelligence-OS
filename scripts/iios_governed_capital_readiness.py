#!/usr/bin/env python3
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

SCHEMA_VERSION="batch10e-governed-capital-readiness-v1"


def _gate(name:str,state:str,evidence:str,owner:str)->dict[str,Any]: return {"gate":name,"state":state,"evidence":evidence,"owner":owner}

def build_readiness(*,qualification:dict[str,Any],stress:dict[str,Any],generated_at:datetime|None=None)->dict[str,Any]:
    paper_pass=qualification.get("status")=="PAPER_QUALIFIED_FOR_HUMAN_READINESS_REVIEW"
    worst=(stress.get("worst_scenario") or {}).get("estimated_nav_change_pct") if isinstance(stress.get("worst_scenario"),dict) else None
    stress_measured=isinstance(worst,(int,float))
    stress_pass=stress_measured and float(worst)>=-15.0
    gates=[
        _gate("10B_PAPER_PERFORMANCE_QUALIFICATION","PASS" if paper_pass else "BLOCKED",str(qualification.get("status") or "UNKNOWN"),"IIOS_MEASUREMENT"),
        _gate("10D_STRESS_TOLERANCE","PASS" if stress_pass else ("WAITING" if not stress_measured else "BLOCKED"),f"worst deterministic paper shock={worst}","IIOS_MEASUREMENT"),
        _gate("HUMAN_CAPITAL_APPROVAL","UNRESOLVED_MANUAL_GATE","No persisted explicit capital-allocation approval exists.","HUMAN_OWNER"),
        _gate("BROKER_CUSTODIAN_APPROVAL","UNRESOLVED_MANUAL_GATE","No governed live broker/custodian authorization is present.","HUMAN_OWNER"),
        _gate("LEGAL_COMPLIANCE_REVIEW","UNRESOLVED_MANUAL_GATE","Legal/compliance scope and jurisdictional review are outside automated 10E authority.","HUMAN_OWNER"),
        _gate("MARKET_DATA_LICENSING_REVIEW","UNRESOLVED_MANUAL_GATE","Production redistribution/usage rights must be reviewed for every live data source.","HUMAN_OWNER"),
        _gate("KILL_SWITCH_AND_INCIDENT_DRILL","UNRESOLVED_MANUAL_GATE","A documented human-observed live-capital kill-switch/incident drill has not been persisted.","HUMAN_OWNER"),
        _gate("RECONCILIATION_AND_ACCOUNTING","UNRESOLVED_MANUAL_GATE","Broker reconciliation, tax and accounting controls require implementation and signoff.","HUMAN_OWNER"),
    ]
    unresolved=[row for row in gates if row["state"]!="PASS"]
    return {
        "schema_version":SCHEMA_VERSION,"generated_at":(generated_at or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat(),
        "status":"NOT_READY_FOR_LIVE_CAPITAL" if unresolved else "READY_FOR_FINAL_HUMAN_CAPITAL_AUTHORIZATION",
        "gates":gates,"unresolved_gate_count":len(unresolved),"paper_qualification_passed":paper_pass,"stress_gate_passed":stress_pass,
        "recommended_next_action":"CONTINUE_GOVERNED_PAPER_COLLECTION" if not paper_pass else "HUMAN_READINESS_REVIEW_ONLY",
        "readiness_meaning":"10E is an evidence dossier. It cannot connect a broker, fund an account, turn on live mode, accept legal terms, or place an order. Even a future all-green dossier still requires explicit human capital authorization.",
        "safety":{"dossier_only":True,"auto_enable_live":False,"auto_connect_broker":False,"auto_fund_account":False,"legal_acceptance_authority":False,"capital_authority":False,"trade_execution_permission":False,"live_execution":False,"human_approval_required":True}
    }
