"""Offline provider contracts; no credential, network, ledger or service access."""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from pathlib import Path

from truth_spine_contract import canonical, seal, utc

SCHEMA = "iios-provider-receipt-v1"
ADAPTER_VERSION = "1.0.0"
PROVIDER_ROLES = {
    "FINANCIAL_DATASETS": "CORPORATE_HISTORICAL_EVIDENCE",
    "ALPACA": "AUTHORITATIVE_MARKET_VALIDATION",
    "MASSIVE": "INDEPENDENT_BROAD_MARKET_VALIDATION",
    "ALPHA_VANTAGE": "SECONDARY_ENRICHMENT",
    "BIGDATA": "GROUNDED_RESEARCH",
    "YAHOO": "DISCOVERY_BENCHMARK_ONLY",
}
SYSTEM_ROLES = {
    "IIOS": "SOLE_TRUTH_AND_DECISION_AUTHORITY",
    "ALPACA_PAPER": "SEPARATELY_GOVERNED_PAPER_ONLY_RAIL",
    "OPENAI": "ORCHESTRATION_STRUCTURED_REASONING",
    "GROK": "INDEPENDENT_PUBLIC_NARRATIVE_CHALLENGER",
    "GEMINI": "INDEPENDENT_LONG_CONTEXT_CHALLENGER",
    "GITHUB_CODEX": "ENGINEERING_CI_RELEASE_PROVENANCE",
    "HERCULES": "UNPUBLISHED_READ_ONLY_UX_TESTING",
    "NORTHSTAR": "OFFICIAL_IIOS_BROWSER_PRESENTATION",
}
AUTHORITY_KEYS = (
    "broker_connection", "paper_order_permission", "trade_execution_permission",
    "live_execution", "ledger_read", "ledger_write", "provider_activation",
)
PILOT = ("MU", "SPY", "XLK", "VNQ", "TLT", "GLD", "UUP", "IBIT", "PFF", "BIL")
DENIED_KEYS = frozenset({
    "apikey", "api_key", "key", "secret", "password", "authorization", "headers",
    "token", "credential", "credential_value", "access_token", "refresh_token",
    "apca-api-key-id", "apca-api-secret-key", "x-api-key",
})


def locked_authority():
    return dict.fromkeys(AUTHORITY_KEYS, False)


