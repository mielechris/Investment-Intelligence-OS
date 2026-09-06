"""Disabled-by-default Tuesday paper-observation controller contracts."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .tuesday_market_evidence import AUTHORITY, PILOT_INSTRUMENTS

SCHEMA_VERSION = "iios-tuesday-controller-v1"
PHASES = (
    "TUESDAY_PREMARKET_LOCKED", "OPENING_EVIDENCE_AUTHORIZED",
    "OPENING_EVIDENCE_COLLECTION", "HUMAN_CANDIDATE_REVIEW",
    "COMMITTEE_REVIEW", "RISK_REVIEW", "FORWARD_OBSERVATION_ACTIVE",
    "INTRADAY_MARK_WINDOW", "CLOSING_MARK_WINDOW", "POST_CLOSE_AUDIT",
    "COMPLETED", "FAILED_CLOSED",
)
NEXT = {left: right for left, right in zip(PHASES[:-2], PHASES[1:-1])}
OBSERVATIONS = ("OPENING_EVIDENCE", "INTRADAY_MARK", "CLOSING_MARK")
PILOTS = tuple(row[0] for row in PILOT_INSTRUMENTS)
GATE_ORDER = ("OPERATIONAL_MODE", "DATE_SESSION", "HUMAN_AUTHORIZATION", "ENTITLEMENT",
    "INSTRUMENT", "OBSERVATION_PHASE", "PER_INSTRUMENT_BUDGET", "GLOBAL_BUDGET",
    "SINGLE_FLIGHT", "CREDENTIAL_SELECTOR", "CREDENTIAL_RETRIEVAL", "PROVIDER_REQUEST")


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@dataclass
class CreditGovernor:
    remaining_allowance: int
    attempted: int = 0
    confirmed: int = 0
    ambiguous: int = 0
    failed: int = 0
    cached: int = 0
    records: list[dict[str, Any]] = field(default_factory=list)

    def reserve(self, ticker: str, phase: str, request_id: str) -> str:
        if ticker not in PILOTS or phase not in OBSERVATIONS or not request_id:
            return "IDENTITY_OR_PHASE_REJECTED"
        if any(row["request_id"] == request_id for row in self.records):
            return "DUPLICATE_REQUEST_REJECTED"
        per_symbol = sum(row["ticker"] == ticker for row in self.records)
        if per_symbol >= 3 or len(self.records) >= 30 or len(self.records) >= self.remaining_allowance:
            return "CREDIT_BUDGET_EXHAUSTED"
        self.attempted += 1
        self.records.append({"ticker": ticker, "phase": phase, "request_id": request_id,
            "result": "RESERVED"})
        return "RESERVED"

    def settle(self, request_id: str, result: str) -> str:
        row = next((item for item in self.records if item["request_id"] == request_id), None)
        if row is None or row["result"] != "RESERVED" or result not in {"CONFIRMED", "AMBIGUOUS", "FAILED"}:
            return "SETTLEMENT_REJECTED"
        row["result"] = result
        if result == "CONFIRMED": self.confirmed += 1
        elif result == "AMBIGUOUS": self.ambiguous += 1
        else: self.failed += 1
        return result

    def cache_repeat(self, request_id: str) -> str:
        if not any(row["request_id"] == request_id and row["result"] == "CONFIRMED" for row in self.records):
            return "CACHE_MISS_NO_RETRY"
        self.cached += 1
        return "CACHE_HIT_ZERO_CREDIT"

    def report(self) -> dict[str, Any]:
        return {"planned": 30, "attempted": self.attempted, "confirmed": self.confirmed,
            "ambiguous": self.ambiguous, "failed": self.failed, "cached": self.cached,
            "remaining_authorized": self.remaining_allowance - len(self.records),
            "per_instrument": {ticker: sum(row["ticker"] == ticker for row in self.records) for ticker in PILOTS}}


@dataclass
class TuesdayPhaseMachine:
    phase: str = "TUESDAY_PREMARKET_LOCKED"
    controller_enabled: bool = False
    history: list[str] = field(default_factory=lambda: ["TUESDAY_PREMARKET_LOCKED"])

    def advance(self, target: str, *, actor: str, evidence_valid: bool = True,
                browser: bool = False) -> str:
        if (not self.controller_enabled or browser or actor not in {"OWNER", "CONTROLLER"}
                or not evidence_valid or NEXT.get(self.phase) != target):
            self.phase = "FAILED_CLOSED"; self.history.append(self.phase); return self.phase
        if target in {"HUMAN_CANDIDATE_REVIEW", "COMMITTEE_REVIEW", "RISK_REVIEW"} and actor != "OWNER":
            self.phase = "FAILED_CLOSED"; self.history.append(self.phase); return self.phase
        self.phase = target; self.history.append(target); return target

    def checkpoint(self) -> dict[str, Any]:
        return {"schema_version": SCHEMA_VERSION, "phase": self.phase,
            "history": tuple(self.history), "sequence": len(self.history) - 1,
            "controller_enabled": self.controller_enabled, "authority": AUTHORITY.copy()}

    @classmethod
    def recover(cls, checkpoint: dict[str, Any]) -> "TuesdayPhaseMachine":
        if checkpoint.get("schema_version") != SCHEMA_VERSION or checkpoint.get("phase") not in PHASES:
            return cls(phase="FAILED_CLOSED")
        history = list(checkpoint.get("history", ()))
        if not history or history[-1] != checkpoint["phase"]:
            return cls(phase="FAILED_CLOSED")
        return cls(checkpoint["phase"], bool(checkpoint.get("controller_enabled")), history)


def credential_gate_trace(*, operational: bool, session: str, human_authorized: bool,
                          entitlement: bool, ticker: str, phase: str, budget_valid: bool,
                          lock_acquired: bool, selector_valid: bool) -> dict[str, Any]:
    checks = (operational, session == "REGULAR", human_authorized, entitlement, ticker in PILOTS,
        phase in OBSERVATIONS, budget_valid, budget_valid, lock_acquired, selector_valid)
    passed = []
    for name, ok in zip(GATE_ORDER[:10], checks):
        if not ok:
            return {"state": "FAILED_CLOSED", "failed_gate": name, "passed": tuple(passed),
                "credential_access": False, "provider_request": False}
        passed.append(name)
    return {"state": "CREDENTIAL_RETRIEVAL_PERMITTED", "failed_gate": None,
        "passed": tuple(passed), "credential_access": True, "provider_request": False}


def monday_holiday_rehearsal() -> dict[str, Any]:
    return {"schema_version": SCHEMA_VERSION, "date": "2026-09-07", "market": "CLOSED_HOLIDAY",
        "controller": "DISABLED", "next_phase": "TUESDAY_PREMARKET_LOCKED",
        "provider_requests": 0, "credits": 0, "keychain_access": 0, "candidates": 0,
        "synthetic_observations": 0, "operational_positions": 0, "orders": 0, "fills": 0,
        "projection_mutations": 0, "sanitized": True, "authority": AUTHORITY.copy()}


SCENARIOS = (
    "MONDAY_HOLIDAY", "TUESDAY_PREMARKET", "REGULAR_SESSION_OPENING", "MU_CURRENT_NO_CANDIDATE",
    "MU_CURRENT_VALID_CANDIDATE", "MU_STALE", "MU_FUTURE", "WRONG_INSTRUMENT", "DUPLICATE_OBSERVATION",
    "TIMEOUT_AMBIGUOUS_CREDIT", "HTTP_FAILURE", "MALFORMED_RESPONSE", "OVERSIZED_RESPONSE",
    "BUDGET_EXHAUSTED", "PER_SYMBOL_LIMIT", "GLOBAL_LIMIT", "LOCK_CONTENTION", "RESTART_AFTER_OPENING",
    "HUMAN_REJECTION", "COMMITTEE_REJECTION", "RISK_REJECTION", "SYNTHETIC_OBSERVATION",
    "INTRADAY_MARK", "CLOSING_MARK", "POST_CLOSE_REPORT", "CORPORATE_ACTION_SUSPENSION",
    "PROFESSIONAL_EVIDENCE_ONLY", "CANDIDATE_LINEAGE_MISSING", "BROWSER_POLLING_BURST", "UNSAFE_AUTHORITY",
)


def rehearsal_matrix() -> dict[str, Any]:
    blocked = {"MONDAY_HOLIDAY", "MU_STALE", "MU_FUTURE", "WRONG_INSTRUMENT", "DUPLICATE_OBSERVATION",
        "TIMEOUT_AMBIGUOUS_CREDIT", "HTTP_FAILURE", "MALFORMED_RESPONSE", "OVERSIZED_RESPONSE",
        "BUDGET_EXHAUSTED", "PER_SYMBOL_LIMIT", "GLOBAL_LIMIT", "LOCK_CONTENTION", "HUMAN_REJECTION",
        "COMMITTEE_REJECTION", "RISK_REJECTION", "CORPORATE_ACTION_SUSPENSION", "PROFESSIONAL_EVIDENCE_ONLY",
        "CANDIDATE_LINEAGE_MISSING", "BROWSER_POLLING_BURST", "UNSAFE_AUTHORITY"}
    rows = [{"scenario": name, "result": "FAILED_CLOSED" if name in blocked else "REHEARSAL_ONLY",
        "provider_requests": 0, "credits": 0, "operational_mutation": False} for name in SCENARIOS]
    return {"schema_version": "iios-tuesday-rehearsal-matrix-v1", "scenario_count": len(rows),
        "results": rows, "hash": _digest(rows), "authority": AUTHORITY.copy()}


def service_contract() -> dict[str, Any]:
    return {"module": "expansion_wing.tuesday_controller_service", "installed": False,
        "activated": False, "network_listener": False, "child_processes": False,
        "browser_route": False, "fixed_pilots": PILOTS, "interval": None,
        "state_mode": "0700", "file_mode": "0600", "keep_alive": False,
        "operational_path_override": False, "raw_logs": False, "authority": AUTHORITY.copy()}


def post_close_report(governor: CreditGovernor, sleeves: dict[str, dict[str, Any]]) -> dict[str, Any]:
    if set(sleeves) - set(PILOTS): raise ValueError("UNKNOWN_INSTRUMENT")
    return {"schema_version": "iios-tuesday-post-close-v2", "session_date": None,
        "phases_completed": (), "accounting": governor.report(), "accepted_evidence": 0,
        "rejected_evidence": 0, "candidates": (), "human_dispositions": (), "committee": (), "risk": (),
        "synthetic_sleeves": sleeves, "modeled_costs": (), "corporate_action_suspensions": (),
        "missing_evidence": ("CURRENT_TUESDAY_EVIDENCE",), "method_eligibility": "INSUFFICIENT_SAMPLE",
        "drawdown": None, "calibration": None, "success_claim": None,
        "operational_noninterference": True, "protected_services_stable": True,
        "authority": AUTHORITY.copy()}
