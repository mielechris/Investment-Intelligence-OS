from datetime import datetime, timezone

from factory.models import AgentDefinition, InterviewInsightPacket, InterviewSession


interviews: dict[str, InterviewSession] = {}
insight_packets: dict[str, InterviewInsightPacket] = {}
agents: dict[str, AgentDefinition] = {}


def save_interview(interview: InterviewSession) -> InterviewSession:
    interview.updated_at = datetime.now(timezone.utc)
    interviews[interview.id] = interview
    return interview


def save_insight_packet(packet: InterviewInsightPacket) -> InterviewInsightPacket:
    insight_packets[packet.interview_id] = packet
    return packet


def save_agent(agent: AgentDefinition) -> AgentDefinition:
    agents[agent.id] = agent
    return agent
