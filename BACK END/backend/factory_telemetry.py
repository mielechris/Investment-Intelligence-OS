from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

from radar_candidate_projection import project_candidate_lineage

SCHEMA_VERSION = "batch9f-factory-telemetry-v1"

DEFAULT_DB_PATH = Path(__file__).resolve().parent / "iios_ledger.db"

RADAR_CASE_ID = "high_speed_market_radar"
OBSERVATION_CASE_ID = "observation_operations"
PAPER_TRADING_CASE_ID = "paper_trading_operations"
PAPER_PORTFOLIO_CASE_ID = "paper_portfolio"
PAPER_ACCOUNT_ID = "paper_portfolio_default"

RADAR_STATE_TYPE = "high_speed_market_radar_state"
RADAR_CYCLE_TYPE = "high_speed_market_radar_cycle"
MODEL_CONTEXT_TYPE = "high_speed_market_model_context"
OBSERVATION_STATE_TYPE = "observation_operations_state"
PAPER_TRADING_STATE_TYPE = "governed_paper_trading_state"

DEFAULT_STARTING_CASH = 10_000.0
DEFAULT_RADAR_CADENCE_MINUTES = 5
DEFAULT_OBSERVATION_CADENCE_MINUTES = 15
DEFAULT_PAPER_TRADING_CADENCE_MINUTES = 15
DEFAULT_GRACE_MINUTES = 5

MEANINGFUL_EVENT_TYPES = {
    "OPPORTUNITY_PROMOTED_TO_CASE",
    "COMMITTEE_COMPLETE",
    "RISK_COMPLETE",
    "GOVERNED_PAPER_ORDER_CREATED",
    "AUTO_MONITOR_FAILED",
    "OPPORTUNITY_AUTOMATION_CYCLE_FAILED",
    "HIGH_SPEED_MARKET_RADAR_COMPLETE",
}

