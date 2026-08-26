from __future__ import annotations

from typing import Any, Callable

from fastapi import APIRouter, HTTPException

import grok_provider
import kimi_provider
from batch8c_production_inputs import production_source_status
from factory_room_api import factory_room_status
from ledger import get_object, latest_object, utc_now
from main import AGENT_CONFIGS
from model_scale_validation import TASK_TYPES, status as calibration_status
from multi_model_intelligence_council import COUNCIL_TYPE, status as council_status


router = APIRouter()

UI_VERSION = "BATCH_8G_FACTORY_INTELLIGENCE_UI_V1"
SYSTEM_VERSION = "0.20.0"

PIPELINE = (
    {
        "id": "8D",
        "name": "Kimi Research & Swarm Intelligence",
        "status": "COMPLETE",
        "version": "0.17.0",
        "room": "RESEARCH_ANNEX",
    },
    {
        "id": "8E",
        "name": "Multi-Model Intelligence Council",
        "status": "COMPLETE",
        "version": "0.18.0",
        "room": "COMMITTEE_ROOM",
    },
    {
        "id": "8F",
        "name": "Scale Validation & Task Calibration",
        "status": "COMPLETE",
        "version": "0.19.0",
        "room": "CALIBRATION_LAB",
    },
    {
        "id": "8G",
        "name": "Factory Intelligence UI",
        "status": "COMPLETE",
        "version": SYSTEM_VERSION,
        "room": "CONTROL_ROOM",
    },
)

AUTHORITY_LOCK = {
    "read_only": True,
    "context_only": True,
    "qualification_evidence": False,
    "gap_resolution_eligible": False,
    "fact_resolution_authority": False,
    "committee_override": False,
    "risk_override": False,
    "capital_authority": False,
    "trade_signal": False,
    "auto_trade_authority": False,
    "paper_order_permission": False,
    "trade_execution_permission": False,
    "live_execution": False,
}


def _safe(
    label: str,
    function: Callable[[], dict[str, Any]],
) -> dict[str, Any]:
    try:
        value = function()
    except Exception as exc:
        return {
            "availability": "OFFLINE",
            "source": label,
            "error_type": type(exc).__name__,
            "data": None,
        }
    if not isinstance(value, dict):
        return {
            "availability": "UNKNOWN",
            "source": label,
            "error_type": "NON_OBJECT_RESPONSE",
            "data": None,
        }
    return {
        "availability": "AVAILABLE",
        "source": label,
        "error_type": None,
        "data": value,
    }


def _source_data(
    source: dict[str, Any],
) -> dict[str, Any]:
    value = source.get("data")
    return value if isinstance(value, dict) else {}


def _availability(
    *,
    installed: bool = True,
    configured: bool | None = None,
    observation_status: str | None = None,
) -> str:
    if not installed:
        return "UNAVAILABLE"
    if configured is False:
        return "PROVIDER_PENDING"
    if observation_status == "AVAILABLE":
        return "READY"
    if configured is True:
        return "CONFIGURED_NO_OBSERVATION"
    return "INSTALLED_NO_OBSERVATION"


def _view_map(
    latest_packet: dict[str, Any] | None,
) -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    packet = latest_packet if isinstance(latest_packet, dict) else {}
    for row in packet.get("views") or []:
        if not isinstance(row, dict):
            continue
        model = str(row.get("model") or "").strip().upper()
        if model:
            output[model] = row
    return output


