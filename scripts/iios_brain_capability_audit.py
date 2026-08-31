#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = ROOT / "config" / "iios_brain_capability_audit_contract.json"
APP = Path.home() / "Library" / "Application Support" / "IIOS"
DEFAULT_OUTPUT = APP / "brain-audit" / "latest_brain_capability_audit.json"
DEFAULT_BRAIN_LEAGUE = APP / "brain-league" / "latest_brain_capability_league.json"
DEFAULT_SCIENTIFIC = APP / "scientific-measurement" / "latest_scientific_measurement.json"
DEFAULT_MODEL_HEALTH = APP / "model-agent-health" / "latest_model_agent_health.json"

SOURCE_FILES = {
    "grok_provider": ROOT / "BACK END" / "backend" / "grok_provider.py",
    "gemini_provider": ROOT / "BACK END" / "backend" / "gemini_provider.py",
    "gemini_rapid": ROOT / "BACK END" / "backend" / "gemini_rapid_research.py",
    "gemini_deep": ROOT / "BACK END" / "backend" / "high_speed_gemini_deep_worker.py",
    "openai_agent": ROOT / "BACK END" / "backend" / "agent_contract_v2.py",
    "openai_committee": ROOT / "BACK END" / "backend" / "eight_agent_orchestrator.py",
    "runtime_launcher": ROOT / "scripts" / "launch_batch9e_live_paper_factory.py",
}


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    tmp.replace(path)


def _has(text: str, *needles: str) -> bool:
    return all(needle in text for needle in needles)


def _runtime_brain_row(brain_league: dict[str, Any], brain: str) -> dict[str, Any]:
    for row in brain_league.get("brains") or []:
        if isinstance(row, dict) and str(row.get("brain") or "").upper() == brain.upper():
            return row
    return {}


def audit_grok(text: str, runtime: dict[str, Any]) -> dict[str, Any]:
    checks = {
        "grok_4_6_selected": 'DEFAULT_MODEL = "grok-4.6"' in text,
        "responses_api_used": '"/responses"' in text,
        "x_search_enabled": '"type": "x_search"' in text,
        "web_search_enabled": '"type": "web_search"' in text,
        "prompt_cache_key_enabled": "prompt_cache_key" in text,
        "binding_cost_governor": "preflight_xai_request" in text and "record_xai_response" in text,
        "zero_retries": "REQUEST_RETRIES = 0" in text,
        "bounded_tool_calls": "MAX_SERVER_SIDE_TOOL_CALLS = 3" in text,
        "bounded_output_tokens": "MAX_OUTPUT_TOKENS = 2000" in text,
        "explicit_reasoning_effort": "reasoning_effort" in text or '"reasoning"' in text,
        "code_execution_used": '"type": "code_execution"' in text,
    }
    core = [
        "grok_4_6_selected",
        "responses_api_used",
        "x_search_enabled",
        "web_search_enabled",
        "prompt_cache_key_enabled",
        "binding_cost_governor",
        "zero_retries",
    ]
    coverage = round(sum(1 for key in core if checks[key]) / len(core) * 100.0, 1)
    return {
        "brain": "GROK",
        "current_role": "REAL_TIME_WIRE_ROOM",
        "configuration_coverage_pct": coverage,
        "configuration_state": "STRONG_WITH_SHADOW_GAPS" if coverage >= 85 else "PARTIAL",
        "checks": checks,
        "runtime_measurement": runtime,
        "underused_or_unverified": [
            {
                "capability": "EXPLICIT_REASONING_EFFORT",
                "state": "NOT_CONFIGURED" if not checks["explicit_reasoning_effort"] else "CONFIGURED",
                "role_relevance": "HIGH",
                "interpretation": "grok-4.6 supports multiple reasoning levels, but IIOS currently leaves reasoning effort implicit. This is a shadow-test candidate, not proof that current output is weak.",
            },
            {
                "capability": "CODE_EXECUTION",
                "state": "UNUSED" if not checks["code_execution_used"] else "USED",
                "role_relevance": "LOW_TO_MEDIUM",
                "interpretation": "Useful for selected quantitative verification tasks, but not required for the Wire Room's real-time narrative role.",
            },
        ],
        "shadow_experiments": [
            "GROK_REASONING_MEDIUM_VS_HIGH_ON_IDENTICAL_RADAR_PACKETS",
            "GROK_BOUNDED_TOOL_BUDGET_SENSITIVITY_ON_COMPLEX_CATALYSTS",
        ],
    }


