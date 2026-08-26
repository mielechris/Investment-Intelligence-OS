from __future__ import annotations
import json, sqlite3
from typing import Any
from uuid import uuid4
from fastapi import APIRouter, Body, HTTPException
from ledger import DB_PATH, latest_object, record_event, record_object, utc_now
from provider_hardening import fetch_gdelt_news, fetch_google_news_rss
from source_ingestion import fetch_fred_series

router = APIRouter()
POLICY_CASE = "jesse_macro_policy_factory"
SCENARIO_BPS={"CUT_100":-100,"CUT_75":-75,"CUT_50":-50,"CUT_25":-25,"HOLD":0,"HIKE_25":25,"HIKE_50":50,"HIKE_75":75,"HIKE_100":100}
TARIFF_RULES=[
 {"key":"STEEL_ALUMINUM","terms":("steel","aluminum","aluminium"),"impacts":[
  ("DOMESTIC_METALS","FAVORABLE","Import protection can support domestic producer pricing."),
  ("AUTOS_EV","UNFAVORABLE","Higher metal input costs can pressure vehicle margins."),
  ("INDUSTRIALS","UNFAVORABLE","Higher input costs can pressure machinery economics."),
  ("CONSTRUCTION","UNFAVORABLE","Higher material costs can raise project costs.")]},
 {"key":"SEMICONDUCTORS","terms":("semiconductor","semiconductors","chip","chips"),"impacts":[
  ("US_SEMICONDUCTORS","MIXED","Protection can support domestic capacity while disrupting global supply chains."),
  ("CONSUMER_ELECTRONICS","UNFAVORABLE","Higher component costs can compress device margins."),
  ("DATA_CENTER_HARDWARE","UNFAVORABLE","Component restrictions can raise infrastructure costs.")]},
 {"key":"SOLAR","terms":("solar","photovoltaic","module","modules"),"impacts":[
  ("US_SOLAR_MANUFACTURING","FAVORABLE","Import protection can support domestic module economics."),
  ("SOLAR_INSTALLERS","UNFAVORABLE","Higher module costs can pressure installation economics."),
  ("UTILITIES_RENEWABLES","UNFAVORABLE","Higher project input costs can slow renewable builds.")]},
 {"key":"AUTOS_EV","terms":("electric vehicle"," ev ","automobile","auto imports","vehicle"),"impacts":[
  ("US_AUTOS","FAVORABLE","Import protection can improve relative domestic pricing power."),
  ("AUTO_PARTS_IMPORTERS","UNFAVORABLE","Tariffs can raise imported component costs."),
  ("CONSUMER_DISCRETIONARY","MIXED","Higher vehicle prices can offset producer benefits.")]},
 {"key":"AGRICULTURE","terms":("soybean","corn","wheat","agriculture","farm products"),"impacts":[
  ("US_AGRICULTURE","MIXED","Effects depend on protection versus retaliation."),
  ("FOOD_PROCESSORS","UNFAVORABLE","Higher commodity costs can pressure processor margins.")]},
]

def _rows(object_type,limit=1000):
    db=sqlite3.connect(DB_PATH,timeout=30); db.row_factory=sqlite3.Row
    try: rows=db.execute("SELECT payload_json FROM ledger_objects WHERE object_type=? ORDER BY created_at DESC LIMIT ?",(object_type,limit)).fetchall()
    finally: db.close()
    return [json.loads(r["payload_json"]) for r in rows]

def normalize_probabilities(values):
    if not isinstance(values,dict) or not values: raise ValueError("probabilities must be a non-empty object")
    cleaned={}
    for k,v in values.items():
        name=str(k or "").upper().replace(" ","_")
        if name not in SCENARIO_BPS: raise ValueError(f"Unknown monetary-policy scenario: {name}")
        try: n=float(v)
        except (TypeError,ValueError): raise ValueError(f"Probability for {name} must be numeric")
        if n<0: raise ValueError("Probabilities cannot be negative")
        cleaned[name]=n
    total=sum(cleaned.values())
    if total<=0: raise ValueError("Probability total must be positive")
    if total>1.5: cleaned={k:v/100 for k,v in cleaned.items()}; total=sum(cleaned.values())
    return {k:v/total for k,v in cleaned.items()}

def policy_distribution_summary(probabilities):
    probs=normalize_probabilities(probabilities); expected=sum(SCENARIO_BPS[k]*p for k,p in probs.items())
    likely=max(probs,key=probs.get); concentration=max(probs.values())
    return {"probabilities":{k:round(v,6) for k,v in probs.items()},
            "expected_policy_change_bps":round(expected,4),"most_likely_scenario":likely,
            "most_likely_probability":round(concentration,6),"distribution_uncertainty":round(1-concentration,6)}

def _fred(series):
    try: rows=fetch_fred_series({"series_id":series,"limit":4})
    except Exception: return None
    return rows[-1] if rows else None

