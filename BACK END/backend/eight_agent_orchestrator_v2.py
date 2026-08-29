from __future__ import annotations

from typing import Any

import eight_agent_orchestrator as base
from agent_contract_v2 import CONTRACT_VERSION, run_specialist_v2


# The existing orchestration topology, persistence, Committee guard, and safety
# invariants remain authoritative. Only the specialist contract is upgraded.
# This preserves exactly 8 specialist calls + 1 Committee call.
base.run_specialist = run_specialist_v2


def agent_wave_plan() -> dict[str, Any]:
    plan = dict(base.agent_wave_plan())
    plan.update(
        {
            "agent_contract_version": CONTRACT_VERSION,
            "specialist_call_count": 8,
            "committee_call_count": 1,
            "extra_model_calls_added": 0,
            "evidence_linked_reasoning": True,
            "scenario_reasoning": True,
            "cross_desk_questions": True,
            "paper_mode": True,
            "trade_execution_permission": False,
            "live_execution": False,
        }
    )
    return plan


def run_eight_agent_orchestration(case_id: str) -> dict[str, Any]:
    result = base.run_eight_agent_orchestration(case_id)
    # Results already persisted by the base orchestrator contain Contract v2
    # fields because base._run_one resolves base.run_specialist at call time.
    return result
