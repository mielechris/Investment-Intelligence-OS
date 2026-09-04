from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class SECContactConfig:
    application_name: str
    contact: str
    explicitly_approved: bool = False

    def user_agent(self) -> str:
        if not self.explicitly_approved or not self.application_name.strip() or not self.contact.strip():
            raise RuntimeError("SEC_CONTACT_NOT_CONFIGURED")
        if "@" not in self.contact and not self.contact.startswith("https://"):
            raise ValueError("SEC_CONTACT_INVALID")
        return f"{self.application_name.strip()} contact: {self.contact.strip()}"


class MockableSECThrottle:
    """Serialized, unscheduled SEC request gate. The caller supplies the mocked/request function."""
    def __init__(self, config: SECContactConfig, *, requests_per_second: float = 1.0,
                 max_retries: int = 1, clock: Callable[[], float] = time.monotonic,
                 sleeper: Callable[[float], None] = time.sleep) -> None:
        if not 0 < requests_per_second <= 1 or not 0 <= max_retries <= 1:
            raise ValueError("SEC_THROTTLE_INVALID")
        self.user_agent = config.user_agent(); self.interval = 1 / requests_per_second
        self.max_retries = max_retries; self.clock = clock; self.sleeper = sleeper
        self._lock = threading.Lock(); self._last: float | None = None

    def request(self, operation: Callable[[str], int]) -> str:
        with self._lock:
            now = self.clock()
            if self._last is not None and now - self._last < self.interval:
                self.sleeper(self.interval - (now - self._last))
            for attempt in range(self.max_retries + 1):
                status = operation(self.user_agent); self._last = self.clock()
                if status == 200: return "SUCCESS"
                if status in {403, 429}: return "ACCESS_POLICY_REJECTED"
                if attempt < self.max_retries: self.sleeper(min(2 ** attempt, 2))
            return "UNAVAILABLE"
