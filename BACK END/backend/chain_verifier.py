from collections import Counter
from typing import Any


EXPECTED_AGENT_KEYS = {
    "policy",
    "macro",
    "fundamentals",
    "market_structure",
    "commodities",
    "geo_weather",
    "skeptic",
    "portfolio",
}

REQUIRED_SINGLE_EVENTS = {
    "CASE_CREATED",
    "EVIDENCE_NORMALIZED",
    "COMMITTEE_COMPLETE",
    "RISK_COMPLETE",
    "PAPER_EXECUTION_CHECKED",
}


def _error(errors: list[str], condition: bool, message: str) -> None:
    if not condition:
        errors.append(message)


def verify_audit(audit: dict[str, Any]) -> dict[str, Any]:
    """Verify the persisted IIOS case lineage and paper-mode safety invariants."""
    errors: list[str] = []
    warnings: list[str] = []

    case = audit.get("case") or {}
    packets = audit.get("evidence_packets") or []
    agents = audit.get("agent_results") or []
    decisions = audit.get("committee_decisions") or []
    risks = audit.get("risk_authorizations") or []
    executions = audit.get("executions") or []
    events = audit.get("events") or []

    case_id = str(case.get("case_id") or "")
    _error(errors, bool(case_id), "Missing case_id")
    _error(errors, case.get("paper_mode") is True, "Case is not locked to paper mode")

    _error(errors, len(packets) == 1, f"Expected 1 evidence packet, found {len(packets)}")
    if packets:
        packet = packets[0]
        _error(errors, packet.get("case_id") == case_id, "Evidence packet case_id mismatch")
        _error(
            errors,
            packet.get("evidence_packet_id") == case.get("evidence_packet_id"),
            "Evidence packet ID does not match case",
        )

    _error(errors, len(agents) == 8, f"Expected 8 agent results, found {len(agents)}")
    agent_keys = {str(agent.get("agent_key")) for agent in agents}
    missing_agents = sorted(EXPECTED_AGENT_KEYS - agent_keys)
    extra_agents = sorted(agent_keys - EXPECTED_AGENT_KEYS)
    _error(errors, not missing_agents, f"Missing specialist agents: {missing_agents}")
    _error(errors, not extra_agents, f"Unexpected specialist agents: {extra_agents}")
    for agent in agents:
        _error(errors, agent.get("case_id") == case_id, f"Agent {agent.get('agent_key')} case_id mismatch")
        _error(errors, bool(agent.get("agent_result_id")), f"Agent {agent.get('agent_key')} missing result ID")
        _error(errors, bool(agent.get("falsifier")), f"Agent {agent.get('agent_key')} missing falsifier")
        _error(errors, isinstance(agent.get("missing_evidence"), list), f"Agent {agent.get('agent_key')} missing evidence list")

    _error(errors, len(decisions) == 1, f"Expected 1 committee decision, found {len(decisions)}")
    decision = decisions[0] if decisions else {}
    if decision:
        _error(errors, decision.get("case_id") == case_id, "Committee decision case_id mismatch")
        _error(errors, str(decision.get("decision_id", "")).startswith("decision_"), "Invalid committee decision_id")
        _error(errors, len(decision.get("agents") or {}) == 8, "Committee packet does not contain 8 agents")
        _error(errors, decision.get("paper_mode") is True, "Committee decision is not paper mode")

    _error(errors, len(risks) == 1, f"Expected 1 risk authorization, found {len(risks)}")
    risk = risks[0] if risks else {}
    if risk:
        _error(errors, risk.get("case_id") == case_id, "Risk authorization case_id mismatch")
        _error(errors, risk.get("decision_id") == decision.get("decision_id"), "Risk decision_id lineage mismatch")
        _error(errors, str(risk.get("risk_authorization_id", "")).startswith("risk_"), "Invalid risk_authorization_id")
        _error(errors, float(risk.get("allowed_notional", 0) or 0) == 0.0, "v0.3/v0.4 risk authorized non-zero notional")
        _error(errors, risk.get("paper_mode") is True, "Risk authorization is not paper mode")
        if risk.get("decision") == "APPROVED":
            warnings.append("Risk returned APPROVED; current guarded prototype normally returns VETOED or WATCH_ONLY")

    _error(errors, len(executions) == 1, f"Expected 1 execution record, found {len(executions)}")
    execution = executions[0] if executions else {}
    if execution:
        _error(errors, execution.get("case_id") == case_id, "Execution case_id mismatch")
        _error(errors, execution.get("decision_id") == decision.get("decision_id"), "Execution decision_id lineage mismatch")
        _error(
            errors,
            execution.get("risk_authorization_id") == risk.get("risk_authorization_id"),
            "Execution risk authorization lineage mismatch",
        )
        _error(errors, execution.get("paper_mode") is True, "Execution is not paper mode")
        _error(errors, execution.get("live_execution") is False, "Live execution flag must be false")
        _error(errors, execution.get("execution") == "NOT_SUBMITTED", "Guarded prototype unexpectedly created an order")

    event_counts = Counter(str(event.get("event_type")) for event in events)
    for event_type in REQUIRED_SINGLE_EVENTS:
        _error(errors, event_counts[event_type] == 1, f"Expected 1 {event_type} event, found {event_counts[event_type]}")
    _error(errors, event_counts["AGENT_COMPLETE"] == 8, f"Expected 8 AGENT_COMPLETE events, found {event_counts['AGENT_COMPLETE']}")

    expected_order = [
        "CASE_CREATED",
        "EVIDENCE_NORMALIZED",
        "AGENT_COMPLETE",
        "COMMITTEE_COMPLETE",
        "RISK_COMPLETE",
        "PAPER_EXECUTION_CHECKED",
    ]
    compact: list[str] = []
    for event in events:
        event_type = str(event.get("event_type"))
        if event_type == "AGENT_COMPLETE":
            if not compact or compact[-1] != "AGENT_COMPLETE":
                compact.append(event_type)
        elif event_type in REQUIRED_SINGLE_EVENTS:
            compact.append(event_type)
    _error(errors, compact == expected_order, f"Audit event order mismatch: {compact}")

    return {
        "passed": not errors,
        "case_id": case_id,
        "errors": errors,
        "warnings": warnings,
        "counts": {
            "evidence_packets": len(packets),
            "agent_results": len(agents),
            "committee_decisions": len(decisions),
            "risk_authorizations": len(risks),
            "executions": len(executions),
            "events": len(events),
        },
        "lineage": {
            "case_id": case_id or None,
            "evidence_packet_id": case.get("evidence_packet_id"),
            "decision_id": decision.get("decision_id"),
            "risk_authorization_id": risk.get("risk_authorization_id"),
            "execution_id": execution.get("execution_id"),
        },
    }
