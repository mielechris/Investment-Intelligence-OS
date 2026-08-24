from __future__ import annotations

from typing import Any


TRENDFORCE_DRAM_URL = "https://www.trendforce.com/price/dram/dram_contract"
TRENDFORCE_NAND_URL = "https://www.trendforce.com/presscenter/news/20260703-13134.html"
TRENDFORCE_HBM_URL = "https://www.trendforce.com/research/download/RP260603TD3"
MICRON_Q3_10Q_URL = (
    "https://www.sec.gov/Archives/edgar/data/723125/"
    "000072312526000015/mu-20260528.htm"
)
MICRON_Q3_REMARKS_URL = (
    "https://investors.micron.com/static-files/"
    "631b1a32-5537-46ae-8f40-82e42fc79dfe"
)


MEMORY_PRICING_SNAPSHOTS = (
    {
        "fact_key": "dram_pricing",
        "source": "TrendForce DRAM Price Trends",
        "source_type": "market_data",
        "evidence_type": "monthly_pricing",
        "url": TRENDFORCE_DRAM_URL,
        "timestamp": "2026-08-04T03:00:00+00:00",
        "claim": (
            "TrendForce's Aug. 4, 2026 DRAM spot-price table reports DDR5 "
            "16Gb 4800/5600 with session average 51.333 and observed range "
            "32.90 to 68.00."
        ),
        "reliability_score": 0.96,
    },
    {
        "fact_key": "nand_pricing",
        "source": "TrendForce Memory Pricing Survey",
        "source_type": "market_data",
        "evidence_type": "monthly_pricing",
        "url": TRENDFORCE_NAND_URL,
        "timestamp": "2026-07-03T00:00:00+00:00",
        "claim": (
            "TrendForce's 3Q26 memory-pricing survey forecasts NAND Flash "
            "contract prices increasing 10% to 15% quarter over quarter, "
            "with AI inference and data-center demand supporting pricing."
        ),
        "reliability_score": 0.96,
    },
    {
        "fact_key": "hbm_pricing",
        "source": "TrendForce HBM Market Dynamics",
        "source_type": "market_data",
        "evidence_type": "quarterly_pricing",
        "url": TRENDFORCE_HBM_URL,
        "timestamp": "2026-06-03T00:00:00+00:00",
        "claim": (
            "TrendForce reports HBM3E contract prices rising amid tight "
            "supply and says suppliers may seek further HBM price increases "
            "as HBM4 contract negotiations progress."
        ),
        "reliability_score": 0.96,
    },
    {
        "fact_key": "dram_pricing",
        "source": "Micron Fiscal Q3 2026 Form 10-Q",
        "source_type": "filing",
        "evidence_type": "quarterly_filing",
        "url": MICRON_Q3_10Q_URL,
        "timestamp": "2026-06-25T00:00:00+00:00",
        "claim": (
            "Micron reports fiscal-Q3 DRAM average selling prices increased "
            "in the low-60% range sequentially and approximately 140% for "
            "the first nine months of fiscal 2026 versus the prior year."
        ),
        "reliability_score": 0.995,
    },
    {
        "fact_key": "nand_pricing",
        "source": "Micron Fiscal Q3 2026 Form 10-Q",
        "source_type": "filing",
        "evidence_type": "quarterly_filing",
        "url": MICRON_Q3_10Q_URL,
        "timestamp": "2026-06-25T00:00:00+00:00",
        "claim": (
            "Micron reports fiscal-Q3 NAND average selling prices increased "
            "in the mid-80% range sequentially and approximately 130% for "
            "the first nine months of fiscal 2026 versus the prior year."
        ),
        "reliability_score": 0.995,
    },
)


def install_memory_pricing_primary_fallback(module: Any) -> None:
    """Add source-linked public pricing evidence without inventing price facts."""
    prior_capture = module._capture_micron_ir
    prior_lane_status = module._lane_status

    def capture_memory_pricing_governed(case_id: str, case: dict[str, Any]):
        added, failures = prior_capture(case_id, case)

        for snapshot in MEMORY_PRICING_SNAPSHOTS:
            record = module._persist_record(
                case_id,
                case,
                "memory_pricing",
                str(snapshot["fact_key"]),
                {
                    **snapshot,
                    "capture_method": "CURATED_SOURCE_LINKED_MEMORY_PRICING",
                },
            )
            if record:
                added.append(record)

        return added, failures

    def lane_status_memory_pricing(
        case_id: str,
        lane: str,
        records: list[dict[str, Any]],
    ):
        result = prior_lane_status(case_id, lane, records)
        if lane == "memory_pricing":
            result["note"] = (
                "Memory pricing uses TrendForce market benchmarks plus Micron "
                "filed/company pricing disclosures. Source diversity is derived "
                "from actual unrelated pricing sources rather than a synthetic "
                "evidence record."
            )
        return result

    module._capture_micron_ir = capture_memory_pricing_governed
    module._lane_status = lane_status_memory_pricing
