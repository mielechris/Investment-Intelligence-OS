import os

os.environ.setdefault(
    "IIOS_USER_AGENT",
    "Investment-Intelligence-OS/0.12.0 research-client github.com/mielechris/Investment-Intelligence-OS",
)
os.environ.setdefault(
    "IIOS_SEC_USER_AGENT",
    "Investment-Intelligence-OS/0.12.0 research mielechris@users.noreply.github.com",
)

try:
    import certifi

    os.environ.setdefault("SSL_CERT_FILE", certifi.where())
except ImportError:
    pass

from main import app
from dashboard_lineage import apply_latest_decision_lineage
from decision_history import router as history_router
import evidence_gap_hunter
from evidence_gap_hunter import router as gap_hunter_router
from hard_data import hard_data_evidence, router as hard_data_router
import insider_intelligence
from insider_intelligence import router as insider_router
from insider_ir_fallback import install_insider_fallback
from insider_secondary_fallback import install_secondary_insider_fallback
from insider_scope_guard import install_insider_scope_guard
import institutional_intelligence
from institutional_intelligence import router as institutional_router
from institutional_secondary_fallback import install_institutional_secondary_fallback
from institutional_integrity_guard import install_institutional_integrity_guard
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
from primary_evidence import primary_evidence_evidence, router as primary_evidence_router
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
# The scope/freshness guard runs last so congressional/political rows and stale insider
# history cannot contaminate current corporate-insider research. Raw history remains in
# the audit ledger for provenance.
install_insider_fallback(insider_intelligence)
install_secondary_insider_fallback(insider_intelligence)
install_insider_scope_guard(insider_intelligence)

# Institutional source precedence:
# 1) Yahoo public market-data modules/options when locally accessible,
# 2) secondary public MarketBeat context for missing lanes,
# 3) integrity normalization so secondary units/semantics cannot masquerade as primary.
install_institutional_secondary_fallback(institutional_intelligence)
install_institutional_integrity_guard(institutional_intelligence)


# Hard Data, Insider/Ownership, Institutional Expectations, and Primary Evidence remain
# separate governed ledger classes. The Gap Hunter can see all of them, but only records
# that are resolution-eligible can satisfy a gap; v0.12 also requires the requirement's
# fact contract to reach its minimum coverage before the Resolution Matrix turns green.
_original_gap_packet_items = evidence_gap_hunter._raw_items_from_packet


def _gap_packet_items_with_governed_data(packet):
    items = _original_gap_packet_items(packet)
    case_id = str((packet or {}).get("case_id") or "")
    if case_id:
        items.extend(hard_data_evidence(case_id))
        items.extend(insider_intelligence.insider_evidence(case_id))
        items.extend(institutional_intelligence.institutional_evidence(case_id))
        items.extend(primary_evidence_evidence(case_id))
    return items


evidence_gap_hunter._raw_items_from_packet = _gap_packet_items_with_governed_data


@app.get("/monitoring/dashboard")
def monitoring_dashboard_live(limit: int = 25):
    """Return one coherent latest-research state per case.

    Monitor snapshots remain useful surveillance data, but the Committee decision and
    its locked evidence summary are authoritative for the current research disposition.
    This prevents an older monitor snapshot from being displayed beside a newer Gap
    Hunter Committee decision.
    """
    dashboard = build_dashboard(limit)
    coherent_rows = []
    for row in dashboard.get("cases", []):
        case_id = str(row.get("case_id", ""))
        snapshot = latest_object("monitor_snapshot", case_id=case_id) if case_id else None
        decision = latest_object("committee_decision", case_id=case_id) if case_id else None
        qualification = latest_object("qualification_assessment", case_id=case_id) if case_id else None

        coherent = apply_latest_decision_lineage(
            row,
            decision=decision,
            snapshot=snapshot,
            qualification=qualification,
        )

        reunderwrite = latest_object("full_reunderwrite", case_id=case_id) if case_id else None
        if reunderwrite:
            coherent["latest_reunderwrite_id"] = reunderwrite.get("full_reunderwrite_id")
            coherent["latest_reunderwrite_disposition"] = (reunderwrite.get("committee") or {}).get("disposition")
            coherent["latest_reunderwrite_confidence"] = (reunderwrite.get("committee") or {}).get("confidence")

        coherent_rows.append(coherent)

    dashboard["cases"] = coherent_rows
    return dashboard