def _model_card(
    *,
    model_id: str,
    label: str,
    role: str,
    provider: str,
    configured: bool | None,
    provider_status: dict[str, Any],
    view: dict[str, Any] | None,
) -> dict[str, Any]:
    view = view if isinstance(view, dict) else {}
    observation_status = str(
        view.get("status") or "NO_OBSERVATION"
    ).upper()
    return {
        "id": model_id,
        "label": label,
        "role": role,
        "provider": provider,
        "availability": _availability(
            configured=configured,
            observation_status=observation_status,
        ),
        "configured": configured,
        "observation_status": observation_status,
        "stance": str(view.get("stance") or "UNKNOWN").upper(),
        "confidence": view.get("confidence"),
        "citation_count": int(view.get("citation_count") or 0),
        "summary": (
            str(view.get("summary") or "").strip()
            or "No model observation has been recorded."
        )[:1200],
        "provider_model": (
            view.get("provider_model")
            or provider_status.get("model_preference")
        ),
        "credential_present": (
            provider_status.get("credential_present")
            if configured is not None
            else None
        ),
        "credential_exposed": False,
        "latency_ms": view.get("latency_ms"),
        "untrusted_model_output": (
            view.get("untrusted_model_output") is True
        ),
        **AUTHORITY_LOCK,
    }


def _calibration_matrix(
    calibration: dict[str, Any],
) -> dict[str, Any]:
    latest = calibration.get("latest_calibration")
    latest = latest if isinstance(latest, dict) else {}
    tasks = latest.get("tasks")
    tasks = tasks if isinstance(tasks, dict) else {}
    rows = []
    for task_type in sorted(TASK_TYPES):
        task = tasks.get(task_type)
        task = task if isinstance(task, dict) else {}
        recommendations = task.get("model_recommendations")
        recommendations = (
            recommendations
            if isinstance(recommendations, dict)
            else {}
        )
        models = []
        for model_id in sorted(
            {
                "IIOS_OPENAI_CORE",
                "KIMI_RESEARCH",
                "GROK_NARRATIVE",
                *recommendations.keys(),
            }
        ):
            recommendation = recommendations.get(model_id)
            recommendation = (
                recommendation
                if isinstance(recommendation, dict)
                else {}
            )
            models.append(
                {
                    "model": model_id,
                    "sample_count": (
                        recommendation.get("sample_count")
                        if recommendation
                        else 0
                    ),
                    "mature": (
                        recommendation.get("mature") is True
                    ),
                    "quality_score": (
                        recommendation.get("quality_score")
                    ),
                    "composite_score": (
                        recommendation.get("composite_score")
                    ),
                    "recommended_task_weight": (
                        recommendation.get(
                            "recommended_task_weight"
                        )
                        if recommendation
                        else None
                    ),
                    "recommendation_active": (
                        recommendation.get(
                            "recommendation_active"
                        )
                        is True
                    ),
                    "manual_review_required": True,
                    "automatically_applied_to_council": False,
                }
            )
        rows.append(
            {
                "task_type": task_type,
                "status": (
                    task.get("status")
                    or "NO_CALIBRATION_AVAILABLE"
                ),
                "mature_model_count": int(
                    task.get("mature_model_count") or 0
                ),
                "minimum_mature_models_required": int(
                    task.get(
                        "minimum_mature_models_required"
                    )
                    or calibration.get(
                        "minimum_mature_models_per_task"
                    )
                    or 2
                ),
                "models": models,
                "manual_promotion_required": True,
                "automatically_applied_to_council": False,
            }
        )
    return {
        "availability": (
            "AVAILABLE" if latest else "NO_CALIBRATION_AVAILABLE"
        ),
        "calibration_version": calibration.get(
            "calibration_version"
        ),
        "evaluation_count": int(
            calibration.get("evaluation_count") or 0
        ),
        "minimum_samples_per_model_task": int(
            calibration.get(
                "minimum_samples_per_model_task"
            )
            or 5
        ),
        "weight_bounds": (
            calibration.get("recommended_weight_bounds")
            or {"minimum": 0.75, "maximum": 1.25}
        ),
        "model_weighting_mode": (
            "TASK_SPECIFIC_RECOMMENDATIONS_ONLY"
        ),
        "universal_model_weighting": False,
        "manual_promotion_required": True,
        "automatically_applied_to_council": False,
        "tasks": rows,
        **AUTHORITY_LOCK,
    }


def _provider_gate(
    key: str,
    label: str,
    ready: bool,
    detail: str,
) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "status": "READY" if ready else "PENDING",
        "ready": ready,
        "detail": detail,
        "blocks_read_only_ui": False,
        "blocks_live_execution": True,
    }


