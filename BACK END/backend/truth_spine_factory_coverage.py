"""Pure, deny-only coverage derived from normalized immutable capture events.

Catalog identities are pinned to committed product/agent definitions by tests.
No operational imports, credential probes, provider calls or filesystem discovery.
"""
from __future__ import annotations

from collections import Counter
from truth_spine_contract import digest, seal, verified, utc
from truth_spine_authority import CAPABILITIES
from truth_spine_generations import cycle_identity

SCHEMA = "iios-full-factory-shadow-coverage-v1"
ROUTES = (("bigdata", "Bigdata.com"), ("financial_datasets", "Financial Datasets"),
          ("alpha_vantage", "Alpha Vantage"), ("alpaca_data", "Alpaca market data"),
          ("alpaca_paper", "Alpaca paper brokerage"), ("openai", "OpenAI"),
          ("gemini", "Gemini"), ("grok", "Grok"), ("mcp", "MCP tool routing"),
          ("vercel", "Vercel presentation/deployment"))
SUBSYSTEMS = (("9A", "Cadence / orchestration", None), ("9B", "Governed research", "research"),
              ("9E", "High-speed market radar", "source_cycle"), ("9G", "Telemetry / Factory Watch", None),
              ("9H", "Independent validation", "validation_9h"),
              ("9I", "Counterfactual / shadow research", "shadow_9i"), ("9J", "Outcomes / judgment", "outcomes_9j"))
HISTORY = (("l7", "L7 paper-account history", "operational", None),
           ("l8", "L8 historical cases", "historical", "case"),
           ("agent_results", "Agent results", None, "agent_result"),
           ("committee_decisions", "Committee decisions", None, "committee_decision"),
           ("opportunities", "Opportunity candidates", None, "opportunity_candidate"),
           ("pattern_reviews", "Historical-pattern reviews", None, "historical_pattern_review"),
           ("measurements_9h", "9H measurements", "validation_9h", None),
           ("counterfactual_9i", "9I counterfactual research", "shadow_9i", None),
           ("outcomes_9j", "9J outcomes / judgment review", "outcomes_9j", None),
           ("pattern_library", "Pattern Library", "patterns", None),
           ("jesse_bank", "Jesse Judgment Bank", None, "judgment_entry"),
           ("price_archive", "Price archive", "price_archive", None),
           ("event_archive", "Event reconstruction", "event_reconstruction", None),
           ("macro_archive", "Macro archives", "macro_regime", None))


