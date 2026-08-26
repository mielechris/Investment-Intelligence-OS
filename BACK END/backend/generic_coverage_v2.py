from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from fastapi import APIRouter

import generic_primary_evidence as generic
import required_evidence_reconciler as reconciler

from ledger import utc_now
from official_sources import fetch_official_web


router = APIRouter()

POLICY_VERSION = "generic-coverage-routing-v2"

_ORIGINAL_CAPTURE = generic.capture_generic_primary_evidence
_ORIGINAL_GENERIC_STATE = reconciler._generic_state


COMPANY_PROFILES = {
    "XOM": {
        "sector": "ENERGY",
        "company": "Exxon Mobil",
        "ir_sources": [
            (
                "https://corporate.exxonmobil.com/investors",
                "ExxonMobil Investor Relations",
            ),
        ],
        "keywords": [
            "production",
            "Guyana",
            "upstream",
            "downstream",
            "refining",
            "volumes",
            "margins",
            "capex",
            "cash flow",
        ],
        "external_sources": [
            (
                "https://www.eia.gov/petroleum/",
                "U.S. Energy Information Administration",
                "official",
                [
                    "crude oil",
                    "inventories",
                    "refinery",
                    "production",
                    "prices",
                ],
            ),
        ],
    },

    "JPM": {
        "sector": "BANK",
        "company": "JPMorgan Chase",
        "ir_sources": [
            (
                "https://www.jpmorganchase.com/ir",
                "JPMorgan Chase Investor Relations",
            ),
        ],
        "keywords": [
            "net interest income",
            "net interest margin",
            "deposits",
            "loans",
            "credit",
            "charge-offs",
            "CET1",
            "capital",
            "investment banking",
        ],
        "external_sources": [],
    },

    "AMZN": {
        "sector": "CLOUD_CONSUMER",
        "company": "Amazon",
        "ir_sources": [
            (
                "https://ir.aboutamazon.com/",
                "Amazon Investor Relations",
            ),
        ],
        "keywords": [
            "AWS",
            "advertising",
            "operating income",
            "capex",
            "free cash flow",
            "fulfillment",
            "customers",
            "AI",
        ],
        "external_sources": [],
    },

    "MSFT": {
        "sector": "CLOUD_SOFTWARE",
        "company": "Microsoft",
        "ir_sources": [
            (
                "https://www.microsoft.com/en-us/Investor",
                "Microsoft Investor Relations",
            ),
        ],
        "keywords": [
            "Azure",
            "cloud",
            "AI",
            "data center",
            "capital expenditures",
            "bookings",
            "commercial remaining performance obligation",
            "margins",
        ],
        "external_sources": [],
    },

    "AVGO": {
        "sector": "SEMICONDUCTOR_INFRASTRUCTURE",
        "company": "Broadcom",
        "ir_sources": [
            (
                "https://investors.broadcom.com/",
                "Broadcom Investor Relations",
            ),
        ],
        "keywords": [
            "AI",
            "networking",
            "VMware",
            "semiconductor",
            "revenue",
            "backlog",
            "shipments",
            "margins",
        ],
        "external_sources": [
            (
                "https://investors.delltechnologies.com/",
                "Dell Technologies Investor Relations",
                "company",
                [
                    "AI servers",
                    "backlog",
                    "shipments",
                    "orders",
                ],
            ),
            (
                "https://investors.hpe.com/",
                "HPE Investor Relations",
                "company",
                [
                    "AI systems",
                    "server",
                    "orders",
                    "backlog",
                ],
            ),
        ],
    },

    "GOOGL": {
        "sector": "CLOUD_ADVERTISING",
        "company": "Alphabet",
        "ir_sources": [
            (
                "https://abc.xyz/investor/",
                "Alphabet Investor Relations",
            ),
        ],
        "keywords": [
            "Google Cloud",
            "advertising",
            "AI",
            "capex",
            "data center",
            "operating margin",
        ],
        "external_sources": [],
    },

    "AMD": {
        "sector": "SEMICONDUCTOR",
        "company": "AMD",
        "ir_sources": [
            (
                "https://ir.amd.com/",
                "AMD Investor Relations",
            ),
        ],
        "keywords": [
            "data center",
            "AI",
            "MI300",
            "revenue",
            "margin",
            "inventory",
            "supply",
        ],
        "external_sources": [],
    },

    "NVDA": {
        "sector": "SEMICONDUCTOR",
        "company": "NVIDIA",
        "ir_sources": [
            (
                "https://investor.nvidia.com/",
                "NVIDIA Investor Relations",
            ),
        ],
        "keywords": [
            "data center",
            "AI",
            "revenue",
            "gross margin",
            "supply",
            "inventory",
        ],
        "external_sources": [],
    },
}


