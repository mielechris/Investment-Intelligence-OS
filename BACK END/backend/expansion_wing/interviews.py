from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

MEDIA_TYPES = {"AUDIO", "VIDEO", "TEXT"}


@dataclass
class InterviewIntake:
    interview_id: str
    subject: str
    media_type: str
    source_uri: str
    consent_recorded: bool
    permitted_uses: list[str]
    confidential_information_excluded: bool
    transcript: str = ""
    speakers: list[str] = field(default_factory=list)
    subject_approved_transcript: bool = False
    reviewer: str = ""

    def readiness(self) -> dict[str, Any]:
        reasons: list[str] = []
        if self.media_type not in MEDIA_TYPES: reasons.append("UNSUPPORTED_MEDIA_TYPE")
        if not self.consent_recorded: reasons.append("CONSENT_REQUIRED")
        if not self.permitted_uses: reasons.append("PERMITTED_USE_REQUIRED")
        if not self.confidential_information_excluded: reasons.append("CONFIDENTIAL_INFORMATION_EXCLUSION_REQUIRED")
        if not self.transcript: reasons.append("TRANSCRIPT_REQUIRED")
        if not self.subject_approved_transcript: reasons.append("TRANSCRIPT_APPROVAL_REQUIRED")
        if not self.reviewer: reasons.append("HUMAN_REVIEWER_REQUIRED")
        return {"status": "READY_FOR_REVIEW" if not reasons else "INCOMPLETE", "reasons": reasons,
                "automatic_judgment_promotion": False}

    def review_packet(self) -> dict[str, Any]:
        return {"intake": asdict(self), "readiness": self.readiness(), "questions": [
            "Describe a win and what evidence mattered before the outcome.",
            "Describe a loss or avoided loss and the invalidation signal.",
            "How did sizing and timing change across regimes?",
            "What would make this principle fail or stop applying?",
            "Which facts are attributable and legally usable?",
        ], "max_led": True, "specialist_follow_up_required": True, "human_review_required": True}