def factory_coverage(generation, events, cycle, phase):
    """Deterministic canonical extension, never a separate dashboard truth source.

    Counts below are EXACTLY attributable retained records, NOT current agent
    invocations or a complete inventory of external activity. Missing is null.
    """
    verified(generation)
    if (cycle["generation"] != generation["content_hash"] or cycle["session"] != generation["session"]
            or cycle["phase"] != phase or cycle["source_cycle_id"] != cycle_identity(cycle)
            or cycle["stores"] != generation["files"]
            or len({e["id"] for e in events}) != len(events)):
        raise ValueError("FACTORY_COVERAGE_BINDING_INVALID")
    for event in events: verified(event)
    files = {f["store"]: f for f in generation["files"]}
    if any(e["store"] not in files for e in events):
        raise ValueError("FACTORY_SOURCE_MISSING")
    def match(kind=None, record_type=None):
        return [e for e in events if (kind is None or files[e["store"]]["kind"] == kind)
                and (record_type is None or e["type"] == record_type)]
    def row(identity, name, component, selected):
        refs = sorted({e["id"]: {"record_id": e["id"], "source_store": e["store"],
            "record_type": e["type"], "payload_hash": e["payload_hash"],
            "classification": e["classification"], "event_time": e["event_time"],
            "observation_time": e["observation_time"], "publication_time": e["publication_time"]}
            for e in selected}.values(), key=lambda r:r["record_id"])
        # Bound large disclosures without losing full-set identity/counts.
        classes = dict(sorted(Counter(e["classification"] for e in selected).items()))
        return {"id": identity, "name": name, "component_type": component,
            "operational_state": "UNAVAILABLE", "evidence_classifications": classes,
            "readiness": "RETAINED_READ_ONLY" if refs else "UNAVAILABLE",
            "authority": dict.fromkeys(CAPABILITIES, False), "source_cycle_id": cycle["source_cycle_id"],
            "generation_id": generation["content_hash"], "last_verified_at": cycle["published_at"],
            "freshness": "CAPTURE_BOUND_NOT_MARKET_FRESHNESS", "phase": phase,
            "bindings": refs[:20], "binding_count": len(refs), "binding_set_hash": digest({"bindings":refs}),
            "activity_counts": {"retained_records": len(refs) if refs else None,
                                "current_invocations": None},
            "last_activity": max((e["event_time"] for e in selected if e["event_time"]), key=utc, default=None),
            "incident_state": "UNKNOWN",
            "limitation": "EXPLICITLY_BOUND_RETAINED_RECORDS_ONLY_NOT_CURRENT_ACTIVITY" if refs else
                          "NO_INDIVIDUALLY_BOUND_GOVERNED_RECORD"}
    rooms = []
    for identity, name, family, exposure, benchmark in ROOMS:
        selected = [e for e in events if e.get("coverage", {}).get("product_id") == identity]
        r = row(identity, name, "PRODUCT_ROOM", selected)
        r.update(product_classification=family, exposure=exposure, benchmark=benchmark,
                 universe_coverage="UNAVAILABLE_NO_ROOM_MEMBERSHIP_BINDING",
                 configured_evidence_routes=["AUTHORIZED_MARKET_EVIDENCE", "PRIMARY_VERIFICATION"],
                 evidence_availability=r["readiness"], candidate_count=
                 sum(e["type"] == "opportunity_candidate" for e in selected) if selected else None,
                 case_count=sum(e["type"] == "case" for e in selected) if selected else None,
                 operational_state="OBSERVATION_ONLY")
        rooms.append(r)
    agents = []
    for identity, name, role in AGENTS:
        selected = [e for e in events if e["type"] == "agent_result" and e.get("coverage", {}).get("agent_id") == identity]
        r = row(identity, name, "SPECIALIST", selected)
        r.update(configured_role=role, operational_state="SUPPRESSED", model_route_status="UNKNOWN",
                 suppression_reason="DENY_ONLY_SHADOW_NO_MODEL_INVOCATION",
                 completed_result_count=sum(e.get("coverage", {}).get("result_state") == "complete" for e in selected) if selected else None)
        agents.append(r)
    governance = [row("independent_skeptic", "Independent Skeptic / Red Team", "GOVERNANCE",
                     [e for e in events if e["type"] == "agent_result" and e.get("coverage", {}).get("agent_id") == "skeptic"]),
                  row("committee", "Investment Committee", "GOVERNANCE", match(record_type="committee_decision")),
                  row("risk", "Deterministic Risk Inspection", "GOVERNANCE", match(record_type="risk_authorization"))]
    governance[0]["registered_agent_reference"] = "skeptic"  # A view, not a ninth specialist.
    for r in governance:
        record_type = {"independent_skeptic": "agent_result", "committee": "committee_decision", "risk": "risk_authorization"}[r["id"]]
        retained = [e for e in match(record_type=record_type) if r["id"] != "independent_skeptic"
                    or e.get("coverage", {}).get("agent_id") == "skeptic"]
        r.update(operational_state="SUPPRESSED", configured_role=r["name"], model_route_status="DISABLED",
                 completed_result_count=sum(e.get("coverage", {}).get("result_state") == "complete" for e in retained)
                 if retained else None,
                 suppression_reason="READ_ONLY_NO_NEW_DECISIONS")
    routes = []
    for identity, name in ROUTES:
        r = row(identity, name, "ROUTING_STATUS", [])
        r.update(configured="UNKNOWN", credential_presence="UNKNOWN", enabled=False,
                 connection="NOT_ATTEMPTED_THIS_SHADOW", permitted_capabilities=[], request_count=0,
                 credit_cost_count=None, activity_scope="THIS_DENY_ONLY_SHADOW_NOT_HOST_HISTORY",
                 rate_budget_state="LOCKED_ZERO_ALLOWANCE", operational_state="DISABLED",
                 last_verified_state="DENY_ONLY_POLICY_NOT_EXTERNAL_CONFIGURATION",
                 limitation="NO_APPROVED_PRECOMPUTED_CONFIGURATION_OR_CREDENTIAL_RECORD",
                 authoritative_truth_source=False)
        routes.append(r)
    history = [row(i,n,"HISTORY_MEMORY",match(k,t)) for i,n,k,t in HISTORY]
    subsystems = [row(i,n,"SUBSYSTEM",match(k) if k else []) for i,n,k in SUBSYSTEMS]
    for r in subsystems: r["limitation"] += "_PROCESS_HEALTH_NOT_INFERRED"
    paper_rows = match("operational", "paper_portfolio_snapshot")
    stamped = [e for e in paper_rows if e["event_time"] is not None]
    latest_time = max((utc(e["event_time"]) for e in stamped), default=None)
    latest = [e for e in stamped if utc(e["event_time"]) == latest_time]
    paper = latest[0].get("coverage", {}).get("paper") if len(latest) == 1 else None
    day = row("day_trading", "Day Trading", "DAY_TRADING", latest if len(latest) == 1 else [])
    day.update(operational_state="OBSERVATION_ONLY", order_allowance=0, broker_connection=False,
               kill_switch="LOCKED_FAIL_CLOSED", paper=paper or {"nav":None,"cash":None,"positions":None},
               paper_scope="RETAINED_L7_SNAPSHOT_NOT_LIVE_ACCOUNT", paper_authority=False, live_authority=False)
    return seal({"schema": SCHEMA, "session": generation["session"], "generation_id": generation["content_hash"],
        "source_cycle_id": cycle["source_cycle_id"], "published_at":cycle["published_at"], "phase":phase,
        "catalog_hash":digest({"rooms":ROOMS,"agents":AGENTS,"routes":ROUTES,"subsystems":SUBSYSTEMS,"history":HISTORY}),
        "rooms":rooms,"agents":agents,"governance":governance,"routes":routes,"history":history,
        "subsystems":subsystems,"day_trading":day,"universes":
            [{k:v for k,v in u.items() if k != "members"} for u in generation["universes"]],
        "permanent_production":"YELLOW_NOT_ASSESSED_BY_SHADOW",
        "limitation":"CONFIGURATION_IDENTITIES_ARE_NOT_ACTIVITY_OR_LIVE_READINESS"})

