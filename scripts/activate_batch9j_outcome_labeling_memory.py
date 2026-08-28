#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import plistlib
import shutil
import subprocess
import sys
from pathlib import Path

BRANCH = "feature/batch9j-outcome-labeling-memory"
DEFAULT_OWNER = "mielechris"
DEFAULT_TELEMETRY_REPO_NAME = "IIOS-Telemetry"
ISSUE_TITLE = "IIOS Outcome Learning - Latest"
LABEL = "com.iios.outcome-learning"
INTERVAL_SECONDS = 3600

LIVE = Path(
    os.getenv(
        "IIOS_LIVE_CHECKOUT",
        "/Users/crm/Documents/GitHub/Investment-Intelligence-OS-Batch8",
    )
).expanduser()
WORKTREE = Path(
    os.getenv(
        "IIOS_9J_WORKTREE",
        "/Users/crm/Documents/GitHub/Investment-Intelligence-OS-batch9j-outcome-learning",
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
PLIST = LAUNCH_DIR / f"{LABEL}.plist"
TELEMETRY_OWNER = os.getenv("IIOS_TELEMETRY_GITHUB_OWNER", DEFAULT_OWNER).strip()
TELEMETRY_REPO_NAME = os.getenv(
    "IIOS_TELEMETRY_GITHUB_REPO_NAME",
    DEFAULT_TELEMETRY_REPO_NAME,
).strip()
TELEMETRY_REPO = f"{TELEMETRY_OWNER}/{TELEMETRY_REPO_NAME}"

PROTECTED_PLISTS = (
    LAUNCH_DIR / "com.iios.factory-telemetry.plist",
    LAUNCH_DIR / "com.iios.market-benchmark.plist",
    LAUNCH_DIR / "com.iios.market-validation.plist",
    LAUNCH_DIR / "com.iios.shadow-counterfactual.plist",
)


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
        raise RuntimeError(f"Command failed ({result.returncode}): {' '.join(args[:6])}\n{detail[:2500]}")
    return result


def _capture(args: list[str], *, cwd: Path | None = None) -> str:
    return _run(args, cwd=cwd, capture=True).stdout.strip()


def _require_command(name: str) -> str:
    value = shutil.which(name)
    if not value:
        raise SystemExit(f"Required command not found: {name}")
    return value


def _file_hash(path: Path) -> str | None:
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _protected_fingerprints() -> dict[str, str | None]:
    return {str(path): _file_hash(path) for path in PROTECTED_PLISTS}


def _require_private_repo(gh: str) -> None:
    result = _run(
        [gh, "api", f"repos/{TELEMETRY_REPO}", "--jq", ".private"],
        check=False,
        capture=True,
    )
    if result.returncode != 0 or result.stdout.strip().lower() != "true":
        raise SystemExit("Refusing Batch 9J activation: IIOS telemetry repository is unavailable or not private")


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
        "IIOS OUTCOME LEARNING — BATCH 9J READ ONLY\n\n"
        "Waiting for complete Batch 9H sessions and forward outcome horizons.\n\n"
        "Outcome labels are governed review inputs only. No automatic Judgment Bank writes, no authority changes, no live execution."
    )
    created = _capture(
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
            raise SystemExit(f"9J path exists but is not a git worktree: {WORKTREE}")
        if _capture([git, "status", "--porcelain"], cwd=WORKTREE):
            raise SystemExit("Refusing to replace 9J worktree because it has local changes")
        _run([git, "fetch", "origin", BRANCH], cwd=WORKTREE)
        _run([git, "reset", "--hard", remote_ref], cwd=WORKTREE)
    else:
        _run([git, "worktree", "add", "--detach", str(WORKTREE), remote_ref], cwd=LIVE)
    branch_after = _capture([git, "branch", "--show-current"], cwd=LIVE)
    status_after = _capture([git, "status", "--porcelain"], cwd=LIVE)
    if branch_after != branch_before or status_after != status_before:
        raise SystemExit("Refusing activation: live IIOS checkout changed while preparing 9J")
    return branch_before, status_before


def _resolve_python() -> Path:
    candidates = (
        LIVE / "BACK END" / "backend" / ".venv" / "bin" / "python",
        Path("/Users/crm/Documents/GitHub/Investment-Intelligence-OS/BACK END/backend/.venv/bin/python"),
    )
    for candidate in candidates:
        if candidate.exists() and os.access(candidate, os.X_OK):
            return candidate
    raise SystemExit("No IIOS backend virtualenv Python found; refusing system-Python daemon fallback")


def _worker_command(python: Path, issue_number: int) -> list[str]:
    return [
        str(python),
        str(WORKTREE / "scripts" / "iios_outcome_learning_memory.py"),
        "--db",
        str(LEDGER),
        "--state-dir",
        str(STATE_DIR),
        "--github-repo",
        TELEMETRY_REPO,
        "--github-issue",
        str(issue_number),
    ]


def _first_refresh(python: Path, issue_number: int) -> dict:
    result = _run(
        _worker_command(python, issue_number),
        cwd=WORKTREE,
        check=False,
        capture=True,
    )
    if result.returncode != 0:
        raise SystemExit("First Batch 9J outcome-learning refresh failed:\n" + (result.stderr or result.stdout or "")[:3500])
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Could not parse first Batch 9J refresh result: {exc}") from exc
    if payload.get("status") != "BATCH9J_OUTCOME_LEARNING_REFRESH_COMPLETE":
        raise SystemExit(f"Unexpected Batch 9J first-refresh status: {payload.get('status')}")
    if payload.get("ledger_mode") != "READ_ONLY":
        raise SystemExit("Batch 9J first refresh did not preserve read-only ledger mode")
    if payload.get("auto_write_judgment_bank") is not False:
        raise SystemExit("Batch 9J first refresh attempted automatic Judgment Bank authority")
    if payload.get("live_execution") is not False:
        raise SystemExit("Batch 9J first refresh did not keep live execution false")
    return payload


def _launch_path(gh: str) -> str:
    current_path = os.environ.get("PATH", "")
    parts = [str(Path(gh).parent), *[item for item in current_path.split(":") if item]]
    return ":".join(dict.fromkeys(parts))


def _install_agent(python: Path, gh: str, issue_number: int) -> None:
    LAUNCH_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    backup = PLIST.with_suffix(".backup.plist")
    if PLIST.exists():
        shutil.copy2(PLIST, backup)
    payload = {
        "Label": LABEL,
        "ProgramArguments": _worker_command(python, issue_number),
        "WorkingDirectory": str(WORKTREE),
        "RunAtLoad": True,
        "StartInterval": INTERVAL_SECONDS,
        "ProcessType": "Background",
        "EnvironmentVariables": {
            "PATH": _launch_path(gh),
            "PYTHONUNBUFFERED": "1",
        },
        "StandardOutPath": str(LOG_DIR / "outcome-learning.out.log"),
        "StandardErrorPath": str(LOG_DIR / "outcome-learning.err.log"),
    }
    temporary = PLIST.with_suffix(".tmp.plist")
    with temporary.open("wb") as handle:
        plistlib.dump(payload, handle, sort_keys=True)
    temporary.replace(PLIST)
    domain = f"gui/{os.getuid()}"
    _run(["launchctl", "bootout", domain, str(PLIST)], check=False, capture=True)
    try:
        _run(["launchctl", "bootstrap", domain, str(PLIST)])
        _run(["launchctl", "kickstart", "-k", f"{domain}/{LABEL}"])
        _run(["launchctl", "print", f"{domain}/{LABEL}"], capture=True)
    except Exception:
        _run(["launchctl", "bootout", domain, str(PLIST)], check=False, capture=True)
        if backup.exists():
            shutil.copy2(backup, PLIST)
            _run(["launchctl", "bootstrap", domain, str(PLIST)], check=False, capture=True)
            _run(["launchctl", "kickstart", "-k", f"{domain}/{LABEL}"], check=False, capture=True)
        raise


def main() -> int:
    if sys.platform != "darwin":
        raise SystemExit("Batch 9J activation is intentionally macOS-only for this IIOS runtime")
    git = _require_command("git")
    gh = _require_command("gh")
    _require_command("launchctl")
    _run([gh, "auth", "status"])

    print("IIOS BATCH 9J — OUTCOME LABELING + LEARNING MEMORY ACTIVATION")
    print(f"Live ledger: {LEDGER}")
    print(f"Private outcome destination: {TELEMETRY_REPO}")
    print("Source sessions: COMPLETE BATCH 9H ONLY")
    print("Forward horizons: +1H / CLOSE / NEXT SESSION / FIFTH SESSION")
    print(f"Outcome refresh cadence: {INTERVAL_SECONDS} seconds")
    print("Ledger access: SQLITE READ ONLY")
    print("Judgment Bank automatic writes: FALSE")
    print("Automatic agent weight changes: FALSE")
    print("Browser-ready JSON: ENABLED")
    print("Broker connected: FALSE")
    print("Live execution: FALSE")

    branch_before, status_before = _prepare_worktree(git)
    _require_private_repo(gh)
    issue_number = _ensure_issue(gh)
    python = _resolve_python()
    protected_before = _protected_fingerprints()
    first = _first_refresh(python, issue_number)
    _install_agent(python, gh, issue_number)
    protected_after = _protected_fingerprints()
    if protected_after != protected_before:
        raise SystemExit("Refusing Batch 9J activation: a protected 9G/9H/9I LaunchAgent changed")

    branch_after = _capture([git, "branch", "--show-current"], cwd=LIVE)
    status_after = _capture([git, "status", "--porcelain"], cwd=LIVE)
    if branch_after != branch_before or status_after != status_before:
        raise SystemExit("Live IIOS checkout changed during Batch 9J activation")

    summary = {
        "status": "BATCH9J_OUTCOME_LABELING_MEMORY_LIVE",
        "worktree": str(WORKTREE),
        "state_dir": str(STATE_DIR),
        "outcome_repo": TELEMETRY_REPO,
        "outcome_repo_private": True,
        "outcome_issue": issue_number,
        "worker_label": LABEL,
        "worker_interval_seconds": INTERVAL_SECONDS,
        "first_refresh_status": first.get("learning_status"),
        "complete_session_count": first.get("complete_session_count"),
        "outcome_count": first.get("outcome_count"),
        "mature_5d_count": first.get("mature_5d_count"),
        "browser_ready_snapshot": first.get("browser_ready_snapshot"),
        "ledger_mode": "READ_ONLY",
        "auto_write_judgment_bank": False,
        "automatic_agent_weight_changes": False,
        "batch9g_telemetry_untouched": True,
        "batch9h_benchmark_validation_untouched": True,
        "batch9i_shadow_untouched": True,
        "protected_launch_agents_unchanged": True,
        "broker_connected": False,
        "live_execution": False,
        "live_checkout_unchanged": True,
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    print("\nBatch 9J is active. Outcome labels remain review-only; 9G, 9H, and 9I remain untouched.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
