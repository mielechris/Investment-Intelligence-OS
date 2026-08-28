#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import plistlib
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

BRANCH = "feature/batch9g-market-validation-superbatch"
SCHEMA_VERSION = "batch9g-factory-telemetry-v2"
DEFAULT_OWNER = "mielechris"
DEFAULT_TELEMETRY_REPO_NAME = "IIOS-Telemetry"
ISSUE_TITLE = "IIOS Factory Telemetry - Latest"
LABEL = "com.iios.factory-telemetry"
INTERVAL_SECONDS = 60
HEARTBEAT_SECONDS = 300

LIVE = Path(
    os.getenv(
        "IIOS_LIVE_CHECKOUT",
        "/Users/crm/Documents/GitHub/Investment-Intelligence-OS-Batch8",
    )
).expanduser()
WORKTREE = Path(
    os.getenv(
        "IIOS_9G_WORKTREE",
        "/Users/crm/Documents/GitHub/Investment-Intelligence-OS-batch9g-market-validation",
    )
).expanduser()
LEDGER = Path(
    os.getenv(
        "IIOS_DB_PATH",
        str(LIVE / "BACK END" / "backend" / "iios_ledger.db"),
    )
).expanduser()
TELEMETRY_OWNER = os.getenv(
    "IIOS_TELEMETRY_GITHUB_OWNER",
    DEFAULT_OWNER,
).strip()
TELEMETRY_REPO_NAME = os.getenv(
    "IIOS_TELEMETRY_GITHUB_REPO_NAME",
    DEFAULT_TELEMETRY_REPO_NAME,
).strip()
TELEMETRY_REPO = f"{TELEMETRY_OWNER}/{TELEMETRY_REPO_NAME}"

STATE_DIR = (
    Path.home()
    / "Library"
    / "Application Support"
    / "IIOS"
    / "telemetry"
)
LOCAL_SNAPSHOT = STATE_DIR / "latest.json"
LOG_DIR = Path.home() / "Library" / "Logs" / "IIOS"
PLIST = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"
PLIST_BACKUP = PLIST.with_suffix(".batch9f-backup.plist")


def _run(
    args: list[str],
    *,
    cwd: Path | None = None,
    check: bool = True,
    capture: bool = False,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        args,
        cwd=str(cwd) if cwd else None,
        text=True,
        capture_output=capture,
        check=False,
    )
    if check and result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(
            f"Command failed ({result.returncode}): "
            f"{' '.join(args[:6])}\n{detail[:2500]}"
        )
    return result


def _capture(args: list[str], *, cwd: Path | None = None) -> str:
    return _run(args, cwd=cwd, capture=True).stdout.strip()


def _require_command(name: str) -> str:
    value = shutil.which(name)
    if not value:
        raise SystemExit(f"Required command not found: {name}")
    return value


def _require_private_repo(gh: str) -> None:
    result = _run(
        [
            gh,
            "api",
            f"repos/{TELEMETRY_REPO}",
            "--jq",
            ".private",
        ],
        check=False,
        capture=True,
    )
    if result.returncode != 0:
        raise SystemExit(
            "Batch 9F private telemetry destination is unavailable. "
            "Refusing 9G activation instead of creating a replacement."
        )
    if result.stdout.strip().lower() != "true":
        raise SystemExit(
            "Refusing activation: telemetry destination is not verified private"
        )


def _require_existing_issue(gh: str) -> int:
    query = f"repos/{TELEMETRY_REPO}/issues?state=open&per_page=100"
    issue_text = _capture(
        [
            gh,
            "api",
            query,
            "--jq",
            f'.[] | select(.title == "{ISSUE_TITLE}") | .number',
        ]
    )
    if not issue_text:
        raise SystemExit(
            "Batch 9F telemetry issue was not found. "
            "Refusing 9G activation because 9F must already be active."
        )
    return int(issue_text.splitlines()[0].strip())


