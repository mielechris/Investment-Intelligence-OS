from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from factory_telemetry import (
    _connect_read_only,
    _fingerprint,
    _resolve_db_path,
    _rows_by_type,
    build_factory_telemetry as _build_batch9f_telemetry,
    build_unavailable_telemetry as _build_batch9f_unavailable,
)

SCHEMA_VERSION = "batch9g-factory-telemetry-v2"
DEFAULT_HEARTBEAT_SECONDS = 300
PAPER_FILL_OBJECT_TYPE = "paper_portfolio_transaction"
PAPER_FILL_EVENT_TYPE = "PAPER_PORTFOLIO_TRANSACTION_INGESTED"


def _safe_limit(value: int, *, default: int = 10, maximum: int = 100) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(1, min(parsed, maximum))


def _recent_paper_fills(
    connection,
    *,
    limit: int = 10,
) -> list[dict[str, Any]]:
    rows = _rows_by_type(
        connection,
        PAPER_FILL_OBJECT_TYPE,
        limit=max(_safe_limit(limit) * 3, 20),
    )
    output: list[dict[str, Any]] = []
    for row in rows:
        if not row.get("source_execution_id"):
            continue
        output.append(
            {
                "fill_id": row.get("paper_portfolio_transaction_id"),
                "source_execution_id": row.get("source_execution_id"),
                "source_case_id": row.get("source_case_id"),
                "ticker": row.get("ticker"),
                "side": row.get("side"),
                "direction": row.get("direction"),
                "quantity": row.get("quantity"),
                "price": row.get("price"),
                "notional": row.get("notional"),
                "created_at": row.get("created_at")
                or row.get("_ledger_created_at"),
                "fill_status": "CONFIRMED_PAPER_FILL",
                "fill_semantics": "PERSISTED_GOVERNED_PAPER_TRANSACTION",
                "paper_mode": True,
                "live_execution": False,
            }
        )
        if len(output) >= _safe_limit(limit):
            break
    return output


def build_factory_telemetry(
    db_path: str | os.PathLike[str] | None = None,
    *,
    promotion_limit: int = 10,
    event_limit: int = 30,
    fill_limit: int = 10,
) -> dict[str, Any]:
    path: Path = _resolve_db_path(db_path)
    snapshot = _build_batch9f_telemetry(
        path,
        promotion_limit=promotion_limit,
        event_limit=event_limit,
    )

    with _connect_read_only(path) as connection:
        fills = _recent_paper_fills(connection, limit=fill_limit)

    snapshot["schema_version"] = SCHEMA_VERSION
    snapshot["recent_paper_fills"] = fills
    snapshot["telemetry_contract"] = {
        "version": SCHEMA_VERSION,
        "meaningful_state_fingerprint": True,
        "heartbeat_expected_seconds": DEFAULT_HEARTBEAT_SECONDS,
        "paper_fill_object_type": PAPER_FILL_OBJECT_TYPE,
        "paper_fill_event_type": PAPER_FILL_EVENT_TYPE,
        "paper_fill_semantics": "SIMULATED_GOVERNED_PAPER_FILL",
        "live_execution": False,
    }

    snapshot.pop("fingerprint", None)
    snapshot["fingerprint"] = _fingerprint(snapshot)
    return snapshot


def build_unavailable_telemetry(error: BaseException) -> dict[str, Any]:
    snapshot = _build_batch9f_unavailable(error)
    snapshot["schema_version"] = SCHEMA_VERSION
    snapshot["telemetry_contract"] = {
        "version": SCHEMA_VERSION,
        "meaningful_state_fingerprint": True,
        "heartbeat_expected_seconds": DEFAULT_HEARTBEAT_SECONDS,
        "paper_fill_object_type": PAPER_FILL_OBJECT_TYPE,
        "paper_fill_event_type": PAPER_FILL_EVENT_TYPE,
        "live_execution": False,
    }
    snapshot.pop("fingerprint", None)
    snapshot["fingerprint"] = _fingerprint(snapshot)
    return snapshot
