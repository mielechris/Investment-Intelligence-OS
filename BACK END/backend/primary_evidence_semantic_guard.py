from __future__ import annotations

from typing import Any


def install_primary_evidence_semantic_guard(module: Any) -> None:
    """Prevent broad product mentions from satisfying narrow primary-evidence facts."""
    prior = module._fact_from_keyword

    def guarded(lane: str, text: str):
        value = str(text or "").lower()
        if lane == "micron_financials" and "hbm" in value:
            if not any(term in value for term in ("margin", "volume", "shipment", "revenue")):
                value = value.replace("hbm", " ")
        if lane == "supply_inventory" and "hbm" in value:
            if not any(term in value for term in ("packaging", "yield", "capacity")):
                value = value.replace("hbm", " ")
        return prior(lane, value)

    module._fact_from_keyword = guarded
