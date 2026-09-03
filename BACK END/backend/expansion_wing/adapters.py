from __future__ import annotations

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .models import Availability

MAX_BYTES = 2_000_000


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_time(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.replace(tzinfo=parsed.tzinfo or timezone.utc).astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def _safe_error(exc: BaseException) -> str:
    return type(exc).__name__[:80]


@dataclass(frozen=True)
class AdapterResult:
    adapter: str
    state: Availability
    provenance: dict[str, Any]
    observed_at: str | None
    content_hash: str | None
    data: Any
    error: str | None = None
    duplicate: bool = False
    fixture: bool = False

    def to_source(self) -> dict[str, Any]:
        return {"observed_at": self.observed_at, "complete": self.state not in {Availability.INCOMPLETE, Availability.UNAVAILABLE},
                "data": self.data, "adapter_state": self.state, "provenance": self.provenance,
                "content_hash": self.content_hash, "duplicate": self.duplicate, "fixture": self.fixture,
                "error": self.error}


class ReadOnlyAdapter:
    def __init__(self, name: str, source_type: str, *, stale_after_seconds: int = 900,
                 timeout_seconds: float = 2.0, fixture: bool = False) -> None:
        self.name = name
        self.source_type = source_type
        self.stale_after_seconds = max(1, stale_after_seconds)
        self.timeout_seconds = max(0.01, min(timeout_seconds, 30.0))
        self.fixture = fixture
        self._hashes: set[str] = set()

    def normalize(self, payload: Any, provenance: dict[str, Any]) -> AdapterResult:
        encoded = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":")).encode()
        digest = hashlib.sha256(encoded).hexdigest()
        duplicate = digest in self._hashes
        self._hashes.add(digest)
        observed_at = payload.get("observed_at") if isinstance(payload, dict) else None
        parsed = _parse_time(observed_at)
        if parsed is None:
            state = Availability.UNKNOWN
        elif (_now() - parsed).total_seconds() > self.stale_after_seconds:
            state = Availability.STALE
        elif isinstance(payload, dict) and payload.get("complete") is False:
            state = Availability.INCOMPLETE
        else:
            state = Availability.CURRENT
        return AdapterResult(self.name, state, provenance, str(observed_at) if observed_at else None,
                             digest, payload, duplicate=duplicate, fixture=self.fixture)

    def unavailable(self, provenance: dict[str, Any], exc: BaseException | None = None) -> AdapterResult:
        return AdapterResult(self.name, Availability.UNAVAILABLE, provenance, None, None, None,
                             _safe_error(exc) if exc else "SOURCE_UNAVAILABLE", fixture=self.fixture)


class JsonArtifactAdapter(ReadOnlyAdapter):
    def read(self, path: str | Path | None) -> AdapterResult:
        provenance = {"adapter": self.name, "source_type": self.source_type,
                      "source": "FIXTURE_FILE" if self.fixture else "SANITIZED_ARTIFACT", "read_only": True}
        if not path:
            return self.unavailable(provenance)
        target = Path(path)
        try:
            if not target.is_file() or target.stat().st_size > MAX_BYTES:
                return self.unavailable(provenance)
            return self.normalize(json.loads(target.read_text(encoding="utf-8")), provenance)
        except (OSError, json.JSONDecodeError) as exc:
            return self.unavailable(provenance, exc)


class CallbackAdapter(ReadOnlyAdapter):
    """Bounded read interface for a future free/public provider; no provider is configured here."""

    def read(self, fetch: Callable[[], Any] | None) -> AdapterResult:
        provenance = {"adapter": self.name, "source_type": self.source_type,
                      "source": "FIXTURE_CALLBACK" if self.fixture else "UNCONFIGURED_PUBLIC_SOURCE", "read_only": True}
        if fetch is None:
            return self.unavailable(provenance)
        pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix=f"adapter-{self.name}")
        future = pool.submit(fetch)
        try:
            return self.normalize(future.result(timeout=self.timeout_seconds), provenance)
        except FutureTimeout as exc:
            future.cancel()
            return self.unavailable(provenance, exc)
        except Exception as exc:  # adapter boundary intentionally sanitizes provider failures
            return self.unavailable(provenance, exc)
        finally:
            pool.shutdown(wait=False, cancel_futures=True)


def adapter_registry(*, fixture: bool = False) -> dict[str, ReadOnlyAdapter]:
    artifact = {
        key: JsonArtifactAdapter(key, f"IIOS_{key.upper()}_SANITIZED_ARTIFACT", fixture=fixture)
        for key in ("9a", "9b", "9e", "9h", "9i", "9j", "paper_fund")
    }
    public = {
        "equity_etf": CallbackAdapter("equity_etf", "PUBLIC_MARKET_EVIDENCE", stale_after_seconds=300, fixture=fixture),
        "treasury_bond": CallbackAdapter("treasury_bond", "PUBLIC_FIXED_INCOME_EVIDENCE", stale_after_seconds=3600, fixture=fixture),
        "ipo_listing": CallbackAdapter("ipo_listing", "PUBLIC_LISTING_EVIDENCE", stale_after_seconds=3600, fixture=fixture),
        "commodity_future": CallbackAdapter("commodity_future", "PUBLIC_DERIVATIVE_EVIDENCE", stale_after_seconds=300, fixture=fixture),
        "investor_intelligence": CallbackAdapter("investor_intelligence", "PUBLIC_ATTRIBUTABLE_SOURCE", stale_after_seconds=86400, fixture=fixture),
        "interview_upload": CallbackAdapter("interview_upload", "USER_UPLOADED_MEDIA_METADATA", stale_after_seconds=86400, fixture=fixture),
    }
    return artifact | public
