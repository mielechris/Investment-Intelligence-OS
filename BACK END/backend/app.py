import os

os.environ.setdefault(
    "IIOS_USER_AGENT",
    "Investment-Intelligence-OS/0.18.0 research-client github.com/mielechris/Investment-Intelligence-OS",
)
os.environ.setdefault(
    "IIOS_SEC_USER_AGENT",
    "Investment-Intelligence-OS/0.18.0 research mielechris@users.noreply.github.com",
)

try:
    import certifi

    os.environ.setdefault("SSL_CERT_FILE", certifi.where())
except ImportError:
    pass

from main import app
from analyst_consensus_fallback import install_analyst_consensus_fallback
from cycle_normalized_valuation import cycle_normalized_evidence, router as cycle_valuation_router
from consensus_revision_history import consensus_revision_evidence
from demand_quality_watch import demand_quality_evidence
from dashboard_lineage import apply_latest_decision_lineage
from decision_history import router as history_router
import evidence_gap_hunter
from evidence_gap_hunter import router as gap_hunter_router
from finra_short_interest_fallback import install_finra_short_interest_fallback
from generic_coverage_v2 import install_generic_coverage_v2, router as generic_coverage_v2_router
from factory_genericization import (
    resolve_case_profile,
    router as factory_genericization_router,
)
from factory_room_api import router as factory_room_router
from generic_primary_evidence import router as generic_primary_evidence_router
from hard_data import hard_data_evidence, router as hard_data_router
from hyperscaler_primary_fallback import install_hyperscaler_primary_fallback
import insider_intelligence
from insider_intelligence import router as insider_router
from insider_ir_fallback import install_insider_fallback
from insider_secondary_fallback import install_secondary_insider_fallback
from insider_scope_guard import install_insider_scope_guard
import institutional_intelligence
from institutional_intelligence import router as institutional_router
from institutional_secondary_fallback import install_institutional_secondary_fallback
from institutional_integrity_guard import install_institutional_integrity_guard
from institutional_research_intelligence import institutional_research_evidence, router as institutional_research_router
from macro_policy_intelligence import market_policy_evidence, router as macro_policy_router
from dislocation_intelligence import router as dislocation_intelligence_router
from thesis_integrity_v2 import thesis_integrity_evidence, router as thesis_integrity_v2_router
from jesse_source_acquisition import router as jesse_source_acquisition_router
from jesse_scheduler import router as jesse_scheduler_router, start_jesse_scheduler, stop_jesse_scheduler
from batch8c_production_inputs import install_batch8c, router as batch8c_production_inputs_router
from kimi_research_intelligence import kimi_research_evidence, router as kimi_research_router
from multi_model_intelligence_council import council_evidence, router as multi_model_council_router
from interview_portal import router as interview_portal_router
from learning_loop import router as learning_router
from ledger import latest_object
import monitoring_engine
from portfolio_context import router as portfolio_context_router
from paper_capital_api import router as paper_capital_router
from paper_sizing_profile import router as paper_sizing_profile_router
from paper_authorization_api import router as paper_authorization_router
from governed_paper_execution_api import router as governed_paper_execution_router
import primary_evidence
import public_case_router
import source_ingestion
from monitoring_engine import build_dashboard, router as monitoring_router, start_scheduler, stop_scheduler
from opportunity_scheduler import start_opportunity_scheduler, stop_opportunity_scheduler
from memory_pricing_primary_fallback import install_memory_pricing_primary_fallback
from official_sources import fetch_google_news_rss, fetch_official_web
from open_evidence_watch import install_open_evidence_watch
from primary_evidence import primary_evidence_evidence, router as primary_evidence_router
from primary_evidence_semantic_guard import install_primary_evidence_semantic_guard
from provider_hardening import fetch_gdelt_news, fetch_market_quote, fetch_sec_companyfacts
from public_case_router import router as public_case_router_api
from requirement_lineage_guard import install_requirement_lineage_guard
from required_evidence_risk_guard import install_required_evidence_risk_guard
from semiconductor_intelligence import router as semiconductor_router
from short_interest_fallback import install_short_interest_fallback
from supply_inventory_primary_fallback import install_supply_inventory_primary_fallback
from valuation_market_primary_fallback import install_valuation_market_primary_fallback
from valuation_market_micron_filing_fallback import install_micron_valuation_filing_fallback


