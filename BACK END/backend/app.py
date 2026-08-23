import os

os.environ.setdefault(
    "IIOS_USER_AGENT",
    "Investment-Intelligence-OS/0.10.5 research-client github.com/mielechris/Investment-Intelligence-OS",
)
os.environ.setdefault(
    "IIOS_SEC_USER_AGENT",
    "Investment-Intelligence-OS/0.10.5 research mielechris@users.noreply.github.com",
)

try:
    import certifi

    os.environ.setdefault("SSL_CERT_FILE", certifi.where())
except ImportError:
    pass

from main import app
from decision_history import router as history_router
import evidence_gap_hunter
from evidence_gap_hunter import router as gap_hunter_router
from hard_data import hard_data_evidence, router as hard_data_router
import insider_intelligence
from insider_intelligence import insider_evidence, router as insider_router
from insider_ir_fallback import install_insider_fallback
from insider_secondary_fallback import install_secondary_insider_fallback
from interview_portal import router as interview_portal_router
from learning_loop import router as learning_router
from ledger import latest_object
import monitoring_engine
import public_case_router
import source_ingestion
from monitoring_engine import (
    build_dashboard,
    router as monitoring_router,
    start_scheduler,
    stop_scheduler,
)
from official_sources import fetch_google_news_rss, fetch_official_web
from provider_hardening import fetch_gdelt_news, fetch_market_quote, fetch_sec_companyfacts
from public_case_router import router as public_case_router_api
from semiconductor_intelligence import router as semiconductor_router


# Provider hardening/fallbacks are installed centrally so every route and background
# refresh uses the same pacing, retry, SSL, official-company, news, and market logic.
source_ingestion.FETCHERS["gdelt_news"] = fetch_gdelt_news
source_ingestion.FETCHERS["sec_companyfacts"] = fetch_sec_companyfacts
source_ingestion.FETCHERS["official_web"] = fetch_official_web
source_ingestion.FETCHERS["google_news_rss"] = fetch_google_news_rss
monitoring_engine._fetch_stooq_quote = fetch_market_quote
public_case_router._fetch_stooq_quote = fetch_market_quote

# Insider source precedence:
# 1) direct SEC EDGAR,
# 2) official Micron IR filing index,
# 3) secondary public insider source for context only.
# Secondary records require primary corroboration and cannot independently resolve a
# qualification gap or authorize a trade.
install_insider_fallback(insider_intelligence)
install_secondary_insider_fallback(insider_intelligence)


# Hard Data and Insider/Ownership records remain separate governed ledger classes. The
# Gap Hunter sees admitted records through its prior-evidence loader; the existing
# quality firewall and resolution matrix still decide what can actually resolve a gap.
_original_gap_packet_items = evidence_gap_hunter._raw_items_from_packet


def _gap_packet_items_with_governed_data(packet):
    items = _original_gap_packet_items(packet)
    case_id = str((packet or {}).get("case_id") or "")
    if case_id:
        items.extend(hard_data_evidence(case_id))
        items.extend(insider_evidence(case_id))
    return items


evidence_gap_hunter._raw_items_from_packet = _gap_packet_items_with_governed_data


@app.get("/monitoring/dashboard")
def monitoring_dashboard_live(limit: int = 25):
    """Return dashboard rows using the newest monitoring evidence when available."""
    dashboard = build_dashboard(limit)
    for row in dashboard.get("cases", []):
        case_id = str(row.get("case_id", ""))
        snapshot = latest_object("monitor_snapshot", case_id=case_id) if case_id else None
        summary = ((snapshot or {}).get("evidence_packet") or {}).get("summary") or {}
        if "average_quality_score" in summary:
            row["evidence_quality"] = summary.get("average_quality_score")
            row["latest_evidence_count"] = summary.get("evidence_count")
        reunderwrite = latest_object("full_reunderwrite", case_id=case_id) if case_id else None
        if reunderwrite:
            row["latest_reunderwrite_id"] = reunderwrite.get("full_reunderwrite_id")
            row["latest_reunderwrite_disposition"] = (reunderwrite.get("committee") or {}).get("disposition")
            row["latest_reunderwrite_confidence"] = (reunderwrite.get("committee") or {}).get("confidence")
        qualification = latest_object("qualification_assessment", case_id=case_id) if case_id else None
        if qualification:
            row["qualification_stage"] = qualification.get("stage")
            row["qualified_buy_candidate"] = qualification.get("qualified_buy_candidate")
    return dashboard


app.include_router(history_router)
app.include_router(gap_hunter_router)
app.include_router(hard_data_router)
app.include_router(insider_router)
app.include_router(interview_portal_router)
app.include_router(learning_router)
app.include_router(monitoring_router)
app.include_router(public_case_router_api)
app.include_router(semiconductor_router)
app.version = "0.10.5"


@app.on_event("startup")
def start_iios_monitoring() -> None:
    start_scheduler()


@app.on_event("shutdown")
def stop_iios_monitoring() -> None:
    stop_scheduler()


@app.get("/system/status")
def system_status():
    """Return the active governed-factory feature level."""
    return {
        "name": "Investment Intelligence OS",
        "version": "0.10.5",
        "paper_mode": True,
        "governed_chain": True,
        "persistent_ledger": True,
        "evidence_engine": True,
        "post_decision_learning": True,
        "judgment_bank": True,
        "automatic_monitoring": True,
        "factory_dashboard": True,
        "semiconductor_memory_intelligence": True,
        "provider_hardening": True,
        "official_company_fallbacks": True,
        "news_rss_fallback": True,
        "decision_history": True,
        "evidence_gap_hunter": True,
        "gap_quality_firewall": True,
        "gap_resolution_matrix": True,
        "hard_data_acquisition": True,
        "hard_data_best_match_mapping": True,
        "hard_data_mapping_repair": True,
        "hard_data_auto_trade_evidence": False,
        "insider_ownership_intelligence": True,
        "insider_primary_source": "SEC_EDGAR_PUBLIC_FILINGS",
        "insider_official_company_fallback": "MICRON_IR_SEC_FILINGS_STATIC_TABLE",
        "insider_secondary_public_fallback": "MARKETBEAT_CONTEXT_ONLY",
        "insider_secondary_requires_primary_corroboration": True,
        "insider_fallback_transaction_inference": False,
        "insider_auto_trade_authority": False,
        "qualified_buy_candidate_gate": True,
        "paper_buy_enabled": False,
        "professional_interview_portal": True,
        "interview_auto_publish_to_trade_evidence": False,
        "automatic_ssl_cert_bundle": bool(os.getenv("SSL_CERT_FILE")),
    }