ROOMS = [
  [
    "us_large_cap_equities",
    "U.S. Large-Cap Equities",
    "EQUITY_ETF",
    "DIRECT",
    "SP500"
  ],
  [
    "us_mid_cap_equities",
    "U.S. Mid-Cap Equities",
    "EQUITY_ETF",
    "DIRECT",
    "SP400"
  ],
  [
    "us_small_cap_equities",
    "U.S. Small-Cap Equities",
    "EQUITY_ETF",
    "DIRECT",
    "RUSSELL2000"
  ],
  [
    "international_developed_equities",
    "International Developed Equities",
    "EQUITY_ETF",
    "DIRECT",
    "MSCI_EAFE"
  ],
  [
    "emerging_market_equities",
    "Emerging-Market Equities",
    "EQUITY_ETF",
    "DIRECT",
    "MSCI_EM"
  ],
  [
    "sector_thematic_etfs",
    "Sector and Thematic ETFs",
    "EQUITY_ETF",
    "DIRECT",
    "SP500"
  ],
  [
    "broad_factor_etfs",
    "Broad-Market and Factor ETFs",
    "EQUITY_ETF",
    "DIRECT",
    "SP500"
  ],
  [
    "treasury_bills_cash",
    "U.S. Treasury Bills and Cash Equivalents",
    "TREASURY",
    "DIRECT",
    "UST_BILL_INDEX"
  ],
  [
    "treasury_notes_bonds",
    "U.S. Treasury Notes and Bonds",
    "TREASURY",
    "DIRECT",
    "UST_AGGREGATE"
  ],
  [
    "treasury_etf_duration_proxies",
    "Treasury ETFs and Duration Proxies",
    "EQUITY_ETF",
    "PROXY",
    "UST_AGGREGATE"
  ],
  [
    "investment_grade_corporate_bonds",
    "Investment-Grade Corporate Bonds",
    "CREDIT",
    "DIRECT",
    "US_IG_INDEX"
  ],
  [
    "high_yield_corporate_bonds",
    "High-Yield Corporate Bonds",
    "CREDIT",
    "DIRECT",
    "US_HY_INDEX"
  ],
  [
    "municipal_bonds_etfs",
    "Municipal Bonds and Municipal ETFs",
    "CREDIT",
    "DIRECT_OR_PROXY",
    "MUNI_INDEX"
  ],
  [
    "listed_equity_etf_options",
    "Listed Equity and ETF Options",
    "OPTION",
    "DERIVATIVE",
    "UNDERLYING_TOTAL_RETURN"
  ],
  [
    "index_options",
    "Index Options",
    "OPTION",
    "DERIVATIVE",
    "UNDERLYING_INDEX"
  ],
  [
    "commodity_etf_etc_proxies",
    "Commodity ETFs and ETC Proxies",
    "COMMODITY",
    "PROXY",
    "COMMODITY_SPOT_REFERENCE"
  ],
  [
    "commodity_futures_references",
    "Commodity Futures References",
    "COMMODITY",
    "REFERENCE",
    "COMMODITY_CONTINUOUS_REFERENCE"
  ],
  [
    "fx_spot_references",
    "Foreign-Exchange Spot References",
    "FX",
    "REFERENCE",
    "CASH_RATE_DIFFERENTIAL"
  ],
  [
    "currency_etfs_fx_proxies",
    "Currency ETFs and FX Proxies",
    "FX",
    "PROXY",
    "FX_SPOT_REFERENCE"
  ],
  [
    "crypto_spot_references",
    "Crypto Spot References",
    "CRYPTO",
    "REFERENCE",
    "CONSOLIDATED_SPOT_REFERENCE"
  ],
  [
    "crypto_etfs_listed_proxies",
    "Crypto ETFs and Listed Proxies",
    "CRYPTO",
    "PROXY",
    "CRYPTO_SPOT_REFERENCE"
  ],
  [
    "reits_listed_real_estate",
    "REITs and Listed Real-Estate Securities",
    "INCOME",
    "DIRECT",
    "REIT_INDEX"
  ],
  [
    "preferred_income_securities",
    "Preferred Stock and Income Securities",
    "INCOME",
    "DIRECT",
    "PREFERRED_INDEX"
  ],
  [
    "money_market_ultra_short",
    "Money-Market and Ultra-Short-Duration Products",
    "INCOME",
    "DIRECT_OR_PROXY",
    "T_BILL_RATE"
  ]
]
AGENTS = [
  [
    "policy",
    "Policy Analyst",
    "Policy Floor"
  ],
  [
    "macro",
    "Macro & Rates Analyst",
    "Macro Desk"
  ],
  [
    "fundamentals",
    "Fundamentals Analyst",
    "Fundamentals Lab"
  ],
  [
    "market_structure",
    "Market Structure Analyst",
    "Tape & Positioning"
  ],
  [
    "commodities",
    "Commodities & Supply Chain Analyst",
    "Physical Markets"
  ],
  [
    "geo_weather",
    "Geopolitics & Weather Analyst",
    "Global Events Room"
  ],
  [
    "skeptic",
    "Skeptic / Red Team",
    "Red Team"
  ],
  [
    "portfolio",
    "Portfolio Context Analyst",
    "Portfolio Control"
  ]
]
