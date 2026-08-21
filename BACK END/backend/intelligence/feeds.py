import asyncio
import json

from fastapi import APIRouter, HTTPException

from intelligence.committee_escalation import committee_escalations
from intelligence.dispatcher import dispatcher
from intelligence.evidence_store import evidence_store
from intelligence.ingestion import ingestion_service
from intelligence.outcome_learning import outcome_learning
from intelligence.paper_execution import paper_execution
from intelligence.paper_portfolio import paper_portfolio
from intelligence.providers import CoinGeckoProvider, FredProvider
from intelligence.providers.alpha_vantage import AlphaVantageProvider
from intelligence.providers.sec_company import fetch_recent_company_filings
from intelligence.providers.sec_ipo import fetch_recent_ipo_filings, sec_ipo_status
from intelligence.risk_review import risk_reviews


router = APIRouter(prefix="/intelligence/feeds", tags=["intelligence-feeds"])


def _status_dict(provider):
    status = provider.status()
    return {"name": status.name, "kind": status.kind, "configured": status.configured, "live": status.live, "detail": status.detail}


@router.get("/status")
def get_feed_status():
    providers = [FredProvider(), CoinGeckoProvider(), AlphaVantageProvider()]
    return {
        "paper_mode": True,
        "live_execution": False,
        "providers": [_status_dict(provider) for provider in providers],
        "specialized_providers": [sec_ipo_status()],
        "ingestion": ingestion_service.status(),
        "dispatcher": dispatcher.counts(),
        "committee_escalations": committee_escalations.counts(),
        "risk_reviews": risk_reviews.counts(),
        "paper_execution": paper_execution.counts(),
        "paper_portfolio": paper_portfolio.summary(),
    }


@router.get("/inbox")
def get_evidence_inbox(limit: int = 100, source_kind: str | None = None):
    items = evidence_store.recent(limit=limit, source_kind=source_kind)
    return {"count": len(items), "total_persisted": evidence_store.count(), "items": items, "paper_mode": True}


@router.get("/dispatch")
def get_dispatch_queue(limit: int = 100):
    return {"counts": dispatcher.counts(), "items": dispatcher.recent(limit=limit), "paper_mode": True}


@router.post("/dispatch/process")
def process_dispatch_queue(limit: int = 5):
    return {"processing": dispatcher.process_pending(limit=max(1, min(limit, 50))), "counts": dispatcher.counts(), "committee_counts": committee_escalations.counts(), "paper_mode": True}


@router.get("/committee-escalations")
def get_committee_escalations(limit: int = 100):
    return {"counts": committee_escalations.counts(), "items": committee_escalations.recent(limit=limit), "paper_mode": True}


@router.post("/committee-escalations/process")
def process_committee_escalations(limit: int = 3):
    return {"processing": committee_escalations.process_pending(limit=max(1, min(limit, 20))), "counts": committee_escalations.counts(), "risk_counts": risk_reviews.counts(), "paper_mode": True}


@router.get("/risk-reviews")
def get_risk_reviews(limit: int = 100):
    return {"counts": risk_reviews.counts(), "items": risk_reviews.recent(limit=limit), "paper_mode": True}


@router.post("/risk-reviews/process")
def process_risk_reviews(limit: int = 3):
    return {"processing": risk_reviews.process_pending(limit=max(1, min(limit, 20))), "counts": risk_reviews.counts(), "paper_counts": paper_execution.counts(), "paper_mode": True}


@router.post("/risk-reviews/backfill")
def backfill_completed_committee_reviews(limit: int = 25):
    enqueued = 0
    for item in committee_escalations.recent(limit=max(1, min(limit, 100))):
        result = item.get("committee_result")
        if item.get("status") != "complete" or not isinstance(result, dict):
            continue
        row = {"escalation_id": item["escalation_id"], "packet_payload": json.dumps(item["packet"])}
        enqueued += int(risk_reviews.maybe_enqueue(escalation_row=row, committee_result=result))
    return {"enqueued": enqueued, "counts": risk_reviews.counts(), "paper_mode": True}


@router.get("/paper-execution")
def get_paper_execution_candidates(limit: int = 100):
    return {"counts": paper_execution.counts(), "items": paper_execution.recent(limit=limit), "paper_mode": True, "live_execution": False}


