"""Ledger-free, append-only collection journal and single-request scheduler."""
from __future__ import annotations

import fcntl
import hashlib
import json
import math
import os
import stat
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path

from .collection_plan import (canonical, digest, instant, request_plan, require_plan, utc,
                              validate_account, validate_authority)


def safe_directory(path):
    path = Path(path)
    if not path.is_absolute() or path.resolve(strict=True) != path:
        raise ValueError("NONCANONICAL_ROOT")
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
        raise ValueError("UNSAFE_DIRECTORY")
    return info.st_dev, info.st_ino


def read_bytes(path, *, allow_root_owner=False):
    path = Path(path)
    if path.resolve(strict=True) != path:
        raise ValueError("NONCANONICAL_FILE")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as stream:
        before = os.fstat(stream.fileno())
        if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                or before.st_uid not in ({os.getuid(), 0} if allow_root_owner else {os.getuid()}) or before.st_mode & 0o022):
            raise ValueError("UNSAFE_FILE")
        data = stream.read()
        after = os.fstat(stream.fileno())
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
                after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
            raise ValueError("FILE_CHANGED_DURING_READ")
        return data


def exclusive(path, data):
    path = Path(path)
    safe_directory(path.parent)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


class Journal:
    def __init__(self, root, release_hash, *, plan):
        self.plan = require_plan(plan)
        self.root = Path(root)
        self.identity = safe_directory(self.root)
        self.release_hash = release_hash

    def check(self):
        if safe_directory(self.root) != self.identity:
            raise ValueError("ROOT_REPLACED")
        for name in ("receipts", "raw", "state", "inputs"):
            safe_directory(self.root / name)

    @contextmanager
    def lock(self, name="session.lock"):
        if name not in ("session.lock", "supervisor.lock"):
            raise ValueError("LOCK_NAME_INVALID")
        self.check()
        path = self.root / "state" / name
        fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600:
                raise ValueError("UNSAFE_LOCK")
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.check()
            yield
        finally:
            os.close(fd)

    def events(self):
        self.check()
        events, parent = [], self.release_hash
        known_rows = {r["proposal_row_sha256"] for r in request_plan(plan=self.plan)}
        for number, path in enumerate(sorted((self.root / "receipts").iterdir())):
            if path.name != f"{number:06d}.json":
                raise ValueError("JOURNAL_INVENTORY_INVALID")
            event = json.loads(read_bytes(path))
            if "row" in event and event["row"] not in known_rows:
                raise ValueError("UNREVIEWED_JOURNAL_ROW")
            if event.get("kind") not in ("ARMED", "RESERVED", "OBSERVED", "MISSED", "FAILED", "CLOSED", "SUPERVISOR_STARTED"):
                raise ValueError("UNKNOWN_JOURNAL_EVENT")
            supplied = event.pop("sha256")
            if event.get("parent") != parent or event.get("sequence") != number or digest(event) != supplied:
                raise ValueError("JOURNAL_CHAIN_INVALID")
            event["sha256"] = supplied
            if events and instant(event["at"]) < instant(events[-1]["at"]):
                raise ValueError("CLOCK_ROLLBACK")
            if event.get("kind") == "OBSERVED":
                body = read_bytes(self.root / "raw" / (event["row"] + ".json"))
                if hashlib.sha256(body).hexdigest() != event.get("raw_sha256"):
                    raise ValueError("RAW_EVIDENCE_CHANGED")
            parent = supplied
            events.append(event)
        return events

    def append(self, kind, now, **fields):
        events = self.events()
        if events and utc(now) < instant(events[-1]["at"]):
            raise ValueError("CLOCK_ROLLBACK")
        event = dict(fields, kind=kind, at=utc(now).isoformat(), sequence=len(events),
                     parent=events[-1]["sha256"] if events else self.release_hash)
        event["sha256"] = digest(event)
        exclusive(self.root / "receipts" / f"{len(events):06d}.json", canonical(event))
        return event

    def disarmed(self):
        path = self.root / "state" / "disarmed.json"
        if path.is_symlink():
            raise ValueError("UNSAFE_DISARM")
        return path.exists()

    def disarm(self, now):
        # Separate immutable stop marker can interrupt a locked request. No PID killing.
        self.check()
        try:
            exclusive(self.root / "state" / "disarmed.json", canonical({"at": utc(now).isoformat(), "release": self.release_hash}))
        except FileExistsError:
            read_bytes(self.root / "state" / "disarmed.json")


