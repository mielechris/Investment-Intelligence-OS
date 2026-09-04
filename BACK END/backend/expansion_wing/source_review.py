from __future__ import annotations

from dataclasses import dataclass

STATES = {"DISCOVERED", "RIGHTS_REVIEW", "APPROVED", "REJECTED", "NORMALIZED", "CLAIMS_PENDING_REVIEW"}
TRANSITIONS = {"DISCOVERED": {"RIGHTS_REVIEW"}, "RIGHTS_REVIEW": {"APPROVED", "REJECTED"},
    "APPROVED": {"NORMALIZED"}, "REJECTED": set(), "NORMALIZED": {"CLAIMS_PENDING_REVIEW"},
    "CLAIMS_PENDING_REVIEW": set()}


@dataclass
class SourceReviewItem:
    source_id: str
    state: str = "DISCOVERED"
    rights_classification: str = "UNKNOWN"
    attribution_verified: bool = False
    source_approved: bool = False

    def transition(self, target: str, *, human_approved: bool) -> str:
        if target not in STATES or target not in TRANSITIONS[self.state]: raise ValueError("INVALID_SOURCE_TRANSITION")
        if not human_approved: raise PermissionError("HUMAN_APPROVAL_REQUIRED")
        if target == "APPROVED" and (self.rights_classification != "PERMITTED" or
                                     not self.attribution_verified or not self.source_approved):
            raise PermissionError("SOURCE_REVIEW_INCOMPLETE")
        self.state = target; return self.state

    def claim_extraction_allowed(self) -> bool:
        return self.state in {"NORMALIZED", "CLAIMS_PENDING_REVIEW"} and self.source_approved

    def judgment_handoff(self) -> dict[str, bool | str]:
        return {"status": "BLOCKED_HUMAN_APPROVAL", "automatic": False, "judgment_bank_write": False}
