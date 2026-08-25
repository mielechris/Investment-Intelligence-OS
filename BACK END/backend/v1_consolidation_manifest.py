from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from dynamic_agent_factory import dynamic_agent_plan
from intelligence_safety_manifest import intelligence_safety_manifest
from ipo_monitoring import ipo_monitor_plan
from production_safety_freeze import production_freeze_manifest


router = APIRouter()
RELEASE_NAME = "IIOS V1.0"
RELEASE_STAGE = "RELEASE_CANDIDATE"
INTEGRATION_BRANCH = "integration/iios-v1.0"
GOVERNED_SOURCE_BRANCH = "feature/governed-chain-v1"
GOVERNED_SOURCE_HEAD = "77de36ad0f0eb4967dcd57d34638dcdd2a046c93"
V12_SOURCE_BRANCH = "feature/v1.2-interview-agent-factory"
V12_SOURCE_HEAD = "a29bbbadde193e65699f11ee99348f9083bbad17"
COMMON_BASE = "8b500fccdd204db6543c0b7396e21fc3c260fb97"


def v1_consolidation_manifest() -> dict[str, Any]:
    dynamic = dynamic_agent_plan()
    ipo = ipo_monitor_plan()
    intelligence = intelligence_safety_manifest()
    production = production_freeze_manifest()

    invariants = {
        "governed_chain_is_authoritative_base": True,
        "intelligence_v1_frozen": intelligence.get("intelligence_v1_frozen") is True,
        "production_safety_invariants_pass": production.get("all_invariants_pass") is True,
        "dynamic_agents_require_source_judgment_approval": dynamic.get("human_approval_required_for_source_judgment") is True,
        "dynamic_agents_require_agent_approval": dynamic.get("human_approval_required_for_agent") is True,
        "dynamic_agents_not_committee_quorum": dynamic.get("committee_quorum_member") is False,
        "dynamic_agents_no_capital_or_execution": all(dynamic.get(key) is False for key in ("capital_authority", "position_sizing_permission", "paper_order_permission", "trade_execution_permission", "live_execution")),
        "ipo_monitor_no_automatic_promotion": ipo.get("automatic_promotion") is False,
        "ipo_monitor_no_automatic_agent_run": ipo.get("automatic_agent_run") is False,
        "ipo_monitor_no_execution": all(ipo.get(key) is False for key in ("auto_trade_authority", "paper_order_permission", "trade_execution_permission", "live_execution")),
    }
    ready = all(invariants.values())

    return {
        "release_name": RELEASE_NAME,
        "release_stage": RELEASE_STAGE,
        "integration_branch": INTEGRATION_BRANCH,
        "source_branches": {
            "authoritative_governed_chain": {"branch": GOVERNED_SOURCE_BRANCH, "head_at_consolidation_start": GOVERNED_SOURCE_HEAD},
            "legacy_v1_2_capability_source": {"branch": V12_SOURCE_BRANCH, "head_at_consolidation_start": V12_SOURCE_HEAD},
            "common_base": COMMON_BASE,
        },
        "selected_from_v1_2": [
            {
                "capability": "Interview-derived dynamic research agents",
                "v1_2_source": ["factory/models.py", "factory/router.py", "factory/store.py"],
                "v1_authoritative_module": "dynamic_agent_factory.py",
                "port_strategy": "Reimplemented on governed ledger + approved Judgment Bank; no duplicate interview store",
            },
            {
                "capability": "SEC IPO monitoring",
                "v1_2_source": ["intelligence/providers/sec_ipo.py", "factory/system_agents.py IPO coverage"],
                "v1_authoritative_module": "ipo_monitoring.py",
                "port_strategy": "Reimplemented on hardened provider layer; manual promotion enters standard governed case chain",
            },
        ],
        "superseded_not_imported": [
            "V1.2 council routers and duplicate system-agent council",
            "V1.2 risk_review.py",
            "V1.2 paper_execution.py",
            "V1.2 memory_retrieval/outcome_learning/postmortem paths",
            "V1.2 duplicate interview extraction/storage path",
            "V1.2 .github/workflows/ci.yml",
        ],
        "deferred_post_v1": [
            "V1.2 paper_portfolio.py accounting model — portfolio/accounting phase remains separate",
            "V1.2 continuous background ingestion/dispatcher — 24/7 operations phase remains separate",
            "V1.2 FactoryPanel/CouncilPanel/OperationsPanel UI — governed V1 UI remains authoritative",
            "Dedicated Redis/Postgres worker infrastructure",
        ],
        "legacy_v1_2_ci_defects_not_in_release_surface": [
            {
                "area": "dispatcher test",
                "legacy_failure": "IPO dispatcher test expected exactly 2 routes while V1.2 system agents routed 5",
                "resolution": "Legacy dispatcher not imported; V1 IPO monitor has no automatic agent dispatch",
            },
            {
                "area": "CouncilPanel TypeScript",
                "legacy_failure": "FormEvent needed a type-only import under verbatimModuleSyntax",
                "resolution": "Legacy CouncilPanel not imported; governed V1 frontend remains authoritative",
            },
        ],
        "invariant_checks": invariants,
        "all_invariants_pass": ready,
        "release_candidate_ready": ready,
        "merge_to_main_allowed_after_green_ci": ready,
        "tag_target_after_merge": "IIOS-V1.0",
        "grok_included": False,
        "grok_next_batch": True,
        "paper_mode": True,
        "auto_trade_authority": False,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }


@router.get("/release/v1/consolidation")
def release_v1_consolidation():
    return v1_consolidation_manifest()