def _prepare_worktree(git: str) -> tuple[str, str]:
    if not LIVE.exists():
        raise SystemExit(f"Live IIOS checkout not found: {LIVE}")
    if not LEDGER.exists():
        raise SystemExit(f"Live IIOS ledger not found: {LEDGER}")

    branch_before = _capture(
        [git, "branch", "--show-current"],
        cwd=LIVE,
    )
    status_before = _capture(
        [git, "status", "--porcelain"],
        cwd=LIVE,
    )

    _run([git, "fetch", "origin", BRANCH], cwd=LIVE)
    remote_ref = f"origin/{BRANCH}"

    if WORKTREE.exists():
        if not (WORKTREE / ".git").exists():
            raise SystemExit(
                f"9G path exists but is not a git worktree: {WORKTREE}"
            )
        worktree_status = _capture(
            [git, "status", "--porcelain"],
            cwd=WORKTREE,
        )
        if worktree_status:
            raise SystemExit(
                "Refusing to replace 9G worktree because it has local changes"
            )
        _run([git, "fetch", "origin", BRANCH], cwd=WORKTREE)
        _run(
            [git, "reset", "--hard", remote_ref],
            cwd=WORKTREE,
        )
    else:
        _run(
            [
                git,
                "worktree",
                "add",
                "--detach",
                str(WORKTREE),
                remote_ref,
            ],
            cwd=LIVE,
        )

    branch_after = _capture(
        [git, "branch", "--show-current"],
        cwd=LIVE,
    )
    status_after = _capture(
        [git, "status", "--porcelain"],
        cwd=LIVE,
    )
    if branch_after != branch_before or status_after != status_before:
        raise SystemExit(
            "Refusing activation: live IIOS checkout changed while preparing 9G"
        )
    return branch_before, status_before


def _resolve_python() -> Path:
    candidates = (
        LIVE / "BACK END" / "backend" / ".venv" / "bin" / "python",
        Path(
            "/Users/crm/Documents/GitHub/Investment-Intelligence-OS/"
            "BACK END/backend/.venv/bin/python"
        ),
    )
    for candidate in candidates:
        if candidate.exists() and os.access(candidate, os.X_OK):
            return candidate
    raise SystemExit(
        "No IIOS backend virtualenv Python found; "
        "refusing system-Python daemon fallback"
    )


def _exporter_command(
    python: Path,
    issue_number: int,
    *,
    stdout: bool,
) -> list[str]:
    exporter = (
        WORKTREE
        / "scripts"
        / "iios_factory_telemetry_exporter_v2.py"
    )
    if not exporter.exists():
        raise SystemExit(f"9G telemetry exporter not found: {exporter}")

    command = [
        str(python),
        str(exporter),
        "--db",
        str(LEDGER),
        "--output",
        str(LOCAL_SNAPSHOT),
        "--github-repo",
        TELEMETRY_REPO,
        "--github-issue",
        str(issue_number),
        "--heartbeat-seconds",
        str(HEARTBEAT_SECONDS),
    ]
    if stdout:
        command.append("--stdout")
    return command


def _validate_first_snapshot(snapshot: dict[str, Any]) -> None:
    if (
        snapshot.get("health", {}).get("state")
        == "TELEMETRY_UNAVAILABLE"
    ):
        raise SystemExit(
            "First Batch 9G telemetry snapshot reports TELEMETRY_UNAVAILABLE"
        )
    if snapshot.get("schema_version") != SCHEMA_VERSION:
        raise SystemExit(
            "First Batch 9G telemetry snapshot has the wrong schema version"
        )
    if (
        snapshot.get("source", {}).get("mode")
        != "LOCAL_LEDGER_READ_ONLY"
    ):
        raise SystemExit(
            "First Batch 9G telemetry snapshot is not local-ledger read-only"
        )
    if not isinstance(snapshot.get("recent_paper_fills"), list):
        raise SystemExit(
            "First Batch 9G telemetry snapshot is missing paper-fill visibility"
        )

    contract = snapshot.get("telemetry_contract") or {}
    if contract.get("heartbeat_expected_seconds") != HEARTBEAT_SECONDS:
        raise SystemExit(
            "Batch 9G telemetry heartbeat contract did not match activation"
        )

    safety = snapshot.get("safety") or {}
    if safety.get("telemetry_read_only") is not True:
        raise SystemExit("Telemetry read-only safety flag is not true")
    if safety.get("live_execution") is not False:
        raise SystemExit("Live execution safety flag is not false")

    serialized = json.dumps(snapshot, sort_keys=True).upper()
    forbidden = (
        "OPENAI_API_KEY",
        "XAI_API_KEY",
        "GEMINI_API_KEY",
        "KIMI_API_KEY",
        "BROKER_PASSWORD",
        "BROKER_SECRET",
        "BROKER_TOKEN",
    )
    leaked = [name for name in forbidden if name in serialized]
    if leaked:
        raise SystemExit(
            f"Refusing activation: forbidden telemetry fields found: {leaked}"
        )


