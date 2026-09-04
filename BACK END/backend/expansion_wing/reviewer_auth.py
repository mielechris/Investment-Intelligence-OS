from __future__ import annotations

import hashlib
import hmac
import json
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable

OWNER = "OWNER_ADMIN"
SPECIALIZED = {"RIGHTS_REVIEWER", "TRANSCRIPT_REVIEWER", "CLAIM_REVIEWER", "JUDGMENT_REVIEWER", "PATTERN_REVIEWER"}
ROLES = {OWNER, *SPECIALIZED}
GOVERNED_ACTIONS = ("RIGHTS", "TRANSCRIPT", "CLAIM", "JUDGMENT", "PATTERN")
ADMIN_ACTION = "ADMINISTER_REVIEWERS"
ACTIONS = (*GOVERNED_ACTIONS, ADMIN_ACTION)
ACTION_ROLE = {"RIGHTS": "RIGHTS_REVIEWER", "TRANSCRIPT": "TRANSCRIPT_REVIEWER",
    "CLAIM": "CLAIM_REVIEWER", "JUDGMENT": "JUDGMENT_REVIEWER", "PATTERN": "PATTERN_REVIEWER"}
FORBIDDEN_AUTHORITIES = frozenset({"LEDGER", "BROKER", "TRADING", "THRESHOLD", "PROVIDER", "SERVICE", "DEPLOYMENT"})
GENESIS_HASH = "0" * 64
_ADMIN_CAPABILITY = object()


@dataclass(frozen=True)
class Reviewer:
    reviewer_id: str
    roles: frozenset[str]
    active: bool = True


@dataclass(frozen=True)
class LocalOwnerCeremony:
    expected_local_identity: str
    presented_local_identity: str
    owner_storage_controlled: bool
    bootstrap_nonce: str
    expected_bootstrap_nonce: str
    browser_supplied: bool = False


class ReviewerRegistry:
    def __init__(self) -> None:
        self.reviewers: dict[str, Reviewer] = {}
        self._bootstrap_closed = False
        self._lock = threading.Lock()

    def bootstrap(self, ceremony: LocalOwnerCeremony, *, reviewer_id: str) -> Reviewer:
        with self._lock:
            if self._bootstrap_closed or self.reviewers: raise PermissionError("BOOTSTRAP_PERMANENTLY_CLOSED")
            if (ceremony.browser_supplied or not ceremony.owner_storage_controlled or
                    not ceremony.expected_local_identity or
                    not hmac.compare_digest(ceremony.expected_local_identity, ceremony.presented_local_identity) or
                    len(ceremony.bootstrap_nonce) < 32 or
                    not hmac.compare_digest(ceremony.bootstrap_nonce, ceremony.expected_bootstrap_nonce)):
                raise PermissionError("LOCAL_OWNER_CEREMONY_REQUIRED")
            if not reviewer_id or len(reviewer_id) > 128: raise ValueError("REVIEWER_ID_INVALID")
            owner = Reviewer(reviewer_id, frozenset({OWNER}))
            self.reviewers = {reviewer_id: owner}; self._bootstrap_closed = True
            return owner

    def _owner(self, actor_id: str) -> Reviewer:
        owners = [value for value in self.reviewers.values() if OWNER in value.roles]
        if len(owners) != 1: raise RuntimeError("REGISTRY_STATE_AMBIGUOUS")
        actor = self.reviewers.get(actor_id)
        if not actor or not actor.active or OWNER not in actor.roles: raise PermissionError("OWNER_ADMIN_REQUIRED")
        return actor

    def _validate_admin(self, actor_id: str, *, operation: str, reviewer_id: str,
                        roles: frozenset[str]) -> None:
        self._owner(actor_id)
        if reviewer_id == actor_id: raise PermissionError("SELF_PRIVILEGE_CHANGE_REJECTED")
        if operation not in {"ADD", "DISABLE", "CHANGE"}: raise ValueError("ADMIN_OPERATION_INVALID")
        if operation in {"ADD", "CHANGE"} and (not roles or not roles <= SPECIALIZED):
            raise PermissionError("PRIVILEGE_ESCALATION_REJECTED")
        current = self.reviewers.get(reviewer_id)
        if operation == "ADD":
            if current is not None: raise ValueError("REVIEWER_DUPLICATE")
        elif current is None: raise ValueError("REVIEWER_MISSING")

    def _administer(self, capability: object, actor_id: str, *, operation: str, reviewer_id: str,
                    roles: frozenset[str] = frozenset()) -> Reviewer:
        if capability is not _ADMIN_CAPABILITY: raise PermissionError("AUTHENTICATED_ADMINISTRATION_REQUIRED")
        self._validate_admin(actor_id, operation=operation, reviewer_id=reviewer_id, roles=roles)
        current = self.reviewers.get(reviewer_id)
        if operation == "ADD": result = Reviewer(reviewer_id, roles)
        elif operation == "DISABLE":
            result = Reviewer(reviewer_id, current.roles, False)
        else:
            result = Reviewer(reviewer_id, roles, current.active)
        self.reviewers[reviewer_id] = result
        return result

