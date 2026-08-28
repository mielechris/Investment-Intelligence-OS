#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import plistlib
import shutil
import subprocess
import sys
from pathlib import Path

BRANCH = "feature/batch9i-shadow-counterfactual-lab"
DEFAULT_OWNER = "mielechris"
DEFAULT_TELEMETRY_REPO_NAME = "IIOS-Telemetry"
SHADOW_ISSUE_TITLE = "IIOS Shadow Strategy - Latest"
SHADOW_LABEL = "com.iios.shadow-counterfactual"
INTERVAL_SECONDS = 1800

LIVE = Path(
    os.getenv(
        "IIOS_LIVE_CHECKOUT",
        "/Users/crm/Documents/GitHub/Investment-Intelligence-OS-Batch8",
    )
).expanduser()
WORKTREE = Path(
    os.getenv(
        "IIOS_9I_WORKTREE",
        "/Users/crm/Documents/GitHub/Investment-Intelligence-OS-batch9i-shadow-counterfactual",
    )
).expanduser()
LEDGER = Path(
    os.getenv(
        "IIOS_DB_PATH",
        str(LIVE / "BACK END" / "backend" / "iios_ledger.db"),
    )
).expanduser()
STATE_DIR = Path.home() / "Library" / "Application Support" / "IIOS" / "market-validation"
LOG_DIR = Path.home() / "Library" / "Logs" / "IIOS"
LAUNCH_DIR = Path.home() / "Library" / "LaunchAgents"
PLIST = LAUNCH_DIR / f"{SHADOW_LABEL}.plist"
REQUIRED_9H_PLISTS = (
    LAUNCH_DIR / "com.iios.market-benchmark.plist",
    LAUNCH_DIR / "com.iios.market-validation.plist",
)

TELEMETRY_OWNER = os.getenv(
    "IIOS_TELEMETRY_GITHUB_OWNER",
    DEFAULT_OWNER,
).strip()
TELEMETRY_REPO_NAME = os.getenv(
    "IIOS_TELEMETRY_GITHUB_REPO_NAME",
    DEFAULT_TELEMETRY_REPO_NAME,
).strip()
TELEMETRY_REPO = f"{TELEMETRY_OWNER}/{TELEMETRY_REPO_NAME}"


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


def _require_9h_active() -> None:
    missing = [str(path) for path in REQUIRED_9H_PLISTS if not path.exists()]
    if missing:
        raise SystemExit(
            "Batch 9I requires Batch 9H to be active first; missing LaunchAgents: "
            + ", ".join(missing)
        )
    if not STATE_DIR.exists():
        raise SystemExit(
            "Batch 9I requires the Batch 9H market-validation state directory"
        )


def _require_private_repo(gh: str) -> None:
    result = _run(
        [gh, "api", f"repos/{TELEMETRY_REPO}", "--jq", ".private"],
        check=False,
        capture=True,
    )
    if result.returncode != 0 or result.stdout.strip().lower() != "true":
        raise SystemExit(
            "Refusing Batch 9I activation: IIOS telemetry repository is unavailable or not private"
        )