def _first_snapshot(
    python: Path,
    issue_number: int,
) -> dict[str, Any]:
    result = _run(
        _exporter_command(
            python,
            issue_number,
            stdout=True,
        ),
        cwd=WORKTREE,
        check=False,
        capture=True,
    )
    if result.returncode != 0:
        raise SystemExit(
            "First real-ledger Batch 9G telemetry publish failed:\n"
            + (result.stderr or result.stdout or "")[:3000]
        )
    try:
        snapshot = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise SystemExit(
            f"Could not parse first Batch 9G telemetry snapshot: {exc}"
        ) from exc
    _validate_first_snapshot(snapshot)
    return snapshot


def _verify_private_issue(
    gh: str,
    issue_number: int,
    fingerprint: str,
) -> None:
    body = _capture(
        [
            gh,
            "api",
            f"repos/{TELEMETRY_REPO}/issues/{issue_number}",
            "--jq",
            ".body",
        ]
    )
    required = (
        "IIOS FACTORY TELEMETRY — BATCH 9G READ ONLY",
        "LOCAL_LEDGER_READ_ONLY",
        SCHEMA_VERSION,
        "iios-heartbeat:",
    )
    missing = [item for item in required if item not in body]
    if missing:
        raise SystemExit(
            "Private telemetry issue is missing Batch 9G proof: "
            + ", ".join(missing)
        )
    if fingerprint and fingerprint not in body:
        raise SystemExit(
            "Private telemetry issue does not contain the Batch 9G fingerprint"
        )


def _backup_current_plist() -> bool:
    if not PLIST.exists():
        return False
    PLIST_BACKUP.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(PLIST, PLIST_BACKUP)
    return True


def _restore_plist_backup() -> None:
    if PLIST_BACKUP.exists():
        shutil.copy2(PLIST_BACKUP, PLIST)


def _install_launch_agent(
    python: Path,
    gh: str,
    issue_number: int,
) -> None:
    PLIST.parent.mkdir(parents=True, exist_ok=True)
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    current_path = os.environ.get("PATH", "")
    gh_dir = str(Path(gh).parent)
    path_parts = [
        gh_dir,
        *[item for item in current_path.split(":") if item],
    ]
    launch_path = ":".join(dict.fromkeys(path_parts))

    payload = {
        "Label": LABEL,
        "ProgramArguments": _exporter_command(
            python,
            issue_number,
            stdout=False,
        ),
        "WorkingDirectory": str(WORKTREE),
        "RunAtLoad": True,
        "StartInterval": INTERVAL_SECONDS,
        "ProcessType": "Background",
        "EnvironmentVariables": {
            "PATH": launch_path,
            "PYTHONUNBUFFERED": "1",
        },
        "StandardOutPath": str(
            LOG_DIR / "factory-telemetry.out.log"
        ),
        "StandardErrorPath": str(
            LOG_DIR / "factory-telemetry.err.log"
        ),
    }

    temporary = PLIST.with_suffix(".batch9g.tmp.plist")
    with temporary.open("wb") as handle:
        plistlib.dump(payload, handle, sort_keys=True)
    temporary.replace(PLIST)

    domain = f"gui/{os.getuid()}"
    _run(
        ["launchctl", "bootout", domain, str(PLIST)],
        check=False,
        capture=True,
    )
    try:
        _run(["launchctl", "bootstrap", domain, str(PLIST)])
        _run(
            [
                "launchctl",
                "kickstart",
                "-k",
                f"{domain}/{LABEL}",
            ]
        )
        _run(
            ["launchctl", "print", f"{domain}/{LABEL}"],
            capture=True,
        )
    except Exception:
        _run(
            ["launchctl", "bootout", domain, str(PLIST)],
            check=False,
            capture=True,
        )
        _restore_plist_backup()
        if PLIST.exists():
            _run(
                ["launchctl", "bootstrap", domain, str(PLIST)],
                check=False,
                capture=True,
            )
            _run(
                [
                    "launchctl",
                    "kickstart",
                    "-k",
                    f"{domain}/{LABEL}",
                ],
                check=False,
                capture=True,
            )
        raise


