import os

import httpx

from intelligence.providers.sec_filing_detail import html_to_text


TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
COMPANY_FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
ARCHIVES_BASE = "https://www.sec.gov/Archives/edgar/data"


FACT_TAGS = {
    "revenue": (
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "Revenues",
        "SalesRevenueNet",
    ),
    "operating_income": ("OperatingIncomeLoss",),
    "net_income": ("NetIncomeLoss", "ProfitLoss"),
    "operating_cash_flow": ("NetCashProvidedByUsedInOperatingActivities",),
    "capex": (
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "PaymentsForAdditionsToPropertyPlantAndEquipment",
    ),
    "cash": (
        "CashAndCashEquivalentsAtCarryingValue",
        "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
    ),
    "total_assets": ("Assets",),
    "total_liabilities": ("Liabilities",),
    "stockholders_equity": (
        "StockholdersEquity",
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
    ),
    "long_term_debt": (
        "LongTermDebtCurrent",
        "LongTermDebtNoncurrent",
        "LongTermDebtAndFinanceLeaseObligationsCurrent",
        "LongTermDebtAndFinanceLeaseObligationsNoncurrent",
    ),
}


def _headers() -> dict[str, str]:
    user_agent = os.getenv("SEC_USER_AGENT", "").strip()
    if not user_agent:
        raise RuntimeError("SEC_USER_AGENT is required for issuer-specific SEC evidence")
    return {"User-Agent": user_agent, "Accept-Encoding": "gzip, deflate"}


def _resolve_company(client: httpx.Client, symbol: str) -> dict:
    response = client.get(TICKERS_URL)
    response.raise_for_status()
    payload = response.json()
    target = symbol.upper().strip()
    for item in payload.values():
        if str(item.get("ticker", "")).upper() == target:
            return {
                "symbol": target,
                "company_name": item.get("title"),
                "cik": str(item.get("cik_str", "")).zfill(10),
            }
    raise RuntimeError(f"SEC ticker mapping did not contain {target}")


def _row_at(recent: dict, index: int) -> dict:
    row = {}
    for key, values in recent.items():
        if isinstance(values, list) and index < len(values):
            row[key] = values[index]
    return row


def _recent_rows(submissions: dict, forms: tuple[str, ...], limit: int) -> list[dict]:
    """Prefer the newest filing for each requested form before adding additional recent rows."""
    recent = (submissions.get("filings") or {}).get("recent") or {}
    form_values = recent.get("form") or []
    selected_indices: list[int] = []

    for requested_form in forms:
        for index, form in enumerate(form_values):
            if form == requested_form:
                selected_indices.append(index)
                break

    if len(selected_indices) < limit:
        for index, form in enumerate(form_values):
            if form in forms and index not in selected_indices:
                selected_indices.append(index)
            if len(selected_indices) >= limit:
                break

    return [_row_at(recent, index) for index in selected_indices[:limit]]


def fetch_company_sec_evidence(
    *,
    symbol: str,
    forms: tuple[str, ...] = ("10-Q", "10-K", "8-K"),
    limit: int = 4,
    text_chars: int = 18000,
) -> dict:
    """Fetch issuer-specific recent SEC filings and bounded primary-document excerpts."""
    headers = _headers()
    with httpx.Client(timeout=20.0, headers=headers, follow_redirects=True) as client:
        company = _resolve_company(client, symbol)
        submissions_response = client.get(SUBMISSIONS_URL.format(cik=company["cik"]))
        submissions_response.raise_for_status()
        submissions = submissions_response.json()
        rows = _recent_rows(submissions, forms, max(1, min(limit, 10)))

        evidence: list[dict] = []
        cik_int = str(int(company["cik"]))
        for row in rows:
            accession = str(row.get("accessionNumber") or "")
            primary_document = str(row.get("primaryDocument") or "")
            accession_compact = accession.replace("-", "")
            primary_url = None
            filing_text = ""
            fetch_error = None
            if accession_compact and primary_document:
                primary_url = f"{ARCHIVES_BASE}/{cik_int}/{accession_compact}/{primary_document}"
                try:
                    document_response = client.get(primary_url)
                    document_response.raise_for_status()
                    filing_text = html_to_text(document_response.text, max_chars=text_chars)
                except Exception as exc:
                    fetch_error = str(exc)

            evidence.append({
                "source": "SEC EDGAR issuer submissions",
                "source_kind": "company",
                "symbol": company["symbol"],
                "company_name": company["company_name"],
                "cik": company["cik"],
                "form": row.get("form"),
                "filing_date": row.get("filingDate"),
                "report_date": row.get("reportDate"),
                "acceptance_datetime": row.get("acceptanceDateTime"),
                "accession_number": accession,
                "items": row.get("items"),
                "primary_document": primary_document,
                "primary_document_url": primary_url,
                "primary_document_excerpt": filing_text,
                "primary_document_truncated": len(filing_text) >= text_chars,
                "fetch_error": fetch_error,
                "detail": (
                    f"Issuer-specific SEC {row.get('form')} filed {row.get('filingDate')} "
                    f"for report date {row.get('reportDate')}."
                ),
            })

    return {
        "company": company,
        "count": len(evidence),
        "evidence": evidence,
    }


