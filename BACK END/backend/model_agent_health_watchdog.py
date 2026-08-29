from __future__ import annotations

import json
import os
import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from ledger import DB_PATH


POLICY_VERSION = "batch10m1-model-agent-health-v1"
STATUS_ACTIVE = "MODEL_AGENT_INTELLIGENCE_HEALTH_ACTIVE"
EXPECTED_AGENTS = (
    "policy",
    "macro",
    "fundamentals",
    "market_structure",
    "commodities",
    "geo_weather",
    "skeptic",
    "portfolio",
)

RADAR_FRESH_SECONDS = 15 * 60
CASE_FLOOR_FRESH_SECONDS = 3 * 60
DEEP_WORKER_FRESH_SECONDS = 5 * 60
UNIVERSE_FRESH_SECONDS = 36 * 60 * 60
RECENT_FAILURE_HOURS = 6
AGENT_WINDOW_HOURS = 24

DEFAULT_ARTIFACT = (
    Path.home()
    / "Library"
    / "Application Support"
    / "IIOS"
    / "model-agent-health"
    / "latest_model_agent_health.json"
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_time(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _age_seconds(value: Any, now: datetime) -> float | None:
    dt = _parse_time(value)
    if dt is None:
        return None
    return round(max(0.0, (now - dt).total_seconds()), 3)


def _payload(raw: Any) -> dict[str, Any]:
    try:
        value = json.loads(str(raw or "{}"))
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def _latest(db: sqlite3.Connection, object_type: str) -> tuple[str | None, dict[str, Any]]:
    row = db.execute(
        "SELECT created_at,payload_json FROM ledger_objects WHERE object_type=? ORDER BY created_at DESC LIMIT 1",
        (object_type,),
    ).fetchone()
    if not row:
        return None, {}
    return str(row["created_at"]), _payload(row["payload_json"])


def _event_counts(db: sqlite3.Connection, cutoff: str) -> dict[str, int]:
    wanted = (
        "HIGH_SPEED_MODEL_RESEARCH_COMPLETE",
        "HIGH_SPEED_MODEL_RESEARCH_FAILED_CLOSED",
        "GEMINI_DEEP_RESEARCH_COMPLETE",
        "GEMINI_DEEP_RESEARCH_FAILED_CLOSED",
        "EIGHT_AGENT_ORCHESTRATION_COMPLETE",
        "HIGH_SPEED_CASE_FLOOR_FAILED_CLOSED",
    )
    out: dict[str, int] = {}
    for event in wanted:
        row = db.execute(
            "SELECT COUNT(*) AS c FROM audit_events WHERE event_type=? AND created_at>=?",
            (event, cutoff),
        ).fetchone()
        out[event] = int(row["c"] if row else 0)
    return out


def _agent_stats(db: sqlite3.Connection, cutoff: str) -> dict[str, dict[str, Any]]:
    rows = db.execute(
        "SELECT created_at,payload_json FROM ledger_objects WHERE object_type='agent_result' AND created_at>=? ORDER BY created_at DESC",
        (cutoff,),
    ).fetchall()
    stats: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"total": 0, "complete": 0, "errors": 0, "latest_at": None, "contract_v2": 0}
    )
    for row in rows:
        value = _payload(row["payload_json"])
        key = str(value.get("agent_key") or "UNKNOWN")
        item = stats[key]
        item["total"] += 1
        if value.get("status") == "complete":
            item["complete"] += 1
        else:
            item["errors"] += 1
        if item["latest_at"] is None:
            item["latest_at"] = str(row["created_at"])
        if value.get("contract_version") == "batch10m1-agent-contract-v2":
            item["contract_v2"] += 1
    return dict(stats)


def _component(
    name: str,
    *,
    state: str,
    age_seconds: float | None = None,
    required: bool = True,
    detail: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "component": name,
        "state": state,
        "required": required,
        "age_seconds": age_seconds,
        "detail": detail or {},
    }