def content_hash(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def pin(value, expected):
    if not isinstance(expected, str) or not re.fullmatch(r"[a-f0-9]{64}", expected):
        raise ValueError("INDEPENDENT_PIN_REQUIRED")
    if content_hash(value) != expected:
        raise ValueError("PARENT_HASH_MISMATCH")


def safe_document(value):
    """Reject secret-bearing structures before hashing or writing them.

    Injected transports must supply public evidence only, never headers or secrets.
    Unknown exception text and provider error messages are never persisted.
    """
    if isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str) or key.lower() in DENIED_KEYS:
                raise ValueError("SENSITIVE_DOCUMENT_REJECTED")
            safe_document(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            safe_document(child)
    elif isinstance(value, str):
        if re.search(r"(?i)(bearer\s|api[_-]?key[=:]|password[=:]|[?&](token|key)=|-----BEGIN .*PRIVATE KEY)", value):
            raise ValueError("SENSITIVE_DOCUMENT_REJECTED")
    elif value is not None and type(value) not in (int, float, bool):
        raise ValueError("PUBLIC_JSON_REQUIRED")
    canonical(value)  # Reject NaN/Infinity; preserve integer timestamp precision.


def symbols(value, *, count=None):
    if not isinstance(value, (list, tuple)) or not value:
        raise ValueError("SYMBOLS_REQUIRED")
    if any(not isinstance(s, str) or not re.fullmatch(r"[A-Z0-9][A-Z0-9.-]{0,15}", s) for s in value):
        raise ValueError("SYMBOL_INVALID")
    if len(set(value)) != len(value) or (count is not None and len(value) != count):
        raise ValueError("UNIVERSE_MEMBERSHIP_INVALID")
    return sorted(value)


def verify_receipt(receipt, expected, *, parents):
    safe_document(receipt)
    pin(receipt, expected)
    body = {k: v for k, v in receipt.items() if k != "content_hash"}
    if receipt.get("content_hash") != content_hash(body) or receipt.get("schema") != SCHEMA:
        raise ValueError("RECEIPT_SCHEMA_OR_HASH_INVALID")
    if receipt.get("parents") != parents or not parents:
        raise ValueError("RECEIPT_PARENT_MISMATCH")
    if receipt.get("authority") != locked_authority():
        raise ValueError("AUTHORITY_VIOLATION")
    if receipt.get("provider") not in PROVIDER_ROLES:
        raise ValueError("PROVIDER_INVALID")
    if content_hash(receipt["observations"]) != receipt["normalized_observation_hash"]:
        raise ValueError("OBSERVATION_HASH_MISMATCH")
    return receipt


def write_receipt(root: Path, receipt: dict, expected: str, *, parents: dict):
    """Owner-only directory FD and exclusive no-follow creation; no replacement."""
    verify_receipt(receipt, expected, parents=parents)
    root = Path(root)
    if root.is_symlink() or root.resolve() != root.absolute():
        raise ValueError("RECEIPT_ROOT_ALIAS_REJECTED")
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        identity = os.fstat(fd)
        if identity.st_uid != os.getuid() or identity.st_mode & 0o022:
            raise ValueError("RECEIPT_ROOT_UNSAFE")
        name = expected + ".json"
        out = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                      0o600, dir_fd=fd)
        with os.fdopen(out, "wb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise ValueError("RECEIPT_FILE_UNSAFE")
            stream.write(canonical(receipt))
            stream.flush()
            os.fsync(stream.fileno())
        os.fsync(fd)
        return root / name
    finally:
        os.close(fd)


def freshness(event, received, maximum_age_seconds):
    if event is None:
        return "UNVERIFIED"
    try:
        age = (utc(received) - utc(event)).total_seconds()
    except ValueError:
        return "UNVERIFIED"
    if age < 0:
        return "FUTURE"
    return "CURRENT" if age <= maximum_age_seconds else "STALE"


def readiness(receipt=None, *, expected=None, parents=None, bindings=None):
    """No I/O; connector linkage is deliberately not runtime integration."""
    fields = ("CONNECTOR", "CREDENTIAL BINDING", "ENTITLEMENT", "FEED TYPE",
              "FRESHNESS", "COVERAGE", "RECEIPT LINEAGE", "COST/CREDIT",
              "RUNTIME INTEGRATION", "OPERATIONAL AUTHORITY")
    states = dict.fromkeys(fields, "UNVERIFIED")
    states["OPERATIONAL AUTHORITY"] = "LOCKED_FALSE"
    if receipt is not None:
        verify_receipt(receipt, expected, parents=parents)
        states.update({"CONNECTOR": "OFFLINE_CONTRACT", "ENTITLEMENT": receipt["entitlement_state"],
                       "FEED TYPE": receipt["delay_classification"], "FRESHNESS": receipt["freshness"],
                       "COVERAGE": receipt["coverage"], "RECEIPT LINEAGE": receipt["provenance"],
                       "COST/CREDIT": receipt["cost_credit_state"]})
    # This batch has no qualified runtime or credential-binding verifier.
    # Caller-supplied GREEN labels/ChatGPT connection flags cannot override them.
    states["OVERALL READINESS"] = "NOT_READY"
    return states


def readiness_matrix(evidence):
    """Each provider has independent receipt and independently supplied parents."""
    if set(evidence) - set(PROVIDER_ROLES):
        raise ValueError("READINESS_PROVIDER_INVALID")
    rows = {}
    for provider in PROVIDER_ROLES:
        item = evidence.get(provider)
        if item is None:
            rows[provider] = readiness()
        else:
            if item["receipt"]["provider"] != provider:
                raise ValueError("READINESS_PROVIDER_SUBSTITUTION")
            rows[provider] = readiness(item["receipt"], expected=item["expected"], parents=item["parents"])
    return {"providers": rows, "overall": "NOT_READY", "authority": locked_authority()}
