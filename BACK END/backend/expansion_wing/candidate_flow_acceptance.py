from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from .candidate_enrichment_bridge import (
    AUTHORITY, BridgePolicy, CandidateEnrichmentBridge, CandidateEvidence, ScannerCandidate, SCANNER_ID,
)

SCHEMA_VERSION = "iios-candidate-flow-acceptance-v1"
CHECKPOINT_SCHEMA = "iios-provider-credit-checkpoint-v1"
FIXTURE_BATCH_SCHEMA = "iios-sanitized-scanner-batch-v1"


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def _time(value: str) -> datetime:
    try: parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError): raise ValueError("TIME_INVALID") from None
    if parsed.tzinfo is None: raise ValueError("TIME_INVALID")
    return parsed


@dataclass(frozen=True)
class CreditCheckpoint:
    confirmed: int
    ambiguous: int
    ceiling: int
    last_batch_id: str | None
    previous_event_hash: str
    event_hash: str

    @property
    def consumed(self) -> int: return self.confirmed + self.ambiguous

    def validate(self) -> None:
        if (not 0 <= self.confirmed <= self.ceiling or not 0 <= self.ambiguous <= self.ceiling or
                self.consumed > self.ceiling or self.ceiling != 1_000 or
                (self.last_batch_id is not None and not re.fullmatch(r"batch_[0-9a-f]{16}", self.last_batch_id)) or
                not re.fullmatch(r"[0-9a-f]{64}", self.previous_event_hash) or
                not re.fullmatch(r"[0-9a-f]{64}", self.event_hash)):
            raise ValueError("CREDIT_CHECKPOINT_INVALID")
        event = {"confirmed": self.confirmed, "ambiguous": self.ambiguous, "ceiling": self.ceiling,
            "last_batch_id": self.last_batch_id, "previous_event_hash": self.previous_event_hash}
        if hashlib.sha256(_canonical(event)).hexdigest() != self.event_hash:
            raise ValueError("CREDIT_CHECKPOINT_INVALID")

    def serialize(self) -> bytes:
        self.validate()
        return _canonical({"schema_version": CHECKPOINT_SCHEMA, **asdict(self)})

    @classmethod
    def parse(cls, encoded: bytes) -> "CreditCheckpoint":
        try: value = json.loads(encoded)
        except (UnicodeDecodeError, json.JSONDecodeError): raise ValueError("CREDIT_CHECKPOINT_INVALID") from None
        fields = {"schema_version", "confirmed", "ambiguous", "ceiling", "last_batch_id",
            "previous_event_hash", "event_hash"}
        if not isinstance(value, dict) or set(value) != fields or value.pop("schema_version") != CHECKPOINT_SCHEMA:
            raise ValueError("CREDIT_CHECKPOINT_INVALID")
        checkpoint = cls(**value); checkpoint.validate(); return checkpoint


def next_checkpoint(previous: CreditCheckpoint, *, confirmed: int, ambiguous: int,
                    batch_id: str) -> CreditCheckpoint:
    event = {"confirmed": confirmed, "ambiguous": ambiguous, "ceiling": previous.ceiling,
        "last_batch_id": batch_id, "previous_event_hash": previous.event_hash}
    digest = hashlib.sha256(_canonical(event)).hexdigest()
    result = CreditCheckpoint(confirmed, ambiguous, previous.ceiling, batch_id, previous.event_hash, digest)
    result.validate(); return result


def genesis_checkpoint(*, confirmed: int = 3, ambiguous: int = 2) -> CreditCheckpoint:
    previous = "0" * 64
    event = {"confirmed": confirmed, "ambiguous": ambiguous, "ceiling": 1_000,
        "last_batch_id": None, "previous_event_hash": previous}
    result = CreditCheckpoint(confirmed, ambiguous, 1_000, None, previous,
        hashlib.sha256(_canonical(event)).hexdigest())
    result.validate(); return result


