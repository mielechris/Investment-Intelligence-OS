from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass, field
from typing import Callable

ROLES = {"OWNER_ADMIN", "RIGHTS_REVIEWER", "TRANSCRIPT_REVIEWER", "CLAIM_REVIEWER", "JUDGMENT_REVIEWER", "PATTERN_REVIEWER"}
ACTION_ROLE = {"RIGHTS": "RIGHTS_REVIEWER", "TRANSCRIPT": "TRANSCRIPT_REVIEWER", "CLAIM": "CLAIM_REVIEWER",
    "JUDGMENT": "JUDGMENT_REVIEWER", "PATTERN": "PATTERN_REVIEWER"}


@dataclass(frozen=True)
class Reviewer:
    reviewer_id: str
    roles: frozenset[str]


class ReviewerRegistry:
    def __init__(self, owner_id: str) -> None:
        self.reviewers = {owner_id: Reviewer(owner_id, frozenset({"OWNER_ADMIN"}))}
    def add(self, actor_id: str, reviewer: Reviewer) -> None:
        actor = self.reviewers.get(actor_id)
        if not actor or "OWNER_ADMIN" not in actor.roles or not reviewer.roles <= ROLES: raise PermissionError("OWNER_ADMIN_REQUIRED")
        if reviewer.reviewer_id in self.reviewers: raise ValueError("REVIEWER_DUPLICATE")
        self.reviewers[reviewer.reviewer_id] = reviewer


@dataclass
class Authenticator:
    secret: bytes
    clock: Callable[[], float] = time.time
    ttl_seconds: int = 900
    used_csrf: set[str] = field(default_factory=set)
    used_idempotency: set[str] = field(default_factory=set)
    requests: dict[str, list[float]] = field(default_factory=dict)

    def session(self, reviewer_id: str) -> str:
        payload = json.dumps({"reviewer_id": reviewer_id, "expires_at": int(self.clock()) + self.ttl_seconds},
            sort_keys=True, separators=(",", ":")).encode()
        return payload.hex() + "." + hmac.new(self.secret, payload, hashlib.sha256).hexdigest()

    def authenticate(self, token: str) -> str:
        try: raw, signature = token.split(".", 1); payload = bytes.fromhex(raw)
        except Exception: raise PermissionError("AUTHENTICATION_REQUIRED") from None
        if not hmac.compare_digest(signature, hmac.new(self.secret, payload, hashlib.sha256).hexdigest()):
            raise PermissionError("AUTHENTICATION_REQUIRED")
        value = json.loads(payload)
        if self.clock() >= value["expires_at"]: raise PermissionError("SESSION_EXPIRED")
        return value["reviewer_id"]

    def authorize(self, registry: ReviewerRegistry, token: str, *, action: str, csrf: str,
                  idempotency_key: str, request_size: int) -> str:
        reviewer_id = self.authenticate(token)
        if request_size > 64_000: raise ValueError("REQUEST_SIZE_LIMIT")
        if len(csrf) < 32 or csrf in self.used_csrf: raise PermissionError("CSRF_OR_REPLAY_REJECTED")
        if len(idempotency_key) < 16: raise ValueError("IDEMPOTENCY_KEY_REQUIRED")
        if idempotency_key in self.used_idempotency: raise PermissionError("IDEMPOTENCY_REPLAY_REJECTED")
        reviewer = registry.reviewers.get(reviewer_id); needed = ACTION_ROLE.get(action)
        if not reviewer or not needed or needed not in reviewer.roles: raise PermissionError("ACTION_NOT_AUTHORIZED")
        recent = [instant for instant in self.requests.get(reviewer_id, []) if self.clock() - instant < 60]
        if len(recent) >= 10: raise RuntimeError("RATE_LIMITED")
        recent.append(self.clock()); self.requests[reviewer_id] = recent; self.used_csrf.add(csrf)
        self.used_idempotency.add(idempotency_key)
        return reviewer_id


def separated_duties(submitter: str, approver: str) -> None:
    if submitter == approver: raise PermissionError("SEPARATION_OF_DUTIES_REQUIRED")
