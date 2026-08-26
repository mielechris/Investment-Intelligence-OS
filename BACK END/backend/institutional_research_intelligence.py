from __future__ import annotations
import hashlib, json, re, sqlite3
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4
from fastapi import APIRouter, Body, HTTPException
from generic_coverage_v2 import COMPANY_PROFILES
from ledger import DB_PATH, get_object, latest_object, record_event, record_object, utc_now

router = APIRouter()
RESEARCH_CASE = "institutional_research_factory"

SOURCE_REGISTRY = [
    "JPMorgan","Deutsche Bank","Wells Fargo Investment Institute","Morningstar",
    "TD Cowen","Cohen & Company","Goldman Sachs","Morgan Stanley","Bank of America",
    "UBS","Barclays","Citi","RBC Capital Markets","HSBC","BNP Paribas",
    "Societe Generale","Nomura","Macquarie"
]

SECTOR_ALIASES = {
    "SEMICONDUCTOR": ("semiconductor","semiconductors","chips","chipmakers","ai accelerators"),
    "TECHNOLOGY": ("technology","software","hardware","tech sector"),
    "CLOUD_SOFTWARE": ("cloud","software","azure","saas"),
    "BANKS": ("banks","banking","financials","lenders","credit"),
    "ENERGY": ("energy","oil","gas","refining","upstream"),
    "INDUSTRIALS": ("industrials","machinery","manufacturing","capital goods"),
    "CONSUMER": ("consumer","retail","consumer discretionary"),
    "HEALTHCARE": ("healthcare","pharma","biotech","pharmaceutical"),
    "UTILITIES": ("utilities","power","electric utility"),
    "REAL_ESTATE": ("real estate","reits","property"),
    "COMMUNICATION_SERVICES": ("communication services","advertising","media"),
    "MATERIALS": ("materials","steel","aluminum","chemicals"),
}
POS = ("favorable","overweight","bullish","positive","constructive","outperform","upside","improving","accelerating","preferred")
NEG = ("unfavorable","underweight","bearish","negative","cautious","underperform","downside","deteriorating","slowing","avoid")

def _rows(object_type: str, limit: int = 2000):
    db = sqlite3.connect(DB_PATH, timeout=30)
    db.row_factory = sqlite3.Row
    try:
        rows = db.execute(
            "SELECT payload_json FROM ledger_objects WHERE object_type=? ORDER BY created_at DESC LIMIT ?",
            (object_type, limit),
        ).fetchall()
    finally:
        db.close()
    return [json.loads(r["payload_json"]) for r in rows]

def _iso(value):
    text = str(value or "").strip()
    if not text: return None
    try: dt = datetime.fromisoformat(text.replace("Z","+00:00"))
    except ValueError: return None
    if dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)

def normalize_sentiment(value):
    text = str(value or "").strip().upper()
    aliases = {"BULLISH":"FAVORABLE","POSITIVE":"FAVORABLE","OVERWEIGHT":"FAVORABLE","OUTPERFORM":"FAVORABLE",
               "BEARISH":"UNFAVORABLE","NEGATIVE":"UNFAVORABLE","UNDERWEIGHT":"UNFAVORABLE",
               "UNDERPERFORM":"UNFAVORABLE","NEUTRAL":"MIXED"}
    text = aliases.get(text,text)
    return text if text in {"FAVORABLE","MIXED","UNFAVORABLE"} else "MIXED"

def _heuristic_views(text):
    corpus = " ".join(str(text or "").lower().split())
    if not corpus: return []
    p = sum(t in corpus for t in POS); n = sum(t in corpus for t in NEG)
    sentiment = "FAVORABLE" if p > n else "UNFAVORABLE" if n > p else "MIXED"
    conviction = min(0.8, 0.45 + 0.05*abs(p-n))
    out = []
    for sector, aliases in SECTOR_ALIASES.items():
        if any(a in corpus for a in aliases):
            out.append({"sector":sector,"sentiment":sentiment,"conviction":conviction,
                        "drivers":[],"risks":[],"tickers":[],"extraction_mode":"DETERMINISTIC_TEXT_HEURISTIC"})
    return out

