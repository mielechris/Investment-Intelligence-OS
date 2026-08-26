from __future__ import annotations
import math
from typing import Any
from urllib.parse import quote_plus, urlencode
from uuid import uuid4
from fastapi import APIRouter, Body, HTTPException
from ledger import record_event, record_object, latest_object, utc_now
from opportunity_acquisition import OPPORTUNITY_LEDGER_CASE, promote_candidate
from provider_hardening import _json_request, fetch_google_news_rss

router = APIRouter()
STRUCTURAL=("bankruptcy","chapter 11","fraud","restatement","going concern","liquidity crisis","default","material weakness","sec investigation","guidance withdrawn","massive dilution")
TEMPORARY=("analyst downgrade","profit taking","sector selloff","market selloff","valuation concerns","missed estimates","earnings reaction","risk-off")

def _num(v):
    if isinstance(v,dict) and "raw" in v: v=v.get("raw")
    try: n=float(v)
    except (TypeError,ValueError): return None
    return n if math.isfinite(n) else None

def _screener(count=30):
    params=urlencode({"formatted":"false","lang":"en-US","region":"US","scrIds":"day_losers","count":max(15,min(int(count),100)),"corsDomain":"finance.yahoo.com"})
    errors=[]
    for host in ("query1.finance.yahoo.com","query2.finance.yahoo.com"):
        try:
            p=_json_request(url=f"https://{host}/v1/finance/screener/predefined/saved?{params}",provider="yahoo_day_losers",
                            minimum_interval_seconds=.35,retries=1,cache_ttl_seconds=120)
            r=((p.get("finance") or {}).get("result") or [None])[0]; q=r.get("quotes") if isinstance(r,dict) else None
            if isinstance(q,list): return q
        except Exception as exc: errors.append(f"{host}:{type(exc).__name__}:{exc}")
    raise RuntimeError(" | ".join(errors) or "Yahoo day-loser screener unavailable")

def _summary(symbol):
    modules="financialData,defaultKeyStatistics,summaryDetail,earningsTrend"; errors=[]
    for host in ("query2.finance.yahoo.com","query1.finance.yahoo.com"):
        try:
            p=_json_request(url=f"https://{host}/v10/finance/quoteSummary/{quote_plus(symbol)}?modules={modules}",
                            provider="yahoo_dislocation_financials",minimum_interval_seconds=.35,retries=1,cache_ttl_seconds=600)
            r=(((p.get("quoteSummary") or {}).get("result") or [None])[0])
            if isinstance(r,dict): return r
        except Exception as exc: errors.append(f"{host}:{type(exc).__name__}:{exc}")
    return {"_error":" | ".join(errors)}

def _metrics(summary,quote):
    f=summary.get("financialData") or {}; s=summary.get("defaultKeyStatistics") or {}
    return {"current_ratio":_num(f.get("currentRatio")),"debt_to_equity":_num(f.get("debtToEquity")),
            "free_cash_flow":_num(f.get("freeCashflow")),"operating_cash_flow":_num(f.get("operatingCashflow")),
            "profit_margin":_num(f.get("profitMargins")),"return_on_equity":_num(f.get("returnOnEquity")),
            "revenue_growth":_num(f.get("revenueGrowth")),"earnings_growth":_num(f.get("earningsGrowth")),
            "market_cap":_num(quote.get("marketCap")) or _num(s.get("marketCap")),
            "trailing_pe":_num(quote.get("trailingPE")) or _num(s.get("trailingPE")),
            "forward_pe":_num(quote.get("forwardPE")) or _num(s.get("forwardPE")),
            "eps_ttm":_num(quote.get("epsTrailingTwelveMonths")),"eps_forward":_num(quote.get("epsForward"))}

