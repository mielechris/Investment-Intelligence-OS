from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Protocol
from zoneinfo import ZoneInfo

EASTERN=ZoneInfo("America/New_York")


class ApprovedCalendar(Protocol):
    def holiday_status(self, session_date: date) -> bool|None: ...


@dataclass(frozen=True)
class SessionTruth:
    state: str
    session_date: str
    observed_at: str
    calendar_approved: bool
    intraday_eligible: bool
    reason: str


def session_truth(now: datetime, calendar: ApprovedCalendar) -> SessionTruth:
    if now.tzinfo is None: raise ValueError("SESSION_CLOCK_INVALID")
    local=now.astimezone(EASTERN); day=local.date(); observed=now.isoformat()
    if day.weekday()>=5:
        return SessionTruth("MARKET_CLOSED_WEEKEND",day.isoformat(),observed,True,False,"EXPECTED_WEEKEND_CLOSURE")
    holiday=calendar.holiday_status(day)
    if holiday is None:
        return SessionTruth("UNKNOWN",day.isoformat(),observed,False,False,"APPROVED_CALENDAR_UNAVAILABLE")
    if holiday:
        return SessionTruth("MARKET_CLOSED_HOLIDAY",day.isoformat(),observed,True,False,"APPROVED_EXCHANGE_HOLIDAY")
    current=local.timetz().replace(tzinfo=None)
    if current<time(9,30): state="PRE_MARKET"
    elif current<time(16): state="REGULAR_SESSION"
    else: state="POST_MARKET"
    return SessionTruth(state,day.isoformat(),observed,True,state=="REGULAR_SESSION","SESSION_CLOCK")


def current_session_evidence(*, session: SessionTruth, evidence_session_date: str|None,
                             evidence_timestamp: str|None, max_age_seconds: int=900) -> dict[str,object]:
    if not evidence_session_date or not evidence_timestamp:
        return {"state":"UNAVAILABLE","current_session":False,"reason":"CURRENT_SESSION_EVIDENCE_MISSING"}
    try: timestamp=datetime.fromisoformat(evidence_timestamp.replace("Z","+00:00"))
    except ValueError: return {"state":"UNAVAILABLE","current_session":False,"reason":"EVIDENCE_TIMESTAMP_INVALID"}
    if timestamp.tzinfo is None: return {"state":"UNAVAILABLE","current_session":False,"reason":"EVIDENCE_TIMESTAMP_INVALID"}
    observed=datetime.fromisoformat(session.observed_at)
    if evidence_session_date!=session.session_date:
        return {"state":"STALE","current_session":False,"reason":"PRIOR_SESSION_EVIDENCE"}
    age=(observed-timestamp).total_seconds()
    if age<0: return {"state":"FAILED_CLOSED","current_session":False,"reason":"FUTURE_EVIDENCE_REJECTED"}
    if age>max_age_seconds: return {"state":"STALE","current_session":True,"reason":"EVIDENCE_STALE"}
    return {"state":"AVAILABLE","current_session":True,"reason":None}
