"""Exact-plan HTTPS boundary. No default credentials, trust, or implicit activation."""
from __future__ import annotations

import signal
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from urllib.parse import urlencode

from .collection_plan import require_plan, utc, validate_row
from .financial_datasets import API_HOST, AUTH_HEADER
from .financial_datasets_tls import _connection


@contextmanager
def deadline_alarm(seconds):
    """Bound DNS, credential retrieval and the entire response, not each socket read."""
    if threading.current_thread() is not threading.main_thread() or signal.getitimer(signal.ITIMER_REAL) != (0.0, 0.0):
        raise ValueError("EXCLUSIVE_DEADLINE_TIMER_REQUIRED")
    def expired(_signum, _frame):
        raise TimeoutError("COLLECTION_DEADLINE")
    previous = signal.getsignal(signal.SIGALRM)
    signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


class CollectionBoundary:
    def __init__(self, credentials, transport, *, plan, stopped, clock=None, alarm=deadline_alarm,
                 connection_factory=_connection):
        self.plan = require_plan(plan)
        self.credentials, self.transport, self.stopped = credentials, transport, stopped
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.alarm, self.connection_factory = alarm, connection_factory

    def request(self, row, deadline):
        validate_row(row, plan=self.plan)
        seconds = min(15.0, (utc(deadline) - utc(self.clock())).total_seconds())
        if seconds <= 0 or self.stopped():
            raise ValueError("DISPATCH_AUTHORITY_EXPIRED")
        connection = None
        secret = b""
        try:
            with self.alarm(seconds):
                if self.transport.trust_readiness() != "READY":
                    raise ValueError("TLS_TRUST_REJECTED")
                context = self.transport.trust.build_context()
                secret = self.credentials.retrieve()
                if utc(self.clock()) >= deadline or self.stopped():
                    raise ValueError("DISPATCH_AUTHORITY_EXPIRED")
                connection = self.connection_factory(API_HOST, 443, context, min(seconds, 5.0))
                connection.request("GET", row["path"] + "?" + urlencode(row["query"]),
                                   headers={AUTH_HEADER: secret.decode("ascii")})
                response = connection.getresponse()
                body = response.read(2_000_001)
                if 300 <= response.status < 400 or response.getheader("Location"):
                    raise ValueError("REDIRECT_REJECTED")
                if utc(self.clock()) >= deadline or self.stopped():
                    raise ValueError("RESPONSE_AFTER_DEADLINE")
                return int(response.status), str(response.getheader("Content-Type") or ""), body
        finally:
            secret = b""
            if connection is not None:
                connection.close()