def _ensure_shadow_issue(gh: str) -> int:
    query = f"repos/{TELEMETRY_REPO}/issues?state=open&per_page=100"
    issue_text = _capture(
        [
            gh,
            "api",
            query,
            "--jq",
            f'.[] | select(.title == "{SHADOW_ISSUE_TITLE}") | .number',
        ]
    )
    if issue_text:
        return int(issue_text.splitlines()[0].strip())

    body = (
        "IIOS SHADOW STRATEGY — BATCH 9I READ ONLY\n\n"
        "Waiting for complete Batch 9H sessions. Counterfactual recommendations remain advisory only.\n\n"
        "No threshold auto-apply, no Committee/Risk changes, no broker or live execution authority."
    )
    created = _capture(
        [
            gh,
            "api",
            "--method",
            "POST",
            f"repos/{TELEMETRY_REPO}/issues",
            "-f",
            f"title={SHADOW_ISSUE_TITLE}",
            "-f",
            f"body={body}",
            "--jq",
            ".number",
        ]
    )
    return int(created.strip())


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
                f"9I path exists but is not a git worktree: {WORKTREE}"
            )
        if _capture([git, "status", "--porcelain"], cwd=WORKTREE):
            raise SystemExit(
                "Refusing to replace 9I worktree because it has local changes"
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
            "Refusing Batch 9I activation: live IIOS checkout changed while preparing shadow worktree"
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


def _shadow_command(python: Path, issue_number: int) -> list[str]:
    return [
        str(python),
        str(WORKTREE / "scripts" / "iios_shadow_counterfactual_lab.py"),
        "--db",
        str(LEDGER),
        "--state-dir",
        str(STATE_DIR),
        "--auto",
        "--github-repo",
        TELEMETRY_REPO,
        "--github-issue",
        str(issue_number),
    ]


def _first_shadow_check(python: Path, issue_number: int) -> dict:
    result = _run(
        _shadow_command(python, issue_number),
        cwd=WORKTREE,
        check=False,
        capture=True,
    )
    if result.returncode != 0:
        raise SystemExit(
            "First Batch 9I shadow check failed:\n"
            + (result.stderr or result.stdout or "")[:3000]
        )
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise SystemExit(
            f"Could not parse first Batch 9I shadow result: {exc}"
        ) from exc
    allowed = {
        "BATCH9I_SHADOW_COUNTERFACTUAL_COMPLETE",
        "SKIPPED_BEFORE_SHADOW_WINDOW",
        "SKIPPED_NON_MARKET_DAY",
        "SKIPPED_NO_COMPLETE_9H_SESSIONS",
        "SKIPPED_ALREADY_EVALUATED",
    }
    status = str(payload.get("status") or "")
    if status not in allowed:
        raise SystemExit(f"Unexpected first Batch 9I shadow status: {status}")
    if payload.get("live_execution") is True:
        raise SystemExit("Batch 9I shadow check reported live execution true")
    return payload


def _launch_path(gh: str) -> str:
    current_path = os.environ.get("PATH", "")
    parts = [
        str(Path(gh).parent),
        *[item for item in current_path.split(":") if item],
    ]
    return ":".join(dict.fromkeys(parts))


def _install_agent(
    python: Path,
    gh: str,
    issue_number: int,
) -> None:
    LAUNCH_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    backup = PLIST.with_suffix(".backup.plist")
    if PLIST.exists():
        shutil.copy2(PLIST, backup)

    payload = {
        "Label": SHADOW_LABEL,
        "ProgramArguments": _shadow_command(python, issue_number),
        "WorkingDirectory": str(WORKTREE),
        "RunAtLoad": True,
        "StartInterval": INTERVAL_SECONDS,
        "ProcessType": "Background",
        "EnvironmentVariables": {
            "PATH": _launch_path(gh),
            "PYTHONUNBUFFERED": "1",
        },
        "StandardOutPath": str(LOG_DIR / "shadow-counterfactual.out.log"),
        "StandardErrorPath": str(LOG_DIR / "shadow-counterfactual.err.log"),
    }

    temporary = PLIST.with_suffix(".tmp.plist")
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
            ["launchctl", "kickstart", "-k", f"{domain}/{SHADOW_LABEL}"]
        )
        _run(
            ["launchctl", "print", f"{domain}/{SHADOW_LABEL}"],
            capture=True,
        )
    except Exception:
        _run(
            ["launchctl", "bootout", domain, str(PLIST)],
            check=False,
            capture=True,
        )
        if backup.exists():
            shutil.copy2(backup, PLIST)
            _run(
                ["launchctl", "bootstrap", domain, str(PLIST)],
                check=False,
                capture=True,
            )
            _run(
                ["launchctl", "kickstart", "-k", f"{domain}/{SHADOW_LABEL}"],
                check=False,
                capture=True,
            )
        raise


def main() -> int:
    if sys.platform != "darwin":
        raise SystemExit(
            "Batch 9I activation is intentionally macOS-only for this IIOS runtime"
        )

    git = _require_command("git")
    gh = _require_command("gh")
    _require_command("launchctl")
    _run([gh, "auth", "status"])

    print("IIOS BATCH 9I — SHADOW STRATEGY + COUNTERFACTUAL LAB ACTIVATION")
    print(f"Live ledger: {LEDGER}")
    print(f"Private shadow destination: {TELEMETRY_REPO}")
    print("Source benchmark: BATCH 9H INDEPENDENT MARKET VALIDATION")
    print("Factory history access: SQLITE READ ONLY")
    print(f"Shadow check cadence: {INTERVAL_SECONDS} seconds")
    print("Minimum complete sessions before threshold advice: 5")
    print("Threshold recommendations: HUMAN REVIEW ONLY")
    print("Automatic threshold changes: FALSE")
    print("Committee/Risk gate changes: FALSE")
    print("Broker connected: FALSE")
    print("Live execution: FALSE")

    _require_9h_active()
    branch_before, status_before = _prepare_worktree(git)
    _require_private_repo(gh)
    shadow_issue = _ensure_shadow_issue(gh)
    python = _resolve_python()
    first_check = _first_shadow_check(python, shadow_issue)
    _install_agent(python, gh, shadow_issue)

    branch_after = _capture([git, "branch", "--show-current"], cwd=LIVE)
    status_after = _capture([git, "status", "--porcelain"], cwd=LIVE)
    if branch_after != branch_before or status_after != status_before:
        raise SystemExit("Live IIOS checkout changed during Batch 9I activation")

    summary = {
        "status": "BATCH9I_SHADOW_COUNTERFACTUAL_LIVE",
        "worktree": str(WORKTREE),
        "state_dir": str(STATE_DIR),
        "shadow_repo": TELEMETRY_REPO,
        "shadow_repo_private": True,
        "shadow_issue": shadow_issue,
        "shadow_label": SHADOW_LABEL,
        "shadow_interval_seconds": INTERVAL_SECONDS,
        "first_shadow_status": first_check.get("status"),
        "minimum_complete_sessions_for_advice": 5,
        "ledger_mode": "READ_ONLY",
        "auto_apply_threshold_changes": False,
        "committee_gate_change_authority": False,
        "risk_gate_change_authority": False,
        "broker_connected": False,
        "live_execution": False,
        "live_checkout_unchanged": True,
        "batch9g_telemetry_untouched": True,
        "batch9h_validation_untouched": True,
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    print(
        "\nBatch 9I is active in shadow-only mode. 9G telemetry and 9H benchmark/validation remain untouched."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