def _add(
    targets: list[dict[str, str]],
    lane: str,
    fact_key: str,
) -> None:
    key = (lane, fact_key)

    if key in {
        (
            row.get("lane"),
            row.get("fact_key"),
        )
        for row in targets
    }:
        return

    targets.append({
        "lane": lane,
        "fact_key": fact_key,
    })


def _contains(
    text: str,
    terms: tuple[str, ...],
) -> bool:
    return any(
        term in text
        for term in terms
    )


def generic_company_targets_v2(
    requirement: str,
) -> list[dict[str, str]]:
    """
    Requirement Router V2.

    Route by semantic groups rather than broad single-word
    matches. In particular, company production volume must
    not become stock trading volume, and server demand must
    not become policy merely because a sentence is complex.
    """
    text = reconciler._norm(
        requirement
    )

    targets: list[
        dict[str, str]
    ] = []

    financial_terms = (
        "10-q",
        "10-k",
        "annual report",
        "quarterly report",
        "earnings release",
        "financial statements",
        "free cash flow",
        "cash flow",
        "balance sheet",
        "operating income",
        "net income",
        "diluted shares",
        "shares outstanding",
        "gross margin",
        "operating margin",
        "capex",
        "depreciation",
        "revenue",
    )

    market_terms = (
        "current stock price",
        "current share price",
        "current price",
        "market price",
        "market capitalization",
        "trading volume",
        "daily volume",
        "relative strength",
        "volatility",
        "liquidity",
        "technical",
        "price trend",
        "confirmed catalyst",
    )

    valuation_terms = (
        "valuation",
        "forward p/e",
        "p/e",
        "ev/ebitda",
        "enterprise value",
        "forward eps",
        "forward revenue",
        "consensus",
        "analyst revision",
        "analyst estimate",
        "estimate revision",
        "peer multiple",
        "historical multiple",
    )

    positioning_terms = (
        "short interest",
        "options positioning",
        "put/call",
        "open interest",
        "institutional flows",
        "institutional or etf flows",
        "etf flows",
        "positioning",
        "crowding",
    )

    portfolio_terms = (
        "portfolio holdings",
        "portfolio weights",
        "portfolio exposure",
        "factor exposure",
        "factor overlap",
        "correlation",
        "concentration",
        "risk limits",
        "liquidity needs",
        "drawdown scenario",
        "drawdown stress",
        "benchmark",
        "portfolio state",
    )

    policy_terms = (
        "government",
        "regulatory",
        "regulation",
        "antitrust",
        "export control",
        "tariff",
        "sanction",
        "federal register",
        "procurement award",
        "government award",
        "incentive",
        "tax policy",
        "trade restriction",
    )

    operating_terms = (
        "production",
        "shipment",
        "shipments",
        "server",
        "backlog",
        "bookings",
        "orders",
        "utilization",
        "capacity",
        "customer",
        "customers",
        "subscriber",
        "advertising",
        "aws",
        "azure",
        "cloud",
        "data center",
        "networking",
        "vmware",
        "inventory",
        "refining",
        "upstream",
        "downstream",
        "guyana",
        "net interest income",
        "net interest margin",
        "nim",
        "deposit",
        "deposits",
        "loan growth",
        "credit losses",
        "charge-off",
        "cet1",
        "guidance",
        "market share",
        "power availability",
        "hardware lead time",
        "adoption",
        "restocking",
        "end consumption",
    )

    independent_terms = (
        "independent",
        "independent confirmation",
        "third-party",
        "third party",
        "server oem",
        "external confirmation",
        "cross-check",
        "cross check",
    )

    energy_operating_terms = (
        "brent",
        "wti",
        "crude",
        "refinery",
        "refining margin",
        "spare capacity",
        "freight",
        "hormuz",
        "shipping delay",
    )

    if _contains(
        text,
        financial_terms,
    ):
        _add(
            targets,
            "generic_company_financials",
            "filing_financials",
        )

    if _contains(
        text,
        market_terms,
    ):
        _add(
            targets,
            "generic_market_context",
            "current_market",
        )

    if _contains(
        text,
        valuation_terms,
    ):
        _add(
            targets,
            "generic_market_context",
            "valuation_consensus",
        )

    if _contains(
        text,
        positioning_terms,
    ):
        _add(
            targets,
            "generic_market_context",
            "market_positioning",
        )

    if _contains(
        text,
        portfolio_terms,
    ):
        _add(
            targets,
            "generic_portfolio_context",
            "portfolio_state",
        )

    if _contains(
        text,
        policy_terms,
    ):
        _add(
            targets,
            "generic_policy_context",
            "official_policy",
        )

    if (
        _contains(
            text,
            operating_terms,
        )
        or _contains(
            text,
            energy_operating_terms,
        )
    ):
        _add(
            targets,
            "generic_operating_context",
            "operating_kpis",
        )

    if _contains(
        text,
        independent_terms,
    ):
        _add(
            targets,
            "generic_external_context",
            "independent_corroboration",
        )

    return targets


