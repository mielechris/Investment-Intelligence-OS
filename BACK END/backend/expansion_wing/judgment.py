from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

STATUSES = {"REPORTED", "PROVISIONAL", "VALIDATED", "REJECTED", "RETIRED"}
TRANSITIONS = {"REPORTED": {"PROVISIONAL", "REJECTED"}, "PROVISIONAL": {"VALIDATED", "REJECTED", "RETIRED"},
               "VALIDATED": {"RETIRED"}, "REJECTED": {"RETIRED"}, "RETIRED": set()}
ATTRIBUTIONS = {"DIRECT", "PARAPHRASED", "INFERRED"}


@dataclass
class JudgmentPrinciple:
    principle_id: str
    source: str
    source_date: str
    professional_identity: str
    attribution: str
    applicable_assets: list[str]
    applicable_regimes: list[str]
    rule: str
    exceptions: list[str]
    entry: str
    sizing: str
    exit: str
    invalidation: str
    supporting_evidence: list[dict[str, Any]]
    opposing_evidence: list[dict[str, Any]]
    confidence: float
    test_specification: dict[str, Any]
    human_reviewer: str
    status: str = "REPORTED"
    limited_quotation: str = ""
    permissions: dict[str, bool] = field(default_factory=lambda: {"right_to_use": False, "confidential": False})

    def validate(self) -> list[str]:
        errors: list[str] = []
        if self.attribution not in ATTRIBUTIONS: errors.append("INVALID_ATTRIBUTION")
        if self.status not in STATUSES: errors.append("INVALID_STATUS")
        if not self.source or not self.source_date: errors.append("SOURCE_AND_DATE_REQUIRED")
        if not self.human_reviewer: errors.append("HUMAN_REVIEWER_REQUIRED")
        if not self.permissions.get("right_to_use"): errors.append("RIGHT_TO_USE_REQUIRED")
        if self.permissions.get("confidential"): errors.append("CONFIDENTIAL_INFORMATION_EXCLUDED")
        if self.status == "VALIDATED" and not self.test_specification.get("forward_paper_validation"):
            errors.append("FORWARD_PAPER_VALIDATION_REQUIRED")
        return errors

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "automatic_trading_rule": False, "human_approval_required": True}


def promote_status(principle: JudgmentPrinciple, new_status: str, *, human_approved: bool) -> JudgmentPrinciple:
    if new_status not in STATUSES:
        raise ValueError("invalid judgment status")
    if not human_approved:
        raise PermissionError("human approval required")
    if new_status not in TRANSITIONS[principle.status]:
        raise ValueError("invalid judgment lifecycle transition")
    if new_status == "VALIDATED" and principle.validate():
        raise ValueError("principle does not satisfy validation contract")
    principle.status = new_status
    return principle
