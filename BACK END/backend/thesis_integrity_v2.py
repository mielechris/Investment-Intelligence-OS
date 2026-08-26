from __future__ import annotations
from typing import Any
from fastapi import APIRouter, HTTPException
from ledger import get_object, latest_object

router = APIRouter()

def classify_integrity(*,thesis_status,flags,observed_return_pct,case_closed=False,price_review_trigger_pct=-10.0):
    status=str(thesis_status or "NOT_MONITORED").upper(); fs={str(x).upper() for x in flags or []}
    hard=status=="THESIS_BROKEN" or "FALSIFIER_TRIGGERED" in fs or "FUNDAMENTAL_BREAK" in fs
    material=bool(fs & {"CATALYST_MISSED","UPDATE_EVIDENCE_CONFLICT","GUIDANCE_BREAK","BALANCE_SHEET_DETERIORATION","REGULATORY_BREAK"})
    if case_closed: state,action="CLOSED","ARCHIVE"
    elif hard: state,action="THESIS_BROKEN","REUNDERWRITE_REQUIRED"
    elif material or status=="REUNDERWRITE_REQUIRED": state,action="MATERIAL_CHANGE","REUNDERWRITE_REQUIRED"
    elif status=="INTACT":
        if observed_return_pct is not None and float(observed_return_pct)<=float(price_review_trigger_pct):
            state,action="EARLY_BUT_INTACT","CONTINUE_MONITORING_WITH_PRICE_REVIEW"
        else: state,action="INTACT","CONTINUE_MONITORING"
    else: state,action="INSUFFICIENT_EVIDENCE","CREATE_OR_REFRESH_THESIS_MONITOR"
    return {"thesis_integrity_state":state,"action":action,
            "price_review_triggered":observed_return_pct is not None and float(observed_return_pct)<=float(price_review_trigger_pct),
            "price_alone_can_break_thesis":False,"evidence_required_to_break_thesis":True}

def assess_thesis_integrity_v2(case_id):
    case=get_object(case_id)
    if not case or not str(case_id).startswith("case_"): raise HTTPException(status_code=404,detail="Unknown case_id")
    t=latest_object("thesis_monitor",case_id=case_id) or {}; p=latest_object("position_monitor",case_id=case_id) or {}
    d=latest_object("committee_decision",case_id=case_id) or {}; m=latest_object("monitor_profile",case_id=case_id) or {}
    result=classify_integrity(thesis_status=t.get("thesis_status"),flags=[str(x) for x in t.get("flags") or []],
                              observed_return_pct=p.get("return_pct"),case_closed=bool(t.get("closed") is True))
    return {"case_id":case_id,"topic":case.get("topic"),"observed_return_pct":p.get("return_pct"),
            "committee_disposition":d.get("disposition"),"committee_confidence":d.get("confidence"),
            "monitoring_enabled":bool(m.get("enabled")),**result,"research_only":True,"paper_mode":True,
            "auto_trade_authority":False,"paper_order_permission":False,"trade_execution_permission":False,"live_execution":False}

def thesis_integrity_evidence(case_id):
    try: s=assess_thesis_integrity_v2(case_id)
    except HTTPException: return []
    return [{"source":"IIOS Thesis Integrity V2","source_type":"governed_analysis","evidence_type":"thesis_integrity",
             "url":f"iios://thesis-integrity/{case_id}","title":"Wrong vs early thesis integrity assessment",
             "claim":f"state={s.get('thesis_integrity_state')}; observed_return_pct={s.get('observed_return_pct')}; price_review_triggered={s.get('price_review_triggered')}; price_alone_can_break_thesis=false; action={s.get('action')}",
             "timestamp":None,"reliability_score":.85,"context_only":True,"gap_resolution_eligible":False,
             "trade_signal":False,"trade_execution_permission":False}]

@router.get("/intelligence/thesis-integrity-v2/{case_id}")
def get_integrity(case_id: str): return assess_thesis_integrity_v2(case_id)
