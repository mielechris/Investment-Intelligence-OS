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

BRANCH = "feature/batch9f-factory-telemetry"
DEFAULT_OWNER = "mielechris"
DEFAULT_TELEMETRY_REPO_NAME = "IIOS-Telemetry"
ISSUE_TITLE = "IIOS Factory Telemetry - Latest"
LABEL = "com.iios.factory-telemetry"
INTERVAL_SECONDS = 60

LIVE = Path(
    os.getenv(
        "IIOS_LIVE_CHECKOUT",
        "/Users/crm/Documents/GitHub/Investment-Intelligence-OS-Batch8",
    )
).expanduser()
WORKTREE = Path(
    os.getenv(
        "IIOS_9F_WORKTREE",
        "/Users/crm/Documents/GitHub/Investment-Intelligence-OS-batch9f-telemetry",
    )
).expanduser()
LEDGER = Path(
    os.getenv(
        "IIOS_DB_PATH",
        str(LIVE / "BACK END" / "backend" / "iios_ledger.db"),
    )
).expanduser()
TELEMETRY_OWNER = os.getenv("IIOS_TELEMETRY_GITHUB_OWNER", DEFAULT_OWNER).strip()
TELEMETRY_REPO_NAME = os.getenv(
    "IIOS_TELEMETRY_GITHUB_REPO_NAME",
    DEFAULT_TELEMETRY_REPO_NAME,
).strip()
TELEMETRY_REPO = f"{TELEMETRY_OWNER}/{TELEMETRY_REPO_NAME}"

STATE_DIR = Path.home() / "Library" / "Application Support" / "IIOS" / "telemetry"
LOCAL_SNAPSHOT = STATE_DIR / "latest.json"
LOG_DIR = Path.home() / "Library" / "Logs" / "IIOS"
PLIST = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"


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
            f"Command failed ({result.returncode}): {' '.join(args[:5])}\n"
            f"{detail[:2000]}"
        )
    return result


def _capture(args: list[str], *, cwd: Path | None = None) -> str:
    return _run(args, cwd=cwd, capture=True).stdout.strip()


def _require_command(name: str) -> str:
    value = shutil.which(name)
    if not value:
        raise SystemExit(f"Required command not found: {name}")
    return value


def _repo_private_state(gh: str) -> bool | None:
    result = _run(
        [gh, "api", f"repos/{TELEMETRY_REPO}", "--jq", ".private"],
        check=False,
        capture=True,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip().lower() == "true"


def _ensure_private_repo(gh: str) -> None:
    private = _repo_private_state(gh)
    if private is None:
        print(f"Creating private telemetry repository: {TELEMETRY_REPO}")
        _run(
            [
                gh,
                "repo",
                "create",
                TELEMETRY_REPO,
                "--private",
                "--description",
                "Sanitized read-only IIOS factory telemetry. No broker or execution authority.",
            ]
        )
        private = _repo_private_state(gh)
    if private is not True:
        raise SystemExit(
            "Refusing activation: telemetry destination is not verified private"
        )


def _ensure_issue(gh: str) -> int:
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
    if issue_text:
        return int(issue_text.splitlines()[0].strip())

    body = (
        "IIOS FACTORY TELEMETRY — READ ONLY\n\n"
        "Waiting for the first sanitized local-ledger snapshot.\n\n"
        "No raw prompts, raw evidence, secrets, broker credentials, or live execution authority."
    )
    issue_text = _capture(
        [
            gh,
            "api",
            "--method",
            "POST",
            f"repos/{TELEMETRY_REPO}/issues",
            "-f",
            f"title={ISSUE_TITLE}",
            "-f",
            f"body={body}",
            "--jq",
            ".number",
        ]
    )
    return int(issue_text.strip())


def _prepare_worktree(git: str) -> tuple[str, str]:
    if not LIVE.exists():
        raise SystemExit(f"Live IIOS checkout not found: {LIVE}")
    if not LEDGER.exists():
        raise SystemExit(f"Live IIOS ledger not found: {LEDGER}")

    branch_before = _capture([git, "branch", "--show-current"], cwd=LIVE)
    status_before = _capture([git, "status", "--porcelain"], cwd=LIVE)

    _run([git, "fetch", "origin", BRANCH], cwd=LIVE)
    remote_ref = f"origin/{BRANCH}"

    if WORKTREE.exists():
        if not (WORKTREE / ".git").exists():
            raise SystemExit(
                f"9F telemetry path exists but is not a git worktree: {WORKTREE}"
            )
        worktree_status = _capture(
            [git, "status", "--porcelain"],
            cwd=WORKTREE,
        )
        if worktree_status:
            raise SystemExit(
                "Refusing to replace 9F telemetry worktree because it has local changes"
            )
        _run([git, "fetch", "origin", BRANCH], cwd=WORKTREE)
        _run([git, "reset", "--hard", remote_ref], cwd=WORKTREE)
    else:
        _run(
            [git, "worktree", "add", "--detach", str(WORKTREE), remote_ref],
            cwd=LIVE,
        )

    branch_after = _capture([git, "branch", "--show-current"], cwd=LIVE)
    status_after = _capture([git, "status", "--porcelain"], cwd=LIVE)
    if branch_after != branch_before or status_after != status_before:
        raise SystemExit(
            "Refusing activation: live IIOS checkout changed while preparing 9F"
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
        "No IIOS backend virtualenv Python found; refusing system-Python daemon fallback"
    )


def _exporter_command(
    python: Path,
    issue_number: int,
    *,
    stdout: bool,
) -> list[str]:
    exporter = WORKTREE / "scripts" / "iios_factory_telemetry_exporter.py"
    if not exporter.exists():
        raise SystemExit(f"9F telemetry exporter not found: {exporter}")
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
    ]
    if stdout:
        command.append("--stdout")
    return command


