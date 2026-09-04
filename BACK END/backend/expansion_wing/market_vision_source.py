from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

from .investor_intelligence import content_hash

PUBLISHER = "Market Vision Inc."
ANALYST = "John T. Barone"
DOMAIN = "mktvsn.com"
SOURCE_TYPE = "PAID_SUBSCRIPTION_COMMODITY_RESEARCH"
TRUST_CLASS = "SECONDARY_DOMAIN_EXPERT"
PUBLICATION_FAMILIES = (
    "The Commodity Update",
    "The Weekly Summary",
    "UNKNOWN_PUBLICATION_VARIANT",
)
COVERAGE = (
    "AGRICULTURE_AND_FOOD_COMMODITIES",
    "ENERGY_AND_BIOFUELS",
    "WEATHER_AND_CROP_CONDITIONS",
    "SUPPLY_DEMAND_INVENTORIES_AND_TRADE_FLOWS",
    "GOVERNMENT_POLICY_AND_REGULATION",
    "INFLATION_AND_INPUT_COST_PRESSURE",
    "TECHNICAL_LEVELS_AND_NEAR_TERM_MARKET_CATALYSTS",
)
IIOS_ROUTES = (
    "Cross-Asset Observatory",
    "Regime Chamber",
    "Tactical Book",
    "Strategic Book",
    "Pattern Laboratory",
    "Judgment Foundry",
    "Failure Museum",
    "Investment Committee evidence packets",
)
ACCURACY_CLASSES = {"UNSCORED", "CORRECT", "PARTIALLY_CORRECT", "INCORRECT", "INDETERMINATE"}
DIRECTIONS = {"UP", "DOWN", "MIXED", "RANGE_BOUND", "NO_DIRECTIONAL_EXPECTATION"}
MAX_NOTE_CHARS = 2_000
MAX_QUOTE_CHARS = 280


def market_vision_registration() -> dict[str, Any]:
    """Return metadata only; this function performs no acquisition or ingestion."""
    return {
        "publisher": PUBLISHER,
        "analyst": ANALYST,
        "domain": DOMAIN,
        "source_type": SOURCE_TYPE,
        "trust_class": TRUST_CLASS,
        "lifecycle": "DISCOVERED",
        "rights_state": "RIGHTS_REVIEW_REQUIRED",
        "claim_state": "REPORTED",
        "publication_families": PUBLICATION_FAMILIES,
        "coverage": COVERAGE,
        "approved_future_routes": IIOS_ROUTES,
        "primary_system": "IIOS",
        "possible_downstream_consumers": ("DULCE",),
        "full_content_retention": False,
        "email_ingestion": False,
        "subscription_rights_inferred": False,
        "automatic_promotion": False,
        "authority": {
            "trading": False,
            "broker": False,
            "ledger_write": False,
            "live_execution": False,
        },
    }


def publication_identity(subject_title: str | None, footer_title: str | None, *, human_verified: bool = False) -> str:
    """Recognize an exact reviewed title; otherwise preserve unknown identity."""
    candidates = {value.strip() for value in (subject_title, footer_title) if value and value.strip()}
    verified = set(PUBLICATION_FAMILIES[:2])
    return candidates.pop() if human_verified and len(candidates) == 1 and candidates <= verified else "UNKNOWN_PUBLICATION_VARIANT"


def bounded_paid_source_note(*, note: str, quotation: str = "", quotation_supported: bool = False,
                             complete_newsletter: bool = False, rights_state: str) -> dict[str, Any]:
    if rights_state != "RIGHTS_REVIEW_REQUIRED":
        raise PermissionError("PAID_SOURCE_RIGHTS_STATE_INVALID")
    if complete_newsletter or len(note) > MAX_NOTE_CHARS:
        raise PermissionError("FULL_PAID_CONTENT_REJECTED")
    normalized = " ".join(note.split())
    if not normalized:
        raise ValueError("BOUNDED_NOTE_REQUIRED")
    if len(quotation) > MAX_QUOTE_CHARS or (quotation and not quotation_supported):
        raise PermissionError("UNSUPPORTED_QUOTATION_REJECTED")
    return {
        "note": normalized,
        "quotation": quotation,
        "content_hash": content_hash(normalized),
        "rights_state": "RIGHTS_REVIEW_REQUIRED",
        "complete_newsletter_retained": False,
    }


class PaidSourceDiscoveryRegistry:
    """Deduplicate bounded notes without admitting paid content as rights-approved evidence."""

    def __init__(self) -> None:
        self._hashes: set[str] = set()

    def register(self, bounded_note: dict[str, Any]) -> str:
        if bounded_note.get("rights_state") != "RIGHTS_REVIEW_REQUIRED":
            raise PermissionError("PAID_SOURCE_RIGHTS_STATE_INVALID")
        digest = bounded_note.get("content_hash")
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError("CONTENT_HASH_INVALID")
        if digest in self._hashes:
            return "DUPLICATE"
        self._hashes.add(digest)
        return "DISCOVERED_RIGHTS_REVIEW_REQUIRED"


@dataclass(frozen=True)
class ForecastObservation:
    observation_id: str
    publication_timestamp: str
    publication_family: str
    commodity: str
    forecast_horizon: str
    directional_expectation: str
    catalysts: tuple[str, ...]
    invalidation_conditions: tuple[str, ...]
    supporting_primary_sources: tuple[str, ...]
    subsequent_outcome: str = "PENDING"
    accuracy_classification: str = "UNSCORED"
    analyst: str = ANALYST
    publisher: str = PUBLISHER
    claim_state: str = "REPORTED"

    def validate(self) -> None:
        if not self.observation_id or not self.commodity or not self.forecast_horizon:
            raise ValueError("FORECAST_IDENTITY_REQUIRED")
        timestamp = datetime.fromisoformat(self.publication_timestamp.replace("Z", "+00:00"))
        if timestamp.tzinfo is None:
            raise ValueError("PUBLICATION_TIMEZONE_REQUIRED")
        if self.publication_family not in PUBLICATION_FAMILIES:
            raise ValueError("PUBLICATION_FAMILY_INVALID")
        if self.directional_expectation not in DIRECTIONS:
            raise ValueError("DIRECTION_INVALID")
        if not self.catalysts or not self.invalidation_conditions:
            raise ValueError("BOUNDED_FORECAST_EVIDENCE_REQUIRED")
        if not self.supporting_primary_sources:
            raise PermissionError("PRIMARY_SOURCE_VERIFICATION_REQUIRED")
        if self.accuracy_classification not in ACCURACY_CLASSES:
            raise ValueError("ACCURACY_CLASS_INVALID")
        if self.analyst != ANALYST or self.publisher != PUBLISHER or self.claim_state != "REPORTED":
            raise ValueError("ATTRIBUTION_REQUIRED")
        if any(not re.fullmatch(r"https://[^\s]+", value) for value in self.supporting_primary_sources):
            raise ValueError("PRIMARY_SOURCE_REFERENCE_INVALID")

    def review_projection(self, *, rights_approved: bool = False, human_approved: bool = False) -> dict[str, Any]:
        self.validate()
        approved = rights_approved and human_approved
        return {
            **asdict(self),
            "routes": IIOS_ROUTES if approved else (),
            "routing_status": "APPROVED" if approved else "BLOCKED_HUMAN_RIGHTS_REVIEW",
            "human_review_required": True,
            "pattern_lab_test_required": True,
            "automatic_promotion": False,
            "investment_recommendation": False,
            "paper_trade_authority": False,
            "failure_museum_eligible": approved and self.accuracy_classification == "INCORRECT",
        }