def _production_gates(
    production: dict[str, Any],
    kimi: dict[str, Any],
    grok: dict[str, Any],
) -> list[dict[str, Any]]:
    fed = production.get("cme_fedwatch")
    fed = fed if isinstance(fed, dict) else {}
    strict_ready = (
        production.get("strict_universe_verified") is True
    )
    fed_ready = (
        fed.get("latest_snapshot_source_verified") is True
    )
    return [
        _provider_gate(
            "STRICT_INDEX_UNIVERSE",
            "Strict S&P 500 + Nasdaq-100 universe",
            strict_ready,
            (
                "Verified governed universe available."
                if strict_ready
                else "No fresh verified production universe."
            ),
        ),
        _provider_gate(
            "FED_PROBABILITY_FEED",
            "Governed Fed probability feed",
            fed_ready,
            (
                "Latest probability snapshot is source-verified."
                if fed_ready
                else "Verified Fed probability snapshot pending."
            ),
        ),
        _provider_gate(
            "KIMI_LIVE_PROVIDER",
            "Kimi live research provider",
            kimi.get("configured") is True,
            (
                "Credential present; live research is config-enabled."
                if kimi.get("configured") is True
                else "Credential or provider entitlement pending."
            ),
        ),
        _provider_gate(
            "GROK_LIVE_PROVIDER",
            "Grok X + web narrative provider",
            grok.get("configured") is True,
            (
                "Credential present; X and web search are config-enabled."
                if grok.get("configured") is True
                else "Credential or provider entitlement pending."
            ),
        ),
    ]


def _desk_rows(
    activity: dict[str, Any],
) -> list[dict[str, Any]]:
    recent_events = activity.get("recent_events")
    recent_events = (
        recent_events if isinstance(recent_events, list) else []
    )
    completions: dict[str, int] = {}
    for event in recent_events:
        if not isinstance(event, dict):
            continue
        payload = event.get("payload")
        payload = payload if isinstance(payload, dict) else {}
        key = str(payload.get("agent_key") or "").strip()
        if key:
            completions[key] = completions.get(key, 0) + 1
    return [
        {
            "key": key,
            "name": config["name"],
            "room": config["room"],
            "focus": config["focus"],
            "status": (
                "ACTIVE"
                if completions.get(key, 0) > 0
                else "IDLE"
            ),
            "recent_completions": completions.get(key, 0),
            "decision_authority": False,
            "capital_authority": False,
            "trade_execution_permission": False,
        }
        for key, config in AGENT_CONFIGS.items()
    ]


def _normalize_cases(
    factory: dict[str, Any],
) -> list[dict[str, Any]]:
    output = []
    for row in factory.get("cases") or []:
        if not isinstance(row, dict):
            continue
        output.append(
            {
                "case_id": row.get("case_id"),
                "ticker": row.get("ticker"),
                "topic": row.get("topic"),
                "stage": row.get("stage") or "UNKNOWN",
                "active_room": (
                    row.get("active_room") or "NONE"
                ),
                "latest_event": row.get("latest_event"),
                "latest_event_at": row.get(
                    "latest_event_at"
                ),
                "agent_count": int(
                    row.get("agent_count") or 0
                ),
                "committee": (
                    row.get("committee") or "UNKNOWN"
                ),
                "committee_confidence": row.get(
                    "committee_confidence"
                ),
                "risk": row.get("risk") or "UNKNOWN",
                "qualified": row.get("qualified") is True,
                "capital": (
                    row.get("capital") or "NOT_STARTED"
                ),
                "sizing": (
                    row.get("sizing") or "NOT_STARTED"
                ),
                "authorization": (
                    row.get("authorization") or "LOCKED"
                ),
                "paper_execution": (
                    row.get("paper_execution")
                    or "NOT_EXECUTED"
                ),
                "trade_execution_permission": False,
                "live_execution": False,
            }
        )
    return output