def financial_strength_score(m):
    score=45.; reasons=[]
    v=m.get("current_ratio")
    if v is not None:
        if v>=1.5: score+=10; reasons.append("STRONG_LIQUIDITY")
        elif v<1: score-=10; reasons.append("WEAK_LIQUIDITY")
    v=m.get("debt_to_equity")
    if v is not None:
        if v<=100: score+=8; reasons.append("MANAGEABLE_LEVERAGE")
        elif v>200: score-=10; reasons.append("HIGH_LEVERAGE")
    v=m.get("free_cash_flow")
    if v is not None: score += 10 if v>0 else -10; reasons.append("POSITIVE_FCF" if v>0 else "NEGATIVE_FCF")
    v=m.get("operating_cash_flow")
    if v is not None: score += 8 if v>0 else -8
    v=m.get("profit_margin")
    if v is not None:
        if v>=.10: score+=8; reasons.append("HEALTHY_MARGIN")
        elif v<0: score-=12; reasons.append("NEGATIVE_MARGIN")
    v=m.get("return_on_equity")
    if v is not None and v>=.10: score+=6; reasons.append("HEALTHY_ROE")
    v=m.get("revenue_growth")
    if v is not None: score += 6 if v>0 else -4
    v=m.get("earnings_growth")
    if v is not None: score += 6 if v>0 else -4
    v=m.get("eps_ttm")
    if v is not None and v>0: score+=5; reasons.append("POSITIVE_EPS")
    return round(max(0,min(100,score)),2),reasons

def classify_decline(news):
    corpus=" ".join(f"{r.get('title') or ''} {r.get('claim') or ''}".lower() for r in news if isinstance(r,dict))
    structural=sorted({t for t in STRUCTURAL if t in corpus}); temporary=sorted({t for t in TEMPORARY if t in corpus})
    c="STRUCTURAL_RISK" if structural else "POSSIBLE_TEMPORARY_DISLOCATION" if temporary else "UNRESOLVED"
    return {"classification":c,"structural_flags":structural,"temporary_flags":temporary}

def rebound_assessment(score,decline_pct,classification):
    p=.10+.003*max(0,score-40)
    if decline_pct is not None and decline_pct<=-5: p+=.05
    if decline_pct is not None and decline_pct<=-10: p+=.03
    if classification=="POSSIBLE_TEMPORARY_DISLOCATION": p+=.10
    if classification=="STRUCTURAL_RISK": p-=.20
    p=max(.03,min(.65,p))
    rec="BUY" if score>=75 and p>=.30 and classification!="STRUCTURAL_RISK" else "WATCH" if score>=60 and classification!="STRUCTURAL_RISK" else "NO_TRADE"
    return {"recommendation":rec,"estimated_probability_next_day_plus_5":round(p,4),"probability_calibrated":False,
            "probability_note":"Deterministic heuristic until enough IIOS postmortems calibrate the +5% next-day hit rate."}