def _clean_view(value):
    if not isinstance(value,dict): return None
    sector = str(value.get("sector") or "").strip().upper().replace(" ","_")
    if not sector: return None
    try: conviction = float(value.get("conviction",0.5))
    except (TypeError,ValueError): conviction = 0.5
    return {"sector":sector,"sentiment":normalize_sentiment(value.get("sentiment")),
            "conviction":max(0,min(1,conviction)),
            "drivers":[str(x) for x in value.get("drivers") or []][:12],
            "risks":[str(x) for x in value.get("risks") or []][:12],
            "tickers":[str(x).upper() for x in value.get("tickers") or []][:25],
            "extraction_mode":str(value.get("extraction_mode") or "STRUCTURED_INPUT")}

def ingest_report(request):
    institution = str(request.get("institution") or "").strip()
    title = str(request.get("title") or "").strip()
    if not institution or not title: raise ValueError("institution and title are required")
    report_text = str(request.get("report_text") or "")
    views = [v for v in (_clean_view(x) for x in request.get("sector_views") or []) if v]
    if not views and report_text: views = _heuristic_views(report_text)
    if not views: raise ValueError("Provide sector_views or report_text with identifiable sector language")
    rid = f"institutional_research_{uuid4().hex}"
    record = {
        "institutional_research_id":rid,"institution":institution,"title":title,
        "report_type":str(request.get("report_type") or "RESEARCH_REPORT").upper(),
        "published_at":str(request.get("published_at") or utc_now()),
        "horizon":str(request.get("horizon") or "UNSPECIFIED"),
        "source_url":request.get("source_url"),
        "access_tier":str(request.get("access_tier") or "AUTHORIZED_OR_PUBLIC").upper(),
        "sector_views":views,
        "content_hash":hashlib.sha256(report_text.encode()).hexdigest() if report_text else None,
        "full_report_persisted":False,"redistribution_allowed":False,
        "licensing_note":"Only normalized metadata/analysis is persisted; full proprietary report text is not redistributed.",
        "context_only":True,"gap_resolution_eligible":False,"trade_signal":False,
        "paper_order_permission":False,"trade_execution_permission":False,"live_execution":False,
        "created_at":utc_now(),
    }
    record_object(rid,"institutional_research_record",RESEARCH_CASE,record,topic=title)
    record_event(RESEARCH_CASE,"INSTITUTIONAL_RESEARCH_INGESTED",entity_id=rid,
                 payload={"institution":institution,"sector_count":len(views),"trade_execution_permission":False})
    return record

def _freshness(value):
    dt = _iso(value)
    if dt is None: return 0.35
    age = max(0,(datetime.now(timezone.utc)-dt).total_seconds()/86400)
    return 1.0 if age<=7 else 0.85 if age<=30 else 0.60 if age<=90 else 0.35 if age<=180 else 0.15