source_ingestion.FETCHERS["gdelt_news"] = fetch_gdelt_news
source_ingestion.FETCHERS["sec_companyfacts"] = fetch_sec_companyfacts
source_ingestion.FETCHERS["official_web"] = fetch_official_web
source_ingestion.FETCHERS["google_news_rss"] = fetch_google_news_rss
monitoring_engine._fetch_stooq_quote = fetch_market_quote
public_case_router._fetch_stooq_quote = fetch_market_quote

install_insider_fallback(insider_intelligence)
install_secondary_insider_fallback(insider_intelligence)
install_insider_scope_guard(insider_intelligence)

install_institutional_secondary_fallback(institutional_intelligence)
install_institutional_integrity_guard(institutional_intelligence)

install_primary_evidence_semantic_guard(primary_evidence)
install_memory_pricing_primary_fallback(primary_evidence)
install_hyperscaler_primary_fallback(primary_evidence)
install_supply_inventory_primary_fallback(primary_evidence)
install_valuation_market_primary_fallback(primary_evidence)
install_micron_valuation_filing_fallback(primary_evidence)
install_analyst_consensus_fallback(primary_evidence)
install_short_interest_fallback(primary_evidence)
install_finra_short_interest_fallback(primary_evidence)
install_open_evidence_watch(primary_evidence, monitoring_engine)
install_generic_coverage_v2()
install_required_evidence_risk_guard(primary_evidence)
install_batch8c()

_original_gap_packet_items = evidence_gap_hunter._raw_items_from_packet


def _gap_packet_items_with_governed_data(packet):
    items = _original_gap_packet_items(packet)
    case_id = str((packet or {}).get("case_id") or "")
    if case_id:
        items.extend(hard_data_evidence(case_id))
        items.extend(insider_intelligence.insider_evidence(case_id))
        items.extend(institutional_intelligence.institutional_evidence(case_id))
        items.extend(institutional_research_evidence(case_id))
        items.extend(kimi_research_evidence(case_id))
        items.extend(council_evidence(case_id))
        items.extend(market_policy_evidence(case_id))
        items.extend(thesis_integrity_evidence(case_id))
        items.extend(primary_evidence_evidence(case_id))
        items.extend(cycle_normalized_evidence(case_id))
        items.extend(consensus_revision_evidence(case_id))
        items.extend(demand_quality_evidence(case_id))
    return items


evidence_gap_hunter._raw_items_from_packet = _gap_packet_items_with_governed_data
install_requirement_lineage_guard(evidence_gap_hunter)


@app.get("/monitoring/dashboard")
def monitoring_dashboard_live(limit: int = 25):
    dashboard = build_dashboard(limit)
    coherent_rows = []
    for row in dashboard.get("cases", []):
        case_id = str(row.get("case_id", ""))
        snapshot = latest_object("monitor_snapshot", case_id=case_id) if case_id else None
        decision = latest_object("committee_decision", case_id=case_id) if case_id else None
        qualification = latest_object("qualification_assessment", case_id=case_id) if case_id else None
        coherent = apply_latest_decision_lineage(row, decision=decision, snapshot=snapshot, qualification=qualification)

        if case_id:
            try:
                identity = resolve_case_profile(
                    case_id
                )

                coherent["ticker"] = (
                    coherent.get("ticker")
                    or identity.get("ticker")
                )

                coherent["company"] = (
                    identity.get("company")
                )

                coherent["sector_profile"] = (
                    identity.get(
                        "sector_profile"
                    )
                )

            except Exception:
                pass

        reunderwrite = latest_object("full_reunderwrite", case_id=case_id) if case_id else None
        if reunderwrite:
            coherent["latest_reunderwrite_id"] = reunderwrite.get("full_reunderwrite_id")
            coherent["latest_reunderwrite_disposition"] = (reunderwrite.get("committee") or {}).get("disposition")
            coherent["latest_reunderwrite_confidence"] = (reunderwrite.get("committee") or {}).get("confidence")
        coherent_rows.append(coherent)
    dashboard["cases"] = coherent_rows
    return dashboard


