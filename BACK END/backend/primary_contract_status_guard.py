from __future__ import annotations

from typing import Any


def install_primary_contract_status_guard(module: Any) -> None:
    """Keep progress labels semantically aligned with actual fact coverage."""
    prior = module._lane_status

    def guarded(case_id: str, lane: str, records: list[dict[str, Any]]):
        result = prior(case_id, lane, records)
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

    module._lane_status = guarded
