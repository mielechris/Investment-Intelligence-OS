from __future__ import annotations

import json
import re
from collections import Counter
from typing import Any
from urllib.parse import urlencode
from uuid import uuid4

from fastapi import APIRouter, HTTPException

from analyst_consensus_fallback import _fetch_stockanalysis
from finra_short_interest_fallback import _fetch_finra
from ledger import (
    get_object,
    latest_object,
    list_objects,
    record_event,
    record_object,
    utc_now,
)
from paper_portfolio_core import build_portfolio_state
from provider_hardening import (
    SEC_USER_AGENT,
    _request_bytes,
    fetch_market_quote,
    fetch_sec_companyfacts,
)


router = APIRouter()

POLICY_VERSION = "generic-primary-evidence-v1"

# Stable SEC registrant identifiers for the current
# validation cohort. This avoids making every research
# run depend on SEC's company_tickers.json endpoint,
# which may return 403 even while Company Facts remains
# available.
KNOWN_SEC_CIKS = {
    "XOM": "34088",
    "JPM": "19617",
    "AMZN": "1018724",
    "MSFT": "789019",
    "AVGO": "1730168",
}

FINANCIAL_TAGS = [
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "Revenues",
    "OperatingIncomeLoss",
    "NetIncomeLoss",
    "NetCashProvidedByUsedInOperatingActivities",
    "PaymentsToAcquirePropertyPlantAndEquipment",
    "DepreciationDepletionAndAmortization",
    "CashAndCashEquivalentsAtCarryingValue",
    "Assets",
    "Liabilities",
    "WeightedAverageNumberOfDilutedSharesOutstanding",
]

LANE_LABELS = {
    "generic_company_financials":
        "Generic Company Financials",
    "generic_market_context":
        "Generic Market / Valuation",
    "generic_policy_context":
        "Generic Policy / Regulation",
    "generic_portfolio_context":
        "Governed Portfolio Context",
}


def _require_case(
    case_id: str,
) -> dict[str, Any]:
    case = get_object(case_id)

    if (
        not case
        or not case_id.startswith("case_")
    ):
        raise HTTPException(
            status_code=404,
            detail="Unknown case_id",
        )

    return case


def _case_ticker(
    case_id: str,
    case: dict[str, Any],
) -> str:
    profile = latest_object(
        "monitor_profile",
        case_id=case_id,
    ) or {}

    ticker = str(
        profile.get("ticker")
        or case.get("ticker")
        or ""
    ).strip().upper()

    if not ticker:
        candidate_id = str(
            case.get("source_candidate_id")
            or ""
        ).strip()

        if candidate_id:
            candidate = (
                get_object(candidate_id)
                or {}
            )

            ticker = str(
                candidate.get("ticker")
                or ""
            ).strip().upper()

    if not ticker:
        topic = str(
            case.get("topic")
            or ""
        )

        match = re.search(
            r"\(([A-Z][A-Z0-9.\-]{0,9})\)",
            topic,
        )

        if match:
            ticker = match.group(1)

    if ticker.endswith(".US"):
        ticker = ticker[:-3]

    if not ticker:
        raise ValueError(
            "Unable to resolve case ticker"
        )

    return ticker


def _resolve_cik(
    ticker: str,
) -> str:
    wanted = ticker.strip().upper()

    known = KNOWN_SEC_CIKS.get(wanted)
    if known:
        return known

    url = (
        "https://www.sec.gov/files/"
        "company_tickers.json"
    )

    raw = _request_bytes(
        url,
        user_agent=SEC_USER_AGENT,
        provider="sec_ticker_map",
        minimum_interval_seconds=0.2,
        retries=2,
        cache_ttl_seconds=24 * 60 * 60,
    )

    payload = json.loads(
        raw.decode("utf-8")
    )

    for row in payload.values():
        if (
            str(
                row.get("ticker")
                or ""
            ).upper()
            != wanted
        ):
            continue

        cik = str(
            row.get("cik_str")
            or ""
        ).strip()

        if cik:
            return cik

    raise ValueError(
        f"SEC CIK not found for {ticker}"
    )


