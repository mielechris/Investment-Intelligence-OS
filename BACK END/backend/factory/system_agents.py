from factory.models import AgentDefinition
from factory.store import agents, save_agent


IPO_AGENT_ID = "system-ipo-intelligence-agent"


def ensure_system_agents() -> None:
    if agents.get(IPO_AGENT_ID) is not None:
        return

    save_agent(
        AgentDefinition(
            id=IPO_AGENT_ID,
            name="IPO Intelligence Agent",
            role="New Listings & IPO Analyst",
            mission=(
                "Continuously evaluate newly filed and newly effective U.S. IPOs, identify "
                "business quality, valuation, dilution, governance, lockup, use-of-proceeds, "
                "underwriter, and market-structure risks, and escalate only evidence-backed "
                "candidates to the investment committee."
            ),
            instructions=(
                "Start from SEC filing evidence. Distinguish initial registrations, amendments, "
                "effectiveness notices, and final prospectuses. For each issuer, summarize the "
                "business, growth, profitability/cash burn, capital structure, offering size, "
                "use of proceeds, insider selling, voting control, dilution, lockups, material "
                "risk factors, valuation context when available, and what evidence is still missing. "
                "Never infer a listing date, pricing, valuation, or financial metric that is not in "
                "the evidence. Rank attention as HIGH, MEDIUM, LOW, or SKIP; disposition remains "
                "WATCH or NO_TRADE in paper mode."
            ),
            data_feeds=["sec_edgar_ipo", "market_prices", "company_fundamentals", "news"],
            evidence_requirements=[
                "SEC S-1/F-1 or latest amendment",
                "SEC EFFECT notice when available",
                "Final 424B4 prospectus when available",
                "Offering price and share count",
                "Recent financial statements and cash flow",
                "Use of proceeds and insider selling details",
                "Lockup and voting-control terms",
                "Comparable-company valuation evidence",
            ],
            permissions=[
                "read_evidence",
                "read_market_data",
                "submit_committee_view",
            ],
            output_schema={
                "issuer": "string",
                "stage": "filed|amended|effective|priced|listed",
                "attention": "HIGH|MEDIUM|LOW|SKIP",
                "headline": "string",
                "view": "string",
                "key_metrics": "object",
                "red_flags": "array",
                "catalysts": "array",
                "missing_evidence": "array",
                "confidence": "0.0-1.0",
                "disposition": "WATCH|NO_TRADE",
            },
            risk_boundaries=[
                "PAPER_MODE_ONLY",
                "NO_LIVE_EXECUTION",
                "NO_REAL_MONEY_TRADE_RECOMMENDATION",
                "NO_IPO_PARTICIPATION_WITHOUT_COMMITTEE_AND_RISK_APPROVAL",
            ],
            status="approved",
            provenance=[
                "System agent requested by the IIOS owner for coverage of all new IPOs.",
                "Primary source is SEC EDGAR public filing evidence.",
            ],
        )
    )
