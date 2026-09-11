"""Single-session, deny-only observation lifecycle. No process or network startup.

The 2026 XNYS core calendar is a reviewed, bounded schedule, not a claim about
unscheduled exchange closures. Future installation must independently approve
the session document. Unknown calendar years fail closed.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from enum import StrEnum
import json
from zoneinfo import ZoneInfo

from truth_spine_authority import CAPABILITIES, disabled_document, validate_authority
from truth_spine_contract import digest, seal, utc, verified

CALENDAR_SOURCE = "https://www.nyse.com/trade/hours-calendars"
HOLIDAYS_2026 = frozenset({"2026-01-01", "2026-01-19", "2026-02-16", "2026-04-03",
                         "2026-05-25", "2026-06-19", "2026-07-03", "2026-09-07",
                         "2026-11-26", "2026-12-25"})
SHORT_2026 = frozenset({"2026-11-27", "2026-12-24"})
CALENDAR_ID = digest({"source": CALENDAR_SOURCE, "year": 2026,
                      "holidays": sorted(HOLIDAYS_2026), "short": sorted(SHORT_2026),
                      "zone": "America/New_York", "open": "09:30", "close": "16:00",
                      "short_close": "13:00"})


class Phase(StrEnum):
    PREMARKET_PREPARATION = "PREMARKET_PREPARATION"
    PREMARKET_READY = "PREMARKET_READY"
    OPENING_OBSERVATION = "OPENING_OBSERVATION"
    REGULAR_SESSION = "REGULAR_SESSION"
    CLOSING_OBSERVATION = "CLOSING_OBSERVATION"
    POST_CLOSE_RECONCILIATION = "POST_CLOSE_RECONCILIATION"
    SESSION_COMPLETE = "SESSION_COMPLETE"
    SHUTDOWN_COMPLETE = "SHUTDOWN_COMPLETE"
    FAILED_CLOSED = "FAILED_CLOSED"


CADENCE = {Phase.PREMARKET_PREPARATION: 900, Phase.PREMARKET_READY: 900,
           Phase.OPENING_OBSERVATION: 300, Phase.REGULAR_SESSION: 900,
           Phase.CLOSING_OBSERVATION: 300, Phase.POST_CLOSE_RECONCILIATION: 300}
SHUTDOWN_SECONDS = 300
RECONCILIATION_SECONDS = 900


def aware(now: datetime) -> datetime:
    return utc(now.isoformat())


@dataclass(frozen=True)
class Session:
    day: str
    calendar_identity: str
    open_at: datetime
    close_at: datetime
    status: str

    @property
    def start(self):
        return self.open_at - timedelta(minutes=90)

    @property
    def reconcile_end(self):
        return self.close_at + timedelta(seconds=RECONCILIATION_SECONDS)

    @property
    def shutdown_end(self):
        return self.reconcile_end + timedelta(seconds=SHUTDOWN_SECONDS)

    def record(self):
        return seal({"schema": "iios-shadow-session-v1", "exchange": "XNYS",
                     "timezone": "America/New_York", "display_timezone": "America/Los_Angeles",
                     "date": self.day, "calendar_identity": self.calendar_identity,
                     "status": self.status, "start": self.start.isoformat(),
                     "open": self.open_at.isoformat(), "close": self.close_at.isoformat(),
                     "reconcile_end": self.reconcile_end.isoformat(),
                     "shutdown_end": self.shutdown_end.isoformat(),
                     "scope": "DENY_ONLY_OBSERVATION_NOT_MARKET_DATA_PROVIDER"})

    @property
    def identity(self):
        return self.record()["content_hash"]

    def phase_at(self, now: datetime) -> Phase:
        now = aware(now)
        if self.status == "CLOSED" or now < self.start or now >= self.shutdown_end:
            return Phase.FAILED_CLOSED
        if now < self.open_at - timedelta(minutes=15):
            return Phase.PREMARKET_PREPARATION
        if now < self.open_at:
            return Phase.PREMARKET_READY
        if now < self.open_at + timedelta(minutes=30):
            return Phase.OPENING_OBSERVATION
        if now < self.close_at - timedelta(minutes=5):
            return Phase.REGULAR_SESSION
        if now < self.close_at:
            return Phase.CLOSING_OBSERVATION
        if now < self.reconcile_end:
            return Phase.POST_CLOSE_RECONCILIATION
        return Phase.SESSION_COMPLETE


def exchange_session(day: str) -> Session:
    d = date.fromisoformat(day)
    if d.year != 2026 or d.isoformat() != day:
        raise ValueError("UNREVIEWED_CALENDAR_DATE")
    eastern = ZoneInfo("America/New_York")
    closed = d.weekday() >= 5 or day in HOLIDAYS_2026
    short = day in SHORT_2026
    return Session(day, CALENDAR_ID,
                   datetime.combine(d, time(9, 30), eastern).astimezone(timezone.utc),
                   datetime.combine(d, time(13 if short else 16), eastern).astimezone(timezone.utc),
                   "CLOSED" if closed else "SHORTENED" if short else "NORMAL")


def parse_session(record: dict) -> Session:
    verified(record)
    if record.get('schema') == 'iios-historical-shadow-session-v1':
        session = HistoricalSession(utc(record['start']), record['duration_seconds'])
        if record != session.record():
            raise ValueError('HISTORICAL_SESSION_BINDING_INVALID')
        return session
    session = exchange_session(record["date"])
    if record != session.record():
        raise ValueError("SESSION_CALENDAR_BINDING_INVALID")
    return session


@dataclass(frozen=True)
class HistoricalSession:
    """Bounded current-time replay of retained inputs, never an exchange session.

    No market clock is overridden or backdated. Input observation timestamps
    remain in captured records. Only capture/publication use this wall clock.
    The final minute is reserved for verified cleanup, not further replay.
    """
    start: datetime
    duration_seconds: int
    status: str = 'HISTORICAL_ONLY'

    def __post_init__(self):
        aware(self.start)
        if type(self.duration_seconds) is not int or not 300 <= self.duration_seconds <= 3600:
            raise ValueError('HISTORICAL_DURATION_INVALID')
        if self.status != 'HISTORICAL_ONLY':
            raise ValueError('HISTORICAL_SCOPE_INVALID')

    @property
    def open_at(self): return self.start

    @property
    def close_at(self): return self.start

    @property
    def reconcile_end(self): return self.start + timedelta(seconds=self.duration_seconds-60)

    @property
    def shutdown_end(self): return self.start + timedelta(seconds=self.duration_seconds)

    def phase_at(self, now):
        now = aware(now)
        if not self.start <= now < self.shutdown_end: return Phase.FAILED_CLOSED
        return Phase.POST_CLOSE_RECONCILIATION if now < self.reconcile_end else Phase.SESSION_COMPLETE

    def record(self):
        return seal({'schema': 'iios-historical-shadow-session-v1',
            'scope': 'BOUNDED_HISTORICAL_REPLAY_NOT_FULL_MARKET_DAY',
            'start': self.start.isoformat(), 'duration_seconds': self.duration_seconds,
            'reconcile_end': self.reconcile_end.isoformat(), 'shutdown_end': self.shutdown_end.isoformat(),
            'market_calendar_authority': False, 'input_times': 'PRESERVED_NOT_REINTERPRETED'})

    @property
    def identity(self): return self.record()['content_hash']


def session_authority(session: Session, release: str, owners: dict, issued: datetime) -> dict:
    """Produces a candidate, NOT owner approval. Installation pins its hash separately."""
    issued = aware(issued)
    if (session.status == "CLOSED" or issued > session.start
            or not 0 < (session.shutdown_end - issued).total_seconds() <= 86400):
        raise ValueError("SESSION_AUTHORITY_LIFETIME_INVALID")
    document = disabled_document(session.identity, release, owners["scheduler"], owners["publisher"],
                                 issued.isoformat(), session.shutdown_end.isoformat())
    validate_session_authority(document, session, release, owners, digest(document), issued)
    return document


def validate_session_authority(document, session, release, owners, approved_hash, now):
    # An edited and resealed JSON document cannot change the independent owner pin.
    if digest(document) != approved_hash or utc(document["issued_at"]) > session.start:
        raise PermissionError("SESSION_AUTHORITY_PIN_INVALID")
    if utc(document["expires_at"]) != session.shutdown_end or aware(now) >= session.shutdown_end:
        raise PermissionError("SESSION_AUTHORITY_EXPIRED")
    return validate_authority(document, binding=session.identity, release=release, owners=owners, now=now)


@dataclass(frozen=True)
class RestartPolicy:
    per_role: int = 1
    total: int = 3
    cooldown_seconds: int = 60

    def validate(self):
        if (type(self.per_role) is not int or type(self.total) is not int
                or type(self.cooldown_seconds) is not int
                or not 0 <= self.per_role <= 2 or not 0 <= self.total <= 3
                or not 60 <= self.cooldown_seconds <= 300):
            raise ValueError("RESTART_POLICY_INVALID")


class Lifecycle:
    """Deterministic reducer; persistence/OS ownership are separate required gates.

    The caller must persist the returned state BEFORE acting on restart/capture
    instructions. No CLI/environment clock override is defined by this module.
    """
    def __init__(self, session: Session, state: dict | None = None):
        self.session = parse_session(session.record())
        self.state = seal({"schema": "iios-shadow-lifecycle-v1", "session": session.identity,
                           "phase": Phase.PREMARKET_PREPARATION, "last_cycle": None,
                           "next_capture": session.start.isoformat(), "last_capture": None,
                           "capture_status": "UNAVAILABLE", "sequence": 0,
                           "missed_phases": [], "incidents":
                           (["HISTORICAL_REPLAY_NOT_FULL_MARKET_DAY"] if isinstance(session, HistoricalSession) else []), "restart_counts":
                           dict.fromkeys(("backend", "scheduler", "publisher"), 0),
                           "restart_after": {}, "post_close_reconciled": False,
                           "capabilities": dict.fromkeys(CAPABILITIES, False)}) if state is None else json.loads(json.dumps(verified(state)))
        if (self.state["session"] != session.identity or set(self.state["capabilities"]) != set(CAPABILITIES)
                or any(v is not False for v in self.state["capabilities"].values())):
            raise ValueError("LIFECYCLE_BINDING_INVALID")
        required = {"schema", "session", "phase", "last_cycle", "next_capture", "last_capture", "capture_status",
                    "sequence", "missed_phases", "incidents", "restart_counts", "restart_after",
                    "post_close_reconciled", "capabilities", "content_hash"}
        if (set(self.state) - {"session_result"} != required or self.state["schema"] != "iios-shadow-lifecycle-v1"
                or self.state["phase"] not in set(Phase) or type(self.state["sequence"]) is not int
                or self.state["sequence"] < 0 or type(self.state["post_close_reconciled"]) is not bool
                or self.state["capture_status"] not in {"CURRENT", "STALE", "UNAVAILABLE"}
                or set(self.state["restart_counts"]) != {"backend", "scheduler", "publisher"}
                or any(type(n) is not int or not 0 <= n <= 1 for n in self.state["restart_counts"].values())
                or not set(self.state["restart_after"]).issubset(self.state["restart_counts"])):
            raise ValueError("LIFECYCLE_SCHEMA_INVALID")
        utc(self.state["next_capture"])
        if self.state["last_cycle"] is not None:
            utc(self.state["last_cycle"])
        for stamp in self.state["restart_after"].values():
            utc(stamp)

    def _save(self):
        self.state["sequence"] += 1
        self.state = seal(self.state)
        return self.state.copy()

    def fail(self, reason: str):
        self.state["phase"] = Phase.FAILED_CLOSED
        self.state["capture_status"] = "STALE"
        self.state["incidents"].append(reason)
        return self._save()

    def tick(self, now: datetime, *, authority_current: bool):
        now = aware(now)
        if self.state["phase"] in (Phase.FAILED_CLOSED, Phase.SHUTDOWN_COMPLETE):
            return self.state.copy()
        if not authority_current:
            return self.fail("AUTHORITY_EXPIRED")
        previous = self.state["last_cycle"]
        if previous and now < utc(previous):
            return self.fail("CLOCK_REGRESSION")
        phase = self.session.phase_at(now)
        if phase == Phase.FAILED_CLOSED:
            return self.fail("SESSION_OUTSIDE_REVIEWED_WINDOW")
        phases = list(CADENCE)
        old = self.state["phase"]
        if phase in phases and old in phases and not isinstance(self.session, HistoricalSession):
            skipped = phases[phases.index(old)+1:phases.index(phase)]
            self.state["missed_phases"].extend(p for p in skipped if p not in self.state["missed_phases"])
        if previous is None and now >= self.session.open_at and not isinstance(self.session, HistoricalSession):
            self.state["incidents"].append("PARTIAL_OBSERVATION_LATE_START")
        due = utc(self.state["next_capture"])
        if now > due + timedelta(seconds=60):
            self.state["capture_status"] = "STALE"
            if "MISSED_REFRESH_NO_BACKFILL" not in self.state["incidents"]:
                self.state["incidents"].append("MISSED_REFRESH_NO_BACKFILL")
        if phase != old and phase in CADENCE:
            self.state["next_capture"] = now.isoformat()
        if phase == Phase.SESSION_COMPLETE and not self.state["post_close_reconciled"]:
            return self.fail("POST_CLOSE_RECONCILIATION_MISSING")
        self.state.update(phase=phase, last_cycle=now.isoformat())
        return self._save()

    def capture_due(self, now):
        return (self.state["phase"] in CADENCE and aware(now) >= utc(self.state["next_capture"]))

    def captured(self, now, generation: str | None):
        now = aware(now)
        if self.state["phase"] not in CADENCE:
            raise PermissionError("TERMINAL_CAPTURE_FORBIDDEN")
        self.state["capture_status"] = "CURRENT" if generation else "STALE"
        if generation:
            self.state["last_capture"] = generation
        else:
            self.state["incidents"].append("CAPTURE_FAILED")
        self.state["next_capture"] = (now + timedelta(seconds=CADENCE[self.state["phase"]])).isoformat()
        return self._save()

    def reconciled(self):
        if self.state["phase"] != Phase.POST_CLOSE_RECONCILIATION or self.state["capture_status"] != "CURRENT":
            return self.fail("POST_CLOSE_RECONCILIATION_FAILED")
        self.state["post_close_reconciled"] = True
        return self._save()

    def reserve_restart(self, role, now, *, authority_current, policy=RestartPolicy()):
        policy.validate()
        now = aware(now)
        if (role not in self.state["restart_counts"] or not authority_current
                or self.state["phase"] in (Phase.FAILED_CLOSED, Phase.SESSION_COMPLETE, Phase.SHUTDOWN_COMPLETE)
                or now >= self.session.reconcile_end):
            return self.fail("RESTART_FORBIDDEN")
        counts = self.state["restart_counts"]
        if counts[role] >= policy.per_role or sum(counts.values()) >= policy.total:
            return self.fail("RESTART_BUDGET_EXHAUSTED")
        counts[role] += 1
        self.state["restart_after"][role] = (now + timedelta(seconds=policy.cooldown_seconds)).isoformat()
        self.state["incidents"].append(role.upper() + "_RESTART_RESERVED")
        return self._save()

    def shutdown(self, *, unresolved: bool, listener_clear: bool):
        # Never consult authority here: expiration cannot revoke safe cleanup.
        if self.state["phase"] == Phase.SHUTDOWN_COMPLETE and not unresolved and listener_clear:
            return self.state.copy()
        if unresolved or not listener_clear:
            return self.fail("SHUTDOWN_INCOMPLETE")
        failed = self.state["phase"] not in (Phase.SESSION_COMPLETE, Phase.SHUTDOWN_COMPLETE)
        if failed and self.state["phase"] != Phase.FAILED_CLOSED:
            self.state["incidents"].append("SESSION_INCOMPLETE_AT_SHUTDOWN")
        self.state["phase"] = Phase.SHUTDOWN_COMPLETE
        self.state["session_result"] = "FAILED_CLOSED" if failed else "COMPLETE"
        return self._save()