def build_overview() -> dict[str, Any]:
    sources = {
        "factory": _safe(
            "factory-room",
            factory_room_status,
        ),
        "council": _safe(
            "multi-model-council",
            council_status,
        ),
        "calibration": _safe(
            "model-calibration",
            calibration_status,
        ),
        "production": _safe(
            "production-inputs",
            production_source_status,
        ),
        "kimi": _safe(
            "kimi-provider",
            kimi_provider.configuration_status,
        ),
        "grok": _safe(
            "grok-provider",
            grok_provider.configuration_status,
        ),
    }

    factory = _source_data(sources["factory"])
    council = _source_data(sources["council"])
    calibration = _source_data(sources["calibration"])
    production = _source_data(sources["production"])
    kimi = _source_data(sources["kimi"])
    grok = _source_data(sources["grok"])

    latest_packet = council.get("latest_packet")
    latest_packet = (
        latest_packet
        if isinstance(latest_packet, dict)
        else {}
    )
    views = _view_map(latest_packet)

    models = [
        _model_card(
            model_id="IIOS_OPENAI_CORE",
            label="IIOS / OpenAI Core",
            role="Governed synthesis and committee core",
            provider="OPENAI_GOVERNED_CORE",
            configured=None,
            provider_status={},
            view=views.get("IIOS_OPENAI_CORE"),
        ),
        _model_card(
            model_id="KIMI_RESEARCH",
            label="Kimi Research",
            role="Long-context deep research and swarm synthesis",
            provider="KIMI_OPEN_PLATFORM",
            configured=kimi.get("configured") is True,
            provider_status=kimi,
            view=views.get("KIMI_RESEARCH"),
        ),
        _model_card(
            model_id="GROK_NARRATIVE",
            label="Grok Narrative",
            role="Real-time X and web narrative intelligence",
            provider="XAI_RESPONSES",
            configured=grok.get("configured") is True,
            provider_status=grok,
            view=views.get("GROK_NARRATIVE"),
        ),
    ]

    activity = factory.get("activity")
    activity = activity if isinstance(activity, dict) else {}
    reconciliation = latest_packet.get("reconciliation")
    reconciliation = (
        reconciliation
        if isinstance(reconciliation, dict)
        else {}
    )
    gates = _production_gates(
        production,
        kimi,
        grok,
    )
    source_availability = {
        key: {
            "availability": value.get("availability"),
            "error_type": value.get("error_type"),
        }
        for key, value in sources.items()
    }
    all_sources_available = all(
        value["availability"] == "AVAILABLE"
        for value in source_availability.values()
    )
    cases = _normalize_cases(factory)

    safety = factory.get("safety")
    safety = safety if isinstance(safety, dict) else {}
    safety_view = {
        "paper_mode": True,
        "live_capital_locked": True,
        "all_current_safety_invariants_pass": (
            safety.get("all_invariants") is True
        ),
        "reported_violation_count": int(
            safety.get("violations") or 0
        ),
        **AUTHORITY_LOCK,
    }

    return {
        "name": "IIOS Factory Intelligence UI",
        "ui_version": UI_VERSION,
        "system_version": SYSTEM_VERSION,
        "generated_at": utc_now(),
        "refresh_seconds": 10,
        "data_state": (
            "LIVE"
            if all_sources_available
            else "PARTIAL"
        ),
        "unknown_state_semantics": True,
        "source_availability": source_availability,
        "pipeline": list(PIPELINE),
        "factory": {
            "rooms": factory.get("rooms") or [],
            "activity": activity,
            "desks": _desk_rows(activity),
            "portfolio": factory.get("portfolio") or {},
            "validation": factory.get("validation") or {},
        },
        "cases": cases,
        "case_count": len(cases),
        "council": {
            "packet_count": int(
                council.get("packet_count") or 0
            ),
            "latest_packet_id": latest_packet.get(
                "multi_model_council_packet_id"
            ),
            "latest_case_id": latest_packet.get("case_id"),
            "reconciliation": {
                "available_model_count": int(
                    reconciliation.get(
                        "available_model_count"
                    )
                    or 0
                ),
                "consensus_stance": (
                    reconciliation.get(
                        "consensus_stance"
                    )
                    or "UNKNOWN"
                ),
                "consensus_score": reconciliation.get(
                    "consensus_score"
                ),
                "divergence_score": reconciliation.get(
                    "divergence_score"
                ),
                "directional_conflict": (
                    reconciliation.get(
                        "directional_conflict"
                    )
                    is True
                ),
                "skeptic_escalation_recommended": (
                    reconciliation.get(
                        "skeptic_escalation_recommended"
                    )
                    is True
                ),
            },
            "models": models,
            "universal_model_weighting": False,
            "governed_iios_committee_remains_authoritative": True,
            **AUTHORITY_LOCK,
        },
        "calibration": _calibration_matrix(calibration),
        "production_gates": gates,
        "ready_gate_count": sum(
            1 for gate in gates if gate["ready"]
        ),
        "pending_gate_count": sum(
            1 for gate in gates if not gate["ready"]
        ),
        "safety": safety_view,
        **AUTHORITY_LOCK,
    }


