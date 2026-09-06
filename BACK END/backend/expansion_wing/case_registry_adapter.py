from __future__ import annotations

import copy
from datetime import datetime, timezone
import json
import threading
import time
from typing import Any, Callable
from urllib.request import Request, urlopen

from .north_star_commissioning import browser_safe_case_registry

DEFAULT_ENDPOINT = "http://127.0.0.1:8002/experience/factory-intelligence/overview"
MAX_RESPONSE_BYTES = 262_144
MAX_CASES = 200
REFRESH_SECONDS = 60.0
SOURCE_TIMEOUT_SECONDS = 12.0
FRESH_SECONDS = 120.0
STALE_SECONDS = 900.0


def _iso(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return value if parsed.tzinfo is not None and parsed.astimezone(timezone.utc) <= datetime.now(timezone.utc) else None


def sanitize_overview(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict) or set(payload).intersection({"prompt", "model_response", "provider_body", "private_9i", "session_results", "credentials"}):
        raise ValueError("CASE_SOURCE_UNSAFE")
    rows = payload.get("cases")
    declared = payload.get("case_count")
    if not isinstance(rows, list) or isinstance(declared, bool) or not isinstance(declared, int) or declared != len(rows) or len(rows) > MAX_CASES:
        raise ValueError("CASE_SOURCE_COUNT_INVALID")
    allowed_source = {"case_id", "ticker", "topic", "stage", "active_room", "qualified", "latest_event", "latest_event_at", "committee", "risk", "paper_execution", "live_execution", "trade_execution_permission", "authorization", "agent_count", "capital", "committee_confidence", "sizing"}
    mapped = []
    for raw in rows:
        if not isinstance(raw, dict) or set(raw) != allowed_source:
            raise ValueError("CASE_SOURCE_FIELDS_INVALID")
        case_id, ticker, stage = raw.get("case_id"), raw.get("ticker"), raw.get("stage")
        if not isinstance(case_id, str) or not isinstance(ticker, str) or stage not in {"COMMITTEE", "RISK", "REJECTED", "CLOSED", "RESEARCH", "AWAITING_EVIDENCE"}:
            raise ValueError("CASE_SOURCE_IDENTITY_INVALID")
        event_at = _iso(raw.get("latest_event_at"))
        if raw.get("latest_event_at") is not None and event_at is None:
            raise ValueError("CASE_SOURCE_TIMESTAMP_INVALID")
        event = raw.get("latest_event") if isinstance(raw.get("latest_event"), str) and len(raw["latest_event"]) <= 96 else None
        committee = raw.get("committee") if isinstance(raw.get("committee"), dict) else {}
        risk = raw.get("risk") if isinstance(raw.get("risk"), dict) else {}
        mapped.append({
            "case_id": case_id, "ticker": ticker[:24], "instrument": "BROWSER_APPROVED_INSTRUMENT",
            "title": raw.get("topic")[:300] if isinstance(raw.get("topic"), str) else None,
            "created_at": None, "updated_at": event_at, "stage": stage,
            "status": "CLOSED" if stage == "CLOSED" else "REJECTED" if stage == "REJECTED" else "INCOMPLETE",
            "originating_cycle_id": None, "evidence_completeness": "INCOMPLETE",
            "thesis_summary": None, "bear_case_summary": None, "invalidation": None,
            "validation_9h_state": "UNAVAILABLE", "shadow_9i_state": "UNAVAILABLE", "outcome_9j_state": "UNAVAILABLE",
            "committee_state": str(committee.get("status") or committee.get("state") or "UNAVAILABLE")[:96],
            "risk_state": str(risk.get("status") or risk.get("state") or "UNAVAILABLE")[:96],
            "paper_eligibility": False, "position_state": "UNAVAILABLE",
            "closure_state": "CLOSED" if stage == "CLOSED" else "OPEN",
            "outcome_availability": "UNAVAILABLE", "blockers": ["BROWSER_SAFE_CASE_DETAILS_INCOMPLETE"],
            "receipt_categories": [event] if event else [],
        })
    observed_at = _iso(payload.get("generated_at"))
    if payload.get("generated_at") is not None and observed_at is None:
        raise ValueError("CASE_SOURCE_TIMESTAMP_INVALID")
    state = "CURRENT" if payload.get("data_state") == "LIVE" else "INCOMPLETE"
    registry = browser_safe_case_registry(mapped, source_state=state)
    registry["source_observed_at"] = observed_at
    return registry


class BackgroundCaseRegistry:
    def __init__(self, endpoint: str = DEFAULT_ENDPOINT, *, refresh_seconds: float = REFRESH_SECONDS,
                 timeout_seconds: float = SOURCE_TIMEOUT_SECONDS,
                 fetcher: Callable[[str, float, int], Any] | None = None,
                 monotonic: Callable[[], float] = time.monotonic) -> None:
        if endpoint != DEFAULT_ENDPOINT or refresh_seconds < 15 or not 1 <= timeout_seconds <= 15:
            raise ValueError("CASE_ADAPTER_CONFIGURATION_INVALID")
        self.endpoint, self.refresh_seconds, self.timeout_seconds = endpoint, refresh_seconds, timeout_seconds
        self.fetcher, self.monotonic = fetcher or self._fetch, monotonic
        self._lock = threading.Lock(); self._stop = threading.Event(); self._wake = threading.Event()
        self._retained: dict[str, Any] | None = None; self._retained_at = 0.0; self._refreshing = False
        self._refresh_count = 0; self._error_category: str | None = None
        self._thread = threading.Thread(target=self._run, name="iios-case-registry-refresh", daemon=True)

    @staticmethod
    def _fetch(endpoint: str, timeout: float, maximum: int) -> Any:
        request = Request(endpoint, method="GET", headers={"Accept": "application/json"})
        with urlopen(request, timeout=timeout) as response:
            if response.status != 200: raise RuntimeError("CASE_SOURCE_HTTP_STATUS")
            raw = response.read(maximum + 1)
        if len(raw) > maximum: raise RuntimeError("CASE_SOURCE_RESPONSE_TOO_LARGE")
        return json.loads(raw)

    def start(self) -> None:
        if not self._thread.is_alive(): self._thread.start()

    def _run(self) -> None:
        while not self._stop.is_set():
            self.refresh_once()
            self._wake.wait(self.refresh_seconds); self._wake.clear()

    def refresh_once(self) -> bool:
        with self._lock:
            if self._refreshing: return False
            self._refreshing = True
        try:
            sanitized = sanitize_overview(self.fetcher(self.endpoint, self.timeout_seconds, MAX_RESPONSE_BYTES))
            retained = copy.deepcopy(sanitized)
            with self._lock:
                self._retained, self._retained_at = retained, self.monotonic()
                self._refresh_count += 1; self._error_category = None
            return True
        except Exception as exc:
            category = "CASE_SOURCE_TIMEOUT" if isinstance(exc, TimeoutError) or "timed out" in str(exc).lower() else "CASE_SOURCE_UNAVAILABLE"
            with self._lock: self._error_category = category
            return False
        finally:
            with self._lock: self._refreshing = False

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            retained = copy.deepcopy(self._retained); age = self.monotonic() - self._retained_at if retained else None
            refreshing, count, error = self._refreshing, self._refresh_count, self._error_category
        if retained is None:
            unavailable = browser_safe_case_registry(None, source_state="UNAVAILABLE")
            unavailable.update({"source_age_seconds": None, "freshness_state": "UNAVAILABLE", "refreshing": refreshing, "refresh_count": count, "error_category": error})
            return unavailable
        retained["source_age_seconds"] = round(max(0.0, age or 0.0), 3)
        retained["freshness_state"] = "CURRENT" if age is not None and age <= FRESH_SECONDS else "STALE" if age is not None and age <= STALE_SECONDS else "UNAVAILABLE"
        retained["state"] = retained["freshness_state"] if retained["freshness_state"] != "UNAVAILABLE" else "UNAVAILABLE"
        retained.update({"refreshing": refreshing, "refresh_count": count, "error_category": error})
        return retained

    def close(self) -> None:
        self._stop.set(); self._wake.set()
        if self._thread.is_alive(): self._thread.join(timeout=min(2.0, self.timeout_seconds))
