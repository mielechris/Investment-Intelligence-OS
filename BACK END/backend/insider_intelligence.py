from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote
from uuid import uuid4
from xml.etree import ElementTree

from fastapi import APIRouter, HTTPException

from ledger import get_object, latest_object, list_objects, record_event, record_object
from provider_hardening import SEC_USER_AGENT, _request_bytes


router = APIRouter()
PAPER_MODE = True
KNOWN_CIKS = {"MU": "0000723125"}
INSIDER_FORMS = {"4", "4/A", "SC 13D", "SC 13D/A", "SC 13G", "SC 13G/A"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _require_case(case_id: str) -> dict[str, Any]:
    case = get_object(case_id)
    if not case or not case_id.startswith("case_"):
        raise HTTPException(status_code=404, detail="Unknown case_id")
    return case


def _normalize_ticker(value: str) -> str:
    ticker = str(value or "").strip().upper()
    if ticker.endswith(".US"):
        ticker = ticker[:-3]
    return ticker


def _sec_bytes(url: str, *, accept: str = "application/json", cache_ttl_seconds: int = 900) -> bytes:
    return _request_bytes(
        url,
        accept=accept,
        user_agent=SEC_USER_AGENT,
        provider="sec_insider",
        minimum_interval_seconds=0.25,
        retries=2,
        cache_ttl_seconds=cache_ttl_seconds,
    )


def _sec_json(url: str, *, cache_ttl_seconds: int = 900) -> Any:
    return json.loads(_sec_bytes(url, cache_ttl_seconds=cache_ttl_seconds).decode("utf-8"))


def resolve_cik(ticker: str) -> str:
    symbol = _normalize_ticker(ticker)
    if symbol in KNOWN_CIKS:
        return KNOWN_CIKS[symbol]
    payload = _sec_json("https://www.sec.gov/files/company_tickers.json", cache_ttl_seconds=24 * 3600)
    for row in payload.values() if isinstance(payload, dict) else []:
        if str(row.get("ticker") or "").upper() == symbol:
            return str(row.get("cik_str") or "").zfill(10)
    raise HTTPException(status_code=404, detail=f"Unable to resolve SEC CIK for ticker {symbol}")


def _float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _boolish(value: Any) -> bool | None:
    text = str(value or "").strip().lower()
    if text in {"1", "true", "yes", "y"}:
        return True
    if text in {"0", "false", "no", "n"}:
        return False
    return None


def _owner_role(owner: ElementTree.Element | None) -> str:
    if owner is None:
        return "Reporting owner"
    rel = owner.find("reportingOwnerRelationship")
    if rel is None:
        return "Reporting owner"
    roles: list[str] = []
    if _boolish(rel.findtext("isDirector")):
        roles.append("Director")
    if _boolish(rel.findtext("isOfficer")):
        title = str(rel.findtext("officerTitle") or "Officer").strip() or "Officer"
        roles.append(title)
    if _boolish(rel.findtext("isTenPercentOwner")):
        roles.append("10% Owner")
    if _boolish(rel.findtext("isOther")):
        other = str(rel.findtext("otherText") or "Other").strip() or "Other"
        roles.append(other)
    return " / ".join(roles) if roles else "Reporting owner"


def classify_transaction(code: str, acquired_disposed: str | None = None) -> str:
    code = str(code or "").strip().upper()
    acquired = str(acquired_disposed or "").strip().upper()
    if code == "P":
        return "OPEN_MARKET_PURCHASE"
    if code == "S":
        return "OPEN_MARKET_SALE"
    if code in {"A", "D"}:
        return "EQUITY_AWARD_OR_ISSUER_TRANSFER"
    if code == "F":
        return "TAX_WITHHOLDING_OR_PAYMENT"
    if code in {"M", "C"}:
        return "OPTION_EXERCISE_OR_CONVERSION"
    if code == "G":
        return "GIFT"
    if code == "J":
        return "OTHER_REPORTED_TRANSACTION"
    if acquired == "A":
        return "OTHER_ACQUISITION"
    if acquired == "D":
        return "OTHER_DISPOSITION"
    return "OTHER"


def _transaction_record(
    tx: ElementTree.Element,
    *,
    owner_name: str,
    owner_role: str,
    ticker: str,
    filing_date: str,
    accession_number: str,
    filing_url: str,
    form: str,
    derivative: bool,
) -> dict[str, Any]:
    code = str(tx.findtext("transactionCoding/transactionCode") or "").strip().upper()
    acquired_disposed = str(tx.findtext("transactionAmounts/transactionAcquiredDisposedCode/value") or "").strip().upper() or None
    shares = _float(tx.findtext("transactionAmounts/transactionShares/value"))
    price = _float(tx.findtext("transactionAmounts/transactionPricePerShare/value"))
    post_shares = _float(tx.findtext("postTransactionAmounts/sharesOwnedFollowingTransaction/value"))
    plan = _boolish(tx.findtext("transactionCoding/aff10b5One"))
    if plan is None:
        plan = _boolish(tx.findtext("aff10b5One"))
    transaction_date = str(tx.findtext("transactionDate/value") or filing_date).strip()
    dollar_value = round(abs(shares * price), 2) if shares is not None and price is not None else None
    nature = classify_transaction(code, acquired_disposed)
    return {
        "record_kind": "FORM4_TRANSACTION",
        "form": form,
        "ticker": ticker,
        "reporting_owner": owner_name,
        "reporting_owner_role": owner_role,
        "transaction_date": transaction_date,
        "filing_date": filing_date,
        "transaction_code": code,
        "transaction_nature": nature,
        "acquired_disposed": acquired_disposed,
        "shares": shares,
        "price_per_share": price,
        "dollar_value": dollar_value,
        "shares_owned_after": post_shares,
        "direct_or_indirect": str(tx.findtext("ownershipNature/directOrIndirectOwnership/value") or "").strip() or None,
        "derivative_security": derivative,
        "plan_10b5_1": plan,
        "accession_number": accession_number,
        "source_url": filing_url,
        "source_name": "U.S. SEC EDGAR Form 4",
        "source_type": "filing",
        "reliability_score": 0.98,
        "admission_status": "ADMITTED",
        "paper_mode": True,
        "trade_execution_permission": False,
    }


def parse_form4_xml(
    xml_bytes: bytes,
    *,
    filing_date: str,
    accession_number: str,
    filing_url: str,
    form: str = "4",
) -> list[dict[str, Any]]:
    root = ElementTree.fromstring(xml_bytes)
    ticker = str(root.findtext("issuer/issuerTradingSymbol") or "").strip().upper()
    owners = root.findall("reportingOwner")
    owner_name = str((owners[0].findtext("reportingOwnerId/rptOwnerName") if owners else None) or "Unknown reporting owner").strip()
    owner_role = _owner_role(owners[0] if owners else None)
    output: list[dict[str, Any]] = []
    for tx in root.findall("nonDerivativeTable/nonDerivativeTransaction"):
        output.append(
            _transaction_record(
                tx,
                owner_name=owner_name,
                owner_role=owner_role,
                ticker=ticker,
                filing_date=filing_date,
                accession_number=accession_number,
                filing_url=filing_url,
                form=form,
                derivative=False,
            )
        )
    for tx in root.findall("derivativeTable/derivativeTransaction"):
        output.append(
            _transaction_record(
                tx,
                owner_name=owner_name,
                owner_role=owner_role,
                ticker=ticker,
                filing_date=filing_date,
                accession_number=accession_number,
                filing_url=filing_url,
                form=form,
                derivative=True,
            )
        )
    return output


def _recent_filings(cik: str) -> list[dict[str, Any]]:
    payload = _sec_json(f"https://data.sec.gov/submissions/CIK{cik}.json", cache_ttl_seconds=15 * 60)
    recent = ((payload or {}).get("filings") or {}).get("recent") or {}
    forms = recent.get("form") or []
    rows: list[dict[str, Any]] = []
    for index, form in enumerate(forms):
        if str(form) not in INSIDER_FORMS:
            continue
        rows.append(
            {
                "form": str(form),
                "accession_number": str((recent.get("accessionNumber") or [""])[index]),
                "filing_date": str((recent.get("filingDate") or [""])[index]),
                "report_date": str((recent.get("reportDate") or [""])[index]),
                "primary_document": str((recent.get("primaryDocument") or [""])[index]),
            }
        )
    return rows


def _filing_url(cik: str, accession: str, primary_document: str) -> str:
    cik_unpadded = str(int(cik))
    accession_compact = accession.replace("-", "")
    return f"https://www.sec.gov/Archives/edgar/data/{cik_unpadded}/{accession_compact}/{quote(primary_document)}"


def fetch_public_insider_records(ticker: str, *, max_form4_filings: int = 12) -> list[dict[str, Any]]:
    cik = resolve_cik(ticker)
    rows = _recent_filings(cik)
    output: list[dict[str, Any]] = []
    form4_seen = 0
    for filing in rows:
        form = filing["form"]
        url = _filing_url(cik, filing["accession_number"], filing["primary_document"])
        if form in {"4", "4/A"}:
            if form4_seen >= max_form4_filings:
                continue
            form4_seen += 1
            xml_bytes = _sec_bytes(
                url,
                accept="application/xml,text/xml,text/html",
                cache_ttl_seconds=30 * 60,
            )
            try:
                output.extend(
                    parse_form4_xml(
                        xml_bytes,
                        filing_date=filing["filing_date"],
                        accession_number=filing["accession_number"],
                        filing_url=url,
                        form=form,
                    )
                )
            except ElementTree.ParseError:
                output.append(
                    {
                        "record_kind": "FORM4_FILING_UNPARSED",
                        "form": form,
                        "ticker": _normalize_ticker(ticker),
                        "filing_date": filing["filing_date"],
                        "accession_number": filing["accession_number"],
                        "source_url": url,
                        "source_name": "U.S. SEC EDGAR",
                        "source_type": "filing",
                        "reliability_score": 0.98,
                        "admission_status": "CONTEXT_ONLY",
                        "paper_mode": True,
                        "trade_execution_permission": False,
                    }
                )
        else:
            output.append(
                {
                    "record_kind": "BENEFICIAL_OWNERSHIP_FILING",
                    "form": form,
                    "ticker": _normalize_ticker(ticker),
                    "filing_date": filing["filing_date"],
                    "report_date": filing["report_date"] or None,
                    "accession_number": filing["accession_number"],
                    "source_url": url,
                    "source_name": "U.S. SEC EDGAR beneficial ownership filing",
                    "source_type": "filing",
                    "reliability_score": 0.98,
                    "admission_status": "ADMITTED",
                    "paper_mode": True,
                    "trade_execution_permission": False,
                }
            )
    return output


def _match_gap(case_id: str) -> str | None:
    decision = latest_object("committee_decision", case_id=case_id) or {}
    requirements = [str(item).strip() for item in decision.get("required_evidence") or [] if str(item).strip()]
    terms = ("insider", "ownership", "beneficial owner", "management buying", "management selling", "positioning")
    for requirement in requirements:
        lower = requirement.lower()
        if any(term in lower for term in terms):
            return requirement
    return None


def _record_id(record: dict[str, Any]) -> str:
    accession = str(record.get("accession_number") or "").replace("-", "")
    owner = "".join(ch for ch in str(record.get("reporting_owner") or "owner").lower() if ch.isalnum())[:18]
    date = str(record.get("transaction_date") or record.get("filing_date") or "").replace("-", "")
    code = str(record.get("transaction_code") or record.get("form") or "filing").replace(" ", "")
    return f"insider_{accession}_{owner}_{date}_{code}_{uuid4().hex[:6]}"


def persist_insider_records(case_id: str, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    case = _require_case(case_id)
    existing = list_objects(case_id, "insider_activity_record")
    fingerprints = {
        (
            str(item.get("accession_number") or ""),
            str(item.get("reporting_owner") or ""),
            str(item.get("transaction_date") or item.get("filing_date") or ""),
            str(item.get("transaction_code") or item.get("form") or ""),
            str(item.get("shares") or ""),
        )
        for item in existing
    }
    gap_requirement = _match_gap(case_id)
    added: list[dict[str, Any]] = []
    for raw in records:
        fingerprint = (
            str(raw.get("accession_number") or ""),
            str(raw.get("reporting_owner") or ""),
            str(raw.get("transaction_date") or raw.get("filing_date") or ""),
            str(raw.get("transaction_code") or raw.get("form") or ""),
            str(raw.get("shares") or ""),
        )
        if fingerprint in fingerprints:
            continue
        fingerprints.add(fingerprint)
        record_id = _record_id(raw)
        record = {
            **raw,
            "insider_activity_id": record_id,
            "case_id": case_id,
            "topic": case.get("topic"),
            "gap_requirement": gap_requirement,
            "created_at": utc_now(),
        }
        record_object(record_id, "insider_activity_record", case_id, record, topic=case.get("topic"))
        added.append(record)
    if added:
        record_event(
            case_id,
            "INSIDER_OWNERSHIP_CAPTURED",
            payload={"records_added": len(added), "gap_requirement": gap_requirement},
        )
    return added


def _record_date(record: dict[str, Any]) -> datetime | None:
    value = str(record.get("transaction_date") or record.get("filing_date") or "").strip()
    try:
        return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def insider_status(case_id: str) -> dict[str, Any]:
    _require_case(case_id)
    records = list_objects(case_id, "insider_activity_record")
    buys = [item for item in records if item.get("transaction_nature") == "OPEN_MARKET_PURCHASE"]
    sales = [item for item in records if item.get("transaction_nature") == "OPEN_MARKET_SALE"]
    planned_sales = [item for item in sales if item.get("plan_10b5_1") is True]
    ownership = [item for item in records if item.get("record_kind") == "BENEFICIAL_OWNERSHIP_FILING"]
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(days=30)
    recent_buys = [item for item in buys if (_record_date(item) or datetime.min.replace(tzinfo=timezone.utc)) >= window_start]
    recent_sales = [item for item in sales if (_record_date(item) or datetime.min.replace(tzinfo=timezone.utc)) >= window_start]
    buy_owners = {str(item.get("reporting_owner") or "") for item in recent_buys if item.get("reporting_owner")}
    sale_owners = {str(item.get("reporting_owner") or "") for item in recent_sales if item.get("reporting_owner")}
    cluster = "NONE"
    if len(buy_owners) >= 2:
        cluster = "OPEN_MARKET_BUY_CLUSTER"
    elif len(sale_owners) >= 3:
        cluster = "OPEN_MARKET_SELL_CLUSTER"
    return {
        "case_id": case_id,
        "records": list(reversed(records[-40:])),
        "summary": {
            "record_count": len(records),
            "open_market_buys": len(buys),
            "open_market_sales": len(sales),
            "planned_10b5_1_sales": len(planned_sales),
            "beneficial_ownership_filings": len(ownership),
            "buy_dollar_value": round(sum(float(item.get("dollar_value") or 0.0) for item in buys), 2),
            "sale_dollar_value": round(sum(float(item.get("dollar_value") or 0.0) for item in sales), 2),
            "cluster_signal_30d": cluster,
            "cluster_is_context_only": True,
        },
        "paper_mode": True,
        "trade_execution_permission": False,
    }


def _claim(record: dict[str, Any]) -> str:
    if record.get("record_kind") == "BENEFICIAL_OWNERSHIP_FILING":
        return f"{record.get('form')} beneficial-ownership filing submitted on {record.get('filing_date')}"
    owner = str(record.get("reporting_owner") or "Reporting owner")
    role = str(record.get("reporting_owner_role") or "")
    nature = str(record.get("transaction_nature") or "reported transaction")
    shares = record.get("shares")
    price = record.get("price_per_share")
    amount = record.get("dollar_value")
    plan = record.get("plan_10b5_1")
    pieces = [f"{owner} ({role}) {nature}"]
    if shares is not None:
        pieces.append(f"shares={shares}")
    if price is not None:
        pieces.append(f"price={price}")
    if amount is not None:
        pieces.append(f"dollar_value={amount}")
    if plan is True:
        pieces.append("10b5-1=yes")
    elif plan is False:
        pieces.append("10b5-1=no")
    if record.get("shares_owned_after") is not None:
        pieces.append(f"shares_owned_after={record.get('shares_owned_after')}")
    return " ".join(pieces)


def insider_evidence(case_id: str) -> list[dict[str, Any]]:
    records = list_objects(case_id, "insider_activity_record")
    output: list[dict[str, Any]] = []
    for record in records:
        if record.get("admission_status") != "ADMITTED":
            continue
        output.append(
            {
                "source": record.get("source_name") or "U.S. SEC EDGAR",
                "source_type": "filing",
                "evidence_type": "fundamental",
                "url": record.get("source_url"),
                "title": f"Insider / ownership · {record.get('form')} · {record.get('reporting_owner') or record.get('record_kind')}",
                "claim": _claim(record),
                "timestamp": record.get("transaction_date") or record.get("filing_date"),
                "reliability_score": 0.98,
                "gap_requirement": record.get("gap_requirement"),
                "insider_activity_id": record.get("insider_activity_id"),
                "insider_context_only": True,
            }
        )
    return output


def auto_capture_insider(case_id: str) -> dict[str, Any]:
    case = _require_case(case_id)
    profile = latest_object("monitor_profile", case_id=case_id) or {}
    ticker = _normalize_ticker(str(profile.get("ticker") or "MU"))
    try:
        fetched = fetch_public_insider_records(ticker)
        added = persist_insider_records(case_id, fetched)
        return {
            "case_id": case_id,
            "topic": case.get("topic"),
            "ticker": ticker,
            "status": "ok",
            "records_fetched": len(fetched),
            "records_added": len(added),
            "summary": insider_status(case_id)["summary"],
            "paper_mode": True,
            "trade_execution_permission": False,
        }
    except Exception as exc:  # provider errors are evidence gaps, not proof of no activity
        record_event(
            case_id,
            "INSIDER_PROVIDER_ERROR",
            payload={"ticker": ticker, "error": f"{type(exc).__name__}: {exc}"},
        )
        return {
            "case_id": case_id,
            "topic": case.get("topic"),
            "ticker": ticker,
            "status": "provider_error",
            "error": f"{type(exc).__name__}: {exc}",
            "records_fetched": 0,
            "records_added": 0,
            "summary": insider_status(case_id)["summary"],
            "paper_mode": True,
            "trade_execution_permission": False,
        }


@router.get("/insider/schema")
def insider_schema():
    return {
        "forms": sorted(INSIDER_FORMS),
        "transaction_codes": {
            "P": "Open-market/private purchase",
            "S": "Open-market/private sale",
            "A/D": "Award or issuer transfer",
            "F": "Tax withholding/payment",
            "M/C": "Exercise or conversion",
            "G": "Gift",
        },
        "cluster_signal_is_context_only": True,
        "paper_mode": True,
        "paper_buy_enabled": False,
    }


@router.get("/insider/{case_id}")
def get_insider(case_id: str):
    return insider_status(case_id)


@router.post("/insider/{case_id}/auto-capture")
def capture_insider(case_id: str):
    return auto_capture_insider(case_id)
