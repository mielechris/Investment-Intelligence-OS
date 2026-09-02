#!/usr/bin/env python3
"""Publish one sanitized, read-only IIOS living snapshot.

This process only performs a local GET and a remote POST. It has no database,
broker, order, ledger, scheduler, or process-control capability.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import sys
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_SOURCE = "http://127.0.0.1:5176/living/overview"
MAX_BYTES = 512 * 1024
REMOTE_SCHEMA_VERSION = "iios_remote_telemetry.v1"
MAX_SOURCE_AGE_SECONDS = 30
MAX_FUTURE_SKEW_SECONDS = 5


def _record(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}



FORBIDDEN_REMOTE_KEYS = {
    "api_key", "apikey", "password", "secret", "credential",
    "authorization", "access_token", "refresh_token", "private_key",
    "account_number", "broker_account",
}


def _sanitize(value: object) -> object:
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, dict):
        return {
            key: _sanitize(child)
            for key, child in value.items()
            if key.strip().lower().replace("-", "_") not in FORBIDDEN_REMOTE_KEYS
        }
    return value


def _parse_generated_at(value: object) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("local snapshot generated_at is required")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("local snapshot generated_at is invalid") from error
    if parsed.tzinfo is None:
        raise ValueError("local snapshot generated_at must include a timezone")
    return parsed.astimezone(timezone.utc)


def _validate(
    snapshot: object,
    *,
    now: datetime | None = None,
    max_age_seconds: int = MAX_SOURCE_AGE_SECONDS,
) -> dict[str, object]:
    root = _record(snapshot)
    observed_at = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    generated_at = _parse_generated_at(root.get("generated_at"))
    age_seconds = (observed_at - generated_at).total_seconds()
    if age_seconds < -MAX_FUTURE_SKEW_SECONDS:
        raise ValueError("local snapshot generated_at is materially in the future")
    if age_seconds > max_age_seconds:
        raise ValueError("local snapshot is stale")

    safety = _record(root.get("safety"))
    if safety.get("live_execution") is not False:
        raise ValueError("local snapshot does not prove live_execution=false")

    validation = _record(root.get("validation"))
    layers = _record(validation.get("layers"))
    factory = _record(layers.get("factory_telemetry"))
    payload = _record(factory.get("payload"))
    telemetry_safety = _record(payload.get("safety"))
    if telemetry_safety.get("telemetry_read_only") is not True:
        raise ValueError("local snapshot does not prove telemetry_read_only=true")
    normalized = _record(_sanitize(root))
    source_schema = root.get("schema_version")
    if isinstance(source_schema, str) and source_schema != REMOTE_SCHEMA_VERSION:
        normalized["source_schema_version"] = source_schema
    normalized["schema_version"] = REMOTE_SCHEMA_VERSION
    return normalized


def _read_snapshot(source: str) -> bytes:
    parsed = urllib.parse.urlparse(source)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost"}:
        raise ValueError("telemetry source must be localhost HTTP")
    request = urllib.request.Request(source, headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=10) as response:
        payload = response.read(MAX_BYTES + 1)
    if len(payload) > MAX_BYTES:
        raise ValueError("local snapshot exceeds 512 KiB")
    normalized = json.dumps(
        _validate(json.loads(payload)),
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    if len(normalized) > MAX_BYTES:
        raise ValueError("normalized snapshot exceeds 512 KiB")
    return normalized


def _publish(
    destination: str,
    token: str,
    payload: bytes,
    bypass_secret: str = "",
) -> dict[str, object]:
    parsed = urllib.parse.urlparse(destination)
    if parsed.scheme != "https":
        raise ValueError("telemetry destination must use HTTPS")
    headers = {
        "Accept": "application/json",
        "x-iios-telemetry-token": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    if bypass_secret:
        headers["x-vercel-protection-bypass"] = bypass_secret
    request = urllib.request.Request(
        destination,
        data=payload,
        method="POST",
        headers=headers,
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        return _record(json.loads(response.read(MAX_BYTES)))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default=DEFAULT_SOURCE)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    try:
        payload = _read_snapshot(args.source)
        if args.dry_run:
            print(f"validated read-only snapshot ({len(payload)} bytes); nothing uploaded")
            return 0
        raise ValueError(
            "direct publication is disabled; use run_preview_living_wall_publisher.py"
        )
    except (ValueError, json.JSONDecodeError, urllib.error.URLError) as error:
        print(f"telemetry publish failed closed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
