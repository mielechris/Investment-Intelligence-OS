from factory.system_agents import RED_TEAM_AGENT_ID
from intelligence.council_router import _build_vote_summary, _deterministic_council_gate


def _review(name: str, stance: str, confidence: float = 0.8, *, applicable: bool = True, agent_id: str | None = None):
    return {
        "agent_id": agent_id or name.lower().replace(" ", "-"),
        "agent_name": name,
        "applicability": "APPLICABLE" if applicable else "NOT_APPLICABLE",
        "stance": stance,
        "confidence": confidence,
    }


def test_non_applicable_specialist_abstains_from_quorum():
    reviews = [
        _review("IPO", "NEUTRAL", 0.99, applicable=False),
        _review("History", "SUPPORT"),
        _review("Fundamentals", "SUPPORT"),
        _review("Macro", "SUPPORT"),
        _review("Market Structure", "SUPPORT"),
        _review("Sentiment", "SUPPORT"),
        _review("Catalyst", "NEUTRAL"),
        _review("Red Team", "NEUTRAL", agent_id=RED_TEAM_AGENT_ID),
    ]
    summary = _build_vote_summary(reviews)

    assert summary["agent_count"] == 8
    assert summary["applicable_count"] == 7
    assert summary["abstain"] == 1
    assert summary["support"] == 5
    assert summary["required_support"] == 5

    passed, reasons = _deterministic_council_gate(summary, {"decision": "PASS_TO_RISK"})
    assert passed is True
    assert reasons == []


def test_missing_evidence_neutral_still_counts_as_applicable():
    reviews = [
        _review("Fundamentals", "NEUTRAL", 0.7, applicable=True),
        _review("IPO", "NEUTRAL", 0.9, applicable=False),
    ]
    summary = _build_vote_summary(reviews)

    assert summary["applicable_count"] == 1
    assert summary["neutral"] == 1
    assert summary["abstain"] == 1


def test_high_confidence_red_team_opposition_blocks_passage():
    reviews = [
        _review("IPO", "NEUTRAL", 0.99, applicable=False),
        _review("History", "SUPPORT"),
        _review("Fundamentals", "SUPPORT"),
        _review("Macro", "SUPPORT"),
        _review("Market Structure", "SUPPORT"),
        _review("Sentiment", "SUPPORT"),
        _review("Catalyst", "SUPPORT"),
        _review("Red Team", "OPPOSE", 0.9, agent_id=RED_TEAM_AGENT_ID),
    ]
    summary = _build_vote_summary(reviews)

    assert summary["red_team_block"] is True
    passed, reasons = _deterministic_council_gate(summary, {"decision": "PASS_TO_RISK"})
    assert passed is False
    assert any("Red Team" in reason for reason in reasons)
