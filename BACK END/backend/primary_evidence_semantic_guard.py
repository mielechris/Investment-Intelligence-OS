from __future__ import annotations

from typing import Any


WHITE_HOUSE_SEMICONDUCTOR_232_URL = (
    "https://www.whitehouse.gov/presidential-actions/2026/01/"
    "adjusting-imports-of-semiconductors-semiconductor-manufacturing-equipment-"
    "and-their-derivative-products-into-the-united-states/"
)


def policy_transmission_supported(text: str) -> bool:
    """Require an explicit policy mechanism tied to supply/capacity before crediting transmission."""
    value = str(text or "").lower()
    policy_mechanism = any(term in value for term in ("tariff", "duty", "export control", "incentive", "offset program"))
    supply_mechanism = any(term in value for term in ("supply chain", "manufacturing capacity", "domestic manufacturing", "capacity", "supply"))
    return policy_mechanism and supply_mechanism


def install_primary_evidence_semantic_guard(module: Any) -> None:
    """Prevent broad mentions from satisfying narrow primary-evidence facts and add targeted policy capture."""
    prior_fact = module._fact_from_keyword
    prior_capture_policy = module._capture_policy

    def guarded(lane: str, text: str):
        value = str(text or "").lower()
        if lane == "micron_financials" and "hbm" in value:
            if not any(term in value for term in ("margin", "volume", "shipment", "revenue")):
                value = value.replace("hbm", " ")
        if lane == "supply_inventory" and "hbm" in value:
            if not any(term in value for term in ("packaging", "yield", "capacity")):
                value = value.replace("hbm", " ")
        if lane == "policy" and any(term in value for term in ("supply", "demand", "capacity")):
            if not policy_transmission_supported(value):
                value = value.replace("supply", " ").replace("demand", " ").replace("capacity", " ")
        return prior_fact(lane, value)

    def capture_policy_targeted(case_id: str, case: dict[str, Any]):
        added, failures = prior_capture_policy(case_id, case)
        records, errors = module._capture_official_page(
            case_id,
            case,
            "policy",
            WHITE_HOUSE_SEMICONDUCTOR_232_URL,
            "White House Semiconductor Section 232 Proclamation",
            ["25 percent", "tariff", "effective", "supply chain", "domestic manufacturing capacity"],
            0.99,
        )
        added.extend(records)
        failures.extend(errors)
        return added, failures

    module._fact_from_keyword = guarded
    module._capture_policy = capture_policy_targeted