class CreditCheckpointStore:
    def __init__(self, root: Path, *, expected_uid: int | None = None) -> None:
        self.root = root; self.path = root / "financial-datasets-credit.json"
        self.expected_uid = os.getuid() if expected_uid is None else expected_uid

    def _safe(self, path: Path, mode: int) -> bool:
        try: info = path.lstat()
        except OSError: return False
        return (not stat.S_ISLNK(info.st_mode) and stat.S_IMODE(info.st_mode) == mode and
            info.st_uid == self.expected_uid)

    def load(self) -> CreditCheckpoint:
        if not self._safe(self.root, 0o700) or not self._safe(self.path, 0o600):
            raise RuntimeError("CREDIT_CHECKPOINT_UNAVAILABLE")
        try:
            if self.path.stat().st_size > 2_000: raise RuntimeError
            return CreditCheckpoint.parse(self.path.read_bytes())
        except (OSError, ValueError, RuntimeError):
            raise RuntimeError("CREDIT_CHECKPOINT_UNAVAILABLE") from None

    def save(self, checkpoint: CreditCheckpoint, *, expected_previous_hash: str) -> None:
        checkpoint.validate()
        current = self.load()
        if current.event_hash != expected_previous_hash or checkpoint.previous_event_hash != expected_previous_hash:
            raise RuntimeError("CREDIT_CHECKPOINT_CONFLICT")
        self._write(checkpoint)

    def initialize(self, checkpoint: CreditCheckpoint) -> None:
        checkpoint.validate()
        if not self._safe(self.root, 0o700) or self.path.exists():
            raise RuntimeError("CREDIT_CHECKPOINT_CONFLICT")
        self._write(checkpoint)

    def _write(self, checkpoint: CreditCheckpoint) -> None:
        descriptor, name = tempfile.mkstemp(prefix=".credit-", dir=self.root)
        temporary = Path(name)
        try:
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(checkpoint.serialize()); stream.flush(); os.fsync(stream.fileno())
            os.replace(temporary, self.path)
            directory = os.open(self.root, os.O_RDONLY)
            try: os.fsync(directory)
            finally: os.close(directory)
        finally:
            try: temporary.unlink()
            except FileNotFoundError: pass


@dataclass(frozen=True)
class ReviewQueueItem:
    candidate_id: str
    ticker: str
    normalized_hash: str
    status: str = "PRIMARY_SOURCE_REVIEW_REQUIRED"


@dataclass(frozen=True)
class AcceptanceResult:
    state: str
    batch_id: str | None
    review_items: tuple[ReviewQueueItem, ...]
    candidate_count: int
    unique_ticker_count: int
    provider_request_count: int
    cache_hit_count: int
    starting_credits: int
    ending_credits: int
    failure_category: str | None

    def browser_safe(self) -> dict[str, Any]:
        return {"schema_version": SCHEMA_VERSION, "state": self.state,
            "candidate_count": self.candidate_count, "unique_ticker_count": self.unique_ticker_count,
            "provider_request_count": self.provider_request_count, "cache_hit_count": self.cache_hit_count,
            "starting_credits": self.starting_credits, "ending_credits": self.ending_credits,
            "new_credits": self.ending_credits - self.starting_credits,
            "primary_review_queue_count": len(self.review_items), "failure_category": self.failure_category,
            "scheduled": False, "provider_enabled": False, "authority": AUTHORITY.copy()}


