from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

ACTIONS = ("SOURCE_RIGHTS_APPROVAL", "ATTRIBUTION_VERIFICATION", "TRANSCRIPT_CORRECTION",
    "SPEAKER_ATTRIBUTION", "PROFESSIONAL_APPROVAL", "CLAIM_CLASSIFICATION", "CONTRADICTION_REVIEW",
    "JUDGMENT_PROMOTION", "PATTERN_SUBMISSION")


@dataclass
class ReviewCase:
    case_id: str
    action: str
    state: str = "PENDING"
    audit_events: list[dict] = field(default_factory=list)

    def decide(self, decision: str, *, reviewer: str, timestamp: str, reason: str, previous_hash: str) -> dict:
        if self.action not in ACTIONS: raise ValueError("REVIEW_ACTION_INVALID")
        if self.state != "PENDING" or decision not in {"APPROVED", "REJECTED"}: raise ValueError("REVIEW_STATE_INVALID")
        if not all((reviewer.strip(), timestamp.strip(), reason.strip())): raise ValueError("REVIEW_AUDIT_FIELDS_REQUIRED")
        if len(previous_hash) != 64: raise ValueError("AUDIT_LINK_INVALID")
        body = {"case_id": self.case_id, "action": self.action, "decision": decision, "reviewer": reviewer,
            "timestamp": timestamp, "reason": reason, "previous_hash": previous_hash, "automatic": False}
        event_hash = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        event = {**body, "event_hash": event_hash}; self.audit_events.append(event); self.state = decision
        return event

    def handoff(self) -> dict:
        ready = self.state == "APPROVED"
        return {"status": "READY_FOR_HUMAN_HANDOFF" if ready else "BLOCKED", "automatic_mutation": False,
                "installed_preview_mutation": False}