_DYNAMIC_FINGERPRINT_KEYS = {
    "generated_at",
    "seconds_since_last_cycle",
    "seconds_until_next_cycle",
    "age_seconds",
    "fingerprint",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _parse_time(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _resolve_db_path(db_path: str | os.PathLike[str] | None = None) -> Path:
    if db_path is not None:
        return Path(db_path).expanduser().resolve()
    configured = os.getenv("IIOS_DB_PATH")
    if configured:
        return Path(configured).expanduser().resolve()
    return DEFAULT_DB_PATH.resolve()


def _connect_read_only(db_path: Path) -> sqlite3.Connection:
    if not db_path.exists():
        raise FileNotFoundError(f"IIOS ledger not found: {db_path}")
    # mode=ro is an enforcement boundary: telemetry cannot mutate the ledger.
    uri = f"file:{quote(str(db_path), safe='/')}?mode=ro"
    connection = sqlite3.connect(uri, uri=True, timeout=30)
    connection.row_factory = sqlite3.Row
    return connection


def _decode_payload(row: sqlite3.Row | None) -> dict[str, Any]:
    if row is None:
        return {}
    try:
        payload = json.loads(row["payload_json"])
    except (TypeError, json.JSONDecodeError, KeyError):
        return {}
    if not isinstance(payload, dict):
        return {}
    created_at = row["created_at"] if "created_at" in row.keys() else None
    return {
        **payload,
        "_ledger_created_at": created_at,
    }


def _rows_by_type(
    connection: sqlite3.Connection,
    object_type: str,
    *,
    limit: int = 100,
    case_id: str | None = None,
    ascending: bool = False,
) -> list[dict[str, Any]]:
    clauses = ["object_type = ?"]
    params: list[Any] = [object_type]
    if case_id is not None:
        clauses.append("case_id = ?")
        params.append(case_id)
    params.append(max(1, min(int(limit), 5000)))
    order = "ASC" if ascending else "DESC"
    rows = connection.execute(
        "SELECT payload_json, created_at "
        "FROM ledger_objects WHERE "
        + " AND ".join(clauses)
        + f" ORDER BY created_at {order} LIMIT ?",
        params,
    ).fetchall()
    return [_decode_payload(row) for row in rows]


def _latest(
    connection: sqlite3.Connection,
    object_type: str,
    *,
    case_id: str | None = None,
) -> dict[str, Any]:
    rows = _rows_by_type(
        connection,
        object_type,
        limit=1,
        case_id=case_id,
    )
    return rows[0] if rows else {}


def _get_object(
    connection: sqlite3.Connection,
    object_id: str | None,
) -> dict[str, Any]:
    if not object_id:
        return {}
    row = connection.execute(
        "SELECT payload_json, created_at "
        "FROM ledger_objects WHERE object_id = ? LIMIT 1",
        (str(object_id),),
    ).fetchone()
    return _decode_payload(row)


def _cadence_summary(
    *,
    worker: str,
    last_completed_at: Any,
    cadence_minutes: int,
    now: datetime,
    grace_minutes: int = DEFAULT_GRACE_MINUTES,
) -> dict[str, Any]:
    cadence = max(1, int(cadence_minutes or 1))
    completed = _parse_time(last_completed_at)
    if completed is None:
        return {
            "worker": worker,
            "availability": "NO_STATE",
            "cadence_minutes": cadence,
            "last_completed_at": None,
            "next_due_at": None,
            "seconds_since_last_cycle": None,
            "seconds_until_next_cycle": None,
            "cadence_state": "UNKNOWN",
        }

    next_due = completed + timedelta(minutes=cadence)
    overdue_after = next_due + timedelta(minutes=max(0, grace_minutes))
    seconds_since = max(0, int((now - completed).total_seconds()))
    seconds_until = max(0, int((next_due - now).total_seconds()))
    return {
        "worker": worker,
        "availability": "AVAILABLE",
        "cadence_minutes": cadence,
        "last_completed_at": completed.isoformat(),
        "next_due_at": next_due.isoformat(),
        "seconds_since_last_cycle": seconds_since,
        "seconds_until_next_cycle": seconds_until,
        "cadence_state": "ON_CADENCE" if now <= overdue_after else "OVERDUE",
    }


def _provider_health(
    connection: sqlite3.Connection,
) -> dict[str, Any]:
    model = _latest(
        connection,
        MODEL_CONTEXT_TYPE,
        case_id=RADAR_CASE_ID,
    )
    cycle = _latest(
        connection,
        RADAR_CYCLE_TYPE,
        case_id=RADAR_CASE_ID,
    )
    fast_sweep = cycle.get("fast_sweep")
    fast_sweep = fast_sweep if isinstance(fast_sweep, dict) else {}
    provider_errors = fast_sweep.get("provider_errors")
    provider_errors = (
        [str(item)[:500] for item in provider_errors]
        if isinstance(provider_errors, list)
        else []
    )

    def clean_status(value: Any) -> dict[str, Any]:
        value = value if isinstance(value, dict) else {}
        return {
            key: value.get(key)
            for key in (
                "configured",
                "provider",
                "model",
                "preferred_model",
                "fallback_model",
                "status",
            )
            if key in value
        }

    return {
        "grok": clean_status(model.get("grok_provider")),
        "gemini": clean_status(
            model.get("gemini_provider")
            or model.get("kimi_provider")
        ),
        "provider_errors": provider_errors,
        "provider_error_count": len(provider_errors),
    }


def _paper_portfolio(
    connection: sqlite3.Connection,
) -> dict[str, Any]:
    snapshots = _rows_by_type(
        connection,
        "paper_portfolio_snapshot",
        limit=1000,
        case_id=PAPER_PORTFOLIO_CASE_ID,
        ascending=True,
    )
    account = _get_object(connection, PAPER_ACCOUNT_ID)
    latest = snapshots[-1] if snapshots else {}

    starting_cash = _safe_float(
        latest.get("starting_cash"),
        _safe_float(account.get("starting_cash"), DEFAULT_STARTING_CASH),
    )
    nav = _safe_float(latest.get("nav"), starting_cash)

    high_water = starting_cash
    max_drawdown_pct = 0.0
    current_drawdown_pct = 0.0
    for snapshot in snapshots:
        one_nav = _safe_float(snapshot.get("nav"), starting_cash)
        high_water = max(high_water, one_nav)
        current_drawdown_pct = (
            ((one_nav / high_water) - 1.0) * 100.0
            if high_water > 0
            else 0.0
        )
        max_drawdown_pct = min(max_drawdown_pct, current_drawdown_pct)

    positions = latest.get("positions")
    positions = positions if isinstance(positions, list) else []
    clean_positions = []
    for position in positions[:50]:
        if not isinstance(position, dict):
            continue
        clean_positions.append(
            {
                "ticker": position.get("ticker"),
                "direction": position.get("direction"),
                "quantity": position.get("quantity"),
                "average_cost": position.get("average_cost"),
                "mark_price": position.get("mark_price"),
                "market_value": position.get("market_value"),
                "unrealized_pnl": position.get("unrealized_pnl"),
                "unrealized_return_pct": position.get(
                    "unrealized_return_pct"
                ),
            }
        )

    cumulative_return_pct = (
        ((nav / starting_cash) - 1.0) * 100.0
        if starting_cash > 0
        else 0.0
    )

    return {
        "snapshot_id": latest.get("paper_portfolio_snapshot_id"),
        "snapshot_as_of": latest.get("created_at")
        or latest.get("_ledger_created_at"),
        "starting_cash": round(starting_cash, 2),
        "nav": round(nav, 2),
        "cash": round(
            _safe_float(latest.get("cash"), starting_cash),
            2,
        ),
        "market_value": round(
            _safe_float(latest.get("market_value")),
            2,
        ),
        "realized_pnl": round(
            _safe_float(latest.get("realized_pnl")),
            2,
        ),
        "unrealized_pnl": round(
            _safe_float(latest.get("unrealized_pnl")),
            2,
        ),
        "total_pnl": round(
            _safe_float(latest.get("total_pnl")),
            2,
        ),
        "gross_exposure": round(
            _safe_float(latest.get("gross_exposure")),
            2,
        ),
        "position_count": _safe_int(
            latest.get("position_count"),
            len(clean_positions),
        ),
        "transaction_count": _safe_int(
            latest.get("transaction_count"),
            0,
        ),
        "positions": clean_positions,
        "snapshot_count": len(snapshots),
        "cumulative_return_pct": round(cumulative_return_pct, 4),
        "current_drawdown_pct": round(current_drawdown_pct, 4),
        "max_drawdown_pct": round(max_drawdown_pct, 4),
        "data_source": "PERSISTED_GOVERNED_PAPER_SNAPSHOTS_ONLY",
    }


def _recent_paper_orders(
    connection: sqlite3.Connection,
    *,
    limit: int = 10,
) -> list[dict[str, Any]]:
    rows = _rows_by_type(
        connection,
        "governed_paper_execution",
        limit=max(limit * 3, 20),
    )
    output: list[dict[str, Any]] = []
    for row in rows:
        if row.get("execution") != "PAPER_ORDER_CREATED":
            continue
        output.append(
            {
                "execution_id": row.get("execution_id"),
                "case_id": row.get("case_id"),
                "status": row.get("status"),
                "execution": row.get("execution"),
                "shares": row.get("shares"),
                "entry_price": row.get("entry_price"),
                "notional": row.get("notional"),
                "created_at": row.get("created_at")
                or row.get("_ledger_created_at"),
            }
        )
        if len(output) >= limit:
            break
    return output


def _case_lineage(
    connection: sqlite3.Connection,
    candidate: dict[str, Any],
) -> dict[str, Any]:
    case_id = str(candidate.get("promoted_case_id") or "").strip()
    case = _get_object(connection, case_id)
    agents = _rows_by_type(
        connection,
        "agent_result",
        limit=100,
        case_id=case_id,
    )
    unique_agent_keys = sorted(
        {
            str(row.get("agent_key") or "").strip()
            for row in agents
            if str(row.get("agent_key") or "").strip()
        }
    )
    committee = _latest(
        connection,
        "committee_decision",
        case_id=case_id,
    )
    risk = _latest(
        connection,
        "risk_authorization",
        case_id=case_id,
    )
    execution = _latest(
        connection,
        "governed_paper_execution",
        case_id=case_id,
    )
    qualification = _latest(
        connection,
        "qualification_assessment",
        case_id=case_id,
    )

    return {
        "case_id": case_id,
        "ticker": candidate.get("ticker"),
        "topic": case.get("topic"),
        "source_candidate_id": candidate.get(
            "opportunity_candidate_id"
        ),
        "promoted_at": candidate.get("promoted_at"),
        "opportunity_score": candidate.get("score"),
        "radar_rank_score": candidate.get("radar_rank_score"),
        "priority": candidate.get("priority"),
        "agents": {
            "completed_count": len(unique_agent_keys),
            "agent_keys": unique_agent_keys,
            "eight_agent_complete": len(unique_agent_keys) >= 8,
        },
        "committee": {
            "decision_id": committee.get("decision_id"),
            "disposition": committee.get("disposition"),
            "confidence": committee.get("confidence"),
            "created_at": committee.get("created_at")
            or committee.get("_ledger_created_at"),
        },
        "qualification": {
            "assessment_id": qualification.get(
                "qualification_assessment_id"
            )
            or qualification.get("assessment_id"),
            "qualified_buy_candidate": qualification.get(
                "qualified_buy_candidate"
            ),
            "created_at": qualification.get("created_at")
            or qualification.get("_ledger_created_at"),
        },
        "risk": {
            "risk_authorization_id": risk.get(
                "risk_authorization_id"
            ),
            "decision": risk.get("decision"),
            "triggered_rules": (
                risk.get("triggered_rules")
                if isinstance(risk.get("triggered_rules"), list)
                else []
            ),
            "created_at": risk.get("created_at")
            or risk.get("_ledger_created_at"),
        },
        "paper_execution": {
            "execution_id": execution.get("execution_id"),
            "status": execution.get("status"),
            "execution": execution.get("execution"),
            "shares": execution.get("shares"),
            "entry_price": execution.get("entry_price"),
            "notional": execution.get("notional"),
            "created_at": execution.get("created_at")
            or execution.get("_ledger_created_at"),
        },
    }


def _recent_promotions(
    connection: sqlite3.Connection,
    *,
    limit: int = 10,
) -> list[dict[str, Any]]:
    # Candidate rows keep their original created_at after promotion, so sort
    # on promoted_at in Python rather than trusting ledger row order.
    candidates = _rows_by_type(
        connection,
        "opportunity_candidate",
        limit=5000,
    )
    promoted = [
        row
        for row in candidates
        if row.get("promoted_case_id") and row.get("promoted_at")
    ]
    promoted.sort(
        key=lambda row: _parse_time(row.get("promoted_at"))
        or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    return [
        _case_lineage(connection, row)
        for row in promoted[: max(1, min(limit, 50))]
    ]


def _recent_events(
    connection: sqlite3.Connection,
    *,
    limit: int = 30,
) -> list[dict[str, Any]]:
    placeholders = ",".join("?" for _ in MEANINGFUL_EVENT_TYPES)
    rows = connection.execute(
        f"SELECT case_id, event_type, entity_id, payload_json, created_at "
        f"FROM audit_events WHERE event_type IN ({placeholders}) "
        "ORDER BY created_at DESC LIMIT ?",
        [*sorted(MEANINGFUL_EVENT_TYPES), max(1, min(limit, 100))],
    ).fetchall()

    allowed_payload_keys = {
        "ticker",
        "opportunity_score",
        "confidence",
        "disposition",
        "decision",
        "triggered_rules",
        "status",
        "execution",
        "shares",
        "entry_price",
        "notional",
        "radar_event_count",
        "scanned_count",
        "queued_count",
        "promoted_case_count",
        "error",
    }
    output: list[dict[str, Any]] = []
    for row in rows:
        try:
            payload = json.loads(row["payload_json"])
        except (TypeError, json.JSONDecodeError):
            payload = {}
        payload = payload if isinstance(payload, dict) else {}
        output.append(
            {
                "case_id": row["case_id"],
                "event_type": row["event_type"],
                "entity_id": row["entity_id"],
                "payload": {
                    key: payload.get(key)
                    for key in allowed_payload_keys
                    if key in payload
                },
                "created_at": row["created_at"],
            }
        )
    return output


def _stable_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _stable_value(item)
            for key, item in sorted(value.items())
            if key not in _DYNAMIC_FINGERPRINT_KEYS
        }
    if isinstance(value, list):
        return [_stable_value(item) for item in value]
    return value


def _fingerprint(snapshot: dict[str, Any]) -> str:
    stable = _stable_value(snapshot)
    encoded = json.dumps(
        stable,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_factory_telemetry(
    db_path: str | os.PathLike[str] | None = None,
    *,
    promotion_limit: int = 10,
    event_limit: int = 30,
) -> dict[str, Any]:
    path = _resolve_db_path(db_path)
    now = datetime.now(timezone.utc)

    with _connect_read_only(path) as connection:
        radar = _latest(
            connection,
            RADAR_STATE_TYPE,
            case_id=RADAR_CASE_ID,
        )
        radar_cycle = _get_object(connection, radar.get("last_cycle_id"))
        candidate_lineage = project_candidate_lineage(radar, radar_cycle, now=now)
        observation = _latest(
            connection,
            OBSERVATION_STATE_TYPE,
            case_id=OBSERVATION_CASE_ID,
        )
        paper_trading = _latest(
            connection,
            PAPER_TRADING_STATE_TYPE,
            case_id=PAPER_TRADING_CASE_ID,
        )

        radar_cadence = _safe_int(
            os.getenv("IIOS_9F_RADAR_EXPECTED_MINUTES"),
            DEFAULT_RADAR_CADENCE_MINUTES,
        )
        observation_cadence = _safe_int(
            observation.get("cycle_minutes"),
            DEFAULT_OBSERVATION_CADENCE_MINUTES,
        )
        paper_trading_cadence = _safe_int(
            os.getenv("IIOS_9F_PAPER_TRADING_EXPECTED_MINUTES"),
            DEFAULT_PAPER_TRADING_CADENCE_MINUTES,
        )

        cadence = {
            "radar": _cadence_summary(
                worker="BATCH_9E_HIGH_SPEED_RADAR",
                last_completed_at=radar.get(
                    "last_cycle_completed_at"
                ),
                cadence_minutes=radar_cadence,
                now=now,
            ),
            "observation": _cadence_summary(
                worker="BATCH_9A_OBSERVATION",
                last_completed_at=observation.get(
                    "last_cycle_completed_at"
                ),
                cadence_minutes=observation_cadence,
                now=now,
            ),
            "paper_trading": _cadence_summary(
                worker="BATCH_9B_PAPER_TRADING",
                last_completed_at=paper_trading.get(
                    "cycle_completed_at"
                ),
                cadence_minutes=paper_trading_cadence,
                now=now,
            ),
        }

        providers = _provider_health(connection)
        portfolio = _paper_portfolio(connection)
        promotions = _recent_promotions(
            connection,
            limit=promotion_limit,
        )
        orders = _recent_paper_orders(connection, limit=10)
        events = _recent_events(connection, limit=event_limit)

        health_flags: list[str] = []
        for name, worker in cadence.items():
            state = worker.get("cadence_state")
            if state == "OVERDUE":
                health_flags.append(f"CADENCE_OVERDUE:{name.upper()}")
            elif state == "UNKNOWN":
                health_flags.append(f"CADENCE_UNKNOWN:{name.upper()}")
        if providers.get("provider_error_count"):
            health_flags.append("PROVIDER_ERRORS_PRESENT")

        snapshot: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "generated_at": utc_now(),
            "source": {
                "mode": "LOCAL_LEDGER_READ_ONLY",
                "ledger_name": path.name,
                "ledger_path_exported": False,
                "raw_prompts_exported": False,
                "raw_evidence_exported": False,
                "secrets_exported": False,
            },
            "radar": {
                "last_cycle_id": radar.get("last_cycle_id"),
                "last_cycle_completed_at": radar.get(
                    "last_cycle_completed_at"
                ),
                "governed_universe_count": radar.get(
                    "governed_universe_count"
                ),
                "screener_hit_count": radar.get(
                    "screener_hit_count"
                ),
                "grok_candidate_count": radar.get(
                    "grok_candidate_count"
                ),
                "gemini_candidate_count": radar.get(
                    "gemini_candidate_count"
                )
                or radar.get("kimi_candidate_count"),
                "promotion_candidate_count": candidate_lineage["promotion_candidate_count"],
                "candidate_lineage_state": candidate_lineage["state"],
                "candidate_lineage_reason": candidate_lineage["reason"],
                "candidate_source_cycle_id": candidate_lineage["source_cycle_id"],
                "candidate_source_artifact_hash": candidate_lineage["source_artifact_hash"],
                "candidate_batch": candidate_lineage["candidate_batch"],
                "promoted_case_count": radar.get(
                    "promoted_case_count"
                ),
                "cycle_duration_seconds": radar.get(
                    "cycle_duration_seconds"
                ),
                "deep_research_duration_seconds": radar.get(
                    "deep_research_duration_seconds"
                ),
            },
            "providers": providers,
            "cadence": cadence,
            "recent_promotions": promotions,
            "paper_fund": portfolio,
            "recent_paper_orders": orders,
            "recent_meaningful_events": events,
            "health": {
                "state": "ATTENTION"
                if health_flags
                else "HEALTHY",
                "flags": health_flags,
            },
            "safety": {
                "paper_mode": True,
                "broker_connected": False,
                "live_capital_locked": True,
                "telemetry_read_only": True,
                "committee_override": False,
                "risk_override": False,
                "capital_override": False,
                "trade_execution_permission": False,
                "live_execution": False,
            },
        }

    snapshot["fingerprint"] = _fingerprint(snapshot)
    return snapshot


def build_unavailable_telemetry(
    error: BaseException,
) -> dict[str, Any]:
    snapshot = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": utc_now(),
        "source": {
            "mode": "LOCAL_LEDGER_READ_ONLY",
            "available": False,
        },
        "health": {
            "state": "TELEMETRY_UNAVAILABLE",
            "flags": [
                f"{type(error).__name__}:{str(error)[:500]}"
            ],
        },
        "safety": {
            "paper_mode": True,
            "telemetry_read_only": True,
            "trade_execution_permission": False,
            "live_execution": False,
        },
    }
    snapshot["fingerprint"] = _fingerprint(snapshot)
    return snapshot
