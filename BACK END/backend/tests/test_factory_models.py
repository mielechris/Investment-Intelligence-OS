from factory.models import AgentDefinition, InterviewInsight, InterviewInsightPacket, InterviewSession


def test_interview_session_defaults_to_draft():
    interview = InterviewSession(
        subject_name="Jesse",
        objective="Capture reusable investment intelligence",
    )
    assert interview.status == "draft"
    assert interview.transcript == ""


def test_insight_packet_preserves_provenance():
    interview = InterviewSession(
        subject_name="Jesse",
        objective="Capture reusable investment intelligence",
    )
    packet = InterviewInsightPacket(
        interview_id=interview.id,
        subject_name=interview.subject_name,
        summary="Interview summary",
        insights=[
            InterviewInsight(
                claim="Track a specific operational signal before acting.",
                category="decision_rule",
                confidence=0.8,
            )
        ],
        provenance_note="Derived from interview; human approval required.",
    )
    assert packet.interview_id == interview.id
    assert packet.insights[0].category == "decision_rule"


def test_agent_is_proposed_and_paper_safe_by_default():
    agent = AgentDefinition(
        name="Specialist",
        role="Sector Analyst",
        mission="Analyze a narrow sector signal.",
        instructions="Use evidence and state uncertainty.",
    )
    assert agent.status == "proposed"
    assert "PAPER_MODE_ONLY" in agent.risk_boundaries
    assert "NO_LIVE_EXECUTION" in agent.risk_boundaries