def ingest_policy_reaction(request):
    try: expected=float(request.get("expected_change_bps")); actual=float(request.get("actual_change_bps"))
    except (TypeError,ValueError): raise ValueError("expected_change_bps and actual_change_bps are required numeric fields")
    rid=f"fed_reaction_{uuid4().hex}"
    record={"monetary_policy_reaction_id":rid,"event_date":str(request.get("event_date") or ""),
            "expected_change_bps":expected,"actual_change_bps":actual,"surprise_bps":actual-expected,
            "returns":request.get("returns") if isinstance(request.get("returns"),dict) else {},
            "regime_tags":[str(x) for x in request.get("regime_tags") or []],
            "source":str(request.get("source") or "GOVERNED_HISTORICAL_EVENT_STUDY"),
            "research_only":True,"paper_mode":True,"trade_execution_permission":False,"live_execution":False,"created_at":utc_now()}
    record_object(rid,"monetary_policy_reaction",POLICY_CASE,record); return record

def _analogs(expected,surprise,limit=8):
    rows=_rows("monetary_policy_reaction")
    def dist(r): return abs(float(r.get("surprise_bps") or 0)-surprise) if surprise is not None else abs(float(r.get("expected_change_bps") or 0)-expected)
    return sorted(rows,key=dist)[:limit]

def build_monetary_policy_snapshot(request):
    summary=policy_distribution_summary(request.get("probabilities")); actual=request.get("actual_decision_bps"); surprise=None
    if actual is not None:
        try: surprise=float(actual)-float(summary["expected_policy_change_bps"])
        except (TypeError,ValueError): raise ValueError("actual_decision_bps must be numeric")
    macro={}
    for series in ("DFF","DGS2","DGS10","BAMLH0A0HYM2"):
        row=_fred(series)
        if row: macro[series]={"value":row.get("value"),"timestamp":row.get("timestamp"),"source":row.get("source")}
    sid=f"monetary_policy_snapshot_{uuid4().hex}"
    payload={"monetary_policy_snapshot_id":sid,**summary,
             "market_implied_source":str(request.get("market_implied_source") or "GOVERNED_UPSTREAM_PROBABILITY_SOURCE_REQUIRED"),
             "probability_source_verified":bool(request.get("probability_source_verified",False)),
             "actual_decision_bps":float(actual) if actual is not None else None,"surprise_bps":surprise,
             "macro_context":macro,"historical_analogs":_analogs(float(summary["expected_policy_change_bps"]),surprise),
             "probability_engine_note":"IIOS does not invent Fed probabilities; distributions must come from a governed source.",
             "context_only":True,"gap_resolution_eligible":False,"trade_signal":False,"paper_order_permission":False,
             "trade_execution_permission":False,"live_execution":False,"created_at":utc_now()}
    record_object(sid,"monetary_policy_snapshot",POLICY_CASE,payload)
    record_event(POLICY_CASE,"MONETARY_POLICY_SNAPSHOT_CREATED",entity_id=sid,
                 payload={"most_likely_scenario":payload["most_likely_scenario"],"trade_execution_permission":False})
    return payload

def analyze_tariff_text(text):
    corpus=f" {str(text or '').lower()} "
    if not any(t in corpus for t in ("tariff","duties","import tax","trade restriction","trade war")):
        return {"matched_rules":[],"sector_impacts":[]}
    matched=[]; impacts=[]
    for rule in TARIFF_RULES:
        if any(t in corpus for t in rule["terms"]):
            matched.append(rule["key"])
            for sector,direction,rationale in rule["impacts"]:
                impacts.append({"sector":sector,"direction":direction,"rationale":rationale,"rule":rule["key"],"confidence":0.60})
    if not matched:
        impacts.append({"sector":"BROAD_MARKET","direction":"MIXED",
                        "rationale":"Tariff event detected but transmission is not specific enough.","rule":"GENERIC_TARIFF","confidence":0.35})
    return {"matched_rules":matched,"sector_impacts":impacts}

def _aggregate(events):
    sm={"FAVORABLE":1.0,"MIXED":0.0,"UNFAVORABLE":-1.0}; buckets={}
    for e in events:
        for i in e.get("sector_impacts") or []: buckets.setdefault(str(i.get("sector")),[]).append(i)
    out=[]
    for sector,rows in buckets.items():
        den=sum(float(r.get("confidence") or .5) for r in rows) or 1
        net=sum(sm.get(str(r.get("direction")),0)*float(r.get("confidence") or .5) for r in rows)/den
        direction="FAVORABLE" if net>=.25 else "UNFAVORABLE" if net<=-.25 else "MIXED"
        out.append({"sector":sector,"direction":direction,"net_score":round(net,4),"event_count":len(rows),
                    "rationales":list(dict.fromkeys(str(r.get("rationale")) for r in rows))[:8]})
    return sorted(out,key=lambda x:abs(float(x["net_score"])),reverse=True)

