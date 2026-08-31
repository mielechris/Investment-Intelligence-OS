#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

import iios_brain_capability_audit as audit

ROOT = Path(__file__).resolve().parents[1]


def text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_contract_safety() -> None:
    contract = json.loads((ROOT / "config/iios_brain_capability_audit_contract.json").read_text(encoding="utf-8"))
    assert contract["verified_on"] == "2026-08-31"
    assert contract["provider_capability_snapshot"]["GROK"]["model"] == "grok-4.6"
    assert contract["provider_capability_snapshot"]["GEMINI_FLASH"]["model"] == "gemini-3.7-flash"
    assert contract["provider_capability_snapshot"]["OPENAI_SOL"]["model"] == "gpt-5.6-sol"
    assert contract["truth_rules"]["no_production_routing_change_without_outcome_linkage"] is True
    assert contract["safety"]["provider_calls_from_audit"] is False
    assert contract["safety"]["model_routing_auto_change"] is False
    assert contract["safety"]["trade_execution_permission"] is False
    assert contract["safety"]["live_execution"] is False


def test_grok_current_configuration() -> None:
    result = audit.audit_grok(text("BACK END/backend/grok_provider.py"), {})
    checks = result["checks"]
    assert checks["grok_4_6_selected"] is True
    assert checks["responses_api_used"] is True
    assert checks["x_search_enabled"] is True
    assert checks["web_search_enabled"] is True
    assert checks["prompt_cache_key_enabled"] is True
    assert checks["binding_cost_governor"] is True
    assert checks["zero_retries"] is True
    assert checks["explicit_reasoning_effort"] is False
    assert result["configuration_state"] == "STRONG_WITH_SHADOW_GAPS"


def test_gemini_current_configuration() -> None:
    result = audit.audit_gemini(
        text("BACK END/backend/gemini_provider.py"),
        text("BACK END/backend/gemini_rapid_research.py"),
        text("BACK END/backend/high_speed_gemini_deep_worker.py"),
        text("scripts/launch_batch9e_live_paper_factory.py"),
        {},
    )
    checks = result["checks"]
    assert checks["flash_3_7_selected"] is True
    assert checks["pro_3_1_selected"] is True
    assert checks["google_search_grounding"] is True
    assert checks["url_context"] is True
    assert checks["structured_outputs"] is True
    assert checks["rapid_medium_thinking"] is True
    assert checks["deep_high_thinking"] is True
    assert checks["runtime_timeout_30"] is True
    assert checks["runtime_retries_0"] is True
    assert result["configuration_state"] == "STRONG"


def test_openai_capacity_gaps_are_truthful() -> None:
    result = audit.audit_openai(
        text("BACK END/backend/agent_contract_v2.py"),
        text("BACK END/backend/eight_agent_orchestrator.py"),
        {},
    )
    checks = result["checks"]
    assert checks["specialists_use_gpt_5_6_luna"] is True
    assert checks["committee_uses_gpt_5_6_luna"] is True
    assert checks["responses_api_used"] is True
    assert checks["exact_eight_plus_one_topology"] is True
    assert checks["evidence_only_specialist_contract"] is True
    assert checks["explicit_reasoning_effort_specialists"] is False
    assert checks["explicit_reasoning_effort_committee"] is False
    assert checks["different_model_for_committee"] is False
    assert result["configuration_state"] == "FUNCTIONAL_CAPACITY_NOT_YET_PROVEN"


def test_build_audit_never_auto_routes() -> None:
    contract = json.loads((ROOT / "config/iios_brain_capability_audit_contract.json").read_text(encoding="utf-8"))
    result = audit.build_audit(contract, {}, {}, {})
    assert result["status"] == "BRAIN_CAPABILITY_AUDIT_COMPLETE_READ_ONLY"
    assert result["decision"]["production_routing_state"] == "HOLD_CURRENT_ROUTING_COLLECT_EVIDENCE"
    assert result["decision"]["auto_apply"] is False
    assert result["runtime_evidence"]["exact_task_outcome_linkage_available"] is False
    assert len(result["model_combinations"]) >= 6
    assert result["ranked_recommendations"][0]["code"] == "OPENAI_COMMITTEE_MODEL_TIER_SHADOW"
    assert all(row["production_change"] is False for row in result["ranked_recommendations"])
    assert result["safety"]["provider_calls_from_audit"] is False
    assert result["safety"]["live_execution"] is False


def main() -> int:
    test_contract_safety()
    test_grok_current_configuration()
    test_gemini_current_configuration()
    test_openai_capacity_gaps_are_truthful()
    test_build_audit_never_auto_routes()
    print("Batch 10M.4 brain capability audit: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
