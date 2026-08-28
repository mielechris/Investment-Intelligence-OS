#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "BACK END" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import iios_factory_telemetry_exporter as batch9f_exporter  # noqa: E402
from factory_telemetry_v2 import (  # noqa: E402
    DEFAULT_HEARTBEAT_SECONDS,
    build_factory_telemetry,
    build_unavailable_telemetry,
)

TELEMETRY_HEADER = "IIOS FACTORY TELEMETRY — BATCH 9G READ ONLY"
FINGERPRINT_MARKER = batch9f_exporter.FINGERPRINT_MARKER
HEARTBEAT_PREFIX = "<!-- iios-heartbeat:"
HEARTBEAT_PATTERN = re.compile(
    r"<!-- iios-heartbeat:([^>]+) -->"
)


def _json_text(snapshot: dict[str, Any]) -> str:
    return batch9f_exporter._json_text(snapshot)


def _heartbeat_marker(published_at: datetime) -> str:
    return (
        f"{HEARTBEAT_PREFIX}"
        f"{published_at.astimezone(timezone.utc).isoformat()} -->"
    )


def _heartbeat_from_body(body: str) -> datetime | None:
    match = HEARTBEAT_PATTERN.search(body or "")
    if not match:
        return None
    text = match.group(1).strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _issue_body(
    snapshot: dict[str, Any],
    *,
    published_at: datetime,
) -> str:
    fingerprint = str(snapshot.get("fingerprint") or "")
    return (
        f"{TELEMETRY_HEADER}\n\n"
        "This issue is machine-updated by the local IIOS telemetry exporter. "
        "It contains sanitized, read-only factory state only.\n\n"
        f"{FINGERPRINT_MARKER.format(fingerprint=fingerprint)}\n"
        f"{_heartbeat_marker(published_at)}\n"
        "```json\n"
        f"{_json_text(snapshot)}\n"
        "```\n"
    )


def publish_private_github_issue(
    snapshot: dict[str, Any],
    *,
    repo: str,
    issue: int,
    heartbeat_seconds: int = DEFAULT_HEARTBEAT_SECONDS,
    now: datetime | None = None,
) -> dict[str, Any]:
    repo = repo.strip()
    if "/" not in repo:
        raise ValueError(
            "Telemetry repository must be owner/repository"
        )
    if issue <= 0:
        raise ValueError("Telemetry issue number must be positive")

    heartbeat_seconds = max(60, int(heartbeat_seconds or 0))
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)

    batch9f_exporter._require_private_repo(repo)
    body = batch9f_exporter._existing_issue_body(repo, issue)
    marker = FINGERPRINT_MARKER.format(
        fingerprint=snapshot.get("fingerprint") or ""
    )
    same_fingerprint = marker in body

    last_heartbeat = _heartbeat_from_body(body)
    heartbeat_fresh = bool(
        last_heartbeat
        and (now - last_heartbeat).total_seconds() < heartbeat_seconds
    )

    if same_fingerprint and heartbeat_fresh:
        return {
            "status": "UNCHANGED",
            "sink": "PRIVATE_GITHUB_ISSUE",
            "repo": repo,
            "issue": issue,
            "fingerprint": snapshot.get("fingerprint"),
            "heartbeat_at": last_heartbeat.isoformat()
            if last_heartbeat
            else None,
        }

    payload = _issue_body(snapshot, published_at=now)
    batch9f_exporter._run_gh(
        "api",
        "--method",
        "PATCH",
        f"repos/{repo}/issues/{issue}",
        "-f",
        f"body={payload}",
    )

    return {
        "status": (
            "HEARTBEAT_PUBLISHED"
            if same_fingerprint
            else "PUBLISHED"
        ),
        "sink": "PRIVATE_GITHUB_ISSUE",
        "repo": repo,
        "issue": issue,
        "fingerprint": snapshot.get("fingerprint"),
        "heartbeat_at": now.isoformat(),
    }