def build_health_snapshot(db_path: str | Path | None = None) -> dict[str, Any]:
    """Read-only intelligence-floor health evaluation. Makes no provider calls."""
    path = Path(db_path or os.getenv("IIOS_DB_PATH") or DB_PATH)
    now = _now()
    if not path.exists():
        return {
            "status": STATUS_ACTIVE,
            "overall_state": "FAILED_CLOSED",
            "policy_version": POLICY_VERSION,
            "database": str(path),
            "issues": ["GOVERNED_LEDGER_MISSING"],
            "provider_requests_made": False,
            "ledger_mutated": False,
            "capital_authority": False,
            "trade_execution_permission": False,
            "live_execution": False,
            "created_at": now.isoformat(),
        }

    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=30)
    db.row_factory = sqlite3.Row
    try:
        universe_ts, universe = _latest(db, "production_index_universe_snapshot")
        radar_ts, radar = _latest(db, "high_speed_market_radar_state")
        model_ts, model = _latest(db, "high_speed_market_model_context")
        deep_ts, deep = _latest(db, "high_speed_gemini_deep_worker_state")
        floor_ts, floor = _latest(db, "high_speed_case_floor_state")
        orchestration_ts, orchestration = _latest(db, "agent_orchestration")
        committee_ts, committee = _latest(db, "committee_decision")

        events = _event_counts(
            db,
            (now - timedelta(hours=RECENT_FAILURE_HOURS)).isoformat(),
        )
        agents = _agent_stats(
            db,
            (now - timedelta(hours=AGENT_WINDOW_HOURS)).isoformat(),
        )
    finally:
        db.close()

    components: list[dict[str, Any]] = []
    issues: list[str] = []

    universe_age = _age_seconds(universe_ts, now)
    indexes = universe.get("indexes") if isinstance(universe.get("indexes"), dict) else {}
    sp = next((v for k, v in indexes.items() if "SP" in str(k).upper()), {})
    ndx = next((v for k, v in indexes.items() if "NASDAQ" in str(k).upper()), {})
    universe_ok = bool(
        universe.get("verified_complete") is True
        and universe_age is not None
        and universe_age <= UNIVERSE_FRESH_SECONDS
        and 490 <= int((sp or {}).get("symbol_count") or 0) <= 520
        and 95 <= int((ndx or {}).get("symbol_count") or 0) <= 110
    )
    components.append(
        _component(
            "STRICT_GOVERNED_UNIVERSE",
            state="HEALTHY" if universe_ok else "DEGRADED",
            age_seconds=universe_age,
            detail={
                "verified_complete": universe.get("verified_complete"),
                "sp500_count": (sp or {}).get("symbol_count"),
                "nasdaq100_count": (ndx or {}).get("symbol_count"),
            },
        )
    )
    if not universe_ok:
        issues.append("STRICT_UNIVERSE_NOT_HEALTHY")

    radar_age = _age_seconds(radar.get("last_cycle_completed_at") or radar_ts, now)
    radar_ok = radar_age is not None and radar_age <= RADAR_FRESH_SECONDS
    components.append(
        _component(
            "9E_RADAR",
            state="HEALTHY" if radar_ok else "STALE",
            age_seconds=radar_age,
            detail={
                "last_cycle_id": radar.get("last_cycle_id"),
                "model_execution_satisfied": radar.get("model_execution_satisfied"),
                "provider_errors": radar.get("provider_errors") or {},
            },
        )
    )
    if not radar_ok:
        issues.append("9E_RADAR_STALE")

    model_age = _age_seconds(model_ts, now)
    model_failures = events["HIGH_SPEED_MODEL_RESEARCH_FAILED_CLOSED"]
    model_completes = events["HIGH_SPEED_MODEL_RESEARCH_COMPLETE"]
    provider_errors = model.get("provider_errors") if isinstance(model.get("provider_errors"), dict) else {}
    model_state = "IDLE_HEALTHY"
    if model_failures > 0 and model_failures > model_completes:
        model_state = "DEGRADED"
        issues.append("MODEL_RESEARCH_RECENT_FAILURES")
    elif model and provider_errors:
        model_state = "DEGRADED"
        issues.append("MODEL_PROVIDER_ERRORS_PRESENT")
    elif model_completes > 0:
        model_state = "HEALTHY"
    components.append(
        _component(
            "GROK_GEMINI_MODEL_CONTEXT",
            state=model_state,
            age_seconds=model_age,
            required=False,
            detail={
                "grok_satisfied": model.get("grok_execution_satisfied"),
                "gemini_satisfied": model.get("gemini_execution_satisfied"),
                "recent_completes": model_completes,
                "recent_failures": model_failures,
                "provider_errors": provider_errors,
            },
        )
    )

    deep_age = _age_seconds(deep_ts, now)
    deep_status = str(deep.get("status") or "UNKNOWN")
    deep_ok = deep_age is not None and deep_age <= DEEP_WORKER_FRESH_SECONDS
    if deep_status == "FAILED_CLOSED":
        deep_state = "DEGRADED"
        issues.append("GEMINI_PRO_RECENT_FAILED_CLOSED")
    elif deep_ok and deep_status == "IDLE":
        deep_state = "IDLE_HEALTHY"
    elif deep_ok:
        deep_state = "HEALTHY"
    else:
        deep_state = "STALE"
        issues.append("GEMINI_PRO_WORKER_STALE")
    components.append(
        _component(
            "GEMINI_PRO_DEEP_WORKER",
            state=deep_state,
            age_seconds=deep_age,
            detail={
                "status": deep_status,
                "queue_depth": deep.get("queue_depth", deep.get("queue_depth_before")),
                "processed": deep.get("processed"),
                "recent_complete": events["GEMINI_DEEP_RESEARCH_COMPLETE"],
                "recent_failed_closed": events["GEMINI_DEEP_RESEARCH_FAILED_CLOSED"],
            },
        )
    )

    floor_age = _age_seconds(floor.get("last_cycle_completed_at") or floor_ts, now)
    floor_ok = floor_age is not None and floor_age <= CASE_FLOOR_FRESH_SECONDS
    queue_before = int(floor.get("queue_depth_before") or 0)
    selected = int(floor.get("selected_count") or 0)
    floor_failures = int(floor.get("failed_closed_count") or 0)
    if not floor_ok:
        floor_state = "STALE"
        issues.append("CASE_FLOOR_STALE")
    elif floor_failures > 0 or events["HIGH_SPEED_CASE_FLOOR_FAILED_CLOSED"] > 0:
        floor_state = "DEGRADED"
        issues.append("CASE_FLOOR_RECENT_FAILURES")
    elif selected == 0 and queue_before == 0:
        floor_state = "IDLE_HEALTHY"
    else:
        floor_state = "HEALTHY"
    components.append(
        _component(
            "GPT_EIGHT_AGENT_CASE_FLOOR",
            state=floor_state,
            age_seconds=floor_age,
            detail={
                "queue_before": queue_before,
                "selected": selected,
                "completed": floor.get("completed_count"),
                "failed_closed": floor_failures,
                "agent_contract_version": floor.get("agent_contract_version"),
            },
        )
    )

    total_agents = sum(int(v.get("total") or 0) for v in agents.values())
    total_agent_errors = sum(int(v.get("errors") or 0) for v in agents.values())
    v2_results = sum(int(v.get("contract_v2") or 0) for v in agents.values())
    if total_agents == 0 and selected == 0:
        agents_state = "IDLE_HEALTHY"
    elif total_agents and total_agent_errors / total_agents <= 0.05:
        agents_state = "HEALTHY"
    else:
        agents_state = "DEGRADED"
        if total_agent_errors:
            issues.append("AGENT_RESULT_ERROR_RATE_ELEVATED")
    components.append(
        _component(
            "EIGHT_GPT_DESKS",
            state=agents_state,
            age_seconds=_age_seconds(orchestration_ts, now),
            detail={
                "expected_agents": list(EXPECTED_AGENTS),
                "recent_stats": agents,
                "recent_result_count": total_agents,
                "recent_error_count": total_agent_errors,
                "contract_v2_results": v2_results,
                "latest_orchestration_case": orchestration.get("case_id"),
            },
        )
    )

    committee_age = _age_seconds(committee_ts, now)
    if selected == 0 and not orchestration:
        committee_state = "IDLE_HEALTHY"
    elif events["EIGHT_AGENT_ORCHESTRATION_COMPLETE"] > 0 or committee:
        committee_state = "HEALTHY"
    else:
        committee_state = "DEGRADED"
        issues.append("COMMITTEE_RESULT_MISSING_AFTER_CASE_ACTIVITY")
    components.append(
        _component(
            "INVESTMENT_COMMITTEE",
            state=committee_state,
            age_seconds=committee_age,
            detail={
                "latest_case": committee.get("case_id"),
                "latest_disposition": committee.get("disposition"),
                "latest_confidence": committee.get("confidence"),
                "recent_orchestrations": events["EIGHT_AGENT_ORCHESTRATION_COMPLETE"],
            },
        )
    )

    hard_states = {row["state"] for row in components if row.get("required") is True}
    if "STALE" in hard_states or "DEGRADED" in hard_states:
        overall = "DEGRADED"
    elif all(row["state"] == "IDLE_HEALTHY" for row in components if row["component"] in {"GROK_GEMINI_MODEL_CONTEXT", "GEMINI_PRO_DEEP_WORKER", "GPT_EIGHT_AGENT_CASE_FLOOR", "EIGHT_GPT_DESKS"}):
        overall = "IDLE_HEALTHY"
    else:
        overall = "HEALTHY"

    return {
        "status": STATUS_ACTIVE,
        "overall_state": overall,
        "policy_version": POLICY_VERSION,
        "database": str(path),
        "components": components,
        "issues": list(dict.fromkeys(issues)),
        "event_window_hours": RECENT_FAILURE_HOURS,
        "agent_window_hours": AGENT_WINDOW_HOURS,
        "provider_requests_made": False,
        "ledger_mutated": False,
        "paper_mode": True,
        "committee_override": False,
        "risk_override": False,
        "capital_authority": False,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
        "created_at": now.isoformat(),
    }


def publish_health_artifact(
    db_path: str | Path | None = None,
    artifact_path: str | Path | None = None,
) -> dict[str, Any]:
    snapshot = build_health_snapshot(db_path=db_path)
    path = Path(artifact_path or os.getenv("IIOS_MODEL_AGENT_HEALTH_ARTIFACT") or DEFAULT_ARTIFACT)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(snapshot, indent=2, sort_keys=True), encoding="utf-8")
    temp.replace(path)
    return {**snapshot, "artifact_path": str(path)}