def _object_state(
    payload: dict[str, Any] | None,
    ready_label: str,
    pending_label: str,
) -> dict[str, Any]:
    value = payload if isinstance(payload, dict) else {}
    return {
        "status": (
            "COMPLETE" if value else "PENDING"
        ),
        "label": ready_label if value else pending_label,
        "object_id": (
            value.get("multi_model_council_packet_id")
            or value.get("committee_decision_id")
            or value.get("decision_id")
            or value.get("risk_authorization_id")
            or value.get("qualification_assessment_id")
            or value.get("generic_position_sizing_id")
            or value.get("automatic_paper_sizing_id")
            or value.get("paper_authorization_id")
            or value.get("governed_paper_execution_id")
            or value.get("kimi_research_packet_id")
        ),
    }


def build_case_detail(
    case_id: str,
) -> dict[str, Any]:
    case = get_object(case_id)
    if not isinstance(case, dict):
        raise ValueError("Unknown case_id")

    committee = latest_object(
        "committee_decision",
        case_id=case_id,
    )
    risk = latest_object(
        "risk_authorization",
        case_id=case_id,
    )
    qualification = latest_object(
        "qualification_assessment",
        case_id=case_id,
    )
    sizing = (
        latest_object(
            "generic_position_sizing",
            case_id=case_id,
        )
        or latest_object(
            "automatic_paper_sizing",
            case_id=case_id,
        )
    )
    authorization = latest_object(
        "paper_authorization",
        case_id=case_id,
    )
    execution = latest_object(
        "governed_paper_execution",
        case_id=case_id,
    )
    council = latest_object(
        COUNCIL_TYPE,
        case_id=case_id,
    )
    kimi = latest_object(
        "kimi_research_packet",
        case_id=case_id,
    )
    monitor = latest_object(
        "monitor_snapshot",
        case_id=case_id,
    )

    council = council if isinstance(council, dict) else {}
    committee = (
        committee if isinstance(committee, dict) else {}
    )
    risk = risk if isinstance(risk, dict) else {}
    qualification = (
        qualification
        if isinstance(qualification, dict)
        else {}
    )
    sizing = sizing if isinstance(sizing, dict) else {}
    authorization = (
        authorization
        if isinstance(authorization, dict)
        else {}
    )
    execution = (
        execution if isinstance(execution, dict) else {}
    )
    kimi = kimi if isinstance(kimi, dict) else {}
    monitor = monitor if isinstance(monitor, dict) else {}

    return {
        "case_id": case_id,
        "topic": case.get("topic"),
        "ticker": (
            case.get("ticker")
            or monitor.get("ticker")
        ),
        "generated_at": utc_now(),
        "journey": [
            {
                "key": "EVIDENCE",
                "status": "COMPLETE",
                "label": "Case evidence folder exists",
            },
            {
                "key": "KIMI_RESEARCH",
                **_object_state(
                    kimi,
                    "Kimi research packet recorded",
                    "No Kimi research packet",
                ),
            },
            {
                "key": "COMMITTEE",
                **_object_state(
                    committee,
                    "Committee decision recorded",
                    "Committee decision pending",
                ),
            },
            {
                "key": "MULTI_MODEL_COUNCIL",
                **_object_state(
                    council,
                    "Model council packet recorded",
                    "Model council packet pending",
                ),
            },
            {
                "key": "RISK",
                **_object_state(
                    risk,
                    "Risk inspection recorded",
                    "Risk inspection pending",
                ),
            },
            {
                "key": "QUALIFICATION",
                **_object_state(
                    qualification,
                    "Qualification assessment recorded",
                    "Qualification pending",
                ),
            },
            {
                "key": "SIZING",
                **_object_state(
                    sizing,
                    "Paper sizing recorded",
                    "Paper sizing pending",
                ),
            },
            {
                "key": "AUTHORIZATION",
                **_object_state(
                    authorization,
                    "One-time paper authorization recorded",
                    "Paper authorization locked",
                ),
            },
            {
                "key": "PAPER_EXECUTION",
                **_object_state(
                    execution,
                    "Governed paper execution recorded",
                    "No paper order",
                ),
            },
        ],
        "committee": {
            "disposition": (
                committee.get("disposition")
                or committee.get("recommendation")
                or "UNKNOWN"
            ),
            "confidence": committee.get("confidence"),
            "headline": (
                committee.get("headline")
                or committee.get("summary")
                or "No committee decision."
            ),
            "summary": (
                committee.get("summary")
                or "No committee decision."
            ),
        },
        "risk": {
            "decision": (
                risk.get("decision") or "UNKNOWN"
            ),
            "triggered_rules": (
                risk.get("triggered_rules") or []
            ),
        },
        "qualification": {
            "qualified_buy_candidate": (
                qualification.get(
                    "qualified_buy_candidate"
                )
                is True
            ),
            "status": (
                qualification.get("status")
                or qualification.get("decision")
                or "UNKNOWN"
            ),
        },
        "council": {
            "packet_id": council.get(
                "multi_model_council_packet_id"
            ),
            "views": council.get("views") or [],
            "reconciliation": (
                council.get("reconciliation") or {}
            ),
            "skeptic_escalation_recommended": (
                council.get(
                    "skeptic_escalation_recommended"
                )
                is True
            ),
        },
        "monitoring": {
            "status": (
                monitor.get("status")
                or (
                    "AVAILABLE"
                    if monitor
                    else "NO_SNAPSHOT"
                )
            ),
            "created_at": monitor.get("created_at"),
            "latest_return_pct": monitor.get(
                "latest_return_pct"
            ),
            "thesis_flags": monitor.get(
                "thesis_flags"
            )
            or [],
        },
        "paper_execution": {
            "execution": (
                execution.get("execution")
                or "NOT_EXECUTED"
            ),
            "reason": execution.get("reason"),
        },
        "unknown_state_semantics": True,
        **AUTHORITY_LOCK,
    }


def status() -> dict[str, Any]:
    return {
        "name": "IIOS Factory Intelligence UI",
        "ui_version": UI_VERSION,
        "system_version": SYSTEM_VERSION,
        "installed": True,
        "read_only_aggregation": True,
        "live_data_contract": True,
        "unknown_state_semantics": True,
        "refresh_seconds": 10,
        "routes": {
            "status": (
                "/experience/factory-intelligence/status"
            ),
            "overview": (
                "/experience/factory-intelligence/overview"
            ),
            "case": (
                "/experience/factory-intelligence/case/{case_id}"
            ),
        },
        **AUTHORITY_LOCK,
    }


@router.get(
    "/experience/factory-intelligence/status"
)
def get_status():
    return status()


@router.get(
    "/experience/factory-intelligence/overview"
)
def get_overview():
    return build_overview()


@router.get(
    "/experience/factory-intelligence/case/{case_id}"
)
def get_case(case_id: str):
    try:
        return build_case_detail(case_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc
