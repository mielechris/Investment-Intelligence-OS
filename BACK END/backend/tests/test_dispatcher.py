from pathlib import Path

from factory.system_agents import IPO_AGENT_ID, MARKET_HISTORY_AGENT_ID, ensure_system_agents
from intelligence.dispatcher import EventDispatcher
from intelligence.models import EvidenceItem


def test_ipo_filing_routes_to_ipo_and_history_agents(tmp_path: Path):
    ensure_system_agents()
    dispatcher = EventDispatcher(database_path=tmp_path / "dispatch.db")
    item = EvidenceItem(
        source_name="SEC EDGAR",
        source_kind="company",
        title="Example Corp S-1 filing",
        summary="IPO-related SEC filing (S-1). Initial registration statement.",
        freshness="fresh",
        confidence=0.99,
    )

    routes = dict(dispatcher.route(item))

    assert IPO_AGENT_ID in routes
    assert MARKET_HISTORY_AGENT_ID in routes
    assert dispatcher.enqueue([item]) == 2
    assert dispatcher.counts()["pending"] == 2


def test_macro_evidence_routes_to_history_agent(tmp_path: Path):
    ensure_system_agents()
    dispatcher = EventDispatcher(database_path=tmp_path / "dispatch.db")
    item = EvidenceItem(
        source_name="Federal Reserve Bank of St. Louis FRED",
        source_kind="macro",
        title="FRED CPIAUCSL latest observation",
        summary="CPIAUCSL = 300.0 for observation date 2026-07-01.",
        freshness="fresh",
        confidence=0.98,
    )

    routes = dict(dispatcher.route(item))

    assert MARKET_HISTORY_AGENT_ID in routes
    assert dispatcher.enqueue([item]) >= 1


def test_dispatch_queue_deduplicates_same_evidence_for_same_agent(tmp_path: Path):
    ensure_system_agents()
    dispatcher = EventDispatcher(database_path=tmp_path / "dispatch.db")
    item = EvidenceItem(
        source_name="CoinGecko",
        source_kind="market",
        title="bitcoin spot price",
        summary="bitcoin spot price = 100000 USD.",
        freshness="fresh",
        confidence=0.95,
    )

    first = dispatcher.enqueue([item])
    second = dispatcher.enqueue([item])

    assert first >= 1
    assert second == 0