def _source_identity(
    item: dict[str, Any],
) -> str:
    raw = (
        item.get("raw")
        if isinstance(
            item.get("raw"),
            dict,
        )
        else item
    )

    url = str(
        raw.get("url")
        or item.get("url")
        or ""
    ).strip()

    host = (
        urlparse(url).netloc.lower()
        if url
        else ""
    )

    source = str(
        raw.get("source")
        or item.get("source")
        or ""
    ).strip().lower()

    return host or source


def generic_state_v2(
    packet_items: list[
        dict[str, Any]
    ],
    lane: str,
    fact_key: str,
) -> dict[str, Any]:

    if (
        lane
        != "generic_external_context"
    ):
        return _ORIGINAL_GENERIC_STATE(
            packet_items,
            lane,
            fact_key,
        )

    if (
        fact_key
        != "independent_corroboration"
    ):
        return {
            "state": "OPEN",
            "covered": False,
        }

    current = [
        item
        for item in packet_items
        if isinstance(item, dict)
        and not item.get("stale")
        and not item.get(
            "missing_fields"
        )
    ]

    qualifying = []

    for item in current:
        raw = (
            item.get("raw")
            if isinstance(
                item.get("raw"),
                dict,
            )
            else item
        )

        lane_value = str(
            raw.get(
                "primary_evidence_lane"
            )
            or item.get(
                "primary_evidence_lane"
            )
            or ""
        )

        fact_value = str(
            raw.get(
                "primary_fact_key"
            )
            or item.get(
                "primary_fact_key"
            )
            or ""
        )

        source_type = str(
            raw.get("source_type")
            or item.get("source_type")
            or ""
        ).lower()

        if (
            lane_value
            == "generic_external_context"
            and fact_value
            == "independent_corroboration"
            and source_type
            in {
                "company",
                "official",
                "regulatory",
                "research",
            }
        ):
            qualifying.append(item)

    identities = {
        _source_identity(item)
        for item in qualifying
        if _source_identity(item)
    }

    if len(identities) >= 2:
        return {
            "state": "SATISFIED",
            "covered": True,
            "independent_sources":
                len(identities),
        }

    if len(identities) == 1:
        return {
            "state": "WATCHING",
            "covered": False,
            "watch_state":
                reconciler.WATCH_STATE,
            "independent_sources": 1,
        }

    return {
        "state": "OPEN",
        "covered": False,
        "independent_sources": 0,
    }


