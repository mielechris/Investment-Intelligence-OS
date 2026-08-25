from __future__ import annotations

from typing import Any
from uuid import uuid4


MICRON_Q3_2026_10Q_URL = "https://www.sec.gov/Archives/edgar/data/723125/000072312526000015/mu-20260528.htm"
MICRON_Q3_2026_PREPARED_REMARKS_URL = "https://investors.micron.com/static-files/631b1a32-5537-46ae-8f40-82e42fc79dfe"


CONTRACT_CONTEXT: tuple[dict[str, Any], ...] = (
    {
        "source": "Micron Fiscal Q3 2026 Form 10-Q",
        "source_type": "filing",
        "evidence_type": "quarterly_filing",
        "url": MICRON_Q3_2026_10Q_URL,
        "timestamp": "2026-06-25T00:00:00+00:00",
        "claim": (
            "Micron states its strategic customer agreements are take-or-pay, include binding commitments for specific volumes over multi-year terms, "
            "and generally use fixed pricing or minimum/maximum price bands."
        ),
        "context_key": "take_or_pay_binding_volume",
    },
    {
        "source": "Micron Fiscal Q3 2026 Prepared Remarks",
        "source_type": "company",
        "evidence_type": "quarterly_company",
        "url": MICRON_Q3_2026_PREPARED_REMARKS_URL,
        "timestamp": "2026-06-24T00:00:00+00:00",
        "claim": (
            "Micron says signed strategic customer agreements represent approximately $100 billion of contracts over remaining terms and project "
            "$22 billion of cash deposits and related financial commitments. The agreements span data-center through other end markets and provide "
            "committed DRAM, including HBM as appropriate, and NAND supply over multi-year horizons."
        ),
        "context_key": "contract_value_and_hbm_scope",
    },
)


def install_hyperscaler_contract_context(module: Any) -> None:
    """Capture supplier-side enforceable memory demand as context, not hyperscaler-specific proof.

    Micron discloses binding multi-year take-or-pay memory contracts and large contractual
    commitments, but does not identify the counterparties as specific hyperscalers. These
    records therefore strengthen the demand thesis while remaining ineligible to satisfy the
    hyperscaler-specific `memory_terms` fact on their own.
    """
    prior_capture = module._capture_hyperscalers
    prior_lane_status = module._lane_status

    def _persist_context(case_id: str, case: dict[str, Any], snapshot: dict[str, Any]) -> dict[str, Any] | None:
        existing = module.list_objects(case_id, "primary_evidence_record")
        fingerprint = (str(snapshot["url"]).lower(), str(snapshot["claim"]).lower())
        for row in existing:
            prior = (str(row.get("source_url") or "").lower(), str(row.get("claim") or "").lower())
            if prior == fingerprint:
                return row

        record_id = f"primary_evidence_{uuid4().hex}"
        record = {
            "primary_evidence_id": record_id,
            "case_id": case_id,
            "topic": case.get("topic"),
            "lane": "hyperscaler_demand",
            "lane_label": "Hyperscaler Demand",
            "fact_key": "memory_terms_context",
            "claim": snapshot["claim"],
            "source_name": snapshot["source"],
            "source_url": snapshot["url"],
            "source_type": snapshot["source_type"],
            "source_grade": "PRIMARY_OFFICIAL_CONTEXT" if snapshot["source_type"] == "filing" else "PRIMARY_COMPANY_CONTEXT",
            "evidence_type": snapshot["evidence_type"],
            "observed_at": snapshot["timestamp"],
            "reliability_score": 0.995 if snapshot["source_type"] == "filing" else 0.99,
            "gap_requirement": module._requirement_for_lane(case_id, "hyperscaler_demand"),
            "gap_resolution_eligible": False,
            "context_only": True,
            "context_reason": "SUPPLIER_SIDE_ENFORCEABLE_MEMORY_DEMAND_WITH_UNDISCLOSED_COUNTERPARTIES",
            "counterparty_scope": "UNDISCLOSED_CUSTOMERS_INCLUDING_DATA_CENTER_AND_OTHER_END_MARKETS",
            "capture_method": "CURATED_SOURCE_LINKED_ENFORCEABLE_DEMAND_CONTEXT",
            "verified_public_source": True,
            "paper_mode": True,
            "trade_execution_permission": False,
            "created_at": module.utc_now(),
        }
        module.record_object(record_id, "primary_evidence_record", case_id, record, topic=case.get("topic"))
        module.record_event(
            case_id,
            "PRIMARY_EVIDENCE_CONTEXT_RECORDED",
            entity_id=record_id,
            payload={
                "lane": "hyperscaler_demand",
                "fact_key": "memory_terms_context",
                "context_reason": record["context_reason"],
            },
        )
        return record

    def capture_hyperscalers_with_contract_context(case_id: str, case: dict[str, Any]):
        added, failures = prior_capture(case_id, case)
        for snapshot in CONTRACT_CONTEXT:
            record = _persist_context(case_id, case, snapshot)
            if record:
                added.append(record)
        return added, failures

    def lane_status_with_contract_context(case_id: str, lane: str, records: list[dict[str, Any]]):
        result = prior_lane_status(case_id, lane, records)
        if lane != "hyperscaler_demand":
            return result

        context_rows = [
            row for row in records
            if row.get("lane") == "hyperscaler_demand"
            and row.get("fact_key") == "memory_terms_context"
            and row.get("context_only") is True
        ]
        result["corroborating_contract_context_records"] = len(context_rows)
        base_note = str(result.get("note") or "").strip()
        contract_note = (
            f" Supplier-side contract corroboration: {len(context_rows)} primary record(s) show take-or-pay, binding multi-year memory volumes, "
            "pricing bands and large contractual commitments, including HBM as appropriate. Counterparties are undisclosed, so these records do not "
            "independently close the hyperscaler-specific memory-terms fact."
        )
        result["note"] = (base_note + contract_note).strip()
        return result

    module._capture_hyperscalers = capture_hyperscalers_with_contract_context
    module._lane_status = lane_status_with_contract_context
