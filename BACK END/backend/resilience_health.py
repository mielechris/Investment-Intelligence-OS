"""IIOS Batch 10 resilience heartbeat.

Health is derived from successful payload validation plus freshness. A running
process alone is never sufficient evidence that a subsystem is healthy.

This module is deliberately execution-agnostic: it cannot place orders, mutate
trading thresholds, connect a broker, or enable live capital.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, Iterable, Mapping, Optional


class HealthStatus(str, Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    DOWN = "DOWN"
    STARTING = "STARTING"
    STALE = "STALE"


DEFAULT_COMPONENT_TTLS: Mapping[str, int] = {
    "market_data": 180,
    "news_evidence": 900,
    "observation_9a": 1200,
    "grok": 1800,
    "gemini": 1800,
    "gpt": 1800,
    "committee": 1800,
    "risk": 1800,
    "paper": 1200,
    "storage": 300,
}

CRITICAL_FOR_PAPER = frozenset({"market_data", "observation_9a", "risk", "paper", "storage"})


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: Optional[datetime]) -> Optional[str]:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class ComponentHealth:
    name: str
    status: HealthStatus
    payload_valid: bool
    last_good_update: Optional[datetime]
    last_attempt_update: Optional[datetime]
    freshness_ttl_seconds: int
    age_seconds: Optional[float]
    reason: str

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["status"] = self.status.value
        payload["last_good_update"] = _iso(self.last_good_update)
        payload["last_attempt_update"] = _iso(self.last_attempt_update)
        return payload


@dataclass
class HeartbeatRegistry:
    """In-memory source-of-truth for explicit subsystem heartbeats.

    Callers must report a heartbeat only after validating a subsystem payload.
    Unknown components begin as STARTING rather than being optimistically marked
    healthy.
    """

    ttls: Mapping[str, int] = field(default_factory=lambda: dict(DEFAULT_COMPONENT_TTLS))
    _last_good: Dict[str, datetime] = field(default_factory=dict)
    _last_attempt: Dict[str, datetime] = field(default_factory=dict)
    _payload_valid: Dict[str, bool] = field(default_factory=dict)
    _reason: Dict[str, str] = field(default_factory=dict)
    _explicit_down: Dict[str, bool] = field(default_factory=dict)

    def __post_init__(self) -> None:
        missing = set(DEFAULT_COMPONENT_TTLS) - set(self.ttls)
        if missing:
            merged = dict(DEFAULT_COMPONENT_TTLS)
            merged.update(self.ttls)
            self.ttls = merged

    def record_success(
        self,
        component: str,
        *,
        at: Optional[datetime] = None,
        payload_valid: bool = True,
        reason: str = "valid payload received",
    ) -> None:
        self._require_component(component)
        at = at or utc_now()
        self._last_attempt[component] = at
        self._payload_valid[component] = bool(payload_valid)
        self._reason[component] = reason
        self._explicit_down[component] = False
        if payload_valid:
            self._last_good[component] = at

    def record_failure(
        self,
        component: str,
        *,
        at: Optional[datetime] = None,
        reason: str = "subsystem failure",
        down: bool = False,
    ) -> None:
        self._require_component(component)
        self._last_attempt[component] = at or utc_now()
        self._payload_valid[component] = False
        self._reason[component] = reason
        self._explicit_down[component] = bool(down)

    def snapshot(self, *, now: Optional[datetime] = None) -> Dict[str, ComponentHealth]:
        now = now or utc_now()
        return {name: self._evaluate(name, now) for name in self.ttls}

    def paper_execution_readiness(self, *, now: Optional[datetime] = None) -> dict:
        states = self.snapshot(now=now)
        blockers = []
        for name in sorted(CRITICAL_FOR_PAPER):
            state = states[name]
            if state.status is not HealthStatus.HEALTHY:
                blockers.append({
                    "component": name,
                    "status": state.status.value,
                    "reason": state.reason,
                })
        return {
            "ready": not blockers,
            "mode": "PAPER_ONLY",
            "broker_connected": False,
            "live_execution": False,
            "blockers": blockers,
        }

    def browser_payload(self, *, now: Optional[datetime] = None) -> dict:
        states = self.snapshot(now=now)
        readiness = self.paper_execution_readiness(now=now)
        return {
            "components": {name: state.to_dict() for name, state in states.items()},
            "paper_execution_readiness": readiness,
            "safety": {
                "broker_connected": False,
                "live_execution": False,
                "automatic_threshold_mutation": False,
            },
        }

    def _evaluate(self, component: str, now: datetime) -> ComponentHealth:
        last_good = self._last_good.get(component)
        last_attempt = self._last_attempt.get(component)
        payload_valid = self._payload_valid.get(component, False)
        ttl = int(self.ttls[component])
        reason = self._reason.get(component, "awaiting first validated heartbeat")

        if self._explicit_down.get(component, False):
            status = HealthStatus.DOWN
            age = self._age(last_good, now)
        elif last_attempt is None:
            status = HealthStatus.STARTING
            age = None
        elif not payload_valid:
            status = HealthStatus.DEGRADED
            age = self._age(last_good, now)
        else:
            age = self._age(last_good, now)
            if age is None:
                status = HealthStatus.STARTING
                reason = "no successful validated heartbeat yet"
            elif age > ttl:
                status = HealthStatus.STALE
                reason = f"last valid payload is older than {ttl}s freshness limit"
            else:
                status = HealthStatus.HEALTHY

        return ComponentHealth(
            name=component,
            status=status,
            payload_valid=payload_valid,
            last_good_update=last_good,
            last_attempt_update=last_attempt,
            freshness_ttl_seconds=ttl,
            age_seconds=age,
            reason=reason,
        )

    @staticmethod
    def _age(value: Optional[datetime], now: datetime) -> Optional[float]:
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        return max(0.0, (now - value).total_seconds())

    def _require_component(self, component: str) -> None:
        if component not in self.ttls:
            raise KeyError(f"unknown IIOS heartbeat component: {component}")


def fail_closed_if_unready(registry: HeartbeatRegistry, *, now: Optional[datetime] = None) -> None:
    """Raise before governed paper execution when critical inputs are not healthy."""
    readiness = registry.paper_execution_readiness(now=now)
    if readiness["ready"]:
        return
    summary = ", ".join(
        f"{item['component']}={item['status']}" for item in readiness["blockers"]
    )
    raise RuntimeError(f"paper execution quarantined: {summary}")
