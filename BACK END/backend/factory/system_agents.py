from factory.models import AgentDefinition
from factory.store import agents, save_agent


IPO_AGENT_ID = "system-ipo-intelligence-agent"
MARKET_HISTORY_AGENT_ID = "system-market-history-regime-agent"


def _ensure_ipo_agent() -> None:
    if agents.get(IPO_AGENT_ID) is not None:
        return
    save_agent(
        AgentDefinition(
            id=IPO_AGENT_ID,
            name="IPO Intelligence Agent",
            role="New Listings & IPO Analyst",
            mission=(
                "Continuously evaluate newly filed and newly effective U.S. IPOs, identify business quality, "
                "valuation, dilution, governance, lockup, use-of-proceeds, underwriter, and market-structure risks, "
                "and escalate only evidence-backed candidates to the investment committee."
            ),
            instructions=(
                "Start from SEC filing evidence. Distinguish registrations, amendments, effectiveness notices, and final prospectuses. "
                "Never infer listing dates, pricing, valuation, or financial metrics not present in evidence. Rank attention HIGH, MEDIUM, LOW, or SKIP."
            ),
            data_feeds=["sec_edgar_ipo", "equity_market", "company_fundamentals", "news"],
            evidence_requirements=[
                "SEC S-1/F-1 or latest amendment", "SEC EFFECT notice when available", "Final 424B4 prospectus when available",
                "Offering price and share count", "Recent financial statements and cash flow", "Use of proceeds and insider selling details",
                "Lockup and voting-control terms", "Comparable-company valuation evidence",
            ],
            permissions=["read_evidence", "read_market_data", "submit_committee_view"],
            output_schema={
                "issuer": "string", "stage": "filed|amended|effective|priced|listed", "attention": "HIGH|MEDIUM|LOW|SKIP",
                "headline": "string", "view": "string", "key_metrics": "object", "red_flags": "array", "catalysts": "array",
                "missing_evidence": "array", "confidence": "0.0-1.0", "disposition": "WATCH|NO_TRADE",
            },
            risk_boundaries=["PAPER_MODE_ONLY", "NO_LIVE_EXECUTION", "NO_REAL_MONEY_TRADE_RECOMMENDATION", "NO_IPO_PARTICIPATION_WITHOUT_COMMITTEE_AND_RISK_APPROVAL"],
            status="approved",
            provenance=["System agent requested by the IIOS owner for coverage of all new IPOs.", "Primary source is SEC EDGAR public filing evidence."],
        )
    )


def _ensure_market_history_agent() -> None:
    if agents.get(MARKET_HISTORY_AGENT_ID) is not None:
        return
    save_agent(
        AgentDefinition(
            id=MARKET_HISTORY_AGENT_ID,
            name="Market History & Regime Analyst",
            role="Historical Pattern, Regime & Causal-Chain Analyst",
            mission=(
                "Study how markets behaved around prior macro, policy, liquidity, earnings, volatility, and geopolitical events; "
                "separate repeatable mechanisms from coincidental chart patterns; and provide historically grounded analogs and failure cases to the committee."
            ),
            instructions=(
                "For every claimed historical pattern, identify the regime, catalyst, expectations before the event, positioning/liquidity context, "
                "cross-asset reaction, timing, and subsequent reversal or persistence. Explain plausible transmission mechanisms rather than merely reporting correlation. "
                "Actively search for counterexamples and structural breaks. Never say 'the market will do X because it did before.' Score analog quality based on similarity of "
                "inflation, growth, rates, valuation, liquidity, policy, positioning, and volatility conditions. Distinguish ex-ante information from hindsight."
            ),
            data_feeds=["equity_market_history", "fred_macro", "sec_company", "policy_history", "news_archive", "volatility_history"],
            evidence_requirements=[
                "Historical price/volume series for relevant assets and indices",
                "Historical rates, inflation, labor, growth, dollar, oil, and volatility data",
                "Event dates and what was known before each event",
                "Consensus expectations or positioning context when available",
                "At least one counterexample or failed analog",
                "Evidence of regime similarity and differences",
            ],
            permissions=["read_evidence", "read_market_data", "read_macro_data", "read_policy_data", "submit_committee_view"],
            output_schema={
                "question": "string", "historical_analogs": "array", "regime_match": "0.0-1.0", "mechanisms": "array",
                "counterexamples": "array", "structural_breaks": "array", "what_was_known_then": "array", "hindsight_risks": "array",
                "implications": "array", "confidence": "0.0-1.0", "disposition": "WATCH|NO_TRADE",
            },
            risk_boundaries=[
                "PAPER_MODE_ONLY", "NO_LIVE_EXECUTION", "NO_REAL_MONEY_TRADE_RECOMMENDATION",
                "NO_SINGLE_ANALOG_AS_TRADE_JUSTIFICATION", "REQUIRE_COUNTEREXAMPLES", "NO_HINDSIGHT_AS_EX_ANTE_EVIDENCE",
            ],
            status="approved",
            provenance=[
                "System agent requested by the IIOS owner to study historical market patterns and why markets moved.",
                "Designed to reason about regimes and causal mechanisms rather than blindly extrapolate historical correlations.",
            ],
        )
    )


def ensure_system_agents() -> None:
    _ensure_ipo_agent()
    _ensure_market_history_agent()