def _validate_first_snapshot(snapshot: dict[str, Any]) -> None:
    if snapshot.get("health", {}).get("state") == "TELEMETRY_UNAVAILABLE":
        raise SystemExit("First telemetry snapshot reports TELEMETRY_UNAVAILABLE")
    if snapshot.get("source", {}).get("mode") != "LOCAL_LEDGER_READ_ONLY":
        raise SystemExit("First telemetry snapshot is not verified local-ledger read-only")
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
    )
    leaked = [name for name in forbidden if name in serialized]
    if leaked:
        raise SystemExit(f"Refusing activation: forbidden telemetry fields found: {leaked}")


def _first_snapshot(python: Path, issue_number: int) -> dict[str, Any]:
    result = _run(
        _exporter_command(python, issue_number, stdout=True),
        cwd=WORKTREE,
        check=False,
        capture=True,
    )
    if result.returncode != 0:
        raise SystemExit(
            "First real-ledger telemetry publish failed:\n"
            + (result.stderr or result.stdout or "")[:3000]
        )
    try:
        snapshot = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Could not parse first telemetry snapshot: {exc}") from exc
    _validate_first_snapshot(snapshot)
    return snapshot


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
    path_parts = [gh_dir, *[item for item in current_path.split(":") if item]]
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
        "StandardOutPath": str(LOG_DIR / "factory-telemetry.out.log"),
        "StandardErrorPath": str(LOG_DIR / "factory-telemetry.err.log"),
    }
    with PLIST.open("wb") as handle:
        plistlib.dump(payload, handle, sort_keys=True)

    domain = f"gui/{os.getuid()}"
    _run(
        ["launchctl", "bootout", domain, str(PLIST)],
        check=False,
        capture=True,
    )
    _run(["launchctl", "bootstrap", domain, str(PLIST)])
    _run(["launchctl", "kickstart", "-k", f"{domain}/{LABEL}"])
    _run(["launchctl", "print", f"{domain}/{LABEL}"], capture=True)


def _verify_private_issue(gh: str, issue_number: int, fingerprint: str) -> None:
    body = _capture(
        [
            gh,
            "api",
            f"repos/{TELEMETRY_REPO}/issues/{issue_number}",
            "--jq",
            ".body",
        ]
    )
    if "IIOS FACTORY TELEMETRY — READ ONLY" not in body:
        raise SystemExit("Private telemetry issue is missing the read-only header")
    if fingerprint and fingerprint not in body:
        raise SystemExit("Private telemetry issue does not contain the first snapshot fingerprint")
    if "LOCAL_LEDGER_READ_ONLY" not in body:
        raise SystemExit("Private telemetry issue does not show local-ledger read-only provenance")


def main() -> int:
    if sys.platform != "darwin":
        raise SystemExit("Batch 9F activation is intentionally macOS-only for this IIOS runtime")

    git = _require_command("git")
    gh = _require_command("gh")
    _require_command("launchctl")
    _run([gh, "auth", "status"])

    print("IIOS BATCH 9F — PRIVATE FACTORY TELEMETRY ACTIVATION")
    print(f"Live ledger: {LEDGER}")
    print(f"Telemetry destination: {TELEMETRY_REPO} (PRIVATE REQUIRED)")
    print("Direction: OUTBOUND ONLY")
    print("Ledger access: SQLITE READ ONLY")
    print("Publish cadence: 60 seconds")
    print("Broker connected: FALSE")
    print("Live execution: FALSE")

    branch_before, status_before = _prepare_worktree(git)
    _ensure_private_repo(gh)
    issue_number = _ensure_issue(gh)
    python = _resolve_python()
    snapshot = _first_snapshot(python, issue_number)
    fingerprint = str(snapshot.get("fingerprint") or "")
    _verify_private_issue(gh, issue_number, fingerprint)
    _install_launch_agent(python, gh, issue_number)

    branch_after = _capture([git, "branch", "--show-current"], cwd=LIVE)
    status_after = _capture([git, "status", "--porcelain"], cwd=LIVE)
    if branch_after != branch_before or status_after != status_before:
        raise SystemExit("Live IIOS checkout changed during telemetry activation")

    summary = {
        "status": "BATCH9F_FACTORY_TELEMETRY_LIVE",
        "telemetry_repo": TELEMETRY_REPO,
        "telemetry_repo_private": True,
        "telemetry_issue": issue_number,
        "ledger": str(LEDGER),
        "ledger_mode": "READ_ONLY",
        "worktree": str(WORKTREE),
        "local_snapshot": str(LOCAL_SNAPSHOT),
        "launch_agent": str(PLIST),
        "publish_interval_seconds": INTERVAL_SECONDS,
        "first_fingerprint": fingerprint,
        "factory_health": snapshot.get("health", {}).get("state"),
        "radar_cadence": snapshot.get("cadence", {}).get("9E"),
        "paper_nav": snapshot.get("paper_fund", {}).get("nav"),
        "paper_total_pnl": snapshot.get("paper_fund", {}).get("total_pnl"),
        "live_execution": False,
        "broker_connected": False,
        "live_checkout_unchanged": True,
    }
    print(json.dumps(summary, indent=2, sort_keys=True, default=str))
    print(
        "\nBatch 9F is active. The factory remains paper-only and the Mac exposes no inbound service."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
