from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .models import AuthorityBoundary, Availability

ALLOWED_TOP_LEVEL = {
    "service_health", "last_cycle", "radar", "cases", "committee", "risk", "books",
    "benchmark_9h", "shadow_9i", "outcomes_9j", "resources", "queue",
}
FORBIDDEN_KEYS = {"credential", "credentials", "secret", "token", "password", "api_key", "raw_log", "raw_logs"}


def _forbidden_key(key: Any) -> bool:
    normalized = str(key).lower().replace("-", "_")
    return normalized in FORBIDDEN_KEYS or any(marker in normalized for marker in ("credential", "password", "secret", "token", "api_key", "raw_log"))


def _sanitize(value: Any, depth: int = 0) -> Any:
    if depth >= 8:
        return "[DEPTH_LIMIT]"
    if isinstance(value, dict):
        return {key: _sanitize(item, depth + 1) for key, item in list(value.items())[:200] if not _forbidden_key(key)}
    if isinstance(value, list):
        return [_sanitize(item, depth + 1) for item in value[:100]]
    if isinstance(value, str):
        return value[:2000]
    return value


def state_for(*, present: bool, observed_at: str | None = None, complete: bool = True,
              stale_after_seconds: int = 900, now: datetime | None = None) -> Availability:
    if not present: return Availability.UNAVAILABLE
    if not complete: return Availability.INCOMPLETE
    if not observed_at: return Availability.UNKNOWN
    try:
        timestamp = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return Availability.UNKNOWN
    current = now or datetime.now(timezone.utc)
    if timestamp.tzinfo is None: timestamp = timestamp.replace(tzinfo=timezone.utc)
    return Availability.STALE if (current - timestamp).total_seconds() > stale_after_seconds else Availability.CURRENT


def build_living_wall_projection(sources: dict[str, Any], *, now: datetime | None = None) -> dict[str, Any]:
    sections: dict[str, Any] = {}
    for key in ALLOWED_TOP_LEVEL:
        source = sources.get(key)
        if not isinstance(source, dict):
            sections[key] = {"state": Availability.UNAVAILABLE, "data": None}
            continue
        state = state_for(present=True, observed_at=source.get("observed_at"),
                          complete=bool(source.get("complete", True)),
                          stale_after_seconds=int(source.get("stale_after_seconds", 900)), now=now)
        sections[key] = {"state": state, "data": _sanitize(source.get("data"))}
    return {"schema_version": "expansion-wing-truth-v1", "sections": sections,
            "authority": AuthorityBoundary().__dict__, "fabricated_activity": False}
