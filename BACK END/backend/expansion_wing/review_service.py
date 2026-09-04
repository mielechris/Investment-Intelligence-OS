from __future__ import annotations

ALLOWED_ACTIONS = {"RIGHTS", "TRANSCRIPT", "CLAIM", "JUDGMENT", "PATTERN"}
REQUIRED_FIELDS = {"action", "case_id", "decision", "reason", "csrf", "idempotency_key"}


class ReviewServiceContract:
    def __init__(self, *, enabled: bool = False, authentication_ready: bool = False,
                 operational_security_ready: bool = False) -> None:
        self.enabled = enabled; self.authentication_ready = authentication_ready
        self.operational_security_ready = operational_security_ready

    def startup(self, host: str) -> str:
        if not self.enabled: raise RuntimeError("REVIEW_SERVICE_DISABLED")
        if host != "127.0.0.1": raise RuntimeError("LOOPBACK_REQUIRED")
        if not self.authentication_ready or not self.operational_security_ready:
            raise RuntimeError("SECURITY_READINESS_REQUIRED")
        return "READY_FOR_REVIEW"

    def validate_request(self, method: str, body: dict) -> dict:
        if method != "POST": return {"status": 405, "error": "METHOD_NOT_ALLOWED"}
        if set(body) != REQUIRED_FIELDS or body.get("action") not in ALLOWED_ACTIONS or body.get("decision") not in {"APPROVED", "REJECTED"}:
            return {"status": 400, "error": "INVALID_REQUEST"}
        return {"status": 202, "error": None, "offline_contract_only": True}

    def routes(self) -> tuple[str, ...]:
        return ("/review/decision",)