def audit_gemini(provider: str, rapid: str, deep: str, launcher: str, runtime: dict[str, Any]) -> dict[str, Any]:
    checks = {
        "flash_3_7_selected": 'DEFAULT_FLASH_MODEL = "gemini-3.7-flash"' in provider,
        "pro_3_1_selected": 'DEFAULT_PRO_MODEL = "gemini-3.1-pro-preview"' in provider,
        "google_search_grounding": '"google_search": {}' in provider,
        "url_context": '"url_context": {}' in provider,
        "structured_outputs": "responseFormat" in provider and "schema" in provider,
        "thinking_levels_supported": "thinkingLevel" in provider,
        "rapid_medium_thinking": '"medium"' in rapid and "DEFAULT_THINKING_LEVEL" in rapid,
        "deep_high_thinking": 'thinking_level="high"' in deep,
        "rapid_fallback_present": "gemini-3.6-flash" in rapid,
        "runtime_timeout_30": '"IIOS_GEMINI_TIMEOUT_SECONDS": "30"' in launcher,
        "runtime_retries_0": '"IIOS_GEMINI_RETRIES": "0"' in launcher,
        "runtime_finalists_6": '"IIOS_9E_GEMINI_FINALISTS": "6"' in launcher,
        "runtime_workers_2": '"IIOS_9E_GEMINI_WORKERS": "2"' in launcher,
        "code_execution_used": "code_execution" in provider or "code_execution" in rapid or "code_execution" in deep,
        "file_search_used": "file_search" in provider or "file_search" in rapid or "file_search" in deep,
    }
    core = [
        "flash_3_7_selected",
        "pro_3_1_selected",
        "google_search_grounding",
        "url_context",
        "structured_outputs",
        "thinking_levels_supported",
        "rapid_medium_thinking",
        "deep_high_thinking",
        "rapid_fallback_present",
        "runtime_timeout_30",
        "runtime_retries_0",
    ]
    coverage = round(sum(1 for key in core if checks[key]) / len(core) * 100.0, 1)
    return {
        "brain": "GEMINI",
        "current_role": "GROUNDED_RAPID_RESEARCH_PLUS_SELECTIVE_DEEP_EVIDENCE",
        "configuration_coverage_pct": coverage,
        "configuration_state": "STRONG" if coverage >= 90 else "PARTIAL",
        "checks": checks,
        "runtime_measurement": runtime,
        "underused_or_unverified": [
            {
                "capability": "ADAPTIVE_THINKING_BY_CASE_COMPLEXITY",
                "state": "PARTIAL",
                "role_relevance": "HIGH",
                "interpretation": "Flash is fixed at medium and Pro at high. IIOS is not yet shadow-testing whether selected high-complexity Flash finalists benefit enough from high thinking to justify added latency/cost.",
            },
            {
                "capability": "CODE_EXECUTION",
                "state": "UNUSED" if not checks["code_execution_used"] else "USED",
                "role_relevance": "MEDIUM",
                "interpretation": "Potentially useful for selected quantitative cross-checks, but it should remain outside the fast radar critical path until measured.",
            },
            {
                "capability": "FILE_SEARCH",
                "state": "UNUSED" if not checks["file_search_used"] else "USED",
                "role_relevance": "MEDIUM",
                "interpretation": "Potentially useful for governed filing/document corpora. Current Google Search + URL Context coverage is already strong for web-grounded research.",
            },
        ],
        "shadow_experiments": [
            "GEMINI_FLASH_MEDIUM_VS_HIGH_ON_HIGH_COMPLEXITY_FINALISTS",
            "GEMINI_PRO_INCREMENTAL_VALUE_VS_FLASH_ON_IDENTICAL_EVIDENCE_GAPS",
            "GEMINI_FILE_OR_CODE_TOOL_VALUE_ON_SELECTED_QUANTITATIVE_CASES",
        ],
    }