@router.post("/paper-execution/test-fixture")
def create_controlled_paper_test_fixture():
    result = paper_execution.create_controlled_test_candidate()
    return {**result, "counts": paper_execution.counts()}


@router.post("/paper-execution/{candidate_id}/simulate")
def simulate_paper_execution(candidate_id: str):
    try:
        order = paper_execution.simulate(candidate_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"candidate_id": candidate_id, "order": order, "portfolio": paper_portfolio.summary(), "paper_mode": True, "live_execution": False}


@router.get("/paper-portfolio")
def get_paper_portfolio(limit: int = 100):
    return {
        "summary": paper_portfolio.summary(),
        "positions": paper_portfolio.recent(limit=limit),
        "paper_mode": True,
        "live_execution": False,
    }


@router.post("/paper-portfolio/{position_id}/mark")
def mark_paper_position(position_id: str, mark_price: float, source: str = "manual"):
    try:
        position = paper_portfolio.mark(position_id, mark_price, source=source)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"position": position, "summary": paper_portfolio.summary(), "paper_mode": True, "live_execution": False}


@router.post("/paper-portfolio/{position_id}/close")
def close_paper_position(position_id: str, exit_price: float, source: str = "manual_close"):
    try:
        position = paper_portfolio.close(position_id, exit_price, source=source)
        learning = outcome_learning.create_from_closed_position(position)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "position": position,
        "outcome_learning": learning,
        "summary": paper_portfolio.summary(),
        "history_dispatch_queue": dispatcher.counts(),
        "paper_mode": True,
        "live_execution": False,
    }


@router.get("/outcome-learning")
def get_outcome_learning(limit: int = 100):
    return {
        "items": outcome_learning.recent(limit=limit),
        "paper_mode": True,
        "live_execution": False,
    }


@router.post("/ingestion/run-now")
async def run_ingestion_now():
    for job in ingestion_service.jobs:
        job.next_run_at = None
    await ingestion_service.run_once()
    return ingestion_service.status()


@router.get("/macro/fred/{series_id}")
def get_fred_series(series_id: str):
    provider = FredProvider()
    try:
        return provider.fetch(series_id=series_id.upper())
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/market/crypto/{asset_id}")
def get_crypto_price(asset_id: str, vs_currency: str = "usd"):
    provider = CoinGeckoProvider()
    try:
        return provider.fetch(asset_id=asset_id.lower(), vs_currency=vs_currency.lower())
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/market/equity/{symbol}")
def get_equity_latest(symbol: str):
    provider = AlphaVantageProvider()
    try:
        return provider.fetch_latest_daily(symbol=symbol.upper())
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/history/equity/{symbol}")
def get_equity_history(symbol: str, outputsize: str = "compact"):
    provider = AlphaVantageProvider()
    if outputsize not in {"compact", "full"}:
        raise HTTPException(status_code=400, detail="outputsize must be compact or full")
    try:
        series = provider.fetch_daily_history(symbol=symbol.upper(), outputsize=outputsize)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"symbol": symbol.upper(), "daily": series, "paper_mode": True}


@router.get("/company/recent")
async def get_recent_company_filings(count_per_form: int = 40):
    try:
        return await fetch_recent_company_filings(count_per_form=count_per_form)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/ipo/recent")
async def get_recent_ipo_filings(count_per_form: int = 25):
    try:
        return await fetch_recent_ipo_filings(count_per_form=count_per_form)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/ipo/replay")
async def replay_recent_ipo_candidate(index: int = 0, count_per_form: int = 5):
    if index < 0:
        raise HTTPException(status_code=400, detail="index must be zero or greater")
    try:
        packet = await fetch_recent_ipo_filings(count_per_form=max(1, min(count_per_form, 25)))
        if index >= len(packet.items):
            raise HTTPException(status_code=404, detail=f"index {index} is outside the {len(packet.items)} returned candidates")
        item = packet.items[index]
        analysis = await asyncio.to_thread(dispatcher.analyze_ipo_item_now, item)
        return {"candidate_index": index, "candidate": item, "analysis": analysis, "paper_mode": True}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
