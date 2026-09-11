#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "BACK END" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from factory_telemetry import (  # noqa: E402
    build_factory_telemetry,
    build_unavailable_telemetry,
)

TELEMETRY_HEADER = "IIOS FACTORY TELEMETRY — READ ONLY"
FINGERPRINT_MARKER = "<!-- iios-fingerprint:{fingerprint} -->"


def _json_text(snapshot: dict[str, Any]) -> str:
    return json.dumps(
        snapshot,
        indent=2,
        sort_keys=True,
        default=str,
    )


def _issue_body(snapshot: dict[str, Any]) -> str:
    fingerprint = str(snapshot.get("fingerprint") or "")
    return (
        f"{TELEMETRY_HEADER}\n\n"
        "This issue is machine-updated by the local IIOS telemetry exporter. "
        "It contains sanitized, read-only factory state only.\n\n"
        f"{FINGERPRINT_MARKER.format(fingerprint=fingerprint)}\n"
        "```json\n"
        f"{_json_text(snapshot)}\n"
        "```\n"
    )


def _run_gh(*args: str) -> str:
    gh = shutil.which("gh")
    if not gh:
        raise RuntimeError(
            "GitHub CLI (gh) is required for the private-issue sink"
        )
    result = subprocess.run(
        [gh, *args],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"gh {' '.join(args[:3])} failed: "
            f"{(result.stderr or result.stdout).strip()[:800]}"
        )
    return result.stdout.strip()


def _require_private_repo(repo: str) -> None:
    visibility = _run_gh(
        "api",
        f"repos/{repo}",
        "--jq",
        ".private",
    ).strip().lower()
    if visibility != "true":
        raise RuntimeError(
            "Refusing telemetry publish: target GitHub repository "
            "must be private"
        )


def _existing_issue_body(repo: str, issue: int) -> str:
    return _run_gh(
        "api",
        f"repos/{repo}/issues/{issue}",
        "--jq",
        ".body",
    )


def publish_private_github_issue(
    snapshot: dict[str, Any],
    *,
    repo: str,
    issue: int,
) -> dict[str, Any]:
    repo = repo.strip()
    if "/" not in repo:
        raise ValueError(
            "Telemetry repository must be owner/repository"
        )
    if issue <= 0:
        raise ValueError("Telemetry issue number must be positive")

    _require_private_repo(repo)
    body = _existing_issue_body(repo, issue)
    marker = FINGERPRINT_MARKER.format(
        fingerprint=snapshot.get("fingerprint") or ""
    )
    if marker in body:
        return {
            "status": "UNCHANGED",
            "sink": "PRIVATE_GITHUB_ISSUE",
            "repo": repo,
            "issue": issue,
            "fingerprint": snapshot.get("fingerprint"),
        }

    payload = _issue_body(snapshot)
    _run_gh(
        "api",
        "--method",
        "PATCH",
        f"repos/{repo}/issues/{issue}",
        "-f",
        f"body={payload}",
    )
    return {
        "status": "PUBLISHED",
        "sink": "PRIVATE_GITHUB_ISSUE",
        "repo": repo,
        "issue": issue,
        "fingerprint": snapshot.get("fingerprint"),
    }


def write_local_snapshot(
    snapshot: dict[str, Any],
    output: Path,
) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(
        _json_text(snapshot) + "\n",
        encoding="utf-8",
    )
    temporary.replace(output)


def one_cycle(args: argparse.Namespace) -> int:
    try:
        snapshot = build_factory_telemetry(args.db)
    except Exception as exc:  # telemetry failure is reported, not hidden
        snapshot = build_unavailable_telemetry(exc)

    if args.output:
        write_local_snapshot(snapshot, Path(args.output))

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
            "sanitized factory telemetry snapshot."
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