def _unit_rows(fact: dict) -> tuple[str | None, list[dict]]:
    units = fact.get("units") or {}
    for preferred in ("USD", "shares", "USD/shares", "pure"):
        rows = units.get(preferred)
        if isinstance(rows, list) and rows:
            return preferred, rows
    for unit, rows in units.items():
        if isinstance(rows, list) and rows:
            return str(unit), rows
    return None, []


def _compact_fact(row: dict, unit: str | None, tag: str) -> dict:
    return {
        "tag": tag,
        "unit": unit,
        "value": row.get("val"),
        "start": row.get("start"),
        "end": row.get("end"),
        "filed": row.get("filed"),
        "form": row.get("form"),
        "fy": row.get("fy"),
        "fp": row.get("fp"),
        "frame": row.get("frame"),
        "accession_number": row.get("accn"),
    }


def _latest_for_forms(facts: dict, tags: tuple[str, ...], forms: set[str]) -> dict | None:
    for tag in tags:
        fact = facts.get(tag)
        if not isinstance(fact, dict):
            continue
        unit, rows = _unit_rows(fact)
        candidates = [row for row in rows if row.get("form") in forms and row.get("val") is not None]
        if not candidates:
            continue
        candidates.sort(
            key=lambda row: (
                str(row.get("end") or ""),
                str(row.get("filed") or ""),
                str(row.get("frame") or ""),
            ),
            reverse=True,
        )
        return _compact_fact(candidates[0], unit, tag)
    return None


def _free_cash_flow(operating_cash_flow: dict | None, capex: dict | None) -> dict | None:
    if not operating_cash_flow or not capex:
        return None
    if operating_cash_flow.get("unit") != "USD" or capex.get("unit") != "USD":
        return None
    if operating_cash_flow.get("start") != capex.get("start") or operating_cash_flow.get("end") != capex.get("end"):
        return None
    try:
        value = float(operating_cash_flow["value"]) - float(capex["value"])
    except (TypeError, ValueError, KeyError):
        return None
    return {
        "unit": "USD",
        "value": value,
        "start": operating_cash_flow.get("start"),
        "end": operating_cash_flow.get("end"),
        "calculation": "operating_cash_flow - capex",
    }


def fetch_company_facts_evidence(*, symbol: str) -> dict:
    """Fetch structured SEC XBRL facts for cash flow, capex, balance sheet, and earnings quality."""
    headers = _headers()
    with httpx.Client(timeout=20.0, headers=headers, follow_redirects=True) as client:
        company = _resolve_company(client, symbol)
        response = client.get(COMPANY_FACTS_URL.format(cik=company["cik"]))
        response.raise_for_status()
        payload = response.json()

    us_gaap = ((payload.get("facts") or {}).get("us-gaap") or {})
    metrics: dict[str, dict] = {}
    for name, tags in FACT_TAGS.items():
        metrics[name] = {
            "annual": _latest_for_forms(us_gaap, tags, {"10-K"}),
            "quarterly": _latest_for_forms(us_gaap, tags, {"10-Q"}),
        }

    annual_fcf = _free_cash_flow(
        metrics["operating_cash_flow"]["annual"],
        metrics["capex"]["annual"],
    )
    quarterly_fcf = _free_cash_flow(
        metrics["operating_cash_flow"]["quarterly"],
        metrics["capex"]["quarterly"],
    )

    return {
        "source": "SEC EDGAR Company Facts XBRL",
        "source_kind": "company",
        "symbol": company["symbol"],
        "company_name": company["company_name"],
        "cik": company["cik"],
        "metrics": metrics,
        "derived": {
            "annual_free_cash_flow": annual_fcf,
            "quarterly_or_ytd_free_cash_flow": quarterly_fcf,
        },
        "guardrails": [
            "Derived free cash flow is calculated only when operating cash flow and capex share the same reported period.",
            "Quarterly SEC cash-flow facts can be year-to-date; period start/end fields must be inspected before comparison.",
            "Missing XBRL tags remain missing rather than being estimated.",
        ],
        "detail": "Structured issuer-specific SEC XBRL facts for financial statements, cash flow, capex, liquidity, leverage, and equity.",
    }
