from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

FAILURE_CATEGORIES = {"PAYLOAD_TOO_LARGE", "QUEUE_FULL", "DUPLICATE", "CONCURRENCY_LIMIT",
    "RETRY_LIMIT", "TIMEOUT", "RIGHTS_REJECTED", "CONSENT_REJECTED", "MALFORMED_INPUT",
    "COST_UNKNOWN", "COST_CEILING"}


@dataclass(frozen=True)
class PipelineLimits:
    max_payload_bytes: int = 25_000_000
    max_queue_depth: int = 100
    max_concurrency: int = 2
    max_retries: int = 2
    timeout_seconds: float = 30.0
    daily_cost_ceiling: float = 0.0
    monthly_cost_ceiling: float = 0.0


@dataclass
class GovernedWorkQueue:
    limits: PipelineLimits = field(default_factory=PipelineLimits)
    _hashes: set[str] = field(default_factory=set)
    _queued: list[dict[str, Any]] = field(default_factory=list)
    active: int = 0

    def admit(self, payload: bytes, *, retries: int = 0, estimated_cost: float | None = 0.0,
              elapsed_seconds: float = 0.0) -> dict[str, Any]:
        reason = None; digest = hashlib.sha256(payload).hexdigest()
        if len(payload) > self.limits.max_payload_bytes: reason = "PAYLOAD_TOO_LARGE"
        elif digest in self._hashes: reason = "DUPLICATE"
        elif len(self._queued) >= self.limits.max_queue_depth: reason = "QUEUE_FULL"
        elif self.active >= self.limits.max_concurrency: reason = "CONCURRENCY_LIMIT"
        elif retries > self.limits.max_retries: reason = "RETRY_LIMIT"
        elif elapsed_seconds < 0 or elapsed_seconds > self.limits.timeout_seconds: reason = "TIMEOUT"
        elif estimated_cost is None: reason = "COST_UNKNOWN"
        elif estimated_cost > self.limits.daily_cost_ceiling or estimated_cost > self.limits.monthly_cost_ceiling:
            reason = "COST_CEILING"
        if reason:
            return {"admitted": False, "failure_category": reason, "sanitized": True, "authority": _authority()}
        self._hashes.add(digest); self._queued.append({"content_hash": digest, "retries": retries})
        return {"admitted": True, "failure_category": None, "sanitized": True, "authority": _authority()}

    def status(self) -> dict[str, Any]:
        return {"queue_count": len(self._queued), "active_count": self.active, "limits": self.limits.__dict__,
                "provider_status": "NOT_ACTIVATED", "authority": _authority()}


def _authority() -> dict[str, bool]:
    return {"broker": False, "order_submission": False, "paper_ledger_write": False,
            "threshold_change": False, "execution_authority": False, "credential_access": False,
            "live_execution": False}


def room_projection(state: dict[str, Any] | None = None) -> dict[str, dict[str, Any]]:
    if state is None:
        return {
            "Interview Studio": {"state": "UNAVAILABLE", "presentation_status": "AVAILABLE_FOR_REVIEWED_UPLOAD", "data": {
                "upload_queue_count": None, "approved_transcript_count": None, "transcription": "NOT_ACTIVATED"}},
            "Investor Archive": {"state": "UNAVAILABLE", "presentation_status": "NOT_ACTIVATED", "data": {
                "source_count": None, "approved_source_count": None, "rights_review_queue_count": None,
                "encryption_key_status": "NOT_CONFIGURED"}},
            "Philosophy Arena": {"state": "CURRENT", "presentation_status": "AVAILABLE_EMPTY", "data": {
                "hypothesis_count": 0, "validated_hypothesis_count": 0}},
            "Judgment Foundry": {"state": "CURRENT", "presentation_status": "AVAILABLE_EMPTY", "data": {
                "reported_count": 0, "provisional_count": 0, "validated_count": 0, "rejected_count": 0, "retired_count": 0}},
            "Pattern Laboratory": {"state": "CURRENT", "presentation_status": "AVAILABLE_EMPTY", "data": {
                "queued_test_count": 0, "completed_test_count": 0, "validated_pattern_count": 0,
                "testing_engine": "AVAILABLE", "point_in_time_required": True}},
        }
    allowed = {"upload_queue_count", "approved_transcript_count", "source_count", "real_source_count",
        "fixture_source_count", "approved_source_count", "discovered_source_count", "rejected_source_count",
        "normalized_source_count", "claims_pending_review_count",
        "quarantine_count", "transcript_correction_count", "speaker_attribution_count",
        "professional_approval_count", "contradiction_case_count", "judgment_handoff_ready_count",
        "pattern_handoff_ready_count", "encryption_key_status",
        "rights_review_queue_count", "hypothesis_count", "validated_hypothesis_count", "reported_count",
        "provisional_count", "validated_count", "rejected_count", "retired_count", "queued_test_count",
        "completed_test_count", "validated_pattern_count"}
    numeric = allowed - {"encryption_key_status"}
    if set(state) - allowed or any(key in state and (not isinstance(state[key], int) or isinstance(state[key], bool) or
        state[key] < 0) for key in numeric) or state.get("encryption_key_status", "NOT_CONFIGURED") not in {
            "NOT_CONFIGURED", "AVAILABLE", "ERROR"}:
        raise ValueError("UNSAFE_KNOWLEDGE_ROOM_STATE")
    base = room_projection()
    mapping = {"Interview Studio": ("upload_queue_count", "quarantine_count", "approved_transcript_count",
            "transcript_correction_count", "speaker_attribution_count", "professional_approval_count"),
        "Investor Archive": ("source_count", "real_source_count", "fixture_source_count", "approved_source_count",
            "rights_review_queue_count", "discovered_source_count", "rejected_source_count",
            "normalized_source_count", "claims_pending_review_count"),
        "Philosophy Arena": ("hypothesis_count", "validated_hypothesis_count", "contradiction_case_count"),
        "Judgment Foundry": ("reported_count", "provisional_count", "validated_count", "rejected_count", "retired_count",
            "judgment_handoff_ready_count"),
        "Pattern Laboratory": ("queued_test_count", "completed_test_count", "validated_pattern_count",
            "pattern_handoff_ready_count")}
    for room, keys in mapping.items():
        base[room]["data"].update({key: state.get(key, 0) for key in keys})
        base[room]["state"] = "CURRENT"; base[room]["presentation_status"] = "AVAILABLE_EMPTY" if not any(state.get(key, 0) for key in keys) else "CURRENT"
    base["Investor Archive"]["data"]["encryption_key_status"] = state.get("encryption_key_status", "NOT_CONFIGURED")
    return base
