import os

import httpx

from intelligence.providers.sec_filing_detail import html_to_text


TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
ARCHIVES_BASE = "https://www.sec.gov/Archives/edgar/data"


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


def _recent_rows(submissions: dict, forms: tuple[str, ...], limit: int) -> list[dict]:
    recent = (submissions.get("filings") or {}).get("recent") or {}
    form_values = recent.get("form") or []
    rows: list[dict] = []
    for index, form in enumerate(form_values):
        if form not in forms:
            continue
        row = {}
        for key, values in recent.items():
            if isinstance(values, list) and index < len(values):
                row[key] = values[index]
        rows.append(row)
        if len(rows) >= limit:
            break
    return rows


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