def observation(row, response, now):
    status, media, body = response
    if status != 200 or media.split(";", 1)[0].strip().lower() != "application/json" or not 0 < len(body) <= 2_000_000:
        raise ValueError("RESPONSE_REJECTED")
    value = json.loads(body)
    if not isinstance(value, dict) or any(k in value for k in ("error", "errors")):
        raise ValueError("RESPONSE_SCHEMA_REJECTED")
    if value.get("next_page_url"):
        raise ValueError("PAGINATION_INCOMPLETE_NO_FOLLOWUP")
    if row["path"] == "/prices/snapshot":
        item = value["snapshot"]
        stamp = instant(item["time"])
        if datetime.fromisoformat(item["time"].replace("Z", "+00:00")).utcoffset() != timedelta(0):
            raise ValueError("PROVIDER_TIMESTAMP_NOT_UTC")
        if item["ticker"] != row["ticker"] or not isinstance(item.get("price"), (int, float)) or isinstance(item["price"], bool) or not math.isfinite(item["price"]):
            raise ValueError("SNAPSHOT_SCHEMA_REJECTED")
        age = (utc(now) - stamp).total_seconds()
        if age < -60:
            raise ValueError("FUTURE_OBSERVATION")
        return {"provider_timestamp": item["time"], "classification": "CURRENT" if age <= 900 else "STALE"}
    if row["path"] == "/company/facts":
        item = value["company_facts"]
        if item["ticker"] != "MU":
            raise ValueError("FACTS_TICKER_REJECTED")
        if item.get("time") is not None:
            stamp = instant(item["time"])
            if (datetime.fromisoformat(item["time"].replace("Z", "+00:00")).utcoffset() != timedelta(0)
                    or (utc(now) - stamp).total_seconds() < -60):
                raise ValueError("FACTS_TIMESTAMP_REJECTED")
        return {"provider_timestamp": item.get("time"), "classification": "COMPANY_METADATA"}
    if value.get("ticker") is not None and value["ticker"] != row["ticker"]:
        raise ValueError("HISTORY_ENVELOPE_TICKER_REJECTED")
    items = value["prices"]
    if not isinstance(items, list) or not items:
        raise ValueError("EMPTY_HISTORICAL_DATA")
    dates = []
    for item in items:
        date = item["time"]
        if (item.get("ticker", value.get("ticker")) != row["ticker"]
                or not isinstance(date, str) or len(date) != 10
                or not row["query"]["start_date"] <= date <= row["query"]["end_date"]):
            raise ValueError("HISTORY_IDENTITY_REJECTED")
        instant(date + "T00:00:00Z")
        for key in ("open", "high", "low", "close", "volume"):
            n = item[key]
            if not isinstance(n, (int, float)) or isinstance(n, bool) or not math.isfinite(n):
                raise ValueError("HISTORY_SCHEMA_REJECTED")
        dates.append(date)
    return {"provider_timestamp": max(dates), "returned_dates": dates, "classification": "HISTORICAL_EOD_NOT_CURRENT_SNAPSHOT"}


