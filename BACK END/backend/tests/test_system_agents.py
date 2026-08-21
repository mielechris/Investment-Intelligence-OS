from factory.store import agents
from factory.system_agents import IPO_AGENT_ID, ensure_system_agents


def test_ipo_system_agent_is_seeded_and_approved():
    ensure_system_agents()
    agent = agents.get(IPO_AGENT_ID)

    assert agent is not None
    assert agent.name == "IPO Intelligence Agent"
    assert agent.status == "approved"
    assert "sec_edgar_ipo" in agent.data_feeds
    assert "NO_LIVE_EXECUTION" in agent.risk_boundaries
    assert "submit_committee_view" in agent.permissions


def test_ipo_system_agent_seed_is_idempotent():
    ensure_system_agents()
    first = agents.get(IPO_AGENT_ID)
    ensure_system_agents()
    second = agents.get(IPO_AGENT_ID)

    assert first is not None
    assert second is not None
    assert first.id == second.id
    assert first.created_at == second.created_at
