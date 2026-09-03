from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any

SOURCE_TYPES = {"SHAREHOLDER_LETTER", "SEC_FILING", "INVESTOR_PRESENTATION", "PUBLIC_INTERVIEW",
    "PODCAST", "CONFERENCE", "UNIVERSITY_LECTURE", "ARTICLE", "ACADEMIC_RESEARCH", "BOOK_NOTE", "USER_INTERVIEW"}
RIGHTS = {"PERMITTED", "REVIEW_REQUIRED", "PROHIBITED"}
CLAIM_CLASSES = {"DIRECT", "PARAPHRASED", "INFERRED"}
REVIEW_STATES = {"PENDING", "APPROVED", "REJECTED"}
MAX_QUOTE_CHARS = 280
MAX_NORMALIZED_CHARS = 100_000


def content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def classify_rights(*, public: bool, user_provided: bool, licensed: bool, paywalled: bool,
                    complete_copyrighted_work: bool) -> str:
    if paywalled or complete_copyrighted_work: return "PROHIBITED"
    if licensed or user_provided: return "PERMITTED"
    return "REVIEW_REQUIRED" if public else "PROHIBITED"


@dataclass(frozen=True)
class ProfessionalProfile:
    professional_id: str
    display_name: str
    profile_type: str
    philosophy_hypotheses: tuple[str, ...] = ()
    fame_confers_validation: bool = False
    human_review_status: str = "PENDING"

    def validate(self) -> None:
        if not self.professional_id or not self.display_name: raise ValueError("PROFILE_IDENTITY_REQUIRED")
        if self.fame_confers_validation: raise ValueError("FAME_IS_NOT_VALIDATION")
        if self.human_review_status not in REVIEW_STATES: raise ValueError("REVIEW_STATUS_INVALID")


@dataclass(frozen=True)
class SourceRecord:
    source_id: str; professional_id: str; title: str; publisher: str
    publication_date: str; retrieval_date: str; source_type: str
    public: bool; user_provided: bool; permitted_use: str; rights_review_status: str
    representation: str; content_hash: str; provenance: str
    applicable_assets: tuple[str, ...]; applicable_regimes: tuple[str, ...]
    freshness: str; human_review_status: str

    def validate(self) -> None:
        if not all((self.source_id, self.professional_id, self.title, self.publisher, self.provenance)):
            raise ValueError("SOURCE_IDENTITY_REQUIRED")
        for value in (self.publication_date, self.retrieval_date): date.fromisoformat(value)
        if self.source_type not in SOURCE_TYPES: raise ValueError("SOURCE_TYPE_INVALID")
        if self.permitted_use not in RIGHTS or self.rights_review_status not in RIGHTS: raise ValueError("RIGHTS_INVALID")
        if self.representation not in CLAIM_CLASSES: raise ValueError("REPRESENTATION_INVALID")
        if self.human_review_status not in REVIEW_STATES: raise ValueError("REVIEW_STATUS_INVALID")
        if not re.fullmatch(r"[0-9a-f]{64}", self.content_hash): raise ValueError("CONTENT_HASH_INVALID")


class SourceRegistry:
    def __init__(self) -> None: self._records: dict[str, SourceRecord] = {}; self._hashes: set[str] = set()
    def register(self, record: SourceRecord) -> str:
        record.validate()
        if record.permitted_use == "PROHIBITED" or record.rights_review_status == "PROHIBITED":
            raise PermissionError("SOURCE_USE_PROHIBITED")
        if record.content_hash in self._hashes: return "DUPLICATE"
        self._records[record.source_id] = record; self._hashes.add(record.content_hash); return "QUEUED_FOR_HUMAN_REVIEW"
    def records(self) -> tuple[SourceRecord, ...]: return tuple(self._records.values())


@dataclass(frozen=True)
class AcquisitionRequest:
    source_id: str; priority: int; estimated_cost: float = 0.0; requires_network: bool = True


class AcquisitionQueue:
    def __init__(self, *, daily_cost_ceiling: float = 0.0) -> None:
        self.daily_cost_ceiling = daily_cost_ceiling; self._items: dict[str, AcquisitionRequest] = {}
    def enqueue(self, request: AcquisitionRequest) -> str:
        if request.estimated_cost < 0 or request.estimated_cost > self.daily_cost_ceiling:
            return "REJECTED_COST_CEILING"
        if request.source_id in self._items: return "DUPLICATE"
        self._items[request.source_id] = request; return "QUEUED_NOT_ACTIVATED"
    def snapshot(self) -> dict[str, Any]:
        return {"status": "NOT_ACTIVATED", "count": len(self._items), "network_execution": False,
                "daily_cost_ceiling": self.daily_cost_ceiling, "overnight_heavy_work_only": True}


def normalize_content(text: str, *, source_type: str, rights: str, quotation: str = "") -> dict[str, Any]:
    if source_type not in SOURCE_TYPES: raise ValueError("SOURCE_TYPE_INVALID")
    if rights != "PERMITTED": raise PermissionError("RIGHTS_APPROVAL_REQUIRED")
    if len(quotation) > MAX_QUOTE_CHARS: raise ValueError("QUOTATION_LIMIT_EXCEEDED")
    normalized = " ".join(text.split())
    if not normalized or len(normalized) > MAX_NORMALIZED_CHARS: raise ValueError("CONTENT_LENGTH_INVALID")
    return {"normalized_text": normalized, "limited_quotation": quotation, "content_hash": content_hash(normalized),
            "complete_copyrighted_work_stored": False}


