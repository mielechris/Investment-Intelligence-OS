from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from email.message import Message
from typing import Callable
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

DEFAULT_USER_AGENT = "IIOS-Expansion-Wing/1.0 research-contact: owner-review-required"


@dataclass(frozen=True)
class AcquisitionPolicy:
    allowed_domains: frozenset[str]
    max_redirects: int = 2
    timeout_seconds: float = 10.0
    max_response_bytes: int = 4_000_000
    minimum_interval_seconds: float = 1.0
    max_retries: int = 1
    user_agent: str = DEFAULT_USER_AGENT
    rights_approved: bool = False
    access_policy_approved: bool = False

    def validate(self) -> None:
        if not self.allowed_domains or any(not domain or "/" in domain for domain in self.allowed_domains):
            raise ValueError("DOMAIN_ALLOWLIST_REQUIRED")
        if not self.user_agent.strip() or "contact" not in self.user_agent.casefold():
            raise ValueError("DESCRIPTIVE_USER_AGENT_REQUIRED")
        if not (0 <= self.max_redirects <= 3 and 0 < self.timeout_seconds <= 30 and
                0 < self.max_response_bytes <= 10_000_000 and self.minimum_interval_seconds >= 0 and
                0 <= self.max_retries <= 2):
            raise ValueError("ACQUISITION_LIMIT_INVALID")
        if not self.rights_approved: raise PermissionError("RIGHTS_APPROVAL_REQUIRED")
        if not self.access_policy_approved: raise PermissionError("ACCESS_POLICY_APPROVAL_REQUIRED")


@dataclass(frozen=True)
class TransportResponse:
    status: int
    final_url: str
    redirect_urls: tuple[str, ...]
    headers: Message | dict[str, str]
    body: bytes


class _SafeRedirect(HTTPRedirectHandler):
    def __init__(self, policy: AcquisitionPolicy) -> None:
        self.policy = policy; self.targets: list[str] = []

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        parsed = urlparse(newurl)
        if (len(self.targets) >= self.policy.max_redirects or parsed.scheme != "https" or
                parsed.hostname not in self.policy.allowed_domains):
            raise RuntimeError("UNSAFE_REDIRECT_REJECTED")
        self.targets.append(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def bounded_urllib_transport(policy: AcquisitionPolicy):
    """Create an explicit, unscheduled transport; calling it is a separately authorized network action."""
    def transport(url: str, headers: dict[str, str], timeout: float, retries: int) -> TransportResponse:
        last_category = "SOURCE_UNAVAILABLE"
        for _attempt in range(retries + 1):
            redirects = _SafeRedirect(policy); opener = build_opener(redirects)
            try:
                with opener.open(Request(url, headers=headers, method="GET"), timeout=timeout) as response:
                    body = response.read(policy.max_response_bytes + 1)
                    return TransportResponse(response.status, response.geturl(), tuple(redirects.targets),
                        response.headers, body)
            except RuntimeError: raise
            except Exception: last_category = "SOURCE_UNAVAILABLE"
        raise RuntimeError(last_category)
    return transport


class OfficialSourceAcquirer:
    def __init__(self, policy: AcquisitionPolicy, *, clock: Callable[[], float] = time.monotonic) -> None:
        policy.validate(); self.policy = policy; self.clock = clock; self._last_request: float | None = None

    def _validate_url(self, url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.username or parsed.password or parsed.port not in (None, 443):
            raise ValueError("HTTPS_SOURCE_REQUIRED")
        if parsed.hostname not in self.policy.allowed_domains: raise PermissionError("DOMAIN_NOT_ALLOWED")

    def acquire(self, url: str, transport: Callable[[str, dict[str, str], float, int], TransportResponse], *,
                publication_time: str = "1970-01-01T00:00:00Z",
                point_in_time_available_at: str = "1970-01-01T00:00:00Z") -> dict:
        self._validate_url(url)
        try:
            datetime.fromisoformat(publication_time.replace("Z", "+00:00"))
            datetime.fromisoformat(point_in_time_available_at.replace("Z", "+00:00"))
        except (TypeError, ValueError): raise ValueError("SOURCE_TIME_INVALID") from None
        now = self.clock()
        if self._last_request is not None and now - self._last_request < self.policy.minimum_interval_seconds:
            raise RuntimeError("RATE_LIMITED")
        self._last_request = now
        response = transport(url, {"User-Agent": self.policy.user_agent}, self.policy.timeout_seconds,
                             self.policy.max_retries)
        if len(response.redirect_urls) > self.policy.max_redirects: raise RuntimeError("REDIRECT_LIMIT_EXCEEDED")
        for target in (*response.redirect_urls, response.final_url): self._validate_url(target)
        if response.status != 200: raise RuntimeError("SOURCE_UNAVAILABLE")
        declared = response.headers.get("Content-Length") if hasattr(response.headers, "get") else None
        if declared:
            try: declared_size = int(declared)
            except (TypeError, ValueError): raise ValueError("MALFORMED_CONTENT_LENGTH") from None
            if declared_size > self.policy.max_response_bytes: raise RuntimeError("RESPONSE_SIZE_LIMIT")
        if len(response.body) > self.policy.max_response_bytes: raise RuntimeError("RESPONSE_SIZE_LIMIT")
        return {"final_url": response.final_url, "retrieved_bytes": len(response.body),
                "content_hash": hashlib.sha256(response.body).hexdigest(), "redirect_count": len(response.redirect_urls),
                "tls_required": True, "rights_approved": True, "access_policy_approved": True,
                "retrieval_time": datetime.now(timezone.utc).isoformat(), "publication_time": publication_time,
                "point_in_time_available_at": point_in_time_available_at,
                "source_provenance": f"OFFICIAL_DOMAIN:{urlparse(response.final_url).hostname}",
                "body": response.body}
