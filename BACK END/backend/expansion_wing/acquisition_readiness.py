from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class OfficialCandidate:
    candidate_id: str
    source_type: str
    exact_domain: str
    rights_state: str = "RIGHTS_REVIEW"
    contact_policy_state: str = "AWAITING_APPROVAL"


FIRST_QUEUE = (
    OfficialCandidate("issuer-letter-candidate", "ISSUER_SHAREHOLDER_LETTER", "berkshirehathaway.com"),
    OfficialCandidate("issuer-filing-candidate", "ISSUER_HOSTED_FILING", "investor.apple.com"),
)


def disabled_acquisition_projection(candidates: tuple[OfficialCandidate, ...] = FIRST_QUEUE) -> dict:
    if any(not item.exact_domain or item.rights_state != "RIGHTS_REVIEW" or
           item.contact_policy_state != "AWAITING_APPROVAL" for item in candidates):
        raise ValueError("ACQUISITION_CANDIDATE_INVALID")
    return {"status": "AWAITING_APPROVED_SOURCE", "candidate_count": len(candidates),
        "rights_review_queue_count": len(candidates), "scheduled": False, "network_enabled": False,
        "provider_enabled": False, "cost_usd": 0, "authority_granted": False}
