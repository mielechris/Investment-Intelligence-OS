#!/usr/bin/env python3
"""Acceptance checks for the Batch 10 resilience + learning foundation."""

from __future__ import annotations

import json
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "BACK END" / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from decision_journal import DecisionEvent, DecisionJournal  # noqa: E402
from resilience_health import (  # noqa: E402
    CRITICAL_FOR_PAPER,
    HealthStatus,
    HeartbeatRegistry,
    fail_closed_if_unready,
)


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_health_freshness_and_fail_closed() -> None:
    now = datetime(2026, 8, 27, 17, 0, tzinfo=timezone.utc)
    registry = HeartbeatRegistry()

    starting = registry.snapshot(now=now)
    check(starting["market_data"].status is HealthStatus.STARTING, "unknown health must STARTING")
    check(registry.paper_execution_readiness(now=now)["ready"] is False, "startup must fail closed")

    for component in CRITICAL_FOR_PAPER:
        registry.record_success(component, at=now, payload_valid=True)

    ready = registry.paper_execution_readiness(now=now)
    check(ready["ready"] is True, "fresh validated critical inputs should allow governed paper readiness")
    check(ready["broker_connected"] is False, "broker invariant changed")
    check(ready["live_execution"] is False, "live-capital invariant changed")

    stale_time = now + timedelta(seconds=1800)
    stale = registry.snapshot(now=stale_time)
    check(stale["market_data"].status is HealthStatus.STALE, "stale market data not detected")
    check(registry.paper_execution_readiness(now=stale_time)["ready"] is False, "stale critical data must fail closed")

    try:
        fail_closed_if_unready(registry, now=stale_time)
    except RuntimeError as exc:
        check("quarantined" in str(exc), "fail-closed exception must explain quarantine")
    else:
        raise AssertionError("fail_closed_if_unready did not block stale inputs")


def test_invalid_payload_is_degraded() -> None:
    now = datetime.now(timezone.utc)
    registry = HeartbeatRegistry()
    registry.record_failure("gpt", at=now, reason="invalid response schema")
    state = registry.snapshot(now=now)["gpt"]
    check(state.status is HealthStatus.DEGRADED, "invalid payload must not appear healthy")
    check(state.payload_valid is False, "invalid payload flag lost")


def test_journal_captures_no_trade_and_shadow_counterfactual() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        journal = DecisionJournal(Path(temp_dir) / "decision-journal.jsonl")
        journal.append(DecisionEvent(
            case_id="case-avgo-001",
            ticker="avgo",
            event_type="PROMOTED",
            score=74,
            stage="9A",
            market_regime="NARROW_LEADERSHIP",
            reason="candidate cleared observation threshold",
        ))
        journal.append_no_trade(
            case_id="case-avgo-001",
            ticker="AVGO",
            reason="committee no-trade and risk veto",
            stage="RISK",
            score=74,
        )
        journal.append_counterfactual(
            case_id="case-avgo-001",
            ticker="AVGO",
            reason="evaluate veto value without portfolio impact",
            proposed_entry=350.0,
            proposed_stop=340.0,
            proposed_target=370.0,
            horizon="1h",
        )

        records = journal.read_recent()
        check(len(records) == 3, "journal dropped events")
        check(records[1]["event_type"] == "NO_TRADE", "NO_TRADE not journaled")
        check(records[2]["shadow_only"] is True, "counterfactual not shadow-only")
        check(records[2]["metadata"]["portfolio_effect"] == "NONE", "shadow ledger gained portfolio authority")
        check(all(r["broker_connected"] is False for r in records), "journal changed broker invariant")
        check(all(r["live_execution"] is False for r in records), "journal changed live invariant")

        raw_lines = (Path(temp_dir) / "decision-journal.jsonl").read_text(encoding="utf-8").splitlines()
        check(len(raw_lines) == 3, "journal is not append-only one-event-per-line")
        for line in raw_lines:
            json.loads(line)


def test_shadow_cannot_impersonate_execution() -> None:
    try:
        DecisionEvent(
            case_id="case-shadow-1",
            ticker="NVDA",
            event_type="PAPER_ORDER",
            shadow_only=True,
        )
    except ValueError:
        pass
    else:
        raise AssertionError("shadow event was allowed to impersonate an executable paper order")


def main() -> int:
    tests = [
        test_health_freshness_and_fail_closed,
        test_invalid_payload_is_degraded,
        test_journal_captures_no_trade_and_shadow_counterfactual,
        test_shadow_cannot_impersonate_execution,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print("Batch 10 resilience acceptance: PASS")
    print("Paper order authority: FALSE")
    print("Broker connected: FALSE")
    print("Live execution: FALSE")
    print("Automatic threshold mutation: FALSE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