@dataclass
class Authenticator:
    secret: bytes
    clock: Callable[[], float] = time.time
    ttl_seconds: int = 900
    used_csrf: set[str] = field(default_factory=set)
    used_idempotency: set[str] = field(default_factory=set)
    requests: dict[str, list[float]] = field(default_factory=dict)
    audit_events: list[dict] = field(default_factory=list)

    def session(self, reviewer_id: str) -> str:
        payload = json.dumps({"reviewer_id": reviewer_id, "expires_at": int(self.clock()) + self.ttl_seconds},
            sort_keys=True, separators=(",", ":")).encode()
        return payload.hex() + "." + hmac.new(self.secret, payload, hashlib.sha256).hexdigest()

    def authenticate(self, token: str) -> str:
        try: raw, signature = token.split(".", 1); payload = bytes.fromhex(raw)
        except Exception: raise PermissionError("AUTHENTICATION_REQUIRED") from None
        if not hmac.compare_digest(signature, hmac.new(self.secret, payload, hashlib.sha256).hexdigest()):
            raise PermissionError("AUTHENTICATION_REQUIRED")
        try: value = json.loads(payload); reviewer_id = value["reviewer_id"]; expires_at = value["expires_at"]
        except Exception: raise PermissionError("AUTHENTICATION_REQUIRED") from None
        if self.clock() >= expires_at: raise PermissionError("SESSION_EXPIRED")
        return reviewer_id

    def authorize(self, registry: ReviewerRegistry, token: str, *, action: str, csrf: str,
                  idempotency_key: str, request_size: int, reason: str, timestamp: str,
                  previous_hash: str, audit_context: dict | None = None) -> dict:
        reviewer_id = self.authenticate(token)
        if request_size > 64_000: raise ValueError("REQUEST_SIZE_LIMIT")
        if len(csrf) < 32 or csrf in self.used_csrf: raise PermissionError("CSRF_OR_REPLAY_REJECTED")
        if len(idempotency_key) < 16: raise ValueError("IDEMPOTENCY_KEY_REQUIRED")
        if idempotency_key in self.used_idempotency: raise PermissionError("IDEMPOTENCY_REPLAY_REJECTED")
        reviewer = registry.reviewers.get(reviewer_id)
        if not reviewer or not reviewer.active: raise PermissionError("REVIEWER_INACTIVE_OR_UNKNOWN")
        allowed = action in ACTIONS and (OWNER in reviewer.roles or ACTION_ROLE.get(action) in reviewer.roles)
        if not allowed: raise PermissionError("ACTION_NOT_AUTHORIZED")
        if not reason.strip() or len(reason) > 1000: raise ValueError("AUDIT_REASON_REQUIRED")
        try: datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        except (AttributeError, ValueError): raise ValueError("AUDIT_TIMESTAMP_INVALID") from None
        expected_previous = self.audit_events[-1]["event_hash"] if self.audit_events else GENESIS_HASH
        if previous_hash != expected_previous: raise ValueError("AUDIT_CHAIN_INVALID")
        if action == ADMIN_ACTION:
            if (not isinstance(audit_context, dict) or set(audit_context) != {"operation", "reviewer_id", "roles"} or
                    audit_context["operation"] not in {"ADD", "DISABLE", "CHANGE"} or
                    not isinstance(audit_context["reviewer_id"], str) or
                    not isinstance(audit_context["roles"], list)):
                raise ValueError("ADMIN_AUDIT_CONTEXT_REQUIRED")
        elif audit_context is not None: raise ValueError("AUDIT_CONTEXT_NOT_ALLOWED")
        recent = [instant for instant in self.requests.get(reviewer_id, []) if self.clock() - instant < 60]
        if len(recent) >= 10: raise RuntimeError("RATE_LIMITED")
        body = {"reviewer_id": reviewer_id, "action": action, "reason": reason, "timestamp": timestamp,
            "previous_hash": previous_hash, "idempotency_key": idempotency_key, "knowledge_review_only": True}
        if audit_context is not None: body["administration"] = audit_context
        event_hash = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        event = {**body, "event_hash": event_hash}
        recent.append(self.clock()); self.requests[reviewer_id] = recent; self.used_csrf.add(csrf)
        self.used_idempotency.add(idempotency_key); self.audit_events.append(event)
        return event

    def administer_reviewers(self, registry: ReviewerRegistry, token: str, *, operation: str,
                             reviewer_id: str, roles: frozenset[str], csrf: str, idempotency_key: str,
                             reason: str, timestamp: str, previous_hash: str) -> tuple[Reviewer, dict]:
        actor_id = self.authenticate(token)
        registry._validate_admin(actor_id, operation=operation, reviewer_id=reviewer_id, roles=roles)
        event = self.authorize(registry, token, action=ADMIN_ACTION, csrf=csrf,
            idempotency_key=idempotency_key, request_size=256, reason=reason,
            timestamp=timestamp, previous_hash=previous_hash,
            audit_context={"operation": operation, "reviewer_id": reviewer_id, "roles": sorted(roles)})
        return registry._administer(_ADMIN_CAPABILITY, actor_id, operation=operation,
            reviewer_id=reviewer_id, roles=roles), event


def separated_duties(submitter: str, approver: str) -> None:
    if submitter == approver: raise PermissionError("SEPARATION_OF_DUTIES_REQUIRED")