def parse_sanitized_batch(value: dict[str, Any]) -> tuple[str, tuple[ScannerCandidate, ...]]:
    if (not isinstance(value, dict) or set(value) != {"schema_version", "batch_id", "generated_at",
            "originating_scanner", "candidates"} or value.get("schema_version") != FIXTURE_BATCH_SCHEMA or
            value.get("originating_scanner") != SCANNER_ID or
            not re.fullmatch(r"batch_[0-9a-f]{16}", str(value.get("batch_id")))):
        raise ValueError("SCANNER_BATCH_INVALID")
    generated = _time(value["generated_at"])
    rows = value.get("candidates")
    if not isinstance(rows, list) or not 1 <= len(rows) <= 5: raise ValueError("SCANNER_BATCH_INVALID")
    candidates = []
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"candidate_id", "ticker", "discovered_at", "missing_fields"}:
            raise ValueError("SCANNER_BATCH_INVALID")
        candidate = ScannerCandidate(row["candidate_id"], row["ticker"], row["discovered_at"],
            SCANNER_ID, tuple(row["missing_fields"]) if isinstance(row["missing_fields"], list) else ())
        candidate.validate()
        if _time(candidate.discovered_at) > generated: raise ValueError("SCANNER_BATCH_INVALID")
        candidates.append(candidate)
    return value["batch_id"], tuple(candidates)


class CandidateFlowAcceptance:
    def __init__(self, bridge: CandidateEnrichmentBridge, store: CreditCheckpointStore,
                 *, enabled: bool = False, fixture_only: bool = True,
                 clock: Callable[[], datetime] | None = None) -> None:
        self.bridge = bridge; self.store = store; self.enabled = enabled; self.fixture_only = fixture_only
        self.clock = clock or datetime.now

    def run(self, payload: dict[str, Any], *, explicitly_authorized: bool = False) -> AcceptanceResult:
        if not self.enabled or not self.fixture_only or not explicitly_authorized:
            return AcceptanceResult("NOT_ACTIVATED", None, (), 0, 0, 0, 0, 0, 0, "AUTHORIZATION_REQUIRED")
        try: batch_id, candidates = parse_sanitized_batch(payload)
        except (ValueError, TypeError):
            return AcceptanceResult("REJECTED", None, (), 0, 0, 0, 0, 0, 0, "SCANNER_BATCH_INVALID")
        try: checkpoint = self.store.load()
        except RuntimeError as exc:
            return AcceptanceResult("REJECTED", batch_id, (), len(candidates), len({x.ticker for x in candidates}),
                0, 0, 0, 0, str(exc))
        if checkpoint.last_batch_id == batch_id:
            return AcceptanceResult("REPLAY_REJECTED", batch_id, (), len(candidates),
                len({x.ticker for x in candidates}), 0, 0, checkpoint.consumed, checkpoint.consumed, "BATCH_REPLAY")
        snapshot = self.bridge.provider.credits.snapshot()
        if snapshot["confirmed"] != checkpoint.confirmed or snapshot["ambiguous"] != checkpoint.ambiguous:
            return AcceptanceResult("REJECTED", batch_id, (), len(candidates), len({x.ticker for x in candidates}),
                0, 0, checkpoint.consumed, checkpoint.consumed, "CREDIT_CHECKPOINT_MISMATCH")
        bridge_result = self.bridge.run(candidates, explicitly_authorized=True)
        final = self.bridge.provider.credits.snapshot()
        updated = next_checkpoint(checkpoint, confirmed=final["confirmed"], ambiguous=final["ambiguous"],
            batch_id=batch_id)
        try: self.store.save(updated, expected_previous_hash=checkpoint.event_hash)
        except RuntimeError as exc:
            return AcceptanceResult("STOPPED_FAIL_CLOSED", batch_id, (), len(candidates),
                len({x.ticker for x in candidates}), bridge_result.provider_request_count,
                bridge_result.cache_hit_count, checkpoint.consumed, final["consumed"], str(exc))
        items = tuple(ReviewQueueItem(item.candidate_id, item.ticker, item.normalized_hash)
            for item in bridge_result.evidence) if bridge_result.state == "READY_FOR_PRIMARY_REVIEW" else ()
        return AcceptanceResult("COMPLETE" if items else "STOPPED_FAIL_CLOSED", batch_id, items,
            len(candidates), len({x.ticker for x in candidates}), bridge_result.provider_request_count,
            bridge_result.cache_hit_count, checkpoint.consumed, final["consumed"], bridge_result.failure_category)
