"""Explicit XNYS session schedules; no default date, authority or external I/O."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

KEYCHAIN_SERVICE = "IIOS_FINANCIAL_DATASETS_API_KEY"
KEYCHAIN_ACCOUNT = "iios-provider"
CREDENTIAL_BINDING = KEYCHAIN_SERVICE + "/" + KEYCHAIN_ACCOUNT
TICKERS = ("MU", "SPY", "XLK", "VNQ", "TLT", "GLD", "UUP", "IBIT", "PFF", "BIL")
PATHS = ("/prices/snapshot", "/prices", "/company/facts")
# Bounded published XNYS cash-equity calendar, not a weekday-only admission rule.
# NYSE's 2026 calendar and ICE's December 23, 2025 holiday announcement.
# Exceptional closures must still be freshly verified before same-day arming.
CALENDAR_SOURCE_SHA256 = "70f5577eb43e60a9dbbecaae3cec23d0f02028c05c7f175013bb3e97816d394f"
HOLIDAYS = frozenset(("2026-01-01", "2026-01-19", "2026-02-16", "2026-04-03",
    "2026-05-25", "2026-06-19", "2026-07-03", "2026-09-07", "2026-11-26", "2026-12-25"))
EARLY_CLOSES = frozenset(("2026-11-27", "2026-12-24"))
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


@dataclass(frozen=True)
class SessionPlan:
    session: str

    def __post_init__(self):
        if not isinstance(self.session, str) or not re.fullmatch(r"2026-\d{2}-\d{2}", self.session):
            raise ValueError("XNYS_CALENDAR_RANGE_OR_DATE_INVALID")
        day = date.fromisoformat(self.session)
        if day.weekday() >= 5 or self.session in HOLIDAYS:
            raise ValueError("XNYS_SESSION_CLOSED")
        if self.session in EARLY_CLOSES:
            raise ValueError("EARLY_CLOSE_REQUIRES_SEPARATE_REVIEWED_SCHEDULE")
        # Do not infer a previous session outside this calendar's supported range.
        self.previous_session

    @property
    def previous_session(self):
        day = date.fromisoformat(self.session) - timedelta(days=1)
        while day.year == 2026 and (day.weekday() >= 5 or day.isoformat() in HOLIDAYS):
            day -= timedelta(days=1)
        if day.year != 2026:
            raise ValueError("PREVIOUS_SESSION_OUTSIDE_CALENDAR")
        return day.isoformat()

    def local_time(self, value):
        return datetime.fromisoformat(self.session + "T" + value + ":00").replace(
            tzinfo=ZoneInfo("America/Los_Angeles"))

    @property
    def opening(self):
        return self.local_time("06:30").astimezone(timezone.utc)

    @property
    def expiry(self):
        return self.local_time("13:05").astimezone(timezone.utc)

    @property
    def label(self):
        return "com.iios.financial-datasets-collection-" + self.session.replace("-", "")

    @property
    def spec_sha256(self):
        return digest({"schema": "fd-session-spec-v2", "session": self.session,
            "calendar": "XNYS", "calendar_source_sha256": CALENDAR_SOURCE_SHA256,
            "previous_session": self.previous_session, "plan_sha256": digest(request_plan(plan=self)),
            "credential_binding": CREDENTIAL_BINDING, "maximum_requests": 50, "maximum_credits": 50})


def require_plan(plan):
    if type(plan) is not SessionPlan:
        raise ValueError("EXPLICIT_VERIFIED_SESSION_PLAN_REQUIRED")
    plan.__post_init__()
    return plan


def request_plan(*, plan):
    require_plan(plan)
    rows = []
    for group, target, deadline in (
        ("OPENING", "06:30", "07:00"),
        ("POINT_IN_TIME_OHLCV", "06:32", "09:30"),
        ("FACTS_OR_PRIOR_BASELINE", "06:34", "09:30"),
        ("INTRADAY", "09:30", "12:55"), ("CLOSING", "13:00", "13:05"),
    ):
        for index, ticker in enumerate(TICKERS):
            when = plan.local_time(target) + timedelta(seconds=6 * index)
            purpose, path, query = group, PATHS[0], {"ticker": ticker}
            if group == "POINT_IN_TIME_OHLCV":
                path = PATHS[1]
                query.update(interval="day", start_date=plan.previous_session, end_date=plan.session)
            elif group == "FACTS_OR_PRIOR_BASELINE":
                if ticker == "MU":
                    purpose, path = "APPLICABLE_FACTS", PATHS[2]
                else:
                    purpose, path = "PRIOR_SESSION_BASELINE", PATHS[1]
                    query.update(interval="day", start_date=plan.previous_session, end_date=plan.previous_session)
            row = {"ordinal": len(rows) + 1, "ticker": ticker, "type": purpose,
                   "method": "GET", "host": "api.financialdatasets.ai", "path": path,
                   "query": query, "target_pdt": when.isoformat(),
                   "target_utc": when.astimezone(timezone.utc).isoformat(),
                   "dispatch_deadline_pdt": plan.local_time(deadline).isoformat(),
                   "public_standard_request_units": 1, "retries": 0}
            row["proposal_row_sha256"] = digest(row)
            rows.append(row)
    return rows


def validate_row(row, *, plan):
    if row not in request_plan(plan=plan):
        raise ValueError("UNREVIEWED_REQUEST")


def verify_document(document, expected):
    if digest(document) != pin(expected):
        raise ValueError("DOCUMENT_PIN_MISMATCH")


def validate_account(account, expected, now, *, plan):
    require_plan(plan)
    verify_document(account, expected)
    if (account.get("session") != plan.session or account.get("spec_sha256") != plan.spec_sha256
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
            or account.get("previous_session") != plan.previous_session
            or account.get("ambiguous_billing") != "RESERVE_FULL_COST_NO_RETRY"
            or not account.get("account_reference") or not account.get("reservation_reference")
            or account.get("credential_binding") != CREDENTIAL_BINDING
            or not instant(account["observed_at"]) <= utc(now) < instant(account["valid_until"])
            or instant(account["valid_until"]) < plan.expiry):
        raise ValueError("ACCOUNT_EVIDENCE_INVALID")
    pin(account.get("entitlement_source_sha256"))
    pin(account.get("cost_balance_source_sha256"))
    pin(account.get("calendar_source_sha256"))


def validate_authority(grant, expected, account_hash, release_hash, now, *, plan, arming=False):
    require_plan(plan)
    verify_document(grant, expected)
    issued, activation = instant(grant["approved_at"]), instant(grant["arm_before"])
    now = utc(now)
    if (grant.get("session") != plan.session or grant.get("spec_sha256") != plan.spec_sha256
            or grant.get("plan_sha256") != digest(request_plan(plan=plan))
            or grant.get("account_sha256") != pin(account_hash)
            or grant.get("release_sha256") != pin(release_hash)
            or grant.get("owner_approved") is not True
            or grant.get("authority") != dict.fromkeys(FORBIDDEN, False)
            or type(grant.get("maximum_credits")) is not int or grant["maximum_credits"] != 50
            or type(grant.get("maximum_requests")) is not int or grant["maximum_requests"] != 50
            or issued.astimezone(ZoneInfo("America/Los_Angeles")).date().isoformat() != plan.session
            or not issued <= now or not issued < activation <= plan.opening
            or not 0 < (activation - issued).total_seconds() <= 1800
            or instant(grant["expires_at"]) != plan.expiry or now >= plan.expiry):
        raise ValueError("SESSION_AUTHORITY_INVALID")
    pin(grant.get("owner_receipt_sha256"))
    if arming and not now < activation:
        raise ValueError("ARMING_WINDOW_MISSED")