app.include_router(cycle_valuation_router)
app.include_router(history_router)
app.include_router(gap_hunter_router)
app.include_router(generic_primary_evidence_router)
app.include_router(generic_coverage_v2_router)
app.include_router(factory_room_router)
app.include_router(factory_genericization_router)
app.include_router(hard_data_router)
app.include_router(insider_router)
app.include_router(institutional_router)
app.include_router(institutional_research_router)
app.include_router(macro_policy_router)
app.include_router(dislocation_intelligence_router)
app.include_router(thesis_integrity_v2_router)
app.include_router(jesse_source_acquisition_router)
app.include_router(jesse_scheduler_router)
app.include_router(batch8c_production_inputs_router)
app.include_router(kimi_research_router)
app.include_router(multi_model_council_router)
app.include_router(primary_evidence_router)
app.include_router(portfolio_context_router)
app.include_router(paper_capital_router)
app.include_router(paper_sizing_profile_router)
app.include_router(paper_authorization_router)
app.include_router(governed_paper_execution_router)
app.include_router(interview_portal_router)
app.include_router(learning_router)
app.include_router(monitoring_router)
app.include_router(public_case_router_api)
app.include_router(semiconductor_router)
app.version = "0.18.0"


@app.on_event("startup")
def start_iios_monitoring() -> None:
    start_scheduler()
    start_opportunity_scheduler()
    start_jesse_scheduler()


@app.on_event("shutdown")
def stop_iios_monitoring() -> None:
    stop_opportunity_scheduler()
    stop_jesse_scheduler()
    stop_scheduler()


