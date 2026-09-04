from __future__ import annotations

import socket
from dataclasses import dataclass

from .reviewer_auth import Authenticator, ReviewerRegistry

ROUTES = {"/review/rights": "RIGHTS", "/review/transcript": "TRANSCRIPT", "/review/claim": "CLAIM",
    "/review/contradiction": "CLAIM", "/review/judgment": "JUDGMENT", "/review/pattern": "PATTERN"}
FORBIDDEN_ROUTE_MARKERS = {"ledger", "broker", "trade", "threshold", "provider", "credential", "service", "deploy"}
MAX_BODY_BYTES = 64_000


@dataclass(frozen=True)
class ReviewPortalConfig:
    enabled: bool = False
    host: str = "127.0.0.1"
    port: int = 0

    def validate(self) -> None:
        if self.host != "127.0.0.1" or not 1024 <= self.port <= 65535 or self.port == 5177:
            raise ValueError("REVIEW_PORTAL_BIND_INVALID")


def port_available(port: int) -> bool:
    if not 1024 <= port <= 65535 or port == 5177: return False
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try: probe.bind(("127.0.0.1", port)); return True
    except OSError: return False
    finally: probe.close()


class ReviewPortalContract:
    def __init__(self, config: ReviewPortalConfig, registry: ReviewerRegistry, authenticator: Authenticator) -> None:
        config.validate(); self.config = config; self.registry = registry; self.authenticator = authenticator
        if any(marker in route for route in ROUTES for marker in FORBIDDEN_ROUTE_MARKERS):
            raise RuntimeError("FORBIDDEN_REVIEW_ROUTE")

    def dispatch(self, method: str, route: str, body: dict, *, encoded_size: int) -> dict:
        if not self.config.enabled: return {"status": 503, "error": "REVIEW_PORTAL_DISABLED"}
        if method != "POST": return {"status": 405, "error": "METHOD_NOT_ALLOWED"}
        if route not in ROUTES: return {"status": 404, "error": "ROUTE_NOT_FOUND"}
        required = {"session", "csrf", "idempotency_key", "reason", "timestamp", "previous_hash"}
        if encoded_size < 0 or encoded_size > MAX_BODY_BYTES or set(body) != required:
            return {"status": 400, "error": "INVALID_REQUEST"}
        try:
            event = self.authenticator.authorize(self.registry, body["session"], action=ROUTES[route],
                csrf=body["csrf"], idempotency_key=body["idempotency_key"], request_size=encoded_size,
                reason=body["reason"], timestamp=body["timestamp"], previous_hash=body["previous_hash"])
        except (PermissionError, RuntimeError, ValueError) as error:
            categories = {"SESSION_EXPIRED", "CSRF_OR_REPLAY_REJECTED", "IDEMPOTENCY_REPLAY_REJECTED", "RATE_LIMITED"}
            category = str(error) if str(error) in categories else "REVIEW_REQUEST_REJECTED"
            return {"status": 403, "error": category}
        return {"status": 202, "error": None, "event_hash": event["event_hash"], "knowledge_review_only": True}