def run_dislocation_scan(request=None):
    request=request or {}; strict={str(x).upper() for x in request.get("universe_symbols") or [] if str(x).strip()}
    candidates=[]
    for quote in _screener(request.get("count") or 30):
        if not isinstance(quote,dict): continue
        symbol=str(quote.get("symbol") or "").upper()
        if not symbol or (strict and symbol not in strict): continue
        if str(quote.get("quoteType") or "EQUITY").upper()!="EQUITY": continue
        decline=_num(quote.get("regularMarketChangePercent")); price=_num(quote.get("regularMarketPrice"))
        company=str(quote.get("shortName") or quote.get("longName") or symbol)
        m=_metrics(_summary(symbol),quote); strength,reasons=financial_strength_score(m)
        try: news=fetch_google_news_rss({"query":f"{company} {symbol} stock","limit":8})
        except Exception: news=[]
        dc=classify_decline(news); rb=rebound_assessment(strength,decline,dc["classification"])
        candidates.append({"ticker":symbol,"company":company,"current_price":price,"intraday_change_pct":decline,
                           "financial_strength_score":strength,"financial_reason_codes":reasons,"financial_metrics":m,
                           "decline_analysis":dc,"news":news,"news_count":len(news),**rb,"target_upside_pct":5.0,
                           "paper_mode":True,"trade_signal":False,"paper_order_permission":False,
                           "trade_execution_permission":False,"live_execution":False})
        if len(candidates)>=15: break
    candidates.sort(key=lambda r:(float(r.get("financial_strength_score") or 0),-float(r.get("intraday_change_pct") or 0)),reverse=True)
    top=candidates[:3]; ids=[]
    for row in top:
        oid=f"opportunity_{uuid4().hex}"; eligible=row["recommendation"] in {"BUY","WATCH"} and row["news_count"]>=1
        obj={"opportunity_candidate_id":oid,"opportunity_scan_id":None,"ticker":row["ticker"],"label":row["company"],
             "query":f"{row['company']} {row['ticker']}","score":row["financial_strength_score"],
             "priority":"HIGH" if row["financial_strength_score"]>=75 else "MEDIUM","eligible_for_promotion":eligible,
             "reason_codes":row["financial_reason_codes"]+[row["decline_analysis"]["classification"]],
             "catalyst_categories":["DISLOCATION"],"news_count":row["news_count"],
             "source_count":len({str(x.get("source")) for x in row["news"] if isinstance(x,dict)}),
             "recent_24h_count":row["news_count"],"quote_ok":row["current_price"] is not None,
             "current_price":row["current_price"],"evidence":list(row["news"]),"evidence_count":row["news_count"],
             "promoted_case_id":None,"created_by":"DISLOCATION_SCANNER_V1","trade_signal":False,"direction":"UNSPECIFIED",
             "paper_mode":True,"paper_order_permission":False,"trade_execution_permission":False,"live_execution":False,"created_at":utc_now()}
        record_object(oid,"opportunity_candidate",OPPORTUNITY_LEDGER_CASE,obj,topic=row["company"]); ids.append(oid)
    promoted=[]
    if request.get("promote_top_three") is True:
        for oid in ids:
            try: promoted.append(promote_candidate(oid))
            except Exception: pass
    sid=f"dislocation_scan_{uuid4().hex}"
    payload={"dislocation_scan_id":sid,"universe_scope":"GOVERNED_SUPPLIED_UNIVERSE" if strict else "YAHOO_US_LARGE_CAP_DAY_LOSERS_PROXY",
             "strict_index_membership":bool(strict),
             "strict_membership_note":"Supply a current governed S&P/Nasdaq symbol list for strict membership; otherwise a US large-cap loser proxy is used.",
             "loser_count":len(candidates),"losers":candidates,"top_three":top,"opportunity_candidate_ids":ids,
             "promoted_count":len(promoted),"goal_next_trading_day_upside_pct":5.0,"paper_mode":True,
             "trade_signal":False,"auto_trade_authority":False,"paper_order_permission":False,
             "trade_execution_permission":False,"live_execution":False,"created_at":utc_now()}
    record_object(sid,"dislocation_scan",OPPORTUNITY_LEDGER_CASE,payload)
    record_event(OPPORTUNITY_LEDGER_CASE,"DISLOCATION_SCAN_COMPLETE",entity_id=sid,
                 payload={"loser_count":len(candidates),"top_three":[r["ticker"] for r in top],"trade_execution_permission":False})
    return payload

@router.post("/intelligence/dislocation/run")
def run_api(request: dict[str,Any]=Body(default={})):
    try: return run_dislocation_scan(request)
    except Exception as exc: raise HTTPException(status_code=502,detail=f"{type(exc).__name__}: {exc}")

@router.get("/intelligence/dislocation/status")
def status():
    return {"latest_scan":latest_object("dislocation_scan",case_id=OPPORTUNITY_LEDGER_CASE),
            "paper_mode":True,"trade_execution_permission":False,"live_execution":False}
