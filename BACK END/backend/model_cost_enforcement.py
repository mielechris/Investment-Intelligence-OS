from __future__ import annotations

import hashlib
import json
import math
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "batch10m-grok-cost-enforcement-v1"
DEFAULT_COST_DIR = Path.home() / "Library" / "Application Support" / "IIOS" / "model-cost"
LEDGER_NAME = "model_usage.jsonl"
ADMISSION_LEDGER_NAME = "admission_events.jsonl"
ARTIFACT_NAME = "latest_model_cost_governor.json"
HOOK_REGISTRY_NAME = "enforcement_hooks.json"

POLICY = {
    "daily_soft_limit_usd": 10.0,
    "daily_hard_limit_usd": 20.0,
    "rolling_7d_soft_limit_usd": 50.0,
    "rolling_7d_hard_limit_usd": 75.0,
    "max_expensive_requests_per_case": 8,
    "max_estimated_input_tokens_per_request": 16000,
    "max_expensive_calls_per_hour": 20,
    "max_x_search_tool_calls_per_request": 3,
    "duplicate_query_ttl_seconds": 1800,
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _parse_time(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return parsed.astimezone(timezone.utc) if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _cost_dir() -> Path:
    value = str(os.getenv("IIOS_MODEL_COST_DIR", "")).strip()
    return Path(value).expanduser() if value else DEFAULT_COST_DIR


def query_fingerprint(query: str | None) -> str | None:
    if not query:
        return None
    normalized = " ".join(str(query).lower().split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:20]


def _append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True, default=str) + "\n")


def _read_events() -> list[dict[str, Any]]:
    path = _cost_dir() / LEDGER_NAME
    if not path.exists():
        return []
    output: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    for line in lines:
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict) and _parse_time(row.get("timestamp")) is not None:
            output.append(row)
    return output


def _window(events: list[dict[str, Any]], start: datetime, end: datetime) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for row in events:
        timestamp = _parse_time(row.get("timestamp"))
        if timestamp is not None and start <= timestamp <= end:
            selected.append(row)
    return selected


def _sum_exact(events: list[dict[str, Any]]) -> float:
    return round(sum(_float(row.get("cost_usd")) or 0.0 for row in events), 8)


def _current_state(now: datetime | None = None) -> dict[str, Any]:
    now_value = now or _utc_now()
    events = _read_events()
    today_start = now_value.replace(hour=0, minute=0, second=0, microsecond=0)
    hour_start = now_value - timedelta(hours=1)
    week_start = now_value - timedelta(days=7)
    today = _window(events, today_start, now_value)
    hour = _window(events, hour_start, now_value)
    week = _window(events, week_start, now_value)
    daily = _sum_exact(today)
    weekly = _sum_exact(week)
    return {
        "now": now_value,
        "events": events,
        "today": today,
        "hour": hour,
        "week": week,
        "daily_exact_spend_usd": daily,
        "weekly_exact_spend_usd": weekly,
    }


def _decision_event(decision: dict[str, Any], *, query_fp: str | None, case_id: str | None, model: str, estimated_input_tokens: int) -> None:
    _append_jsonl(
        _cost_dir() / ADMISSION_LEDGER_NAME,
        {
            "timestamp": _iso(_utc_now()),
            "decision": decision.get("decision"),
            "reasons": list(decision.get("reasons") or []),
            "query_fingerprint": query_fp,
            "case_id": case_id,
            "provider": "XAI",
            "model": model,
            "estimated_input_tokens": max(0, int(estimated_input_tokens or 0)),
            "binding": True,
            "prompt_persisted": False,
            "api_key_persisted": False,
        },
    )