def _committee_requirements(
    case_id: str,
) -> list[str]:
    decision = latest_object(
        "committee_decision",
        case_id=case_id,
    ) or {}

    return [
        str(value).strip()
        for value in (
            decision.get(
                "required_evidence"
            )
            or []
        )
        if str(value).strip()
    ]


def _persist(
    *,
    case_id: str,
    case: dict[str, Any],
    lane: str,
    fact_key: str,
    item: dict[str, Any],
    source_grade: str,
    verified_public_source: bool = True,
) -> dict[str, Any] | None:

    claim = str(
        item.get("claim")
        or item.get("title")
        or ""
    ).strip()

    url = str(
        item.get("url")
        or ""
    ).strip()

    if not claim or not url:
        return None

    fingerprint = (
        lane,
        fact_key,
        url.lower(),
        claim.lower(),
    )

    for prior in list_objects(
        case_id,
        "primary_evidence_record",
    ):
        prior_key = (
            str(
                prior.get("lane")
                or ""
            ),
            str(
                prior.get("fact_key")
                or ""
            ),
            str(
                prior.get("source_url")
                or ""
            ).lower(),
            str(
                prior.get("claim")
                or ""
            ).lower(),
        )

        if prior_key == fingerprint:
            return prior

    record_id = (
        f"primary_evidence_"
        f"{uuid4().hex}"
    )

    record = {
        "primary_evidence_id":
            record_id,

        "case_id":
            case_id,

        "topic":
            case.get("topic"),

        "lane":
            lane,

        "lane_label":
            LANE_LABELS.get(
                lane,
                lane,
            ),

        "fact_key":
            fact_key,

        "claim":
            claim,

        "source_name":
            str(
                item.get("source")
                or "Governed source"
            ),

        "source_url":
            url,

        "source_type":
            str(
                item.get("source_type")
                or "official"
            ).lower(),

        "source_grade":
            source_grade,

        "evidence_type":
            str(
                item.get("evidence_type")
                or "fundamental"
            ),

        "observed_at":
            item.get("timestamp")
            or utc_now(),

        "reliability_score":
            float(
                item.get(
                    "reliability_score"
                )
                or 0.90
            ),

        "gap_resolution_eligible":
            True,

        "verified_public_source":
            verified_public_source,

        "first_party_governed_source":
            (
                source_grade
                == "FIRST_PARTY_GOVERNED"
            ),

        "paper_mode":
            True,

        "auto_trade_authority":
            False,

        "trade_execution_permission":
            False,

        "live_execution":
            False,

        "created_at":
            utc_now(),
    }

    record_object(
        record_id,
        "primary_evidence_record",
        case_id,
        record,
        topic=case.get("topic"),
    )

    record_event(
        case_id,
        "GENERIC_PRIMARY_EVIDENCE_RECORDED",
        entity_id=record_id,
        payload={
            "lane":
                lane,

            "fact_key":
                fact_key,

            "source_grade":
                source_grade,

            "trade_execution_permission":
                False,

            "live_execution":
                False,
        },
    )

    return record


