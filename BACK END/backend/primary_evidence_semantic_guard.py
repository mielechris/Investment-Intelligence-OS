from __future__ import annotations

from typing import Any


WHITE_HOUSE_SEMICONDUCTOR_232_URL = (
    "https://www.whitehouse.gov/presidential-actions/2026/01/"
    "adjusting-imports-of-semiconductors-semiconductor-manufacturing-equipment-"
    "and-their-derivative-products-into-the-united-states/"
)
MICRON_Q3_2026_PRESS_RELEASE_URL = (
    "https://investors.micron.com/news/press-release/2026/"
    "Micron-Technology-Inc--Reports-Record-Results-for-the-Third-Quarter-of-Fiscal-2026/default.aspx"
)
MICRON_HBM4_VOLUME_URL = (
    "https://investors.micron.com/news/press-release/2026/"
    "Micron-in-High-Volume-Production-of-HBM4-Designed-for-NVIDIA-Vera-Rubin-PCIe-Gen6-SSD-and-SOCAMM2-03-16-2026/default.aspx"
)
MICRON_Q3_2026_10Q_URL = (
    "https://www.sec.gov/Archives/edgar/data/723125/000072312526000015/mu-20260528.htm"
)


def policy_transmission_supported(text: str) -> bool:
    """Require an explicit policy mechanism tied to supply/capacity before crediting ingestion."""
    value = str(text or "").lower()
    policy_mechanism = any(term in value for term in ("tariff", "duty", "export control", "incentive", "offset program"))
    supply_mechanism = any(term in value for term in ("supply chain", "manufacturing capacity", "domestic manufacturing", "capacity", "supply"))
    return policy_mechanism and supply_mechanism


def install_primary_evidence_semantic_guard(module: Any) -> None:
    """Prevent broad mentions from satisfying narrow facts and add resilient official-source fallbacks."""
    prior_fact = module._fact_from_keyword
    prior_capture_policy = module._capture_policy
    prior_capture_micron_ir = module._capture_micron_ir
    prior_lane_status = module._lane_status

    def guarded(lane: str, text: str):
        value = str(text or "").lower()
        if lane == "micron_financials":
            if "hbm" in value and not any(term in value for term in ("margin", "volume", "shipment", "revenue")):
                value = value.replace("hbm", " ")
            if "revenue" in value and "hbm" not in value:
                return "revenue"
            if "inventor" in value:
                return "inventory"
            if "cash provided by operating activities" in value or "operating cash flow" in value:
                return "cash_flow"
            if "cash equivalent" in value or "cash, marketable investments" in value:
                return "cash"
            if "current debt" in value or "long-term debt" in value or "repayments of debt" in value:
                return "debt"
            if "capital expenditure" in value or "capex" in value:
                return "capex"
            if "prices increased" in value or "higher pricing" in value or "average selling price" in value:
                return "asp_sensitivity"
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

    def capture_micron_financials_static(case_id: str, case: dict[str, Any]):
        added, failures = prior_capture_micron_ir(case_id, case)
        for keywords in (
            ["Revenue", "Inventories", "net cash provided by operating activities", "cash equivalents", "Current debt", "Long-term debt"],
            ["capital expenditures", "free cash flow", "higher pricing", "prices increased"],
        ):
            records, errors = module._capture_official_page(
                case_id,
                case,
                "micron_financials",
                MICRON_Q3_2026_PRESS_RELEASE_URL,
                "Micron Fiscal Q3 2026 Results",
                keywords,
                0.98,
            )
            added.extend(records)
            failures.extend(errors)
        records, errors = module._capture_official_page(
            case_id,
            case,
            "micron_financials",
            MICRON_HBM4_VOLUME_URL,
            "Micron HBM4 Volume Production",
            ["HBM4", "volume shipment", "high-volume production"],
            0.96,
        )
        added.extend(records)
        failures.extend(errors)
        # The filed Q3 2026 10-Q explicitly quantifies DRAM/NAND ASP changes and says
        # gross-margin improvement was primarily driven by higher average selling prices.
        # This is the required primary evidence for ASP sensitivity, not a generic
        # narrative statement that pricing was favorable.
        records, errors = module._capture_official_page(
            case_id,
            case,
            "micron_financials",
            MICRON_Q3_2026_10Q_URL,
            "Micron Fiscal Q3 2026 Form 10-Q",
            [
                "average selling prices",
                "Margins improved primarily due to increases in average selling prices",
                "Sales of DRAM products increased",
                "Sales of NAND products increased",
            ],
            0.995,
        )
        added.extend(records)
        failures.extend(errors)
        return added, failures

    def lane_status_guarded(case_id: str, lane: str, records: list[dict[str, Any]]):
        result = prior_lane_status(case_id, lane, records)
        covered = int(result.get("covered_facts") or 0)
        total = int(result.get("total_facts") or 0)
        pct = int(result.get("coverage_pct") or 0)
        requirement = str(result.get("requirement") or "").lower()
        facts = result.get("facts") or []
        transmission_open = any(
            str(row.get("key") or "") == "transmission" and not bool(row.get("covered"))
            for row in facts
            if isinstance(row, dict)
        )
        transmission_required = lane == "policy" and any(
            term in requirement for term in ("measurable", "transmission", "substitution", "supply-chain")
        )

        if total and covered == total:
            result["status"] = "COMPLETE_FACT_COVERAGE"
        elif transmission_required and transmission_open:
            result["status"] = "PARTIAL_CRITICAL_FACT_OPEN"
        elif pct:
            result["status"] = "PARTIAL"
        else:
            result["status"] = "OPEN"
        return result

    module._fact_from_keyword = guarded
    module._capture_policy = capture_policy_targeted
    module._capture_micron_ir = capture_micron_financials_static
    module._lane_status = lane_status_guarded
