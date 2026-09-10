"""Superbatch 3: immutable DENY-only authority. No credential or activation path.

Ownership identifies the only read-only observer allowed to hold a lease; it is
not permission to schedule provider dispatch or publish operational mutations.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import NoReturn

from truth_spine_contract import seal, utc, verified

CAPABILITIES = (
    "provider_requests", "credential_access", "paid_model_requests", "paper_order",
    "broker", "live_execution", "operational_ledger_write", "promotion",
    "scheduler_authority", "publisher_authority",
)


def disabled_document(binding: str, release: str, scheduler: str, publisher: str,
                      issued_at: str, expires_at: str) -> dict:
    return seal({"schema": "iios-disabled-authority-v1", "binding": binding,
                 "release_id": release, "issued_at": issued_at, "expires_at": expires_at,
                 "capabilities": dict.fromkeys(CAPABILITIES, False),
                 "owners": {"scheduler": scheduler, "publisher": publisher},
                 "activation": "NOT_IMPLEMENTED"})


def validate_authority(document: dict, *, binding: str, release: str,
                       owners: dict, now: datetime) -> dict:
    verified(document)
    if (set(document) != {"schema", "binding", "release_id", "issued_at", "expires_at",
                         "capabilities", "owners", "activation", "content_hash"}
            or document["schema"] != "iios-disabled-authority-v1"
            or document["binding"] != binding or document["release_id"] != release
            or document["owners"] != owners or set(owners) != {"scheduler", "publisher"}
            or any(not isinstance(v, str) or not v for v in owners.values())
            or document["activation"] != "NOT_IMPLEMENTED"
            or set(document["capabilities"]) != set(CAPABILITIES)
            or any(v is not False for v in document["capabilities"].values())):
        raise PermissionError("AUTHORITY_CONTRACT_INVALID")
    if now.tzinfo is None or now.utcoffset() != timezone.utc.utcoffset(now):
        raise PermissionError("AUTHORITY_CLOCK_INVALID")
    issued, expires = utc(document["issued_at"]), utc(document["expires_at"])
    if not issued <= now <= expires or not 0 < (expires-issued).total_seconds() <= 86400:
        raise PermissionError("AUTHORITY_NOT_CURRENT")
    return document


def require_capability(capability: str, *, document: dict | None = None,
                       binding: str = "", release: str = "", owners: dict | None = None) -> NoReturn:
    """No caller flag/environment override can grant capability in this release."""
    if capability not in CAPABILITIES:
        raise PermissionError("UNKNOWN_CAPABILITY")
    if document is None:
        raise PermissionError("AUTHORITY_MISSING")
    validate_authority(document, binding=binding, release=release, owners=owners or {},
                       now=datetime.now(timezone.utc))
    raise PermissionError("NO_PAPER_AUTHORITY" if capability == "paper_order" else "CAPABILITY_DISABLED")


def gateway(request: dict, **authority_context) -> NoReturn:
    """Future gateway contract; no provider implementations or secret-bearing input."""
    required = {"provider", "selector_identity", "capability", "endpoint", "entitlement",
                "retention", "request_identity", "rate_policy", "cost_budget", "source_binding",
                "session_binding", "classification", "receipt_schema", "citation_policy"}
    if set(request) != required or any(not isinstance(v, (str, int)) or isinstance(v, bool)
                                       for v in request.values()):
        raise PermissionError("GATEWAY_CONTRACT_INVALID")
    if request["provider"] not in {"FINANCIAL_DATASETS", "OPENAI", "GEMINI", "GROK"}:
        raise PermissionError("PROVIDER_NOT_IMPLEMENTED")
    require_capability("provider_requests" if request["provider"] == "FINANCIAL_DATASETS"
                       else "paid_model_requests", **authority_context)