def run_tariff_transmission_scan(request=None):
    request=request or {}; manual=str(request.get("text") or "").strip(); items=[]
    if manual:
        items=[{"source":str(request.get("source") or "MANUAL_GOVERNED_INPUT"),"title":str(request.get("title") or "Tariff policy event"),
                "claim":manual,"timestamp":str(request.get("timestamp") or utc_now()),"url":request.get("source_url")}]
    else:
        q="(tariff OR duties OR import tax OR trade war) (United States OR US OR China OR Europe OR Mexico OR Canada)"
        try: items += fetch_gdelt_news({"query":q,"limit":20,"timespan":"48h"})
        except Exception: pass
        try:
            fallback=fetch_google_news_rss({"query":q,"limit":20}); seen={(str(x.get("url")),str(x.get("title"))) for x in items}
            for row in fallback:
                key=(str(row.get("url")),str(row.get("title")))
                if key not in seen: seen.add(key); items.append(row)
        except Exception: pass
    events=[]
    for row in items[:40]:
        analysis=analyze_tariff_text(f"{row.get('title') or ''} {row.get('claim') or ''}")
        if analysis["sector_impacts"]: events.append({"source":row.get("source"),"title":row.get("title"),
                                                     "timestamp":row.get("timestamp"),"url":row.get("url"),**analysis})
    sid=f"tariff_transmission_{uuid4().hex}"
    payload={"tariff_transmission_snapshot_id":sid,"event_count":len(events),"events":events,"sector_impacts":_aggregate(events),
             "context_only":True,"gap_resolution_eligible":False,"trade_signal":False,"auto_trade_authority":False,
             "paper_order_permission":False,"trade_execution_permission":False,"live_execution":False,"created_at":utc_now()}
    record_object(sid,"tariff_transmission_snapshot",POLICY_CASE,payload)
    record_event(POLICY_CASE,"TARIFF_TRANSMISSION_SCAN_COMPLETE",entity_id=sid,
                 payload={"event_count":len(events),"sector_count":len(payload["sector_impacts"]),"trade_execution_permission":False})
    return payload

def market_policy_evidence(case_id):
    out=[]; fed=latest_object("monetary_policy_snapshot",case_id=POLICY_CASE)
    if fed:
        out.append({"source":fed.get("market_implied_source"),"source_type":"macro_policy_context",
                    "evidence_type":"monetary_policy_probability","url":None,"title":"Monetary policy probability distribution",
                    "claim":f"Most likely={fed.get('most_likely_scenario')} probability={fed.get('most_likely_probability')}; expected={fed.get('expected_policy_change_bps')} bps; source_verified={fed.get('probability_source_verified')}",
                    "timestamp":fed.get("created_at"),"reliability_score":.75 if fed.get("probability_source_verified") else .45,
                    "context_only":True,"gap_resolution_eligible":False,"trade_signal":False,"trade_execution_permission":False})
    tariff=latest_object("tariff_transmission_snapshot",case_id=POLICY_CASE)
    if tariff and tariff.get("sector_impacts"):
        out.append({"source":"IIOS Tariff Transmission Engine","source_type":"policy_analysis",
                    "evidence_type":"tariff_sector_transmission","url":None,"title":"Tariff transmission sector map",
                    "claim":f"Sector impacts={tariff.get('sector_impacts')}","timestamp":tariff.get("created_at"),
                    "reliability_score":.60,"context_only":True,"gap_resolution_eligible":False,
                    "trade_signal":False,"trade_execution_permission":False})
    return out

@router.post("/intelligence/monetary-policy/reaction/ingest")
def ingest_reaction(request: dict[str,Any]=Body(...)):
    try: return ingest_policy_reaction(request)
    except ValueError as exc: raise HTTPException(status_code=422,detail=str(exc))

@router.post("/intelligence/monetary-policy/snapshot")
def snapshot(request: dict[str,Any]=Body(...)):
    try: return build_monetary_policy_snapshot(request)
    except ValueError as exc: raise HTTPException(status_code=422,detail=str(exc))

@router.get("/intelligence/monetary-policy/status")
def status():
    return {"latest_snapshot":latest_object("monetary_policy_snapshot",case_id=POLICY_CASE),
            "reaction_count":len(_rows("monetary_policy_reaction")),"probabilities_must_be_governed":True,
            "trade_execution_permission":False,"live_execution":False}

@router.post("/intelligence/tariff-transmission/run")
def tariff_run(request: dict[str,Any]=Body(default={})): return run_tariff_transmission_scan(request)

@router.get("/intelligence/tariff-transmission/status")
def tariff_status():
    return {"latest_snapshot":latest_object("tariff_transmission_snapshot",case_id=POLICY_CASE),
            "trade_execution_permission":False,"live_execution":False}