def audit_openai(agent: str, committee: str, runtime: dict[str, Any]) -> dict[str, Any]:
    checks = {
        "specialists_use_gpt_5_6_luna": 'MODEL = "gpt-5.6-luna"' in agent,
        "committee_uses_gpt_5_6_luna": 'model="gpt-5.6-luna"' in committee,
        "responses_api_used": ".responses.create(" in agent and ".responses.create(" in committee,
        "exact_eight_plus_one_topology": "FIRST_WAVE" in committee and "SECOND_WAVE" in committee and "_synthesize_committee" in committee,
        "evidence_only_specialist_contract": "Use only evidence supplied in this packet" in agent,
        "explicit_reasoning_effort_specialists": "reasoning_effort" in agent or "reasoning=" in agent,
        "explicit_reasoning_effort_committee": "reasoning_effort" in committee or "reasoning=" in committee,
        "specialist_tools_enabled": 'tools=' in agent or '"tools"' in agent,
        "committee_tools_enabled": 'tools=' in committee or '"tools"' in committee,
        "different_model_for_committee": not ('MODEL = "gpt-5.6-luna"' in agent and 'model="gpt-5.6-luna"' in committee),
    }
    core = [
        "specialists_use_gpt_5_6_luna",
        "committee_uses_gpt_5_6_luna",
        "responses_api_used",
        "exact_eight_plus_one_topology",
        "evidence_only_specialist_contract",
    ]
    coverage = round(sum(1 for key in core if checks[key]) / len(core) * 100.0, 1)
    return {
        "brain": "OPENAI",
        "current_role": "EIGHT_GOVERNED_SPECIALIST_DESKS_PLUS_COMMITTEE_SYNTHESIS",
        "configuration_coverage_pct": coverage,
        "configuration_state": "FUNCTIONAL_CAPACITY_NOT_YET_PROVEN",
        "checks": checks,
        "runtime_measurement": runtime,
        "underused_or_unverified": [
            {
                "capability": "MODEL_TIER_SPECIALIZATION",
                "state": "NOT_USED",
                "role_relevance": "VERY_HIGH",
                "interpretation": "All eight desks and the Committee use Luna. OpenAI documents Luna for cost-sensitive high-volume work, Terra as intelligence/cost balance, and Sol for complex professional work. The Committee and Skeptic are strong candidates for shadow model-tier tests.",
            },
            {
                "capability": "EXPLICIT_REASONING_EFFORT",
                "state": "NOT_CONFIGURED",
                "role_relevance": "VERY_HIGH",
                "interpretation": "The code does not explicitly choose reasoning effort for specialist or Committee calls. GPT-5.6 supports multiple reasoning levels, so reasoning-effort selection should be tested by task in shadow.",
            },
            {
                "capability": "WEB_OR_FILE_TOOLS_ON_AGENT_FLOOR",
                "state": "INTENTIONALLY_DISABLED",
                "role_relevance": "LOW_FOR_CURRENT_CONTRACT",
                "interpretation": "This is not currently a defect: Agent Contract v2 deliberately restricts desks to the governed evidence packet. Any tool-enabled OpenAI research lane should be a separate evidence-acquisition experiment, not a silent change to the governed desks.",
            },
        ],
        "shadow_experiments": [
            "COMMITTEE_LUNA_VS_TERRA_VS_SOL_SAME_CASE_PACKET",
            "COMMITTEE_REASONING_MEDIUM_HIGH_XHIGH_SAME_PACKET",
            "SKEPTIC_LUNA_VS_TERRA_OR_SOL_SAME_PEER_CONTEXT",
            "SELECTIVE_STRONG_MODEL_FOR_SKEPTIC_AND_COMMITTEE_ONLY",
        ],
    }


def combination_designs() -> list[dict[str, Any]]:
    return [
        {
            "experiment": "CURRENT_SPECIALIZED_STACK_BASELINE",
            "sequence": ["GROK real-time discovery", "GEMINI grounded verification", "OPENAI governed desks + Committee"],
            "purpose": "Measure the existing specialization before changing anything.",
        },
        {
            "experiment": "SEQUENTIAL_WIRE_BOOKS_COMMITTEE",
            "sequence": ["GROK discovery", "GEMINI verifies/contradicts", "OPENAI synthesizes"],
            "purpose": "Test whether explicit handoffs improve evidence quality and decision clarity.",
        },
        {
            "experiment": "PARALLEL_GROK_GEMINI_OPENAI_ARBITER",
            "sequence": ["GROK + GEMINI independently in parallel", "OPENAI contradiction arbitration"],
            "purpose": "Measure recall and contradiction-detection gains against added latency and cost.",
        },
        {
            "experiment": "OPENAI_ONLY_CONTROL",
            "sequence": ["OpenAI governed control path"],
            "purpose": "Prevent IIOS from assuming multi-model complexity adds value.",
        },
        {
            "experiment": "GEMINI_ONLY_RESEARCH_CONTROL",
            "sequence": ["Gemini grounded research control"],
            "purpose": "Measure whether search-grounded Gemini alone covers enough research value in selected tasks.",
        },
        {
            "experiment": "GROK_ONLY_DISCOVERY_CONTROL",
            "sequence": ["Grok real-time discovery control"],
            "purpose": "Measure incremental discovery value before downstream verification/synthesis.",
        },
    ]