def _capture_sector_operating(
    case_id: str,
    case: dict[str, Any],
    ticker: str,
) -> tuple[
    list[dict[str, Any]],
    list[str],
]:
    profile = COMPANY_PROFILES.get(
        ticker
    )

    if not profile:
        return [], []

    records = []
    failures = []

    for url, label in (
        profile.get("ir_sources")
        or []
    ):
        try:
            items = fetch_official_web({
                "url": url,
                "label": label,
                "keywords":
                    profile["keywords"],
                "limit": 6,
                "evidence_type":
                    "fundamental",
                "reliability_score":
                    0.94,
                "window_chars":
                    1000,
            })

            for item in items:
                record = generic._persist(
                    case_id=case_id,
                    case=case,
                    lane=
                        "generic_operating_context",
                    fact_key=
                        "operating_kpis",
                    item={
                        **item,
                        "source_type":
                            "company",
                    },
                    source_grade=
                        "PRIMARY_COMPANY",
                )

                if record:
                    records.append(record)

        except Exception as exc:
            failures.append(
                "OPERATING:"
                f"{label}:"
                f"{type(exc).__name__}:"
                f"{exc}"
            )

    return records, failures


def _capture_external_context(
    case_id: str,
    case: dict[str, Any],
    ticker: str,
) -> tuple[
    list[dict[str, Any]],
    list[str],
]:
    profile = COMPANY_PROFILES.get(
        ticker
    )

    if not profile:
        return [], []

    records = []
    failures = []

    for (
        url,
        label,
        source_type,
        keywords,
    ) in (
        profile.get(
            "external_sources"
        )
        or []
    ):
        try:
            items = fetch_official_web({
                "url": url,
                "label": label,
                "keywords": keywords,
                "limit": 5,
                "evidence_type":
                    "fundamental",
                "reliability_score":
                    0.95,
                "window_chars":
                    1000,
            })

            for item in items:
                normalized = {
                    **item,
                    "source_type":
                        source_type,
                }

                record = generic._persist(
                    case_id=case_id,
                    case=case,
                    lane=
                        "generic_external_context",
                    fact_key=
                        "independent_corroboration",
                    item=normalized,
                    source_grade=(
                        "PRIMARY_OFFICIAL"
                        if source_type
                        in {
                            "official",
                            "regulatory",
                        }
                        else
                        "PRIMARY_COMPANY"
                    ),
                )

                if record:
                    records.append(record)

        except Exception as exc:
            failures.append(
                "EXTERNAL:"
                f"{label}:"
                f"{type(exc).__name__}:"
                f"{exc}"
            )

    return records, failures


def _capture_portfolio_v2(
    case_id: str,
    case: dict[str, Any],
    ticker: str,
) -> tuple[
    list[dict[str, Any]],
    list[str],
]:
    records = []
    failures = []

    try:
        state = (
            generic.build_portfolio_state()
        )

        nav = float(
            state.get("nav")
            or 0.0
        )

        cash = float(
            state.get("cash")
            or 0.0
        )

        gross = float(
            state.get(
                "gross_exposure"
            )
            or state.get(
                "gross_exposure_pct"
            )
            or 0.0
        )

        drawdown = float(
            state.get(
                "current_drawdown_pct"
            )
            or state.get(
                "drawdown_pct"
            )
            or 0.0
        )

        positions = (
            state.get("positions")
            or []
        )

        exact_value = sum(
            float(
                row.get("market_value")
                or row.get("notional")
                or 0.0
            )
            for row in positions
            if str(
                row.get("ticker")
                or row.get("symbol")
                or ""
            ).upper()
            == ticker
        )

        overlap_pct = (
            exact_value / nav * 100.0
            if nav > 0
            else 0.0
        )

        # Make the current snapshot authoritative.
        if hasattr(
            generic,
            "_supersede_portfolio",
        ):
            generic._supersede_portfolio(
                case_id,
                case,
            )

        stamp = utc_now()

        item = {
            "source":
                "IIOS governed paper portfolio",

            "source_type":
                "portfolio_data",

            "evidence_type":
                "portfolio_snapshot",

            "url":
                (
                    "iios://paper-portfolio/"
                    f"{case_id}/coverage-v2/"
                    f"{stamp}"
                ),

            "title":
                (
                    f"{ticker} prospective "
                    "governed portfolio state"
                ),

            "claim":
                (
                    "Prospective governed portfolio "
                    f"state for {ticker}: "
                    f"NAV={nav}; cash={cash}; "
                    f"gross exposure={gross}; "
                    f"exact ticker overlap="
                    f"{round(overlap_pct, 4)}%; "
                    f"current drawdown="
                    f"{round(drawdown, 4)}%; "
                    f"position count="
                    f"{len(positions)}."
                ),

            "timestamp":
                stamp,

            "reliability_score":
                1.0,
        }

        record = generic._persist(
            case_id=case_id,
            case=case,
            lane=
                "generic_portfolio_context",
            fact_key=
                "portfolio_overlap",
            item=item,
            source_grade=
                "FIRST_PARTY_GOVERNED",
            verified_public_source=
                False,
        )

        if record:
            records.append(record)

    except Exception as exc:
        failures.append(
            "PORTFOLIO_V2:"
            f"{type(exc).__name__}: "
            f"{exc}"
        )

    return records, failures