@app.get("/system/status")
def system_status():
    return {
        "name": "Investment Intelligence OS",
        "version": "0.18.0",
        "paper_mode": True,
        "governed_chain": True,
        "persistent_ledger": True,
        "evidence_engine": True,
        "post_decision_learning": True,
        "judgment_bank": True,
        "automatic_monitoring": True,
        "institutional_research_intelligence": True,
        "cross_sector_sentiment_engine": True,
        "monetary_policy_probability_engine": True,
        "monetary_policy_probability_requires_governed_source": True,
        "tariff_transmission_engine": True,
        "daily_dislocation_scanner": True,
        "generic_thesis_integrity_v2": True,
        "jesse_live_source_acquisition": True,
        "jesse_internal_scheduler": True,
        "dislocation_11am_pacific_scheduler": True,
        "dislocation_next_day_calibration": True,
        "authorized_research_inbox": True,
        "governed_fed_probability_feed_adapter": True,
        "governed_dislocation_universe_registry": True,
        "automatic_official_index_universe_refresh": True,
        "strict_scheduled_dislocation_universe": True,
        "cme_fedwatch_production_adapter": True,
        "cme_fedwatch_eod_realtime_modes": True,
        "production_input_source_health": True,
        "production_inputs_fail_closed": True,
        "kimi_research_intelligence": True,
        "kimi_k3_long_context_research": True,
        "kimi_iios_parallel_research": True,
        "kimi_native_swarm_bridge": True,
        "kimi_formula_web_search": True,
        "kimi_consumer_deep_research_api_claimed": False,
        "kimi_full_report_persistence": False,
        "kimi_context_only_default": True,
        "kimi_auto_trade_authority": False,
        "multi_model_intelligence_council": True,
        "grok_x_search_intelligence": True,
        "grok_web_search_intelligence": True,
        "model_divergence_skeptic_escalation": True,
        "universal_model_weighting": False,
        "multi_model_committee_override": False,
        "multi_model_risk_override": False,
        "grok_auto_trade_authority": False,
        "opportunity_scanner_available": True,
        "opportunity_auto_scan_default": False,
        "opportunity_scan_interval_floor_minutes": 240,
        "opportunity_auto_dispatch_default": False,
        "opportunity_auto_trade_authority": False,
        "peer_aware_eight_agent_orchestration": True,
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
        "requirement_lineage_guard": True,
        "primary_fact_contracts": True,
        "primary_fact_coverage_required_for_resolution": True,
        "primary_evidence_semantic_guard": True,
        "policy_measured_transmission_required": True,
        "micron_hbm_economics_contract": True,
        "micron_hbm_economics_all_six_facts_required": True,
        "micron_hbm_margin_direct_annual_filing_support": True,
        "micron_hbm_customer_concentration_inference_allowed": False,
        "hyperscaler_demand_primary_engine": True,
        "hyperscaler_primary_sources": ["MICROSOFT_IR", "META_IR", "AMAZON_IR", "ALPHABET_OFFICIAL"],
        "hyperscaler_cancellation_inference_allowed": False,
        "hyperscaler_memory_terms_inference_allowed": False,
        "supply_inventory_primary_engine": True,
        "supply_inventory_required_suppliers": ["MICRON", "SK_HYNIX", "SAMSUNG", "CXMT"],
        "supply_inventory_supplier_coverage_required_for_resolution": True,
        "supply_inventory_cxmt_primary_source": "SHANGHAI_STOCK_EXCHANGE_PROSPECTUS",
        "supply_inventory_cxmt_primary_coverage": True,
        "supply_inventory_wafer_start_inference_allowed": False,
        "supply_inventory_utilization_inference_allowed": False,
        "valuation_market_primary_engine": True,
        "valuation_market_dynamic_by_ticker": True,
        "valuation_market_sources": ["SEC_COMPANYFACTS", "STOOQ", "YAHOO_PUBLIC_MARKET_DATA", "GOVERNED_CONSENSUS", "NASDAQ_SHORT_INTEREST", "FINRA_CONSOLIDATED_SHORT_INTEREST", "OCC_DAILY_OPEN_INTEREST", "FIRST_PARTY_PORTFOLIO"],
        "valuation_market_micron_sec_fallback": True,
        "valuation_market_filing_backed_ttm_pe": True,
        "valuation_market_portfolio_overlap_required_when_requested": True,
        "market_session_weekend_freshness": True,
        "cboe_delayed_page_auto_scraping": False,
        "secondary_institutional_data_can_resolve_valuation_gap": False,
        "governed_analyst_consensus_engine": True,
        "analyst_consensus_provider_order": ["YAHOO_PUBLIC_MARKET_DATA", "STOCKANALYSIS_GOVERNED_CONSENSUS", "USER_VERIFIED_GOVERNED_CONSENSUS"],
        "analyst_consensus_fact_scope": "VALUATION_MARKET_CONSENSUS_ONLY",
        "analyst_consensus_auto_trade_authority": False,
        "governed_short_interest_engine": True,
        "short_interest_primary_source": "NASDAQ_OR_FINRA_REGULATORY_SHORT_INTEREST",
        "short_interest_provider_order": ["NASDAQ_EXCHANGE_API", "FINRA_CONSOLIDATED_SHORT_INTEREST", "USER_VERIFIED_NASDAQ"],
        "short_interest_fact_scope": "VALUATION_MARKET_SHORT_INTEREST_ONLY",
        "short_interest_auto_trade_authority": False,
        "governed_options_positioning_engine": True,
        "options_positioning_primary_source": "OCC_DAILY_OPEN_INTEREST",
        "options_positioning_fact_scope": "VALUATION_MARKET_OPTIONS_ONLY",
        "options_positioning_put_call_is_directional_trade_signal": False,
        "options_positioning_auto_trade_authority": False,
        "governed_portfolio_snapshot": True,
        "portfolio_factor_overlap_engine": True,
        "portfolio_overlap_first_party_evidence": True,
        "portfolio_snapshot_freshness_days": 7,
        "portfolio_overlap_auto_trade_authority": False,
        "periodic_evidence_freshness_floor": True,
        "annual_filing_freshness_class": True,
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
            "MICRON_HBM_ECONOMICS",
            "VALUATION_MARKET",
            "POLICY_REGULATION",
        ],
        "primary_evidence_sources": [
            "SEC_COMPANYFACTS",
            "COMPANY_IR",
            "OFFICIAL_GOVERNMENT",
            "HARD_MARKET_DATA",
            "SHANGHAI_STOCK_EXCHANGE",
            "STOOQ",
            "YAHOO_PUBLIC_MARKET_DATA",
            "STOCKANALYSIS_GOVERNED_CONSENSUS",
            "NASDAQ_SHORT_INTEREST_REPORT",
            "FINRA_CONSOLIDATED_SHORT_INTEREST",
            "OCC_DAILY_OPEN_INTEREST",
            "FIRST_PARTY_PORTFOLIO",
        ],
        "primary_memory_pricing_auto_provider": False,
        "qualified_buy_candidate_gate": True,
        "paper_capital_gate": True,
        "thesis_invalidation_gate": True,
        "governed_position_sizing": True,
        "one_time_paper_authorization": True,
        "governed_paper_execution_bridge": True,
        "paper_capital_status_api": True,
        "paper_buy_enabled": False,
        "professional_interview_portal": True,
        "interview_auto_publish_to_trade_evidence": False,
        "automatic_ssl_cert_bundle": bool(os.getenv("SSL_CERT_FILE")),
    }
