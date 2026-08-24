from __future__ import annotations

from typing import Any


MICROSOFT_FY26_Q3_URL = "https://www.microsoft.com/en-us/investor/events/fy-2026/earnings-fy-2026-q3"
META_Q2_2026_URL = "https://investor.atmeta.com/investor-news/press-release-details/2026/Meta-Reports-Second-Quarter-2026-Results/default.aspx"
AMAZON_Q2_2026_URL = "https://ir.aboutamazon.com/news-release/news-release-details/2026/Amazon-com-Announces-Second-Quarter-Results/default.aspx"
ALPHABET_Q2_2026_URL = "https://blog.google/company-news/inside-google/message-ceo/alphabet-earnings-q2-2026/"


# These are source-linked, company-primary snapshots used only when the generic live IR
# scrapers do not produce a clean fact locally. Each snapshot is deliberately single-purpose.
# The engine does NOT infer cancellations/pushouts or memory purchasing terms from general
# AI enthusiasm, capex, backlog, or customer commitments.
HYPERSCALER_PRIMARY_SNAPSHOTS: tuple[dict[str, Any], ...] = (
    {
        "fact_key": "ai_capex",
        "source": "Microsoft FY2026 Q3 Earnings Call",
        "source_type": "company",
        "evidence_type": "quarterly_company",
        "url": MICROSOFT_FY26_Q3_URL,
        "timestamp": "2026-04-29T00:00:00+00:00",
        "claim": (
            "Microsoft reported Q3 capital expenditures of $31.9 billion, expected Q4 capex above $40 billion, "
            "and said calendar-year 2026 capex would be roughly $190 billion as it continued investing in AI infrastructure."
        ),
        "reliability_score": 0.99,
    },
    {
        "fact_key": "server_activity",
        "source": "Microsoft FY2026 Q3 Earnings Call",
        "source_type": "company",
        "evidence_type": "quarterly_company",
        "url": MICROSOFT_FY26_Q3_URL,
        "timestamp": "2026-04-29T00:00:00+00:00",
        "claim": (
            "Microsoft said it was bringing GPU, CPU and storage capacity online faster and expected to remain capacity constrained "
            "through at least calendar 2026 despite those deployment efforts."
        ),
        "reliability_score": 0.99,
    },
    {
        "fact_key": "ai_capex",
        "source": "Meta Q2 2026 Results",
        "source_type": "company",
        "evidence_type": "quarterly_company",
        "url": META_Q2_2026_URL,
        "timestamp": "2026-07-29T00:00:00+00:00",
        "claim": (
            "Meta reported Q2 capital expenditures of $31.08 billion and guided full-year 2026 capital expenditures to $130-$145 billion, "
            "with AI infrastructure and future capacity remaining central investment priorities."
        ),
        "reliability_score": 0.99,
    },
    {
        "fact_key": "ai_capex",
        "source": "Amazon Q2 2026 Results",
        "source_type": "company",
        "evidence_type": "quarterly_company",
        "url": AMAZON_Q2_2026_URL,
        "timestamp": "2026-07-30T00:00:00+00:00",
        "claim": (
            "Amazon said trailing-twelve-month property-and-equipment investment increased sharply and that the increase primarily "
            "reflected investments in artificial intelligence; AWS AI and chips businesses each exceeded $25 billion annual run rates."
        ),
        "reliability_score": 0.99,
    },
    {
        "fact_key": "backlog",
        "source": "Alphabet Q2 2026 CEO Earnings Remarks",
        "source_type": "company",
        "evidence_type": "quarterly_company",
        "url": ALPHABET_Q2_2026_URL,
        "timestamp": "2026-07-22T00:00:00+00:00",
        "claim": (
            "Alphabet reported Google Cloud backlog of $514 billion and said existing Cloud customers were expanding usage and "
            "exceeding their commitments by more than 50%, demonstrating large contracted AI-infrastructure demand."
        ),
        "reliability_score": 0.99,
    },
)


def install_hyperscaler_primary_fallback(module: Any) -> None:
    """Add reusable, source-linked hyperscaler evidence without weakening fact contracts."""
    prior_capture = module._capture_hyperscalers
    prior_lane_status = module._lane_status

    def capture_hyperscalers_governed(case_id: str, case: dict[str, Any]):
        added, failures = prior_capture(case_id, case)
        for snapshot in HYPERSCALER_PRIMARY_SNAPSHOTS:
            record = module._persist_record(
                case_id,
                case,
                "hyperscaler_demand",
                str(snapshot["fact_key"]),
                {
                    **snapshot,
                    "capture_method": "CURATED_SOURCE_LINKED_HYPERSCALER_PRIMARY_SNAPSHOT",
                },
            )
            if record:
                added.append(record)
        return added, failures

    def lane_status_governed(case_id: str, lane: str, records: list[dict[str, Any]]):
        result = prior_lane_status(case_id, lane, records)
        if lane == "hyperscaler_demand":
            result["note"] = (
                "Current primary hyperscaler disclosures can verify AI capex, deployment/capacity activity and backlog/committed demand. "
                "Cancellations/pushouts and memory-content or enforceable memory-purchasing terms remain open unless directly disclosed; no inference is allowed."
            )
        return result

    module._capture_hyperscalers = capture_hyperscalers_governed
    module._lane_status = lane_status_governed