@dataclass(frozen=True)
class Claim:
    claim_id: str; source_id: str; proposition: str; polarity: str; representation: str
    evidence_known_at: str; applicable_assets: tuple[str, ...] = (); applicable_regimes: tuple[str, ...] = ()
    human_review_status: str = "PENDING"

    def validate(self) -> None:
        if self.representation not in CLAIM_CLASSES: raise ValueError("REPRESENTATION_INVALID")
        if self.polarity not in {"SUPPORTS", "CONTRADICTS"}: raise ValueError("POLARITY_INVALID")
        date.fromisoformat(self.evidence_known_at)


def contradictions(claims: list[Claim]) -> list[dict[str, str]]:
    for claim in claims: claim.validate()
    pairs = []
    for index, left in enumerate(claims):
        for right in claims[index + 1:]:
            if left.proposition.casefold() == right.proposition.casefold() and left.polarity != right.polarity:
                pairs.append({"left": left.claim_id, "right": right.claim_id, "status": "HUMAN_REVIEW_REQUIRED"})
    return pairs


PHILOSOPHIES = {"VALUE_QUALITY": ("moat", "intrinsic value", "balance sheet"),
    "GROWTH_AT_REASONABLE_PRICE": ("growth", "earnings"), "CYCLE_CREDIT": ("cycle", "credit", "risk premium"),
    "MACRO_REFLEXIVITY": ("liquidity", "reflexivity", "macro"), "SYSTEMATIC_TREND": ("trend", "momentum"),
    "FACTOR_RESEARCH": ("factor", "value premium", "quality premium")}


def philosophy_hypotheses(text: str) -> list[str]:
    lowered = text.casefold(); return [name for name, terms in PHILOSOPHIES.items() if any(term in lowered for term in terms)]


def failure_case(*, claim_id: str, outcome: str, known_at_decision: str, invalidation: str,
                 skill_versus_luck: str, reviewed: bool) -> dict[str, Any]:
    return {"claim_id": claim_id, "outcome": outcome, "evidence_known_at_decision": known_at_decision,
            "invalidation": invalidation, "skill_versus_luck": skill_versus_luck,
            "human_review_status": "APPROVED" if reviewed else "PENDING", "automatic_promotion": False}


def review_packet(profile: ProfessionalProfile, source: SourceRecord, claims: list[Claim]) -> dict[str, Any]:
    profile.validate(); source.validate(); [claim.validate() for claim in claims]
    return {"profile": asdict(profile), "source": asdict(source), "claims": [asdict(item) for item in claims],
            "contradictions": contradictions(claims), "judgment_bank_auto_write": False,
            "pattern_lab_auto_run": False, "human_approval_required": True}


def judgment_handoff(packet: dict[str, Any], *, human_approved: bool) -> dict[str, Any]:
    return {"status": "READY" if human_approved else "BLOCKED_HUMAN_APPROVAL",
            "automatic_write": False, "packet_hash": content_hash(json_canonical(packet))}


def pattern_handoff(packet: dict[str, Any], *, human_approved: bool, point_in_time_locked: bool) -> dict[str, Any]:
    ready = human_approved and point_in_time_locked
    return {"status": "READY" if ready else "BLOCKED", "point_in_time_required": True,
            "future_information_allowed": False, "automatic_run": False}


def json_canonical(value: Any) -> str:
    import json
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


@dataclass
class InterviewSession:
    interview_id: str; professional_id: str; media_type: str
    consent: bool = False; permitted_uses: tuple[str, ...] = (); confidential_exclusion: bool = False
    transcript: str = ""; speakers: tuple[str, ...] = (); corrected: bool = False; professional_approved: bool = False
    answers: dict[str, str] = field(default_factory=dict)

    def intake_status(self) -> dict[str, Any]:
        reasons = []
        if self.media_type not in {"AUDIO", "VIDEO", "TEXT"}: reasons.append("MEDIA_TYPE_INVALID")
        if not self.consent: reasons.append("CONSENT_REQUIRED")
        if not self.permitted_uses: reasons.append("PERMITTED_USE_REQUIRED")
        if not self.confidential_exclusion: reasons.append("CONFIDENTIAL_EXCLUSION_REQUIRED")
        return {"status": "READY" if not reasons else "INCOMPLETE", "reasons": reasons, "processing_authorized": not reasons}

    def approval_status(self) -> dict[str, Any]:
        ready = self.intake_status()["status"] == "READY" and bool(self.transcript) and bool(self.speakers) and self.corrected and self.professional_approved
        return {"status": "APPROVED" if ready else "PENDING", "judgment_bank_auto_write": False,
                "human_judgment_approval_required": True}


INTERVIEW_TOPICS = ("wins_and_losses", "evidence_known_at_decision", "position_sizing", "holding_period",
    "invalidation", "exit", "market_regime", "skill_versus_luck")
JESSE_THEME_LEADS = (
    "balance-sheet strength", "reinvestment aligned with company mission", "semiconductor and wafer-cleaning opportunities",
    "R&D versus near-term revenue", "Intel capital-allocation mistakes", "MSTR dilution and operating-business concerns",
    "future wins-versus-losses storytelling",
)


def interview_plan(subject: str) -> dict[str, Any]:
    return {"orchestrator": "MAX", "subject": subject, "required_topics": INTERVIEW_TOPICS,
            "specialist_follow_up_routing": True, "jesse_theme_leads": JESSE_THEME_LEADS if subject.casefold() == "jesse" else (),
            "theme_evidence_status": "SOURCE_REVIEW_REQUIRED", "statements_invented": False}
