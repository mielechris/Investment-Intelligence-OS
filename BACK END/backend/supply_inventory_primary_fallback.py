from __future__ import annotations

from typing import Any


MICRON_Q3_2026_PREPARED_REMARKS_URL = (
    "https://investors.micron.com/static-files/631b1a32-5537-46ae-8f40-82e42fc79dfe"
)
MICRON_Q3_2026_10Q_URL = (
    "https://investors.micron.com/static-files/23023765-dfef-4e7e-845b-cd744fc20d93"
)
SK_HYNIX_Q2_2026_URL = "https://news.skhynix.com/en/q2-2026-business-results/"
SAMSUNG_Q2_2026_URL = "https://news.samsung.com/global/samsung-electronics-announces-second-quarter-2026-results"
CXMT_SSE_PROSPECTUS_URL = (
    "https://static.sse.com.cn/stock/disclosure/announcement/c/202512/002170_20251230_B8QS.pdf"
)


SUPPLY_PRIMARY_SNAPSHOTS: tuple[dict[str, Any], ...] = (
    {
        "fact_key": "inventory",
        "supplier": "Micron",
        "source": "Micron Fiscal Q3 2026 Prepared Remarks",
        "source_type": "company",
        "evidence_type": "quarterly_company",
        "url": MICRON_Q3_2026_PREPARED_REMARKS_URL,
        "timestamp": "2026-06-24T00:00:00+00:00",
        "claim": (
            "Micron reported fiscal-Q3 ending inventory of $8.6 billion and 120 days of inventory; "
            "DRAM inventories were described as very tight and below 120 days."
        ),
        "reliability_score": 0.99,
    },
    {
        "fact_key": "bit_shipments",
        "supplier": "Micron",
        "source": "Micron Fiscal Q3 2026 Form 10-Q",
        "source_type": "filing",
        "evidence_type": "quarterly_filing",
        "url": MICRON_Q3_2026_10Q_URL,
        "timestamp": "2026-06-25T00:00:00+00:00",
        "claim": (
            "Micron reported quarter-over-quarter DRAM bit shipments up in the low-single-digit percentage range "
            "and NAND bit shipments up in the mid-single-digit percentage range in fiscal Q3 2026."
        ),
        "reliability_score": 0.995,
    },
    {
        "fact_key": "capacity",
        "supplier": "Micron",
        "source": "Micron Fiscal Q3 2026 Form 10-Q",
        "source_type": "filing",
        "evidence_type": "quarterly_filing",
        "url": MICRON_Q3_2026_10Q_URL,
        "timestamp": "2026-06-25T00:00:00+00:00",
        "claim": (
            "Micron said its new fabs are intended to provide additional wafer capacity in line with demand trends and "
            "that it is advancing global assembly/test capacity, including plans for advanced HBM packaging capability."
        ),
        "reliability_score": 0.995,
    },
    {
        "fact_key": "capacity",
        "supplier": "SK hynix",
        "source": "SK hynix Q2 2026 Financial Results",
        "source_type": "company",
        "evidence_type": "quarterly_company",
        "url": SK_HYNIX_Q2_2026_URL,
        "timestamp": "2026-07-29T00:00:00+00:00",
        "claim": (
            "SK hynix said customer demand exceeded supply capabilities and it was accelerating M15X mass production while "
            "expanding production capacity through Yongin Phase 1 and the P&T7 advanced-packaging facility."
        ),
        "reliability_score": 0.99,
    },
    {
        "fact_key": "hbm_packaging_yield",
        "supplier": "SK hynix",
        "source": "SK hynix Q2 2026 Financial Results",
        "source_type": "company",
        "evidence_type": "quarterly_company",
        "url": SK_HYNIX_Q2_2026_URL,
        "timestamp": "2026-07-29T00:00:00+00:00",
        "claim": (
            "SK hynix said HBM4 mass shipments began in Q2 and described stable supply capability based on high yield, "
            "while preparing additional advanced-packaging capacity."
        ),
        "reliability_score": 0.99,
    },
    {
        "fact_key": "capacity",
        "supplier": "Samsung",
        "source": "Samsung Electronics Q2 2026 Results",
        "source_type": "company",
        "evidence_type": "quarterly_company",
        "url": SAMSUNG_Q2_2026_URL,
        "timestamp": "2026-07-30T00:00:00+00:00",
        "claim": (
            "Samsung said its Memory Business was increasing production while operating under limited capacity and expected "
            "supply constraints to continue as it scaled HBM4 sales and other high-value server-memory products."
        ),
        "reliability_score": 0.99,
    },
    {
        "fact_key": "utilization",
        "supplier": "CXMT",
        "source": "Shanghai Stock Exchange · CXMT Prospectus",
        "source_type": "regulatory",
        "evidence_type": "annual_filing",
        "url": CXMT_SSE_PROSPECTUS_URL,
        "timestamp": "2025-12-29T00:00:00+00:00",
        "claim": (
            "CXMT's Shanghai Stock Exchange prospectus directly reports utilization of its "
            "12-inch DRAM wafer-manufacturing lines rising across the disclosed periods from "
            "85.45% to 87.06%, 92.46%, and 94.63%."
        ),
        "reliability_score": 0.995,
    },
    {
        "fact_key": "capacity",
        "supplier": "CXMT",
        "source": "Shanghai Stock Exchange · CXMT Prospectus",
        "source_type": "regulatory",
        "evidence_type": "annual_filing",
        "url": CXMT_SSE_PROSPECTUS_URL,
        "timestamp": "2025-12-29T00:00:00+00:00",
        "claim": (
            "CXMT's Shanghai Stock Exchange prospectus states that the company operates three 12-inch DRAM wafer fabs in Hefei and Beijing, "
            "ranks first in China and fourth globally by DRAM capacity and shipment volume, and continues to expand production capacity as new lines are completed."
        ),
        "reliability_score": 0.995,
    },
)