def capture_generic_primary_evidence_v2(
    case_id: str,
) -> dict[str, Any]:

    base = _ORIGINAL_CAPTURE(
        case_id
    )

    case = generic._require_case(
        case_id
    )

    ticker = generic._case_ticker(
        case_id,
        case,
    )

    # Keep Micron's legacy specialized engine intact.
    if ticker == "MU":
        return {
            **base,
            "coverage_v2":
                "SKIPPED_LEGACY_MICRON",
        }

    added = []
    failures = []

    for function in (
        _capture_sector_operating,
        _capture_external_context,
        _capture_portfolio_v2,
    ):
        records, errors = function(
            case_id,
            case,
            ticker,
        )

        added.extend(records)
        failures.extend(errors)

    merged_failures = list(
        base.get("failures")
        or []
    ) + failures

    return {
        **base,

        "policy_version":
            POLICY_VERSION,

        "coverage_v2":
            "COMPLETE",

        "sector_profile":
            (
                COMPANY_PROFILES.get(
                    ticker,
                    {}
                ).get("sector")
            ),

        "v2_records_seen_or_added":
            len(added),

        "records_seen_or_added":
            (
                int(
                    base.get(
                        "records_seen_or_added"
                    )
                    or 0
                )
                + len(added)
            ),

        "failures":
            merged_failures,

        "failure_count":
            len(merged_failures),

        "trade_execution_permission":
            False,

        "live_execution":
            False,
    }


def install_generic_coverage_v2() -> None:
    if getattr(
        generic,
        "_GROUP_BATCH6_INSTALLED",
        False,
    ):
        return

    # Requirement Router V2.
    reconciler._generic_company_targets = (
        generic_company_targets_v2
    )

    # New governed external-context lane.
    reconciler._generic_state = (
        generic_state_v2
    )

    # Upgrade Generic Primary Evidence without replacing
    # the proven Group Batch 5 engine.
    generic.capture_generic_primary_evidence = (
        capture_generic_primary_evidence_v2
    )

    # required_evidence_risk_guard imported reconcile_committee
    # by value, so rebind it to the upgraded reconciler.
    import required_evidence_risk_guard as risk_guard

    risk_guard.reconcile_committee = (
        reconciler.reconcile_committee
    )

    generic._GROUP_BATCH6_INSTALLED = True


@router.get(
    "/generic-coverage-v2/{case_id}"
)
def coverage_status(
    case_id: str,
):
    case = generic._require_case(
        case_id
    )

    ticker = generic._case_ticker(
        case_id,
        case,
    )

    return {
        "case_id": case_id,
        "ticker": ticker,
        "policy_version":
            POLICY_VERSION,
        "sector_profile":
            COMPANY_PROFILES.get(
                ticker
            ),
        "paper_mode": True,
        "trade_execution_permission":
            False,
        "live_execution": False,
    }
