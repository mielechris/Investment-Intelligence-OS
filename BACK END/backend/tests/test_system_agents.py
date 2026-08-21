from factory.store import agents
from factory.system_agents import IPO_AGENT_ID, MARKET_HISTORY_AGENT_ID, ensure_system_agents


def test_system_agents_are_seeded_and_approved():
    ensure_system_agents()

    ipo = agents.get(IPO_AGENT_ID)
    history = agents.get(MARKET_HISTORY_AGENT_ID)

    assert ipo is not None
    assert ipo.name == "IPO Intelligence Agent"
    assert ipo.status == "approved"
    assert "sec_edgar_ipo" in ipo.data_feeds
    assert "NO_LIVE_EXECUTION" in ipo.risk_boundaries

    assert history is not None
    assert history.name == "Market History & Regime Analyst"
    assert history.status == "approved"
    assert "equity_market_history" in history.data_feeds
    assert "NO_SINGLE_ANALOG_AS_TRADE_JUSTIFICATION" in history.risk_boundaries
    assert "REQUIRE_COUNTEREXAMPLES" in history.risk_boundaries


def test_system_agent_seed_is_idempotent():
    ensure_system_agents()
    first_ipo = agents.get(IPO_AGENT_ID)
    first_history = agents.get(MARKET_HISTORY_AGENT_ID)
    ensure_system_agents()
    second_ipo = agents.get(IPO_AGENT_ID)
    second_history = agents.get(MARKET_HISTORY_AGENT_ID)

    assert first_ipo is not None and second_ipo is not None
    assert first_history is not None and second_history is not None
    assert first_ipo.created_at == second_ipo.created_at
    assert first_history.created_at == second_history.created_at
