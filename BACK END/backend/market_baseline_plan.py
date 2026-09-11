"""Pure bulk checkpoint planning; no scheduler startup or universe retrieval."""
from __future__ import annotations

from datetime import timedelta

from provider_gateway_contract import content_hash, locked_authority, pin, seal, symbols, utc


def monday_plan(universe, expected_universe, calendar, expected_calendar, *, mode="FULL_MARKET"):
    pin(universe, expected_universe)
    pin(calendar, expected_calendar)
    members = symbols(universe["symbols"], count=517)
    if calendar != {"calendar": "XNYS", "session": "2026-09-14", "open": "2026-09-14T13:30:00+00:00", "close": "2026-09-14T20:00:00+00:00"}:
        raise ValueError("INDEPENDENT_MONDAY_SESSION_REQUIRED")
    if mode not in ("FULL_MARKET", "FILTERED"):
        raise ValueError("MODE_INVALID")
    targets = (("OPENING", utc(calendar["open"]) + timedelta(seconds=30)),
               ("INTRADAY", utc(calendar["open"]) + timedelta(hours=3)),
               ("CLOSING", utc(calendar["close"]) + timedelta(seconds=30)))
    rows = [{"phase": phase, "target": target.isoformat(),
             "last_dispatch": (target + timedelta(seconds=30)).isoformat(),
             "response_deadline_seconds": 20, "provider": "MASSIVE", "mode": mode,
             "maximum_requests": 1, "retry_count": 0} for phase, target in targets]
    return seal({"schema": "iios-market-baseline-plan-v1", "session": calendar["session"],
                 "universe_parent": expected_universe, "calendar_parent": expected_calendar,
                 "symbols": members, "symbol_hash": content_hash(members), "checkpoints": rows,
                 "maximum_requests": 3, "maximum_credits": None, "cost": "UNVERIFIED",
                 "missed_observations": "NEVER_BACKFILL", "status": "PROPOSED",
                 "authority": locked_authority()})


def checkpoint_state(row, now):
    stamp = utc(now)
    if stamp < utc(row["target"]):
        return "WAIT"
    if stamp > utc(row["last_dispatch"]):
        return "MISSED_PARTIAL_SESSION"
    return "DUE_REQUIRES_SEPARATE_AUTHORITY"