def _capture_financials(
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
        cik = _resolve_cik(ticker)

        items = fetch_sec_companyfacts(
            {
                "cik": cik,
                "tags":
                    FINANCIAL_TAGS,
                "limit": 30,
            }
        )

        for item in items:
            normalized = {
                **item,
                "source":
                    "SEC EDGAR",
                "source_type":
                    "filing",
                "evidence_type":
                    "fundamental",
            }

            record = _persist(
                case_id=case_id,
                case=case,
                lane=
                    "generic_company_financials",
                fact_key=
                    "filing_financials",
                item=normalized,
                source_grade=
                    "PRIMARY_OFFICIAL",
            )

            if record:
                records.append(record)

    except Exception as exc:
        failures.append(
            "SEC:"
            f"{type(exc).__name__}: "
            f"{exc}"
        )

    return records, failures


def _capture_market(
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
        quote = fetch_market_quote(
            ticker
        )

        if quote.get("status") != "ok":
            raise ValueError(
                quote.get("error")
                or "Market quote unavailable"
            )

        for item in (
            quote.get("items")
            or []
        )[:1]:
            normalized = {
                **item,

                "source_type":
                    "market_data",

                "evidence_type":
                    "market_data",

                "claim":
                    (
                        f"{ticker} current "
                        f"market price="
                        f"{quote.get('current_price')}"
                    ),
            }

            record = _persist(
                case_id=case_id,
                case=case,
                lane=
                    "generic_market_context",
                fact_key=
                    "current_market",
                item=normalized,
                source_grade=
                    "HARD_MARKET_DATA",
            )

            if record:
                records.append(record)

    except Exception as exc:
        failures.append(
            "MARKET:"
            f"{type(exc).__name__}: "
            f"{exc}"
        )

    return records, failures


def _capture_consensus(
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
        parsed, url = (
            _fetch_stockanalysis(
                ticker
            )
        )

        item = {
            "source":
                "StockAnalysis analyst "
                "forecast aggregation",

            "source_type":
                "consensus_data",

            "evidence_type":
                "analyst_consensus",

            "url":
                url,

            "title":
                f"{ticker} governed "
                "consensus",

            "claim":
                (
                    f"{ticker} forward EPS "
                    f"consensus="
                    f"{parsed.get('eps_consensus')}; "
                    f"consensus revenue="
                    f"{parsed.get('revenue_consensus')}; "
                    f"fiscal year="
                    f"{parsed.get('year')}; "
                    f"attribution="
                    f"{parsed.get('attribution')}."
                ),

            "timestamp":
                parsed.get(
                    "updated_at"
                )
                or utc_now(),

            "reliability_score":
                0.84,
        }

        record = _persist(
            case_id=case_id,
            case=case,
            lane=
                "generic_market_context",
            fact_key=
                "valuation_consensus",
            item=item,
            source_grade=
                "GOVERNED_CONSENSUS",
        )

        if record:
            records.append(record)

    except Exception as exc:
        failures.append(
            "CONSENSUS:"
            f"{type(exc).__name__}: "
            f"{exc}"
        )

    return records, failures


def _capture_positioning(
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
        data, api_url, public_url = (
            _fetch_finra(ticker)
        )

        item = {
            "source":
                "FINRA Consolidated "
                "Short Interest",

            "source_type":
                "regulatory",

            "evidence_type":
                "short_interest",

            "url":
                public_url,

            "title":
                f"{ticker} FINRA "
                "short interest",

            "claim":
                (
                    f"{ticker} short interest "
                    f"settlement="
                    f"{data.get('settlement_date')}; "
                    f"current shares short="
                    f"{data.get('current_short')}; "
                    f"previous="
                    f"{data.get('previous_short')}; "
                    f"change="
                    f"{data.get('change_percent')}%; "
                    f"days to cover="
                    f"{data.get('days_to_cover')}; "
                    f"regulatory API={api_url}."
                ),

            "timestamp":
                data.get(
                    "settlement_date"
                ),

            "reliability_score":
                0.98,
        }

        record = _persist(
            case_id=case_id,
            case=case,
            lane=
                "generic_market_context",
            fact_key=
                "market_positioning",
            item=item,
            source_grade=
                "PRIMARY_OFFICIAL",
        )

        if record:
            records.append(record)

    except Exception as exc:
        failures.append(
            "POSITIONING:"
            f"{type(exc).__name__}: "
            f"{exc}"
        )

    return records, failures


def _supersede_portfolio(
    case_id: str,
    case: dict[str, Any],
) -> None:
    for row in list_objects(
        case_id,
        "primary_evidence_record",
    ):
        if (
            row.get("source_grade")
            != "FIRST_PARTY_GOVERNED"
            or row.get("fact_key")
            != "portfolio_overlap"
            or row.get(
                "gap_resolution_eligible"
            )
            is not True
        ):
            continue

        record_id = str(
            row.get(
                "primary_evidence_id"
            )
            or ""
        )

        if not record_id:
            continue

        record_object(
            record_id,
            "primary_evidence_record",
            case_id,
            {
                **row,
                "gap_resolution_eligible":
                    False,
                "superseded_at":
                    utc_now(),
            },
            topic=case.get("topic"),
        )


def _capture_portfolio(
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
        state = build_portfolio_state()

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
            or 0.0
        )

        positions = (
            state.get("positions")
            or []
        )

        exact_market_value = sum(
            float(
                row.get(
                    "market_value"
                )
                or 0.0
            )
            for row in positions
            if str(
                row.get("ticker")
                or ""
            ).upper()
            == ticker.upper()
        )

        overlap_pct = (
            exact_market_value
            / nav
            * 100.0
            if nav > 0
            else 0.0
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

        _supersede_portfolio(
            case_id,
            case,
        )

        item = {
            "source":
                "IIOS governed "
                "paper portfolio",

            "source_type":
                "portfolio_data",

            "evidence_type":
                "portfolio_snapshot",

            "url":
                (
                    "iios://paper-portfolio/"
                    f"{case_id}"
                ),

            "title":
                (
                    f"{ticker} prospective "
                    "portfolio overlap"
                ),

            "claim":
                (
                    "Prospective first-party "
                    "governed portfolio overlap "
                    f"for {ticker}: "
                    f"NAV={nav}; cash={cash}; "
                    f"gross exposure={gross}; "
                    f"exact ticker overlap="
                    f"{round(overlap_pct, 4)}%; "
                    f"drawdown="
                    f"{round(drawdown, 4)}%; "
                    f"positions="
                    f"{len(positions)}."
                ),

            "timestamp":
                utc_now(),

            "reliability_score":
                1.0,
        }

        record = _persist(
            case_id=case_id,
            case=case,
            lane=
                "generic_portfolio_context",
            fact_key=
                "portfolio_overlap",
            item=item,
            source_grade=
                "FIRST_PARTY_GOVERNED",
            verified_public_source=False,
        )

        if record:
            records.append(record)

    except Exception as exc:
        failures.append(
            "PORTFOLIO:"
            f"{type(exc).__name__}: "
            f"{exc}"
        )

    return records, failures


def _capture_policy(
    case_id: str,
    case: dict[str, Any],
) -> tuple[
    list[dict[str, Any]],
    list[str],
]:
    records = []
    failures = []

    policy_requirement = next(
        (
            requirement
            for requirement
            in _committee_requirements(
                case_id
            )
            if any(
                term
                in requirement.lower()
                for term in (
                    "government",
                    "policy",
                    "regulatory",
                    "regulation",
                    "antitrust",
                    "tariff",
                    "export control",
                    "procurement",
                    "sanction",
                )
            )
        ),
        None,
    )

    if not policy_requirement:
        return records, failures

    try:
        query = (
            policy_requirement[:240]
        )

        url = (
            "https://www.federalregister.gov/"
            "api/v1/documents.json?"
            + urlencode(
                {
                    "per_page":
                        5,
                    "order":
                        "newest",
                    "conditions[term]":
                        query,
                }
            )
        )

        payload = json.loads(
            _request_bytes(
                url,
                provider=
                    "federal_register",
                minimum_interval_seconds=
                    0.4,
                retries=2,
                cache_ttl_seconds=
                    30 * 60,
            ).decode("utf-8")
        )

        for row in (
            payload.get("results")
            or []
        )[:3]:

            title = str(
                row.get("title")
                or ""
            ).strip()

            if not title:
                continue

            item = {
                "source":
                    "Federal Register",

                "source_type":
                    "regulatory",

                "evidence_type":
                    "policy",

                "url":
                    row.get("html_url")
                    or row.get("json_url")
                    or url,

                "title":
                    title,

                "claim":
                    (
                        f"{title}; "
                        f"publication_date="
                        f"{row.get('publication_date')}; "
                        f"agency="
                        f"{row.get('agencies')}."
                    ),

                "timestamp":
                    row.get(
                        "publication_date"
                    ),

                "reliability_score":
                    0.99,
            }

            record = _persist(
                case_id=case_id,
                case=case,
                lane=
                    "generic_policy_context",
                fact_key=
                    "official_policy",
                item=item,
                source_grade=
                    "PRIMARY_OFFICIAL",
            )

            if record:
                records.append(record)

    except Exception as exc:
        failures.append(
            "POLICY:"
            f"{type(exc).__name__}: "
            f"{exc}"
        )

    return records, failures


def capture_generic_primary_evidence(
    case_id: str,
) -> dict[str, Any]:

    case = _require_case(case_id)

    ticker = _case_ticker(
        case_id,
        case,
    )

    if ticker in {
        "MU",
    }:
        return {
            "status":
                "SKIPPED_LEGACY_MICRON",

            "case_id":
                case_id,

            "ticker":
                ticker,

            "records_seen_or_added":
                0,

            "failures":
                [],

            "paper_mode":
                True,

            "trade_execution_permission":
                False,

            "live_execution":
                False,
        }

    captured = []
    failures = []

    for function in (
        _capture_financials,
        _capture_market,
        _capture_consensus,
        _capture_positioning,
        _capture_portfolio,
    ):
        records, errors = function(
            case_id,
            case,
            ticker,
        )

        captured.extend(records)
        failures.extend(errors)

    records, errors = _capture_policy(
        case_id,
        case,
    )

    captured.extend(records)
    failures.extend(errors)

    snapshot_id = (
        f"generic_primary_snapshot_"
        f"{uuid4().hex}"
    )

    snapshot = {
        "generic_primary_snapshot_id":
            snapshot_id,

        "policy_version":
            POLICY_VERSION,

        "case_id":
            case_id,

        "ticker":
            ticker,

        "records_seen_or_added":
            len(captured),

        "record_ids":
            sorted(
                {
                    str(
                        row.get(
                            "primary_evidence_id"
                        )
                    )
                    for row in captured
                    if row.get(
                        "primary_evidence_id"
                    )
                }
            ),

        "failures":
            failures,

        "failure_count":
            len(failures),

        "paper_mode":
            True,

        "auto_trade_authority":
            False,

        "trade_execution_permission":
            False,

        "live_execution":
            False,

        "created_at":
            utc_now(),
    }

    record_object(
        snapshot_id,
        "generic_primary_evidence_snapshot",
        case_id,
        snapshot,
        topic=case.get("topic"),
    )

    record_event(
        case_id,
        "GENERIC_PRIMARY_EVIDENCE_CAPTURE_COMPLETE",
        entity_id=snapshot_id,
        payload={
            "ticker":
                ticker,

            "records":
                len(captured),

            "failures":
                len(failures),

            "trade_execution_permission":
                False,

            "live_execution":
                False,
        },
    )

    return snapshot


def generic_primary_status(
    case_id: str,
) -> dict[str, Any]:
    case = _require_case(case_id)

    ticker = _case_ticker(
        case_id,
        case,
    )

    rows = [
        row
        for row in list_objects(
            case_id,
            "primary_evidence_record",
        )
        if (
            str(
                row.get("lane")
                or ""
            ).startswith("generic_")
            or row.get("fact_key")
            == "portfolio_overlap"
        )
        and row.get(
            "gap_resolution_eligible"
        )
        is True
    ]

    counts = Counter(
        str(
            row.get("lane")
            or "unknown"
        )
        for row in rows
    )

    return {
        "case_id":
            case_id,

        "ticker":
            ticker,

        "records":
            rows,

        "record_count":
            len(rows),

        "lane_counts":
            dict(counts),

        "latest_snapshot":
            latest_object(
                "generic_primary_evidence_snapshot",
                case_id=case_id,
            ),

        "paper_mode":
            True,

        "trade_execution_permission":
            False,

        "live_execution":
            False,
    }


@router.post(
    "/generic-primary-evidence/{case_id}/capture"
)
def capture_route(
    case_id: str,
):
    return capture_generic_primary_evidence(
        case_id
    )


@router.get(
    "/generic-primary-evidence/{case_id}"
)
def status_route(
    case_id: str,
):
    return generic_primary_status(
        case_id
    )