def main() -> int:
    if sys.platform != "darwin":
        raise SystemExit(
            "Batch 9G activation is intentionally macOS-only "
            "for this IIOS runtime"
        )

    git = _require_command("git")
    gh = _require_command("gh")
    _require_command("launchctl")
    _run([gh, "auth", "status"])

    print("IIOS BATCH 9G — MARKET VALIDATION TELEMETRY ACTIVATION")
    print(f"Live ledger: {LEDGER}")
    print(f"Telemetry destination: {TELEMETRY_REPO} (PRIVATE REQUIRED)")
    print("Direction: OUTBOUND ONLY")
    print("Ledger access: SQLITE READ ONLY")
    print(f"Snapshot cadence: {INTERVAL_SECONDS} seconds")
    print(f"Heartbeat freshness: {HEARTBEAT_SECONDS} seconds")
    print("Paper-fill semantics: PERSISTED GOVERNED PAPER TRANSACTION")
    print("Broker connected: FALSE")
    print("Live execution: FALSE")

    branch_before, status_before = _prepare_worktree(git)
    _require_private_repo(gh)
    issue_number = _require_existing_issue(gh)
    python = _resolve_python()

    snapshot = _first_snapshot(python, issue_number)
    fingerprint = str(snapshot.get("fingerprint") or "")
    _verify_private_issue(gh, issue_number, fingerprint)

    backup_created = _backup_current_plist()
    _install_launch_agent(python, gh, issue_number)

    branch_after = _capture(
        [git, "branch", "--show-current"],
        cwd=LIVE,
    )
    status_after = _capture(
        [git, "status", "--porcelain"],
        cwd=LIVE,
    )
    if branch_after != branch_before or status_after != status_before:
        raise SystemExit(
            "Live IIOS checkout changed during Batch 9G telemetry activation"
        )

    summary = {
        "status": "BATCH9G_MARKET_VALIDATION_TELEMETRY_LIVE",
        "telemetry_repo": TELEMETRY_REPO,
        "telemetry_repo_private": True,
        "telemetry_issue": issue_number,
        "ledger": str(LEDGER),
        "ledger_mode": "READ_ONLY",
        "worktree": str(WORKTREE),
        "local_snapshot": str(LOCAL_SNAPSHOT),
        "launch_agent": str(PLIST),
        "launch_agent_backup": (
            str(PLIST_BACKUP) if backup_created else None
        ),
        "publish_interval_seconds": INTERVAL_SECONDS,
        "heartbeat_seconds": HEARTBEAT_SECONDS,
        "schema_version": snapshot.get("schema_version"),
        "first_fingerprint": fingerprint,
        "factory_health": snapshot.get("health", {}).get("state"),
        "paper_fill_count": len(
            snapshot.get("recent_paper_fills") or []
        ),
        "paper_nav": snapshot.get("paper_fund", {}).get("nav"),
        "paper_total_pnl": snapshot.get("paper_fund", {}).get(
            "total_pnl"
        ),
        "live_execution": False,
        "broker_connected": False,
        "live_checkout_unchanged": True,
    }
    print(json.dumps(summary, indent=2, sort_keys=True, default=str))
    print(
        "\nBatch 9G telemetry is active. The factory remains paper-only, "
        "the live IIOS checkout was not modified, and the Mac exposes "
        "no inbound service."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