app.include_router(history_router)
app.include_router(gap_hunter_router)
app.include_router(hard_data_router)
app.include_router(insider_router)
app.include_router(institutional_router)
app.include_router(primary_evidence_router)
app.include_router(interview_portal_router)
app.include_router(learning_router)
app.include_router(monitoring_router)
app.include_router(public_case_router_api)
app.include_router(semiconductor_router)
app.version = "0.12.0"


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
        "version": "0.12.0",
        "paper_mode": True,
        "governed_chain": True,
        "persistent_ledger": True,
        "evidence_engine": True,
        "post_decision_learning": True,
        "judgment_bank": True,
        "automatic_monitoring": True,
        "factory_dashboard": True,
        "dashboard_latest_decision_lineage": True,
        "semiconductor_memory_intelligence": True,
        "provider_hardening": True,
        "official_company_fallbacks": True,
        "news_rss_fallback": True,
        "decision_history": True,
        "evidence_gap_hunter": True,
        "gap_quality_firewall": True,
        "gap_resolution_matrix": True,
        "primary_fact_contracts": True,
        "primary_fact_coverage_required_for_resolution": True,
        "hard_data_acquisition": True,
        "hard_data_best_match_mapping": True,
        "hard_data_mapping_repair": True,
        "hard_data_auto_trade_evidence": False,
        "insider_ownership_intelligence": True,
        "insider_primary_source": "SEC_EDGAR_PUBLIC_FILINGS",
        "insider_official_company_fallback": "MICRON_IR_SEC_FILINGS_STATIC_TABLE",
        "insider_secondary_public_fallback": "MARKETBEAT_CONTEXT_ONLY",
        "insider_secondary_requires_primary_corroboration": True,
        "insider_scope_filter": "CORPORATE_INSIDERS_ONLY",
        "insider_political_trade_exclusion": True,
        "insider_coverage_aware_summary": True,
        "insider_freshness_window_days": 90,
        "insider_stale_history_current_signal": False,
        "insider_stale_history_research_admission": False,
        "insider_date_display_utc": True,
        "insider_fallback_transaction_inference": False,
        "insider_auto_trade_authority": False,
        "institutional_expectations_layer": True,
        "institutional_lanes": [
            "INSTITUTIONAL_OWNERSHIP_13F_CONTEXT",
            "ANALYST_ESTIMATE_REVISIONS",
            "SHORT_INTEREST",
            "OPTIONS_POSITIONING",
            "CATALYST_CALENDAR",
        ],
        "institutional_primary_source": "YAHOO_PUBLIC_MARKET_DATA_WHEN_AVAILABLE",
        "institutional_secondary_public_fallback": "MARKETBEAT_CONTEXT_ONLY",
        "institutional_integrity_guard": True,
        "institutional_unknown_13f_date_not_current": True,
        "institutional_percentage_schema": "DECIMAL_FRACTION",
        "institutional_analyst_fallback_scope_honest": True,
        "institutional_primary_corroboration_required": True,
        "institutional_gap_resolution_eligible": False,
        "institutional_auto_trade_authority": False,
        "primary_evidence_acquisition": True,
        "primary_evidence_lanes": [
            "MEMORY_PRICING",
            "SUPPLY_INVENTORY",
            "HYPERSCALER_DEMAND",
            "MICRON_FILING_FINANCIALS",
            "VALUATION_MARKET",
            "POLICY_REGULATION",
        ],
        "primary_evidence_sources": ["SEC_COMPANYFACTS", "COMPANY_IR", "OFFICIAL_GOVERNMENT", "HARD_MARKET_DATA"],
        "primary_memory_pricing_auto_provider": False,
        "qualified_buy_candidate_gate": True,
        "paper_buy_enabled": False,
        "professional_interview_portal": True,
        "interview_auto_publish_to_trade_evidence": False,
        "automatic_ssl_cert_bundle": bool(os.getenv("SSL_CERT_FILE")),
    }