def aggregate_sector_sentiment(records=None, *, sector=None):
    rows = records if records is not None else _rows("institutional_research_record")
    target = str(sector or "").upper().replace(" ","_") or None
    buckets = {}
    for record in rows:
        for view in record.get("sector_views") or []:
            key = str(view.get("sector") or "").upper()
            if key and (not target or key==target): buckets.setdefault(key,[]).append((record,view))
    output=[]; score_map={"FAVORABLE":1.0,"MIXED":0.0,"UNFAVORABLE":-1.0}
    for key,items in buckets.items():
        num=den=0.0; counts={"FAVORABLE":0,"MIXED":0,"UNFAVORABLE":0}; inst=set(); drivers=[]; risks=[]
        for record,view in items:
            s=normalize_sentiment(view.get("sentiment")); counts[s]+=1; inst.add(str(record.get("institution") or "UNKNOWN"))
            w=max(0.05,min(1,float(view.get("conviction") or 0.5)))*_freshness(record.get("published_at"))
            num += score_map[s]*w; den += w
            drivers += [str(x) for x in view.get("drivers") or []]; risks += [str(x) for x in view.get("risks") or []]
        score = num/den if den else 0.0
        label = "FAVORABLE" if score>=0.25 else "UNFAVORABLE" if score<=-0.25 else "MIXED"
        output.append({"sector":key,"sentiment":label,"consensus_score":round(score,4),
                       "disagreement_index":round(1-min(1,abs(score)),4),
                       "favorable_count":counts["FAVORABLE"],"mixed_count":counts["MIXED"],
                       "unfavorable_count":counts["UNFAVORABLE"],"institution_count":len(inst),
                       "report_count":len(items),"top_drivers":list(dict.fromkeys(drivers))[:10],
                       "top_risks":list(dict.fromkeys(risks))[:10]})
    output.sort(key=lambda x:(abs(float(x["consensus_score"])),x["report_count"]),reverse=True)
    return {"sector":target,"sectors":output,"report_count":len(rows),"context_only":True,
            "trade_signal":False,"trade_execution_permission":False,"live_execution":False}

def _identity(case_id):
    case=get_object(case_id) or {}; profile=latest_object("monitor_profile",case_id=case_id) or {}
    ticker=str(profile.get("ticker") or case.get("ticker") or "").upper().replace(".US","")
    if not ticker:
        m=re.search(r"\(([A-Z][A-Z0-9.\-]{0,9})\)",str(case.get("topic") or "")); ticker=m.group(1) if m else ""
    sector=str((COMPANY_PROFILES.get(ticker) or {}).get("sector") or "").upper()
    return ticker or None, sector or None

def institutional_research_evidence(case_id):
    ticker,sector=_identity(case_id); out=[]
    if not ticker and not sector: return out
    for record in _rows("institutional_research_record",1000):
        for view in record.get("sector_views") or []:
            tickers={str(x).upper() for x in view.get("tickers") or []}; vs=str(view.get("sector") or "").upper()
            if not ((ticker and ticker in tickers) or (sector and vs==sector)): continue
            out.append({"source":record.get("institution"),"source_type":"institutional_research",
                        "evidence_type":"institutional_context","url":record.get("source_url"),
                        "title":f"Institutional research - {record.get('title')}",
                        "claim":f"{record.get('institution')} {vs}: {normalize_sentiment(view.get('sentiment'))}; conviction={view.get('conviction')}; drivers={view.get('drivers')}; risks={view.get('risks')}",
                        "timestamp":record.get("published_at"),"reliability_score":0.70,
                        "context_only":True,"gap_resolution_eligible":False,"trade_signal":False,
                        "trade_execution_permission":False})
            if len(out)>=20: return out
    return out

@router.get("/intelligence/institutional-research/sources")
def sources():
    return {"sources":[{"institution":x,"access_mode":"AUTHORIZED_OR_PUBLIC"} for x in SOURCE_REGISTRY],
            "authorized_access_required":True,"full_report_redistribution":False,
            "trade_execution_permission":False,"live_execution":False}

@router.post("/intelligence/institutional-research/ingest")
def ingest(request: dict[str,Any]=Body(...)):
    try: return ingest_report(request)
    except ValueError as exc: raise HTTPException(status_code=422,detail=str(exc))

@router.get("/intelligence/institutional-research/sector-sentiment")
def sentiment(sector: str|None=None): return aggregate_sector_sentiment(sector=sector)

@router.get("/intelligence/institutional-research/case/{case_id}")
def case_context(case_id: str):
    return {"case_id":case_id,"evidence":institutional_research_evidence(case_id),
            "context_only":True,"trade_execution_permission":False,"live_execution":False}