def build_audit(contract: dict[str, Any], brain_league: dict[str, Any], scientific: dict[str, Any], model_health: dict[str, Any]) -> dict[str, Any]:
    source = {key: _read_text(path) for key, path in SOURCE_FILES.items()}
    grok = audit_grok(source["grok_provider"], _runtime_brain_row(brain_league, "GROK"))
    gemini = audit_gemini(
        source["gemini_provider"],
        source["gemini_rapid"],
        source["gemini_deep"],
        source["runtime_launcher"],
        _runtime_brain_row(brain_league, "GEMINI"),
    )
    openai = audit_openai(source["openai_agent"], source["openai_committee"], _runtime_brain_row(brain_league, "OPENAI"))

    league = scientific.get("model_task_league") if isinstance(scientific.get("model_task_league"), dict) else {}
    task_rows = [row for row in league.get("task_rows") or [] if isinstance(row, dict)]
    exact_outcome_linkage_available = any(row.get("accuracy_score") is not None for row in task_rows)

    recommendations = [
        {
            "priority": 1,
            "code": "OPENAI_COMMITTEE_MODEL_TIER_SHADOW",
            "action": "Replay identical completed case packets through Luna, Terra, and Sol Committee variants in shadow and compare decision quality, dissent preservation, evidence-gap usefulness, latency, and exact cost.",
            "production_change": false,
        },
        {
            "priority": 2,
            "code": "OPENAI_REASONING_EFFORT_SHADOW",
            "action": "Test explicit reasoning levels on Committee and Skeptic before changing the eight high-volume desks.",
            "production_change": false,
        },
        {
            "priority": 3,
            "code": "GROK_REASONING_EFFORT_SHADOW",
            "action": "Run bounded medium/high reasoning comparisons on identical complex radar packets with X Search and Web Search unchanged.",
            "production_change": false,
        },
        {
            "priority": 4,
            "code": "GEMINI_COMPLEXITY_ADAPTIVE_THINKING_SHADOW",
            "action": "Compare medium versus high Flash thinking only on high-complexity finalists; retain Pro for evidence-gap-driven deep work.",
            "production_change": false,
        },
        {
            "priority": 5,
            "code": "MULTI_MODEL_COMBINATION_BAKEOFF",
            "action": "Run specialized sequential, parallel-arbiter, and single-model controls on the same historical/live shadow cases.",
            "production_change": false,
        },
        {
            "priority": 6,
            "code": "PERSIST_EXACT_MODEL_TASK_OUTCOME_LINKAGE",
            "action": "Do not declare a winner until model/task outputs can be linked to later benchmark and case outcomes.",
            "production_change": false,
        },
    ]

    return {
        "schema_version": "batch10m4-brain-capability-audit-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "BRAIN_CAPABILITY_AUDIT_COMPLETE_READ_ONLY",
        "provider_docs_verified_on": contract.get("verified_on"),
        "provider_capability_snapshot": contract.get("provider_capability_snapshot") or {},
        "audit_order": contract.get("audit_order") or [],
        "brains": [grok, gemini, openai],
        "model_combinations": combination_designs(),
        "ranked_recommendations": recommendations,
        "runtime_evidence": {
            "brain_league_status": brain_league.get("status"),
            "routing_state": brain_league.get("routing_state"),
            "scientific_model_league_status": league.get("status"),
            "model_agent_health_status": model_health.get("overall_state") or model_health.get("status"),
            "exact_task_outcome_linkage_available": exact_outcome_linkage_available,
        },
        "decision": {
            "production_routing_state": "HOLD_CURRENT_ROUTING_COLLECT_EVIDENCE",
            "why": "Configuration/capability gaps can be audited now, but task-level superiority must be proven with exact outcome linkage and shadow comparison.",
            "auto_apply": false,
        },
        "truth_rules": contract.get("truth_rules") or {},
        "safety": contract.get("safety") or {},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="IIOS Batch 10M.4 read-only Grok/Gemini/OpenAI capability audit")
    parser.add_argument("--contract", default=str(DEFAULT_CONTRACT))
    parser.add_argument("--brain-league", default=str(DEFAULT_BRAIN_LEAGUE))
    parser.add_argument("--scientific", default=str(DEFAULT_SCIENTIFIC))
    parser.add_argument("--model-health", default=str(DEFAULT_MODEL_HEALTH))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--stdout", action="store_true")
    args = parser.parse_args()

    contract = _read_json(Path(args.contract).expanduser())
    if not contract:
        raise SystemExit("Brain capability audit contract is missing or invalid")
    audit = build_audit(
        contract,
        _read_json(Path(args.brain_league).expanduser()),
        _read_json(Path(args.scientific).expanduser()),
        _read_json(Path(args.model_health).expanduser()),
    )
    output = Path(args.output).expanduser()
    _write_json(output, audit)
    if args.stdout:
        print(json.dumps(audit, indent=2, sort_keys=True, default=str))
    else:
        print(json.dumps({
            "status": audit["status"],
            "output": str(output),
            "routing_state": audit["decision"]["production_routing_state"],
            "provider_calls_made": False,
            "live_execution": False,
        }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
