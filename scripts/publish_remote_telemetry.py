#!/usr/bin/env python3
"""Publish one sanitized, read-only IIOS living snapshot.

This process only performs a local GET and a remote POST. It has no database,
broker, order, ledger, scheduler, or process-control capability.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_SOURCE = "http://127.0.0.1:5176/living/overview"
MAX_BYTES = 512 * 1024


def _record(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}


def _validate(snapshot: object) -> dict[str, object]:
    root = _record(snapshot)
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
    return root


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


def _publish(destination: str, token: str, payload: bytes) -> dict[str, object]:
    parsed = urllib.parse.urlparse(destination)
    if parsed.scheme != "https":
        raise ValueError("telemetry destination must use HTTPS")
    request = urllib.request.Request(
        destination,
        data=payload,
        method="POST",
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        return _record(json.loads(response.read(MAX_BYTES)))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default=DEFAULT_SOURCE)
    parser.add_argument("--destination", default=os.getenv("IIOS_TELEMETRY_INGEST_URL", ""))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    try:
        payload = _read_snapshot(args.source)
        if args.dry_run:
            print(f"validated read-only snapshot ({len(payload)} bytes); nothing uploaded")
            return 0

        token = os.getenv("IIOS_TELEMETRY_INGEST_TOKEN", "")
        if not args.destination or not token:
            raise ValueError(
                "IIOS_TELEMETRY_INGEST_URL and IIOS_TELEMETRY_INGEST_TOKEN are required"
            )
        result = _publish(args.destination, token, payload)
        if result.get("accepted") is not True:
            raise ValueError("remote receiver did not accept the snapshot")
        print(
            "published governed read-only snapshot; "
            f"generated_at={result.get('generated_at')}"
        )
        return 0
    except (ValueError, json.JSONDecodeError, urllib.error.URLError) as error:
        print(f"telemetry publish failed closed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
