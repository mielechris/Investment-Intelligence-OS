#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "batch10m-model-cost-governor-v1"
DEFAULT_COST_DIR = Path.home() / "Library" / "Application Support" / "IIOS" / "model-cost"
LEDGER_NAME = "model_usage.jsonl"
ARTIFACT_NAME = "latest_model_cost_governor.json"
HOOK_REGISTRY_NAME = "enforcement_hooks.json"

POLICY = {
    "daily_soft_limit_usd": 10.0,
    "daily_hard_limit_usd": 20.0,
    "rolling_7d_soft_limit_usd": 50.0,
    "rolling_7d_hard_limit_usd": 75.0,
    "max_web_searches_per_case": 5,
    "max_expensive_requests_per_case": 8,
    "max_input_tokens_per_expensive_request": 16000,
    "max_expensive_calls_per_hour": 20,
    "duplicate_query_ttl_seconds": 1800,
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _parse_time(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return parsed.astimezone(timezone.utc) if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    tmp.replace(path)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _binding_hook_connected(cost_dir: Path) -> bool:
    registry = _read_json(cost_dir / HOOK_REGISTRY_NAME)
    hooks = registry.get("hooks") if isinstance(registry.get("hooks"), dict) else {}
    grok = hooks.get("xai_grok_social_intelligence") if isinstance(hooks.get("xai_grok_social_intelligence"), dict) else {}
    return grok.get("connected") is True and grok.get("binding") is True


def query_fingerprint(query: str | None) -> str | None:
    if not query:
        return None
    normalized = " ".join(str(query).lower().split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:20]


def record_usage(cost_dir: Path, event: dict[str, Any]) -> dict[str, Any]:
    """Append one provider/model usage event without estimating unknown dollar cost."""
    cost_dir.mkdir(parents=True, exist_ok=True)
    timestamp = _parse_time(event.get("timestamp")) or _utc_now()
    exact_cost = _float(event.get("cost_usd"))
    if exact_cost is not None and exact_cost < 0:
        exact_cost = None
    row = {
        "timestamp": _iso(timestamp),
        "provider": str(event.get("provider") or "UNKNOWN").upper(),
        "model": str(event.get("model") or "UNKNOWN"),
        "task_type": str(event.get("task_type") or "UNKNOWN").upper(),
        "case_id": str(event.get("case_id") or "") or None,
        "agent": str(event.get("agent") or "") or None,
        "input_tokens": _int(event.get("input_tokens")),
        "cached_input_tokens": _int(event.get("cached_input_tokens")),
        "output_tokens": _int(event.get("output_tokens")),
        "web_search_calls": _int(event.get("web_search_calls")),
        "x_search_calls": _int(event.get("x_search_calls")),
        "cost_usd": round(exact_cost, 8) if exact_cost is not None else None,
        "cost_source": str(event.get("cost_source") or ("PROVIDER_REPORTED" if exact_cost is not None else "NOT_REPORTED")),
        "latency_ms": _float(event.get("latency_ms")),
        "query_fingerprint": str(event.get("query_fingerprint") or "") or query_fingerprint(str(event.get("query") or "")),
    }
    with (cost_dir / LEDGER_NAME).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")
    return row


def _read_events(cost_dir: Path) -> list[dict[str, Any]]:
    path = cost_dir / LEDGER_NAME
    if not path.exists():
        return []
    events: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    for line in lines:
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict) and _parse_time(value.get("timestamp")) is not None:
            events.append(value)
    return events


def _breakdown(events: list[dict[str, Any]], field: str) -> list[dict[str, Any]]:
    buckets: dict[str, dict[str, Any]] = defaultdict(lambda: {"requests": 0, "priced_requests": 0, "exact_cost_usd": 0.0, "input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 0, "web_search_calls": 0, "x_search_calls": 0})
    for row in events:
        key = str(row.get(field) or "UNKNOWN")
        bucket = buckets[key]
        bucket["requests"] += 1
        bucket["input_tokens"] += _int(row.get("input_tokens"))
        bucket["cached_input_tokens"] += _int(row.get("cached_input_tokens"))
        bucket["output_tokens"] += _int(row.get("output_tokens"))
        bucket["web_search_calls"] += _int(row.get("web_search_calls"))
        bucket["x_search_calls"] += _int(row.get("x_search_calls"))
        cost = _float(row.get("cost_usd"))
        if cost is not None:
            bucket["priced_requests"] += 1
            bucket["exact_cost_usd"] += cost
    output = []
    for key, value in buckets.items():
        output.append({field: key, **value, "exact_cost_usd": round(float(value["exact_cost_usd"]), 4)})
    output.sort(key=lambda row: (float(row["exact_cost_usd"]), int(row["requests"])), reverse=True)
    return output


def _window(events: list[dict[str, Any]], start: datetime, end: datetime) -> list[dict[str, Any]]:
    selected = []
    for row in events:
        timestamp = _parse_time(row.get("timestamp"))
        if timestamp is not None and start <= timestamp <= end:
            selected.append(row)
    return selected


def _sum_exact(events: list[dict[str, Any]]) -> float:
    return round(sum(_float(row.get("cost_usd")) or 0.0 for row in events), 4)


def _budget_state(daily_spend: float, weekly_spend: float, priced_requests: int, *, binding: bool = False) -> str:
    if priced_requests <= 0:
        return "INSTRUMENTATION_BOOTSTRAP" if binding else "INSTRUMENTATION_GAP"
    if daily_spend >= POLICY["daily_hard_limit_usd"] or weekly_spend >= POLICY["rolling_7d_hard_limit_usd"]:
        return "HARD_LIMIT"
    if daily_spend >= POLICY["daily_soft_limit_usd"] or weekly_spend >= POLICY["rolling_7d_soft_limit_usd"]:
        return "SOFT_LIMIT"
    return "WITHIN_BUDGET"


def admission_decision(*, artifact: dict[str, Any], case_id: str | None = None, input_tokens: int = 0, web_searches_requested: int = 0, query_fingerprint_value: str | None = None, now: datetime | None = None) -> dict[str, Any]:
    """Legacy advisory decision helper. Binding enforcement lives at the xAI call boundary."""
    now_value = now or _utc_now()
    state = str(artifact.get("budget_state") or "INSTRUMENTATION_GAP")
    reasons: list[str] = []
    decision = "ALLOW"
    if state == "HARD_LIMIT":
        decision = "HUMAN_REVIEW_REQUIRED"
        reasons.append("EXACT_SPEND_AT_OR_ABOVE_HARD_POLICY_LIMIT")
    elif state in {"SOFT_LIMIT", "INSTRUMENTATION_GAP"}:
        decision = "DEFER_EXPENSIVE_RESEARCH"
        reasons.append("SOFT_LIMIT_OR_COST_INSTRUMENTATION_GAP")
    if input_tokens > int(POLICY["max_input_tokens_per_expensive_request"]):
        decision = "DEFER_EXPENSIVE_RESEARCH" if decision == "ALLOW" else decision
        reasons.append("INPUT_CONTEXT_EXCEEDS_POLICY")
    if web_searches_requested > int(POLICY["max_web_searches_per_case"]):
        decision = "DEFER_EXPENSIVE_RESEARCH" if decision == "ALLOW" else decision
        reasons.append("WEB_SEARCH_REQUEST_EXCEEDS_CASE_POLICY")
    recent = artifact.get("recent_request_index") if isinstance(artifact.get("recent_request_index"), dict) else {}
    if case_id:
        case = recent.get("by_case") if isinstance(recent.get("by_case"), dict) else {}
        if _int(case.get(case_id)) >= int(POLICY["max_expensive_requests_per_case"]):
            decision = "DEFER_EXPENSIVE_RESEARCH" if decision == "ALLOW" else decision
            reasons.append("CASE_REQUEST_COUNT_AT_POLICY_LIMIT")
    if query_fingerprint_value:
        duplicates = recent.get("fingerprints") if isinstance(recent.get("fingerprints"), dict) else {}
        last_seen = _parse_time(duplicates.get(query_fingerprint_value))
        if last_seen and (now_value - last_seen).total_seconds() <= int(POLICY["duplicate_query_ttl_seconds"]):
            decision = "DEFER_EXPENSIVE_RESEARCH" if decision == "ALLOW" else decision
            reasons.append("DUPLICATE_QUERY_INSIDE_TTL")
    return {"decision": decision, "reasons": reasons or ["WITHIN_ADVISORY_POLICY"], "binding": False, "human_approval_required_for_material_provider_or_routing_change": True}


def build_governor(cost_dir: Path, *, now: datetime | None = None) -> dict[str, Any]:
    now_value = now or _utc_now()
    binding = _binding_hook_connected(cost_dir)
    events = _read_events(cost_dir)
    today_start = now_value.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = now_value - timedelta(days=7)
    hour_start = now_value - timedelta(hours=1)
    today = _window(events, today_start, now_value)
    week = _window(events, week_start, now_value)
    hour = _window(events, hour_start, now_value)
    priced = [row for row in week if _float(row.get("cost_usd")) is not None]
    unpriced = len(week) - len(priced)
    daily_exact = _sum_exact(today)
    weekly_exact = _sum_exact(week)
    coverage = round((len(priced) / len(week) * 100.0), 1) if week else 0.0
    by_case: dict[str, int] = defaultdict(int)
    fingerprints: dict[str, str] = {}
    for row in hour:
        case_id = str(row.get("case_id") or "")
        if case_id:
            by_case[case_id] += 1
        fp = str(row.get("query_fingerprint") or "")
        ts = str(row.get("timestamp") or "")
        if fp and ts:
            fingerprints[fp] = max(fingerprints.get(fp, ""), ts)

    status = "MODEL_COST_GOVERNOR_ENFORCEMENT_ACTIVE" if binding else ("MODEL_COST_GOVERNOR_ACTIVE" if events else "MODEL_COST_GOVERNOR_INSTRUMENTATION_REQUIRED")
    budget_state = _budget_state(daily_exact, weekly_exact, len(priced), binding=binding)
    artifact = {
        "schema_version": "batch10m-grok-cost-enforcement-v1" if binding else SCHEMA_VERSION,
        "generated_at": _iso(now_value),
        "status": status,
        "budget_state": budget_state,
        "exact_cost_policy": "XAI_COST_IN_USD_TICKS_ONLY_FOR_DOLLAR_TOTALS" if binding else "ONLY_PROVIDER_REPORTED_OR_EXPLICITLY_RECORDED_EXACT_COST_IS_SUMMED",
        "no_spend_estimate_invented": True,
        "enforcement_hooks_connected": binding,
        "binding_xai_grok_hook": binding,
        "policy": dict(POLICY),
        "today": {
            "requests": len(today),
            "priced_requests": sum(1 for row in today if _float(row.get("cost_usd")) is not None),
            "exact_spend_usd": daily_exact if today else None,
            "input_tokens": sum(_int(row.get("input_tokens")) for row in today),
            "cached_input_tokens": sum(_int(row.get("cached_input_tokens")) for row in today),
            "output_tokens": sum(_int(row.get("output_tokens")) for row in today),
            "web_search_calls": sum(_int(row.get("web_search_calls")) for row in today),
            "x_search_calls": sum(_int(row.get("x_search_calls")) for row in today),
        },
        "rolling_7d": {
            "requests": len(week),
            "priced_requests": len(priced),
            "unpriced_requests": unpriced,
            "exact_cost_coverage_pct": coverage,
            "exact_spend_usd": weekly_exact if week else None,
            "input_tokens": sum(_int(row.get("input_tokens")) for row in week),
            "cached_input_tokens": sum(_int(row.get("cached_input_tokens")) for row in week),
            "output_tokens": sum(_int(row.get("output_tokens")) for row in week),
            "web_search_calls": sum(_int(row.get("web_search_calls")) for row in week),
            "x_search_calls": sum(_int(row.get("x_search_calls")) for row in week),
        },
        "breakdowns": {
            "provider": _breakdown(week, "provider"),
            "model": _breakdown(week, "model"),
            "task_type": _breakdown(week, "task_type"),
            "agent": _breakdown(week, "agent"),
        },
        "recent_request_index": {"expensive_calls_last_hour": len(hour), "by_case": dict(by_case), "fingerprints": fingerprints},
        "measurement_gaps": (
            (["NO_POST_HOOK_XAI_REQUEST_RECORDED_YET"] if binding and not events else [])
            + (["NO_LOCAL_MODEL_USAGE_LEDGER_YET"] if not binding and not events else [])
            + (["SOME_REQUESTS_HAVE_NO_PROVIDER_REPORTED_EXACT_COST"] if unpriced else [])
            + ([] if binding else ["ADMISSION_POLICY_IS_ADVISORY_UNTIL_CALL_SITES_ARE_EXPLICITLY_INSTRUMENTED"])
        ),
        "safety": {
            "advisory_only": not binding,
            "spend_measurement_only": True,
            "scope": "XAI_GROK_RESEARCH_COST_ONLY" if binding else "MODEL_TOOL_COST_OBSERVABILITY",
            "auto_change_model_routing": False,
            "auto_change_provider": False,
            "auto_disable_models": False,
            "auto_restart_workers": False,
            "broker_connection_authority": False,
            "capital_authority": False,
            "trade_execution_permission": False,
            "live_execution": False,
            "human_approval_required": True,
            "no_model_weight_change": True,
            "no_portfolio_change": True,
        },
    }
    return artifact


def main() -> int:
    parser = argparse.ArgumentParser(description="Build IIOS exact-cost model/tool usage governor artifact without downgrading a binding Grok hook.")
    parser.add_argument("--cost-dir", default=str(DEFAULT_COST_DIR))
    args = parser.parse_args()
    cost_dir = Path(args.cost_dir).expanduser()
    payload = build_governor(cost_dir)
    _atomic_write(cost_dir / ARTIFACT_NAME, payload)
    print(json.dumps({
        "status": payload["status"],
        "budget_state": payload["budget_state"],
        "exact_cost_coverage_pct": (payload.get("rolling_7d") or {}).get("exact_cost_coverage_pct"),
        "rolling_7d_exact_spend_usd": (payload.get("rolling_7d") or {}).get("exact_spend_usd"),
        "enforcement_hooks_connected": payload["enforcement_hooks_connected"],
        "binding_xai_grok_hook": payload.get("binding_xai_grok_hook"),
        "live_execution": False,
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
