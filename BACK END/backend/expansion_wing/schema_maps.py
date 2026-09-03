from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _time(payload: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = payload.get(key)
        if value:
            return str(value)
    return None


@dataclass(frozen=True)
class SchemaContract:
    name: str
    versions: tuple[str, ...]
    mapper: Callable[[dict[str, Any]], dict[str, Any]]

    def map(self, payload: Any) -> dict[str, Any]:
        if not isinstance(payload, dict):
            return {"complete": False, "errors": ["MALFORMED_ROOT"], "data": {}}
        version = str(payload.get("schema_version") or "LEGACY_UNVERSIONED")
        mapped = self.mapper(payload)
        errors = list(mapped.pop("errors", []))
        if version not in self.versions:
            errors.append("LEGACY_OR_UNKNOWN_SCHEMA")
        return {"observed_at": mapped.pop("observed_at", None), "complete": not errors,
                "errors": sorted(set(errors)), "schema_version": version, "data": mapped}


def _worker(payload: dict[str, Any], completed_key: str) -> dict[str, Any]:
    return {"observed_at": _time(payload, completed_key, "generated_at", "created_at"),
            "status": payload.get("status") or ("ENABLED" if payload.get("enabled") is True else "UNKNOWN"), "cycle_id": payload.get("cycle_id") or payload.get("last_cycle_id") or payload.get("observation_operations_state_id") or payload.get("paper_trading_operations_state_id"),
            "counts": _dict(payload.get("counts")), "errors": [] if _time(payload, completed_key, "generated_at", "created_at") else ["MISSING_TIMESTAMP"]}


def _nine_e(payload: dict[str, Any]) -> dict[str, Any]:
    return {"observed_at": _time(payload, "last_cycle_completed_at", "generated_at", "created_at"),
            "last_cycle_id": payload.get("last_cycle_id"), "governed_universe_count": payload.get("governed_universe_count"),
            "screener_hit_count": payload.get("screener_hit_count"), "promotion_candidate_count": payload.get("promotion_candidate_count"),
            "promoted_case_count": payload.get("promoted_case_count"),
            "errors": [] if _time(payload, "last_cycle_completed_at", "generated_at", "created_at") else ["MISSING_TIMESTAMP"]}


def _nine_h(payload: dict[str, Any]) -> dict[str, Any]:
    metrics = _dict(payload.get("metrics"))
    opportunities = _list(payload.get("opportunities"))
    return {"observed_at": _time(payload, "observed_at", "generated_at", "created_at"), "session_id": payload.get("session_id"),
            "benchmark_complete": bool(payload.get("benchmark_complete")), "opportunities": opportunities,
            "opportunity_count": metrics.get("opportunity_count", len(opportunities)), "detected_count": metrics.get("detected_count"),
            "missed_count": metrics.get("missed_count"), "miss_rate_pct": metrics.get("opportunity_miss_rate_pct"),
            "errors": (["MISSING_SESSION_ID"] if not payload.get("session_id") else [])
            + (["BENCHMARK_INCOMPLETE"] if payload.get("benchmark_complete") is not True else [])}


def _nine_i(payload: dict[str, Any]) -> dict[str, Any]:
    complete_sessions = payload.get("complete_session_count")
    minimum_sessions = payload.get("minimum_complete_sessions_for_advice")
    errors = [] if payload.get("status") else ["MISSING_STATUS"]
    if not isinstance(complete_sessions, int) or not isinstance(minimum_sessions, int):
        errors.append("MISSING_WARMUP_COUNTS")
    elif complete_sessions < minimum_sessions:
        errors.append("WARMUP_INCOMPLETE")
    return {"observed_at": _time(payload, "generated_at", "created_at"), "status": payload.get("status") or "UNKNOWN",
            "complete_session_count": complete_sessions, "minimum_complete_sessions_for_advice": minimum_sessions,
            "session_ids": _list(payload.get("session_ids")), "policies": _dict(payload.get("policies")),
            "errors": errors}


def _nine_j(payload: dict[str, Any]) -> dict[str, Any]:
    return {"observed_at": _time(payload, "generated_at", "created_at"), "status": payload.get("status") or "UNKNOWN",
            "complete_session_count": payload.get("complete_session_count"), "outcome_count": payload.get("outcome_count"),
            "market_outcome_counts": _dict(payload.get("market_outcome_counts")), "recent_outcomes": _list(payload.get("recent_outcomes"))[:20],
            "errors": [] if payload.get("status") else ["MISSING_STATUS"]}


def _paper(payload: dict[str, Any]) -> dict[str, Any]:
    starting = payload.get("starting_cash")
    return {"observed_at": _time(payload, "generated_at", "created_at", "snapshot_as_of"),
            "account_id": payload.get("paper_portfolio_account_id") or payload.get("account_id"),
            "starting_cash": starting, "cash": payload.get("cash"), "nav": payload.get("nav") or payload.get("equity"),
            "realized_pnl": payload.get("realized_pnl"), "unrealized_pnl": payload.get("unrealized_pnl"),
            "positions": _list(payload.get("positions")), "position_count": payload.get("position_count"),
            "errors": [] if float(starting or 0) == 10_000 else ["PAPER_FUND_NOT_10000"]}


CONTRACTS = {
    "9a": SchemaContract("9a", ("batch9a-observation-v1", "LEGACY_UNVERSIONED"), lambda p: _worker(p, "last_cycle_completed_at")),
    "9b": SchemaContract("9b", ("batch9b-paper-trading-v1", "LEGACY_UNVERSIONED"), lambda p: _worker(p, "cycle_completed_at")),
    "9e": SchemaContract("9e", ("batch9e-high-speed-radar-v1", "LEGACY_UNVERSIONED"), _nine_e),
    "9h": SchemaContract("9h", ("batch9h-independent-market-benchmark-v1", "batch9g-market-validation-scorecard-v1"), _nine_h),
    "9i": SchemaContract("9i", ("batch9i-remote-shadow-strategy-v1", "batch9i-shadow-counterfactual-rollup-v1"), _nine_i),
    "9j": SchemaContract("9j", ("batch9j-browser-outcome-summary-v1", "batch9j-outcome-learning-memory-v1"), _nine_j),
    "paper_fund": SchemaContract("paper_fund", ("paper-portfolio-core-v1", "LEGACY_UNVERSIONED"), _paper),
}