REQUIRED_SUPPLIERS = ("Micron", "SK hynix", "Samsung", "CXMT")


def install_supply_inventory_primary_fallback(module: Any) -> None:
    """Add current supplier-specific operational evidence to Supply / Inventory.

    v0.12.7 covers all four suppliers named by the Committee using primary/company or
    regulatory sources. Wafer starts and utilization remain explicitly open where current
    primary disclosures do not quantify them. Supplier coverage does not substitute for
    missing operational facts.
    """
    prior_capture = module._capture_peer_supply
    prior_lane_status = module._lane_status

    def _persist_supplier_snapshot(case_id: str, case: dict[str, Any], snapshot: dict[str, Any]):
        record = module._persist_record(
            case_id,
            case,
            "supply_inventory",
            str(snapshot["fact_key"]),
            {
                **snapshot,
                "capture_method": "CURATED_SOURCE_LINKED_SUPPLY_PRIMARY_SNAPSHOT",
            },
        )
        if not record:
            return None

        # Preserve supplier provenance on the ledger row without changing the generic
        # primary-evidence schema used by other sectors.
        supplier = str(snapshot.get("supplier") or "").strip()
        if supplier and str(record.get("supplier") or "") != supplier:
            repaired = {
                **record,
                "supplier": supplier,
                "supplier_provenance_added_at": module.utc_now(),
            }
            record_id = str(repaired.get("primary_evidence_id") or "")
            if record_id:
                module.record_object(
                    record_id,
                    "primary_evidence_record",
                    case_id,
                    repaired,
                    topic=case.get("topic"),
                )
                module.record_event(
                    case_id,
                    "PRIMARY_EVIDENCE_SUPPLIER_PROVENANCE_RECORDED",
                    entity_id=record_id,
                    payload={
                        "lane": "supply_inventory",
                        "fact_key": snapshot["fact_key"],
                        "supplier": supplier,
                    },
                )
            return repaired
        return record

    def capture_peer_supply_governed(case_id: str, case: dict[str, Any]):
        added, failures = prior_capture(case_id, case)
        for snapshot in SUPPLY_PRIMARY_SNAPSHOTS:
            record = _persist_supplier_snapshot(case_id, case, snapshot)
            if record:
                added.append(record)
        return added, failures

    def lane_status_supply(case_id: str, lane: str, records: list[dict[str, Any]]):
        result = prior_lane_status(case_id, lane, records)
        if lane != "supply_inventory":
            return result

        lane_rows = [
            row for row in records
            if row.get("lane") == "supply_inventory"
            and row.get("gap_resolution_eligible") is True
        ]
        suppliers = {
            str(row.get("supplier") or "").strip()
            for row in lane_rows
            if str(row.get("supplier") or "").strip()
        }
        missing = [supplier for supplier in REQUIRED_SUPPLIERS if supplier not in suppliers]
        result["supplier_coverage"] = {
            "covered": sorted(suppliers),
            "required": list(REQUIRED_SUPPLIERS),
            "missing": missing,
            "covered_count": len([supplier for supplier in REQUIRED_SUPPLIERS if supplier in suppliers]),
            "required_count": len(REQUIRED_SUPPLIERS),
        }
        result["note"] = (
            "Supplier coverage: "
            + " · ".join(f"{supplier} {'✓' if supplier in suppliers else 'OPEN'}" for supplier in REQUIRED_SUPPLIERS)
            + ". Current primary evidence can verify inventory, bit shipments, capacity expansion and HBM packaging/yield evidence. "
            "CXMT coverage is sourced to its Shanghai Stock Exchange prospectus, which also directly supports utilization. Wafer starts remain open unless directly quantified; "
            "supplier coverage cannot substitute for those missing operational facts."
        )
        return result

    module._capture_peer_supply = capture_peer_supply_governed
    module._lane_status = lane_status_supply