def one_cycle(args: argparse.Namespace) -> int:
    try:
        snapshot = build_factory_telemetry(args.db)
    except Exception as exc:
        snapshot = build_unavailable_telemetry(exc)

    if args.output:
        batch9f_exporter.write_local_snapshot(
            snapshot,
            Path(args.output),
        )

    publish_result = None
    repo = args.github_repo or os.getenv(
        "IIOS_TELEMETRY_GITHUB_REPO"
    )
    issue_text = (
        str(args.github_issue)
        if args.github_issue is not None
        else os.getenv("IIOS_TELEMETRY_GITHUB_ISSUE")
    )

    if repo or issue_text:
        if not repo or not issue_text:
            raise RuntimeError(
                "Both telemetry GitHub repo and issue are required"
            )
        publish_result = publish_private_github_issue(
            snapshot,
            repo=repo,
            issue=int(issue_text),
            heartbeat_seconds=args.heartbeat_seconds,
        )

    if args.stdout:
        print(_json_text(snapshot))
    elif publish_result:
        print(json.dumps(publish_result, sort_keys=True))
    elif args.output:
        print(
            json.dumps(
                {
                    "status": "WROTE_LOCAL_SNAPSHOT",
                    "output": str(Path(args.output)),
                    "fingerprint": snapshot.get("fingerprint"),
                },
                sort_keys=True,
            )
        )
    else:
        print(_json_text(snapshot))

    return (
        2
        if snapshot.get("health", {}).get("state")
        == "TELEMETRY_UNAVAILABLE"
        else 0
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Read the IIOS ledger without mutation and publish a "
            "sanitized Batch 9G factory telemetry snapshot."
        )
    )
    parser.add_argument(
        "--db",
        help="Optional IIOS ledger path; defaults to IIOS_DB_PATH.",
    )
    parser.add_argument(
        "--output",
        help="Optional local JSON snapshot path.",
    )
    parser.add_argument(
        "--github-repo",
        help=(
            "Private owner/repo telemetry destination. "
            "Can also use IIOS_TELEMETRY_GITHUB_REPO."
        ),
    )
    parser.add_argument(
        "--github-issue",
        type=int,
        help=(
            "Private telemetry issue number. "
            "Can also use IIOS_TELEMETRY_GITHUB_ISSUE."
        ),
    )
    parser.add_argument(
        "--interval-seconds",
        type=int,
        default=0,
        help=(
            "0 runs once. Positive values run continuously; "
            "minimum continuous interval is 30 seconds."
        ),
    )
    parser.add_argument(
        "--heartbeat-seconds",
        type=int,
        default=int(
            os.getenv(
                "IIOS_TELEMETRY_HEARTBEAT_SECONDS",
                str(DEFAULT_HEARTBEAT_SECONDS),
            )
        ),
        help=(
            "Refresh the private telemetry issue at least this often "
            "even when the meaningful-state fingerprint is unchanged. "
            "Minimum is 60 seconds."
        ),
    )
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="Print the sanitized snapshot JSON.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    interval = max(0, int(args.interval_seconds or 0))
    if interval and interval < 30:
        raise SystemExit(
            "Continuous telemetry interval must be at least 30 seconds"
        )
    if int(args.heartbeat_seconds or 0) < 60:
        raise SystemExit(
            "Telemetry heartbeat interval must be at least 60 seconds"
        )

    if not interval:
        return one_cycle(args)

    exit_code = 0
    try:
        while True:
            try:
                exit_code = max(exit_code, one_cycle(args))
            except Exception as exc:
                print(
                    json.dumps(
                        {
                            "status": "EXPORT_ERROR",
                            "error": (
                                f"{type(exc).__name__}: {exc}"
                            )[:1000],
                        },
                        sort_keys=True,
                    ),
                    file=sys.stderr,
                )
                exit_code = max(exit_code, 3)
            time.sleep(interval)
    except KeyboardInterrupt:
        return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
