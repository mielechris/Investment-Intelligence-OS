from __future__ import annotations

import hashlib
import json
from typing import Any

from .models import Availability, Book, Eligibility, OpportunityPassport, utc_now

OBSERVATION_ONLY_ASSETS = {"IPO", "NEW_LISTING", "BOND", "TREASURY", "FUTURE"}
KNOWN_ASSETS = {
    "EQUITY", "EMERGING_EQUITY", "SMID_EQUITY", "ETF", "IPO", "NEW_LISTING",
    "BOND", "TREASURY", "COMMODITY", "FUTURE", "CURRENCY", "DIGITAL_ASSET",
}


def _stable_id(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return f"opp_{hashlib.sha256(canonical.encode()).hexdigest()[:20]}"


def create_passport(payload: dict[str, Any]) -> OpportunityPassport:
    asset = str(payload.get("asset_class") or "").upper().strip()
    instrument = str(payload.get("instrument") or "").upper().strip()
    provenance = payload.get("provenance") if isinstance(payload.get("provenance"), list) else []
    observed_at = str(payload.get("observed_at") or utc_now())
    basis = {"instrument": instrument, "asset_class": asset, "observed_at": observed_at, "provenance": provenance}
    requested_book = str(payload.get("applicable_book") or "OBSERVATION_ONLY").upper()
    try:
        book = Book(requested_book)
    except ValueError:
        book = Book.OBSERVATION_ONLY
    if asset in OBSERVATION_ONLY_ASSETS or asset in {"CURRENCY", "DIGITAL_ASSET"}:
        book = Book.OBSERVATION_ONLY
    try:
        freshness = Availability(str(payload.get("evidence_freshness") or "UNKNOWN").upper())
    except ValueError:
        freshness = Availability.UNKNOWN
    passport = OpportunityPassport(
        passport_id=str(payload.get("passport_id") or _stable_id(basis)),
        instrument=instrument,
        asset_class=asset,
        observed_at=observed_at,
        provenance=provenance,
        discovery_reason=str(payload.get("discovery_reason") or "").strip(),
        catalyst=str(payload.get("catalyst") or "").strip(),
        expected_horizon=str(payload.get("expected_horizon") or "").strip(),
        upside_range_pct=payload.get("upside_range_pct"),
        downside_range_pct=payload.get("downside_range_pct"),
        invalidation=str(payload.get("invalidation") or "").strip(),
        liquidity=dict(payload.get("liquidity") or {}),
        volatility=dict(payload.get("volatility") or {}),
        correlation=dict(payload.get("correlation") or {}),
        evidence_freshness=freshness,
        confidence=max(0.0, min(1.0, float(payload.get("confidence") or 0.0))),
        missing_evidence=[str(x) for x in payload.get("missing_evidence") or []],
        applicable_book=book,
        asset_details=dict(payload.get("asset_details") or {}),
    )
    return apply_asset_gates(passport)


def apply_asset_gates(passport: OpportunityPassport) -> OpportunityPassport:
    reasons: list[str] = []
    required = {
        "instrument": passport.instrument,
        "asset_class": passport.asset_class,
        "provenance": passport.provenance,
        "discovery_reason": passport.discovery_reason,
        "expected_horizon": passport.expected_horizon,
        "invalidation": passport.invalidation,
        "liquidity": passport.liquidity,
        "volatility": passport.volatility,
        "correlation": passport.correlation,
    }
    reasons.extend(f"MISSING_{key.upper()}" for key, value in required.items() if not value)
    if passport.asset_class not in KNOWN_ASSETS:
        reasons.append("UNSUPPORTED_ASSET_CLASS")
    if passport.evidence_freshness in {Availability.STALE, Availability.UNKNOWN, Availability.UNAVAILABLE}:
        reasons.append(f"EVIDENCE_{passport.evidence_freshness}")
    if passport.missing_evidence:
        reasons.append("MISSING_MATERIAL_EVIDENCE")
    if passport.asset_class in {"BOND", "TREASURY"}:
        for key in ("yield", "duration", "maturity", "credit_quality"):
            if passport.asset_details.get(key) in (None, ""):
                reasons.append(f"MISSING_{key.upper()}")
    if passport.asset_class == "FUTURE":
        for key in ("contract_size", "initial_margin", "leverage", "expiry", "rollover", "overnight_risk"):
            if passport.asset_details.get(key) in (None, ""):
                reasons.append(f"MISSING_{key.upper()}")
    if passport.asset_class in {"IPO", "NEW_LISTING"}:
        for key in ("listing_date", "lockup", "float", "price_range"):
            if passport.asset_details.get(key) in (None, ""):
                reasons.append(f"MISSING_{key.upper()}")
    passport.gate_reasons = sorted(set(reasons))
    if reasons:
        passport.eligibility = Eligibility.INCOMPLETE
    elif passport.asset_class in OBSERVATION_ONLY_ASSETS or passport.applicable_book == Book.OBSERVATION_ONLY:
        passport.eligibility = Eligibility.OBSERVATION_ONLY
    else:
        passport.eligibility = Eligibility.ELIGIBLE
    return passport