def preflight_xai_request(*, query: str, model: str, case_id: str | None = None, estimated_input_tokens: int = 0) -> dict[str, Any]:
    """Binding admission gate for the Grok/X-search request boundary only."""
    state = _current_state()
    now_value: datetime = state["now"]
    fp = query_fingerprint(query)
    reasons: list[str] = []
    decision = "ALLOW"

    daily = float(state["daily_exact_spend_usd"])
    weekly = float(state["weekly_exact_spend_usd"])
    if daily >= float(POLICY["daily_hard_limit_usd"]) or weekly >= float(POLICY["rolling_7d_hard_limit_usd"]):
        decision = "BLOCK_HARD_BUDGET"
        reasons.append("EXACT_SPEND_AT_OR_ABOVE_HARD_LIMIT")
    elif daily >= float(POLICY["daily_soft_limit_usd"]) or weekly >= float(POLICY["rolling_7d_soft_limit_usd"]):
        decision = "DEFER_SOFT_BUDGET"
        reasons.append("EXACT_SPEND_AT_OR_ABOVE_SOFT_LIMIT")

    if estimated_input_tokens > int(POLICY["max_estimated_input_tokens_per_request"]):
        decision = "DEFER_CONTEXT_LIMIT" if decision == "ALLOW" else decision
        reasons.append("ESTIMATED_INPUT_CONTEXT_EXCEEDS_POLICY")

    hour = list(state["hour"])
    if len(hour) >= int(POLICY["max_expensive_calls_per_hour"]):
        decision = "DEFER_HOURLY_LIMIT" if decision == "ALLOW" else decision
        reasons.append("EXPENSIVE_CALLS_AT_HOURLY_LIMIT")

    if case_id:
        case_count = sum(1 for row in hour if str(row.get("case_id") or "") == str(case_id))
        if case_count >= int(POLICY["max_expensive_requests_per_case"]):
            decision = "DEFER_CASE_LIMIT" if decision == "ALLOW" else decision
            reasons.append("CASE_REQUEST_COUNT_AT_POLICY_LIMIT")

    if fp:
        ttl = int(POLICY["duplicate_query_ttl_seconds"])
        for row in reversed(state["events"]):
            if str(row.get("query_fingerprint") or "") != fp:
                continue
            seen = _parse_time(row.get("timestamp"))
            if seen and 0 <= (now_value - seen).total_seconds() <= ttl:
                decision = "DEFER_DUPLICATE" if decision == "ALLOW" else decision
                reasons.append("DUPLICATE_QUERY_INSIDE_TTL")
            break

    result = {
        "decision": decision,
        "allow": decision == "ALLOW",
        "reasons": reasons or ["WITHIN_BINDING_GROK_COST_POLICY"],
        "binding": True,
        "daily_exact_spend_usd": daily,
        "rolling_7d_exact_spend_usd": weekly,
        "query_fingerprint": fp,
        "policy_version": SCHEMA_VERSION,
        "trade_execution_permission": False,
        "capital_authority": False,
        "live_execution": False,
    }
    _decision_event(result, query_fp=fp, case_id=case_id, model=model, estimated_input_tokens=estimated_input_tokens)
    return result


def _response_dump(response: Any) -> dict[str, Any]:
    if hasattr(response, "model_dump"):
        try:
            value = response.model_dump()
            if isinstance(value, dict):
                return value
        except Exception:
            pass
    return response if isinstance(response, dict) else {}


def record_xai_response(response: Any, *, model: str, query: str, case_id: str | None, latency_ms: float | None, task_type: str = "GROK_X_SEARCH") -> dict[str, Any]:
    dump = _response_dump(response)
    usage = dump.get("usage") if isinstance(dump.get("usage"), dict) else {}
    details = usage.get("input_tokens_details") if isinstance(usage.get("input_tokens_details"), dict) else {}
    ticks = _int(usage.get("cost_in_usd_ticks"))
    exact_cost = round(ticks / 10_000_000_000, 10) if ticks > 0 else None
    tool_calls = _int(usage.get("num_server_side_tools_used"))
    row = {
        "timestamp": _iso(_utc_now()),
        "provider": "XAI",
        "model": model,
        "task_type": task_type,
        "case_id": case_id,
        "agent": "GROK_SOCIAL_INTELLIGENCE",
        "input_tokens": _int(usage.get("input_tokens")),
        "cached_input_tokens": _int(details.get("cached_tokens")),
        "output_tokens": _int(usage.get("output_tokens")),
        "web_search_calls": 0,
        "x_search_calls": tool_calls,
        "server_side_tool_calls": tool_calls,
        "cost_usd": exact_cost,
        "cost_source": "XAI_COST_IN_USD_TICKS" if exact_cost is not None else "NOT_REPORTED",
        "cost_in_usd_ticks": ticks or None,
        "latency_ms": _float(latency_ms),
        "query_fingerprint": query_fingerprint(query),
        "request_completed": True,
        "prompt_persisted": False,
        "api_key_persisted": False,
    }
    _append_jsonl(_cost_dir() / LEDGER_NAME, row)
    publish_governor_artifact()
    return row


def record_xai_failure(*, model: str, query: str, case_id: str | None, latency_ms: float | None, error_type: str, task_type: str = "GROK_X_SEARCH") -> dict[str, Any]:
    row = {
        "timestamp": _iso(_utc_now()),
        "provider": "XAI",
        "model": model,
        "task_type": task_type,
        "case_id": case_id,
        "agent": "GROK_SOCIAL_INTELLIGENCE",
        "input_tokens": 0,
        "cached_input_tokens": 0,
        "output_tokens": 0,
        "web_search_calls": 0,
        "x_search_calls": 0,
        "server_side_tool_calls": 0,
        "cost_usd": None,
        "cost_source": "NOT_REPORTED_ON_FAILED_REQUEST",
        "latency_ms": _float(latency_ms),
        "query_fingerprint": query_fingerprint(query),
        "request_completed": False,
        "error_type": str(error_type or "UNKNOWN")[:120],
        "prompt_persisted": False,
        "api_key_persisted": False,
    }
    _append_jsonl(_cost_dir() / LEDGER_NAME, row)
    publish_governor_artifact()
    return row