class CollectionSession:
    """Dependencies are explicit; production constructs them only after release validation."""
    def __init__(self, journal, account, account_hash, authority, authority_hash, *, clock, boundary, verify_runtime):
        self.journal, self.account, self.account_hash = journal, account, account_hash
        self.plan = require_plan(journal.plan)
        self.authority, self.authority_hash = authority, authority_hash
        self.clock, self.boundary, self.verify_runtime = clock, boundary, verify_runtime

    def gates(self, *, arming=False):
        now = utc(self.clock())
        self.verify_runtime()
        validate_account(self.account, self.account_hash, now, plan=self.plan)
        validate_authority(self.authority, self.authority_hash, self.account_hash,
                           self.journal.release_hash, now, plan=self.plan, arming=arming)
        if self.journal.disarmed():
            raise ValueError("SESSION_DISARMED")
        return now

    def arm(self):
        with self.journal.lock():
            now = self.gates(arming=True)
            if self.journal.events():
                raise ValueError("SESSION_NOT_PRISTINE")
            self.journal.append("ARMED", now, authority_sha256=self.authority_hash,
                                account_sha256=self.account_hash, released_credits=50)

    def tick(self):
        with self.journal.lock():
            now = utc(self.clock())
            events = self.journal.events()
            if not events:
                return "DISABLED"
            if now < instant(events[-1]["at"]):
                raise ValueError("CLOCK_ROLLBACK")
            arm = events[0]
            if (arm["kind"] != "ARMED" or arm.get("authority_sha256") != self.authority_hash
                    or arm.get("account_sha256") != self.account_hash):
                raise ValueError("ARM_RECEIPT_MISMATCH")
            if any(e["kind"] in ("FAILED", "CLOSED") for e in events):
                return "CLOSED"
            if now >= self.plan.expiry or self.journal.disarmed():
                self.journal.append("CLOSED", now, released_credits=0, coverage=self.coverage(events, now))
                return "CLOSED"
            try:
                now = self.gates()
                reserved = {e["row"] for e in events if e["kind"] == "RESERVED"}
                outcomes = {e["row"] for e in events if e["kind"] in ("OBSERVED", "FAILED") and "row" in e}
                if reserved - outcomes:
                    raise ValueError("UNCERTAIN_PREVIOUS_DISPATCH_NO_RETRY")
                skipped = {e["row"] for e in events if e["kind"] == "MISSED"}
                for row in request_plan(plan=self.plan):
                    key = row["proposal_row_sha256"]
                    if key in reserved or key in skipped:
                        continue
                    deadline = instant(row["dispatch_deadline_pdt"])
                    if now >= deadline - timedelta(seconds=20):
                        self.journal.append("MISSED", now, row=key, type=row["type"], reason="INSUFFICIENT_DEADLINE_BUDGET")
                        continue
                    if now < instant(row["target_utc"]):
                        continue
                    times = [instant(e["at"]) for e in events if e["kind"] == "RESERVED"]
                    if len(times) >= 50:
                        raise ValueError("CREDIT_CAP_REACHED")
                    if sum(now - timedelta(seconds=60) < t <= now for t in times) >= 10:
                        return "RATE_WAIT"
                    # Durable reservation precedes credential access and transmission.
                    self.journal.append("RESERVED", now, row=key, cost=1,
                                        late_seconds=(now - instant(row["target_utc"])).total_seconds())
                    try:
                        now = self.gates()
                        response = self.boundary.request(row, min(deadline, self.plan.expiry) - timedelta(seconds=1))
                        observed = utc(self.clock())
                        details = observation(row, response, observed)
                        if observed >= deadline or observed >= self.plan.expiry or self.journal.disarmed():
                            raise ValueError("RESPONSE_OUTSIDE_AUTHORITY")
                        raw = response[2]
                        exclusive(self.journal.root / "raw" / (key + ".json"), raw)
                        self.journal.append("OBSERVED", observed, row=key, raw_sha256=hashlib.sha256(raw).hexdigest(), **details)
                        return "OBSERVED"
                    except Exception:
                        # Never persist exception text, request headers or provider error bodies.
                        self.journal.append("FAILED", utc(self.clock()), row=key,
                                            category="REQUEST_FAILED_OR_AMBIGUOUS", charged_reservation=1, released_credits=0)
                        return "FAILED_CLOSED"
                return "WAIT"
            except Exception:
                self.journal.append("FAILED", utc(self.clock()), category="PREFLIGHT_OR_RECOVERY_FAILED", released_credits=0)
                return "FAILED_CLOSED"

    def coverage(self, events, now):
        observed = {e["row"]: e for e in events if e["kind"] == "OBSERVED"}
        expected = request_plan(plan=self.plan)
        missing_open = [r["ticker"] for r in expected if r["type"] == "OPENING" and (
            r["proposal_row_sha256"] not in observed or observed[r["proposal_row_sha256"]].get("classification") != "CURRENT")]
        missing = [r["ordinal"] for r in expected if r["proposal_row_sha256"] not in observed]
        stale = [e["row"] for e in observed.values() if e.get("classification") == "STALE"]
        complete = not missing and not stale
        classification = "COMPLETE_SCHEDULED_COLLECTION" if complete else (
            "PARTIAL_SESSION" if utc(now) >= self.plan.opening + timedelta(minutes=30) else "INCOMPLETE_COLLECTION")
        return {"classification": classification, "missing_opening_tickers": missing_open,
                "missing_ordinals": missing, "stale_rows": stale, "official_close_proven": False,
                "trading_authorized": False}
