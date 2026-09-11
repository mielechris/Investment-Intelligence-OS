"""Exact reviewed September 11 schedule; no authority or external I/O."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

SESSION = "2026-09-11"
SPEC_SHA256 = "c3d969a576630a3e55ba1fa6f619147c53c78489d4ca327a72da114c129d057c"
TICKERS = ("MU", "SPY", "XLK", "VNQ", "TLT", "GLD", "UUP", "IBIT", "PFF", "BIL")
PATHS = ("/prices/snapshot", "/prices", "/company/facts")
OPEN = datetime(2026, 9, 11, 13, 30, tzinfo=timezone.utc)
EXPIRY = datetime(2026, 9, 11, 20, 5, tzinfo=timezone.utc)
FORBIDDEN = ("ledger_read", "ledger_write", "broker", "paper_order", "live_execution",
             "provider_model", "mcp", "promotion")


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def pin(value):
    if not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{64}", value):
        raise ValueError("INDEPENDENT_PIN_REQUIRED")
    return value


def instant(value):
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if result.tzinfo is None or result.utcoffset() is None:
            raise ValueError()
        return result.astimezone(timezone.utc)
    except (AttributeError, TypeError, ValueError):
        raise ValueError("AWARE_TIME_REQUIRED") from None


def utc(now):
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("AWARE_TIME_REQUIRED")
    return now.astimezone(timezone.utc)


def request_plan():
    rows = []
    for group, target, deadline in (
        ("OPENING", "06:30", "07:00"),
        ("POINT_IN_TIME_OHLCV", "06:32", "09:30"),
        ("FACTS_OR_PRIOR_BASELINE", "06:34", "09:30"),
        ("INTRADAY", "09:30", "12:55"), ("CLOSING", "13:00", "13:05"),
    ):
        for index, ticker in enumerate(TICKERS):
            when = datetime.fromisoformat(SESSION + "T" + target + ":00").replace(
                tzinfo=ZoneInfo("America/Los_Angeles")) + timedelta(seconds=6 * index)
            purpose, path, query = group, PATHS[0], {"ticker": ticker}
            if group == "POINT_IN_TIME_OHLCV":
                path = PATHS[1]
                query.update(interval="day", start_date="2026-09-10", end_date=SESSION)
            elif group == "FACTS_OR_PRIOR_BASELINE":
                if ticker == "MU":
                    purpose, path = "APPLICABLE_FACTS", PATHS[2]
                else:
                    purpose, path = "PRIOR_SESSION_BASELINE", PATHS[1]
                    query.update(interval="day", start_date="2026-09-10", end_date="2026-09-10")
            row = {"ordinal": len(rows) + 1, "ticker": ticker, "type": purpose,
                   "method": "GET", "host": "api.financialdatasets.ai", "path": path,
                   "query": query, "target_pdt": when.isoformat(),
                   "target_utc": when.astimezone(timezone.utc).isoformat(),
                   "dispatch_deadline_pdt": SESSION + "T" + deadline + ":00-07:00",
                   "public_standard_request_units": 1, "retries": 0}
            row["proposal_row_sha256"] = digest(row)
            rows.append(row)
    return rows


def validate_row(row):
    if row not in request_plan():
        raise ValueError("UNREVIEWED_REQUEST")


def verify_document(document, expected):
    if digest(document) != pin(expected):
        raise ValueError("DOCUMENT_PIN_MISMATCH")


def validate_account(account, expected, now):
    verify_document(account, expected)
    if (account.get("session") != SESSION or account.get("spec_sha256") != SPEC_SHA256
            or account.get("entitled") is not True or account.get("tickers") != list(TICKERS)
            or account.get("paths") != list(PATHS)
            or account.get("unit_costs") != dict.fromkeys(PATHS, 1)
            or any(type(v) is not int for v in account["unit_costs"].values())
            or type(account.get("reserved_credits")) is not int or account["reserved_credits"] != 50
            or type(account.get("available_credits")) is not int or account["available_credits"] < 50
            or type(account.get("requests_per_minute")) is not int or account["requests_per_minute"] < 10
            or account.get("overage_or_topup") is not False
            or account.get("internal_use_permitted") is not True
            or account.get("calendar_open") is not True
            or account.get("previous_session") != "2026-09-10"
            or account.get("ambiguous_billing") != "RESERVE_FULL_COST_NO_RETRY"
            or not account.get("account_reference") or not account.get("reservation_reference")
            or account.get("credential_binding") != "com.iios.expansion-wing.financial-datasets/financial-datasets-api-key"
            or not instant(account["observed_at"]) <= utc(now) < instant(account["valid_until"])
            or instant(account["valid_until"]) < EXPIRY):
        raise ValueError("ACCOUNT_EVIDENCE_INVALID")
    pin(account.get("entitlement_source_sha256"))
    pin(account.get("cost_balance_source_sha256"))
    pin(account.get("calendar_source_sha256"))


def validate_authority(grant, expected, account_hash, release_hash, now, *, arming=False):
    verify_document(grant, expected)
    issued, activation = instant(grant["approved_at"]), instant(grant["arm_before"])
    now = utc(now)
    if (grant.get("session") != SESSION or grant.get("spec_sha256") != SPEC_SHA256
            or grant.get("plan_sha256") != digest(request_plan())
            or grant.get("account_sha256") != pin(account_hash)
            or grant.get("release_sha256") != pin(release_hash)
            or grant.get("owner_approved") is not True
            or grant.get("authority") != dict.fromkeys(FORBIDDEN, False)
            or type(grant.get("maximum_credits")) is not int or grant["maximum_credits"] != 50
            or type(grant.get("maximum_requests")) is not int or grant["maximum_requests"] != 50
            or issued.astimezone(ZoneInfo("America/Los_Angeles")).date().isoformat() != SESSION
            or not issued <= now or not issued < activation <= OPEN
            or not 0 < (activation - issued).total_seconds() <= 1800
            or instant(grant["expires_at"]) != EXPIRY or now >= EXPIRY):
        raise ValueError("SESSION_AUTHORITY_INVALID")
    pin(grant.get("owner_receipt_sha256"))
    if arming and not now < activation:
        raise ValueError("ARMING_WINDOW_MISSED")
