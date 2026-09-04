from __future__ import annotations

import json
import os
import stat
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .candidate_flow_acceptance import CandidateFlowAcceptance
from .post_close_candidate_pipeline import (
    AUTHORITY,
    ClosingSessionEvidence,
    PrimarySourceAttestation,
    finalize_post_close,
)

SCHEMA_VERSION = "iios-post-close-operations-v1"
MAX_MANIFEST_BYTES = 4_096


@dataclass(frozen=True)
class PostCloseProjection:
    state: str
    session_date: str | None
    candidate_count: int
    provider_request_count: int
    new_credits: int
    primary_review_queue_count: int
    verified_candidate_count: int
    governed_case_draft_count: int
    failure_category: str | None
    automatic_schedule: bool = False
    authority_granted: bool = False

    def validate(self) -> None:
        states = {"NOT_ACTIVATED", "WAITING_FOR_CLOSE", "AWAITING_PRIMARY_SOURCES",
                  "READY_FOR_GOVERNED_CASE_DRAFT", "STOPPED_FAIL_CLOSED"}
        counts = (self.candidate_count, self.provider_request_count, self.new_credits,
                  self.primary_review_queue_count, self.verified_candidate_count,
                  self.governed_case_draft_count)
        if (self.state not in states or any(not isinstance(value, int) or isinstance(value, bool)
            or value < 0 or value > 5 for value in counts) or self.automatic_schedule is not False
            or self.authority_granted is not False):
            raise ValueError("POST_CLOSE_PROJECTION_INVALID")

    def browser_safe(self) -> dict[str, Any]:
        self.validate()
        return {"schema_version": SCHEMA_VERSION, **asdict(self), "authority": AUTHORITY.copy()}


class ProjectionStore:
    def __init__(self, root: Path, *, expected_uid: int | None = None) -> None:
        self.root = root
        self.path = root / "post-close-projection.json"
        self.expected_uid = os.getuid() if expected_uid is None else expected_uid

    def _safe(self, path: Path, mode: int) -> bool:
        try: info = path.lstat()
        except OSError: return False
        return (not stat.S_ISLNK(info.st_mode) and stat.S_IMODE(info.st_mode) == mode
                and info.st_uid == self.expected_uid)

    def write(self, projection: PostCloseProjection) -> None:
        encoded = json.dumps(projection.browser_safe(), sort_keys=True, separators=(",", ":")).encode("ascii")
        if not self._safe(self.root, 0o700) or len(encoded) > MAX_MANIFEST_BYTES:
            raise RuntimeError("POST_CLOSE_STORE_UNAVAILABLE")
        descriptor, name = tempfile.mkstemp(prefix=".post-close-", dir=self.root)
        temporary = Path(name)
        try:
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(encoded); stream.flush(); os.fsync(stream.fileno())
            os.replace(temporary, self.path)
            directory = os.open(self.root, os.O_RDONLY)
            try: os.fsync(directory)
            finally: os.close(directory)
        finally:
            try: temporary.unlink()
            except FileNotFoundError: pass

    def read(self) -> dict[str, Any]:
        if not self._safe(self.root, 0o700) or not self._safe(self.path, 0o600):
            raise RuntimeError("POST_CLOSE_STORE_UNAVAILABLE")
        try:
            if self.path.stat().st_size > MAX_MANIFEST_BYTES: raise ValueError
            value = json.loads(self.path.read_bytes())
        except (OSError, ValueError, json.JSONDecodeError):
            raise RuntimeError("POST_CLOSE_STORE_UNAVAILABLE") from None
        expected = {"schema_version", *PostCloseProjection.__dataclass_fields__, "authority"}
        if not isinstance(value, dict) or set(value) != expected or value.pop("schema_version") != SCHEMA_VERSION:
            raise RuntimeError("POST_CLOSE_STORE_UNAVAILABLE")
        if value.pop("authority") != AUTHORITY:
            raise RuntimeError("POST_CLOSE_STORE_UNAVAILABLE")
        try: PostCloseProjection(**value).validate()
        except (TypeError, ValueError): raise RuntimeError("POST_CLOSE_STORE_UNAVAILABLE") from None
        return {"schema_version": SCHEMA_VERSION, **value, "authority": AUTHORITY.copy()}


class PostCloseController:
    def __init__(self, acceptance: CandidateFlowAcceptance, store: ProjectionStore,
                 *, enabled: bool = False) -> None:
        self.acceptance = acceptance; self.store = store; self.enabled = enabled

    def run(self, closing: ClosingSessionEvidence, scanner_payload: dict[str, Any],
            attestations: tuple[PrimarySourceAttestation, ...] = (), *,
            explicitly_authorized: bool = False) -> PostCloseProjection:
        if not self.enabled or not explicitly_authorized:
            result = PostCloseProjection("NOT_ACTIVATED", None, 0, 0, 0, 0, 0, 0,
                                         "AUTHORIZATION_REQUIRED")
            return result
        try: closing.validate()
        except ValueError:
            result = PostCloseProjection("WAITING_FOR_CLOSE", closing.session_date, 0, 0, 0, 0, 0, 0,
                                         "CLOSING_SESSION_INCOMPLETE")
            self.store.write(result); return result
        accepted = self.acceptance.run(scanner_payload, explicitly_authorized=True)
        finalized = finalize_post_close(closing, accepted, attestations, explicitly_authorized=True)
        projection = PostCloseProjection(
            finalized.state, finalized.session_date, accepted.candidate_count,
            accepted.provider_request_count, accepted.ending_credits - accepted.starting_credits,
            len(accepted.review_items), finalized.verified_candidate_count,
            finalized.governed_case_count, finalized.failure_category)
        self.store.write(projection)
        return projection


def read_browser_projection(store: ProjectionStore) -> dict[str, Any]:
    return store.read()