def register_hook() -> dict[str, Any]:
    cost_dir = _cost_dir()
    cost_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "updated_at": _iso(_utc_now()),
        "hooks": {
            "xai_grok_social_intelligence": {
                "connected": True,
                "binding": True,
                "pre_call_admission": True,
                "post_call_exact_cost": True,
                "prompt_persisted": False,
                "api_key_persisted": False,
            }
        },
        "trade_execution_permission": False,
        "capital_authority": False,
        "live_execution": False,
    }
    tmp = cost_dir / (HOOK_REGISTRY_NAME + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(cost_dir / HOOK_REGISTRY_NAME)
    publish_governor_artifact()
    return payload


def publish_governor_artifact() -> dict[str, Any]:
    state = _current_state()
    week = list(state["week"])
    today = list(state["today"])
    priced = [row for row in week if _float(row.get("cost_usd")) is not None]
    unpriced = len(week) - len(priced)
    coverage = round((len(priced) / len(week) * 100.0), 1) if week else 0.0
    daily = float(state["daily_exact_spend_usd"])
    weekly = float(state["weekly_exact_spend_usd"])
    if daily >= POLICY["daily_hard_limit_usd"] or weekly >= POLICY["rolling_7d_hard_limit_usd"]:
        budget_state = "HARD_LIMIT"
    elif daily >= POLICY["daily_soft_limit_usd"] or weekly >= POLICY["rolling_7d_soft_limit_usd"]:
        budget_state = "SOFT_LIMIT"
    else:
        budget_state = "WITHIN_BUDGET" if week else "INSTRUMENTATION_BOOTSTRAP"

    artifact = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _iso(_utc_now()),
        "status": "MODEL_COST_GOVERNOR_ENFORCEMENT_ACTIVE",
        "budget_state": budget_state,
        "enforcement_hooks_connected": True,
        "binding_xai_grok_hook": True,
        "exact_cost_policy": "XAI_COST_IN_USD_TICKS_ONLY_FOR_DOLLAR_TOTALS",
        "no_spend_estimate_invented": True,
        "policy": dict(POLICY),
        "today": {
            "requests": len(today),
            "priced_requests": sum(1 for row in today if _float(row.get("cost_usd")) is not None),
            "exact_spend_usd": round(daily, 4) if today else None,
            "input_tokens": sum(_int(row.get("input_tokens")) for row in today),
            "cached_input_tokens": sum(_int(row.get("cached_input_tokens")) for row in today),
            "output_tokens": sum(_int(row.get("output_tokens")) for row in today),
            "x_search_calls": sum(_int(row.get("x_search_calls")) for row in today),
        },
        "rolling_7d": {
            "requests": len(week),
            "priced_requests": len(priced),
            "unpriced_requests": unpriced,
            "exact_cost_coverage_pct": coverage,
            "exact_spend_usd": round(weekly, 4) if week else None,
            "input_tokens": sum(_int(row.get("input_tokens")) for row in week),
            "cached_input_tokens": sum(_int(row.get("cached_input_tokens")) for row in week),
            "output_tokens": sum(_int(row.get("output_tokens")) for row in week),
            "x_search_calls": sum(_int(row.get("x_search_calls")) for row in week),
        },
        "measurement_gaps": (["NO_POST_HOOK_XAI_REQUEST_RECORDED_YET"] if not week else []) + (["SOME_FAILED_REQUESTS_HAVE_NO_PROVIDER_REPORTED_EXACT_COST"] if unpriced else []),
        "safety": {
            "scope": "XAI_GROK_RESEARCH_COST_ONLY",
            "auto_trade_authority": False,
            "paper_order_permission": False,
            "broker_connection_authority": False,
            "capital_authority": False,
            "trade_execution_permission": False,
            "live_execution": False,
            "no_model_weight_change": True,
            "no_portfolio_change": True,
        },
    }
    cost_dir = _cost_dir()
    cost_dir.mkdir(parents=True, exist_ok=True)
    tmp = cost_dir / (ARTIFACT_NAME + ".tmp")
    tmp.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(cost_dir / ARTIFACT_NAME)
    return artifact


def main() -> int:
    hook = register_hook()
    artifact = publish_governor_artifact()
    print(json.dumps({
        "status": artifact["status"],
        "budget_state": artifact["budget_state"],
        "enforcement_hooks_connected": artifact["enforcement_hooks_connected"],
        "rolling_7d_exact_spend_usd": (artifact.get("rolling_7d") or {}).get("exact_spend_usd"),
        "hook": hook["hooks"]["xai_grok_social_intelligence"],
        "trade_execution_permission": False,
        "capital_authority": False,
        "live_execution": False,
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
