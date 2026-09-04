from __future__ import annotations

FIELDS = {"operational_aead", "keychain", "reviewer_authentication", "malware_scanner",
    "backup_recovery", "sec_configuration", "review_service"}
STATES = {"NOT_CONFIGURED", "AVAILABLE_FOR_REVIEW", "READY", "ERROR", "DISABLED", "NOT_AVAILABLE"}


def browser_security_readiness(values: dict[str, str]) -> dict:
    if set(values) != FIELDS or any(value not in STATES for value in values.values()):
        raise ValueError("SECURITY_READINESS_INVALID")
    return {"schema_version": "expansion-wing-security-readiness-v1", "states": dict(sorted(values.items())),
        "secrets_exposed": False, "identities_exposed": False, "paths_exposed": False,
        "security_internals_exposed": False}
