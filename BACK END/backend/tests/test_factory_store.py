from pathlib import Path

from factory.models import AgentDefinition, InterviewInsightPacket, InterviewSession
from factory.store import SQLiteJsonStore


def test_interview_store_survives_reopen(tmp_path: Path):
    database_path = tmp_path / "factory.db"
    store = SQLiteJsonStore(
        table_name="test_interviews",
        model_type=InterviewSession,
        key_field="id",
        database_path=database_path,
    )

    interview = InterviewSession(
        subject_name="Jesse",
        objective="Capture reusable investment decision rules",
        transcript="Watch the operational signal before the headline catches up.",
        status="ready",
    )
    store.save(interview)

    reopened = SQLiteJsonStore(
        table_name="test_interviews",
        model_type=InterviewSession,
        key_field="id",
        database_path=database_path,
    )
    loaded = reopened.get(interview.id)

    assert loaded is not None
    assert loaded.subject_name == "Jesse"
    assert loaded.transcript == interview.transcript
    assert len(reopened) == 1


def test_agent_approval_state_persists(tmp_path: Path):
    database_path = tmp_path / "factory.db"
    store = SQLiteJsonStore(
        table_name="test_agents",
        model_type=AgentDefinition,
        key_field="id",
        database_path=database_path,
    )

    agent = AgentDefinition(
        name="Operational Signal Analyst",
        role="Specialist Analyst",
        mission="Track operational signals before consensus reprices.",
        instructions="Use evidence and state uncertainty.",
    )
    store.save(agent)

    agent.status = "approved"
    store.save(agent)

    reopened = SQLiteJsonStore(
        table_name="test_agents",
        model_type=AgentDefinition,
        key_field="id",
        database_path=database_path,
    )
    loaded = reopened.get(agent.id)

    assert loaded is not None
    assert loaded.status == "approved"
    assert loaded.risk_boundaries == [
        "PAPER_MODE_ONLY",
        "NO_LIVE_EXECUTION",
        "NO_REAL_MONEY_TRADE_RECOMMENDATION",
    ]


def test_insight_packet_round_trip(tmp_path: Path):
    database_path = tmp_path / "factory.db"
    store = SQLiteJsonStore(
        table_name="test_packets",
        model_type=InterviewInsightPacket,
        key_field="interview_id",
        database_path=database_path,
    )

    packet = InterviewInsightPacket(
        interview_id="interview-1",
        subject_name="Jesse",
        summary="Operational signals can lead headline consensus.",
        provenance_note="Derived from a human interview; approval required.",
    )
    store.save(packet)

    loaded = store.get("interview-1")
    assert loaded is not None
    assert loaded.summary == packet.summary
    assert loaded.provenance_note == packet.provenance_note
