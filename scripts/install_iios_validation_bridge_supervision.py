#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import plistlib
import shutil
import signal
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, time as clock_time, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote
from zoneinfo import ZoneInfo


REPO = Path(__file__).resolve().parents[1]
SOURCE_CONFIG = REPO / "config" / "iios_validation_bridge_supervision.json"
SOURCE_WORKER = REPO / "scripts" / "iios_validation_bridge_worker.py"
SOURCE_SUPERVISOR = REPO / "scripts" / "iios_validation_bridge_supervisor.py"
LAUNCH_AGENTS = Path.home() / "Library" / "LaunchAgents"
NEW_YORK = ZoneInfo("America/New_York")
UNIVERSE_MAX_AGE_HOURS = 36.0


def expand(value: str) -> Path:
    return Path(os.path.expanduser(value)).resolve()


def read_source_config() -> dict[str, Any]:
    value = json.loads(SOURCE_CONFIG.read_text(encoding="utf-8"))
    required = {"9H_COLLECTOR", "9H_VALIDATOR", "9I_SHADOW"}
    if not isinstance(value, dict) or set((value.get("services") or {}).keys()) != required:
        raise SystemExit("Validation bridge source config must define exactly 9H_COLLECTOR, 9H_VALIDATOR, and 9I_SHADOW")
    return value


def run(args: list[str], *, cwd: Path | None = None, check: bool = True, timeout: int = 60) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            args,
            cwd=str(cwd) if cwd else None,
            text=True,
            capture_output=True,
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        result = subprocess.CompletedProcess(args, 124, exc.stdout or "", exc.stderr or "timeout")
    if check and result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(f"Command failed rc={result.returncode}: {' '.join(args[:6])}\n{detail[:2500]}")
    return result


def require_command(name: str) -> str:
    value = shutil.which(name)
    if not value:
        raise SystemExit(f"Required command not found: {name}")
    return value


def launchctl(*args: str, timeout: int = 20) -> subprocess.CompletedProcess[str]:
    return run(["launchctl", *args], check=False, timeout=timeout)


def domain() -> str:
    return f"gui/{os.getuid()}"


def pgrep(fragment: str) -> list[int]:
    result = run(["pgrep", "-f", fragment], check=False, timeout=10)
    if result.returncode not in (0, 1):
        return []
    output: list[int] = []
    for raw in (result.stdout or "").splitlines():
        try:
            pid = int(raw.strip())
        except ValueError:
            continue
        if pid != os.getpid():
            output.append(pid)
    return sorted(set(output))


def alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False


def stop_pids(pids: list[int], timeout_seconds: int = 10) -> None:
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            pass
    deadline = time.time() + timeout_seconds
    remaining = list(pids)
    while remaining and time.time() < deadline:
        time.sleep(0.25)
        remaining = [pid for pid in remaining if alive(pid)]
    for pid in remaining:
        try:
            os.kill(pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass


def bootout_label(label: str) -> None:
    plist = LAUNCH_AGENTS / f"{label}.plist"
    if plist.exists():
        launchctl("bootout", domain(), str(plist))
    else:
        launchctl("bootout", f"{domain()}/{label}")


def parse_time(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def market_session_open() -> bool:
    current = datetime.now(NEW_YORK)
    if current.weekday() >= 5:
        return False
    minute = current.hour * 60 + current.minute
    return 570 <= minute < 970


def require_private_repo(gh: str, repo: str) -> None:
    result = run([gh, "api", f"repos/{repo}", "--jq", ".private"], check=False, timeout=30)
    if result.returncode != 0 or result.stdout.strip().lower() != "true":
        raise SystemExit("Refusing validation bridge activation: telemetry repository is unavailable or not private")


def ensure_issue(gh: str, repo: str, title: str, waiting_body: str) -> int:
    result = run(
        [gh, "api", f"repos/{repo}/issues?state=open&per_page=100", "--jq", f'.[] | select(.title == "{title}") | .number'],
        timeout=30,
    )
    if result.stdout.strip():
        return int(result.stdout.splitlines()[0].strip())
    created = run(
        [
            gh,
            "api",
            "--method",
            "POST",
            f"repos/{repo}/issues",
            "-f",
            f"title={title}",
            "-f",
            f"body={waiting_body}",
            "--jq",
            ".number",
        ],
        timeout=30,
    )
    return int(created.stdout.strip())


def prepare_worktree(git: str, live: Path, worktree: Path, branch: str) -> None:
    run([git, "fetch", "origin", branch], cwd=live, timeout=90)
    remote = f"origin/{branch}"
    if worktree.exists():
        if not (worktree / ".git").exists():
            raise SystemExit(f"Path exists but is not a git worktree: {worktree}")
        dirty = run([git, "status", "--porcelain"], cwd=worktree).stdout.strip()
        if dirty:
            raise SystemExit(f"Refusing to replace dirty validation worktree: {worktree}")
        run([git, "fetch", "origin", branch], cwd=worktree, timeout=90)
        run([git, "reset", "--hard", remote], cwd=worktree, timeout=60)
    else:
        run([git, "worktree", "add", "--detach", str(worktree), remote], cwd=live, timeout=90)


def resolve_python(live: Path) -> Path:
    candidates = (
        live / "BACK END" / "backend" / ".venv" / "bin" / "python",
        Path("/Users/crm/Documents/GitHub/Investment-Intelligence-OS/BACK END/backend/.venv/bin/python"),
    )
    for candidate in candidates:
        if candidate.exists() and os.access(candidate, os.X_OK):
            return candidate
    raise SystemExit("No IIOS backend virtualenv Python found")


def seed_universe_cache(ledger: Path, state_dir: Path) -> dict[str, Any]:
    uri = f"file:{quote(str(ledger), safe='/')}?mode=ro"
    connection = sqlite3.connect(uri, uri=True, timeout=30)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            "SELECT payload_json, created_at FROM ledger_objects WHERE object_type = ? ORDER BY created_at DESC LIMIT 100",
            ("production_index_universe_snapshot",),
        ).fetchall()
    finally:
        connection.close()

    current = datetime.now(timezone.utc)
    selected: dict[str, Any] | None = None
    selected_at: datetime | None = None
    for row in rows:
        try:
            payload = json.loads(row["payload_json"])
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue
        if payload.get("verified_complete") is not True or payload.get("strict_membership") is not True:
            continue
        created = parse_time(payload.get("created_at") or payload.get("as_of") or row["created_at"])
        if created is None or (current - created).total_seconds() > UNIVERSE_MAX_AGE_HOURS * 3600:
            continue
        if not isinstance(payload.get("symbols"), list) or not payload.get("symbols"):
            continue
        selected = payload
        selected_at = created
        break
    if selected is None or selected_at is None:
        raise SystemExit("No fresh verified production universe is available to seed Batch 9H")

    symbols: list[str] = []
    seen: set[str] = set()
    for row in selected.get("symbols") or []:
        ticker = str(row.get("ticker") if isinstance(row, dict) else row or "").strip().upper()
        if ticker and ticker not in seen:
            seen.add(ticker)
            symbols.append(ticker)
    if not symbols:
        raise SystemExit("Verified production universe contained no usable symbols")

    state_dir.mkdir(parents=True, exist_ok=True)
    cache_path = state_dir / "benchmark_universe.json"
    payload = {
        "schema_version": "batch9h-benchmark-universe-v1",
        "source": "LIVE_VERIFIED_PRODUCTION_UNIVERSE_SEED",
        "verified_complete": True,
        "strict_membership": True,
        "symbols": symbols,
        "symbol_count": len(symbols),
        "source_lineage": selected.get("source_lineage") or [],
        "source_snapshot_id": selected.get("production_index_universe_snapshot_id"),
        "official_capture_created_at": selected_at.isoformat(),
        "cached_at": current.isoformat(),
        "activation_seed_ledger_mode": "READ_ONLY",
        "collector_ledger_read": False,
        "collector_ledger_write": False,
        "independent_of_iios_promotion_decisions": True,
        "live_execution": False,
    }
    temporary = cache_path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(cache_path)
    return payload


def runtime_paths(config: dict[str, Any]) -> dict[str, Path]:
    root = expand(str(config.get("runtime_root") or "~/.iios/validation-bridge"))
    return {
        "root": root,
        "bin": root / "bin",
        "config": root / "config.json",
        "worker": root / "bin" / "iios_validation_bridge_worker.py",
        "supervisor": root / "bin" / "iios_validation_bridge_supervisor.py",
        "plist": LAUNCH_AGENTS / f"{config['supervisor_label']}.plist",
        "legacy_backup": root / "legacy-plists",
    }


def write_command(paths: dict[str, Path], service_key: str, title: str) -> Path:
    command_path = paths["root"] / f"start_{service_key.lower()}.command"
    safe_title = title.replace('"', "")
    text = (
        "#!/bin/zsh\n"
        f"printf '\\033]0;{safe_title}\\007'\n"
        f"exec /usr/bin/python3 '{paths['worker']}' --config '{paths['config']}' --service {service_key}\n"
    )
    command_path.write_text(text, encoding="utf-8")
    command_path.chmod(0o755)
    return command_path


def supervisor_plist(config: dict[str, Any], paths: dict[str, Path]) -> dict[str, Any]:
    log_dir = expand(str(config.get("log_directory") or "~/.iios/logs"))
    log_dir.mkdir(parents=True, exist_ok=True)
    return {
        "Label": str(config["supervisor_label"]),
        "ProgramArguments": [
            "/usr/bin/python3",
            str(paths["supervisor"]),
            "--config",
            str(paths["config"]),
        ],
        "WorkingDirectory": str(paths["root"]),
        "RunAtLoad": True,
        "StartInterval": max(300, int(config.get("supervisor_interval_seconds") or 300)),
        "ProcessType": "Background",
        "LowPriorityIO": True,
        "StandardOutPath": str(log_dir / "validation-bridge-supervisor.launchd.out.log"),
        "StandardErrorPath": str(log_dir / "validation-bridge-supervisor.launchd.err.log"),
        "EnvironmentVariables": {"PYTHONUNBUFFERED": "1"},
    }


def build_runtime_config(config: dict[str, Any], *, gh: str, python: Path, issue_9h: int, issue_9i: int) -> dict[str, Any]:
    runtime = json.loads(json.dumps(config))
    state_dir = expand(str(config["state_directory"]))
    ledger = expand(str(config["ledger_path"]))
    repo = str(config["telemetry_repo"])
    current_path = os.environ.get("PATH", "")
    runtime["path_env"] = ":".join(dict.fromkeys([str(Path(gh).parent), *[item for item in current_path.split(":") if item]]))
    runtime["runtime_root"] = str(expand(str(config["runtime_root"])))
    runtime["heartbeat_directory"] = str(expand(str(config["heartbeat_directory"])))
    runtime["log_directory"] = str(expand(str(config["log_directory"])))
    runtime["state_directory"] = str(state_dir)
    runtime["ledger_path"] = str(ledger)

    collector = runtime["services"]["9H_COLLECTOR"]
    collector["working_directory"] = str(expand(str(collector["worktree"])))
    collector["command"] = [
        str(python),
        str(expand(str(collector["worktree"])) / collector["script"]),
        "--state-dir",
        str(state_dir),
    ]

    validator = runtime["services"]["9H_VALIDATOR"]
    validator["working_directory"] = str(expand(str(validator["worktree"])))
    validator["command"] = [
        str(python),
        str(expand(str(validator["worktree"])) / validator["script"]),
        "--db",
        str(ledger),
        "--state-dir",
        str(state_dir),
        "--auto",
        "--github-repo",
        repo,
        "--github-issue",
        str(issue_9h),
    ]

    shadow = runtime["services"]["9I_SHADOW"]
    shadow["working_directory"] = str(expand(str(shadow["worktree"])))
    shadow["command"] = [
        str(python),
        str(expand(str(shadow["worktree"])) / shadow["script"]),
        "--db",
        str(ledger),
        "--state-dir",
        str(state_dir),
        "--auto",
        "--github-repo",
        repo,
        "--github-issue",
        str(issue_9i),
    ]
    runtime["resolved_issues"] = {"9H": issue_9h, "9I": issue_9i}
    return runtime


def validate(config: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for source in (SOURCE_WORKER, SOURCE_SUPERVISOR):
        if not source.exists():
            errors.append(f"Missing source: {source}")
    live = expand(str(config["live_checkout"]))
    ledger = expand(str(config["ledger_path"]))
    if not live.exists():
        errors.append(f"Live checkout not found: {live}")
    if not ledger.exists():
        errors.append(f"Ledger not found: {ledger}")
    safety = config.get("safety") or {}
    for key in ("9A_touched", "9B_touched", "9E_touched", "9G_touched", "9J_touched"):
        if safety.get(key) is not False:
            errors.append(f"Safety contract requires {key}=false")
    if safety.get("live_execution") is not False or safety.get("trade_execution_permission") is not False:
        errors.append("Live/trade execution must remain false")
    return errors


def print_plan(config: dict[str, Any]) -> int:
    errors = validate(config)
    print("=" * 80)
    print("IIOS 9H/9I VALIDATION TERMINAL-BRIDGE — PLAN")
    print("=" * 80)
    print("Runtime mutation: NONE")
    print("Purpose: replace direct launchd access to ~/Documents/GitHub for 9H/9I")
    print("Managed: 9H collector, 9H validator, 9I shadow lab")
    print("9A/9B/9E/9G/9J: UNTOUCHED")
    print("launchd runtime root:", expand(str(config["runtime_root"])))
    print("9H collector cadence: 5 minutes")
    print("9H validator cadence: 15 minutes")
    print("9I shadow cadence: 30 minutes")
    print("9I minimum complete 9H sessions for advice: 5 (unchanged)")
    print("Live execution: FALSE / UNCHANGED")
    if market_session_open():
        print("SESSION GUARD: ACTIVE — activation will refuse until after 16:10 ET")
    if errors:
        print("VALIDATION ERRORS:")
        for error in errors:
            print(" -", error)
        return 2
    print("Validation: PASS")
    print("Activate after the market session with: --activate")
    return 0


def activate(config: dict[str, Any], *, force_session_migration: bool = False) -> int:
    if sys.platform != "darwin":
        raise SystemExit("Validation bridge activation is macOS-only")
    if market_session_open() and not force_session_migration:
        raise SystemExit("Refusing to migrate 9H during the regular session. Preserve today's full-session benchmark and activate after 16:10 ET.")
    errors = validate(config)
    if errors:
        for error in errors:
            print(error)
        return 2

    git = require_command("git")
    gh = require_command("gh")
    require_command("launchctl")
    run([gh, "auth", "status"], timeout=30)
    repo = str(config["telemetry_repo"])
    require_private_repo(gh, repo)

    live = expand(str(config["live_checkout"]))
    branch_before = run([git, "branch", "--show-current"], cwd=live).stdout.strip()
    status_before = run([git, "status", "--porcelain"], cwd=live).stdout.strip()

    worktrees: dict[tuple[str, str], Path] = {}
    for service in config["services"].values():
        key = (str(service["branch"]), str(service["worktree"]))
        worktrees[key] = expand(str(service["worktree"]))
    for (branch, _), worktree in worktrees.items():
        prepare_worktree(git, live, worktree, branch)

    python = resolve_python(live)
    state_dir = expand(str(config["state_directory"]))
    universe = seed_universe_cache(expand(str(config["ledger_path"])), state_dir)
    issue_9h = ensure_issue(
        gh,
        repo,
        str(config["services"]["9H_VALIDATOR"]["github_issue_title"]),
        "IIOS MARKET VALIDATION — BATCH 9H READ ONLY\n\nWaiting for the next complete end-of-session validation report.",
    )
    issue_9i = ensure_issue(
        gh,
        repo,
        str(config["services"]["9I_SHADOW"]["github_issue_title"]),
        "IIOS SHADOW STRATEGY — BATCH 9I READ ONLY\n\nWaiting for complete Batch 9H sessions. Counterfactual recommendations remain advisory only.",
    )

    paths = runtime_paths(config)
    paths["bin"].mkdir(parents=True, exist_ok=True)
    paths["legacy_backup"].mkdir(parents=True, exist_ok=True)
    expand(str(config["heartbeat_directory"])).mkdir(parents=True, exist_ok=True)
    expand(str(config["log_directory"])).mkdir(parents=True, exist_ok=True)

    # Stop only the legacy 9H/9I services. Core factory workers are not represented here.
    for label in config.get("legacy_labels") or []:
        bootout_label(str(label))
        old_plist = LAUNCH_AGENTS / f"{label}.plist"
        if old_plist.exists():
            destination = paths["legacy_backup"] / old_plist.name
            shutil.move(str(old_plist), str(destination))
    bootout_label(str(config["supervisor_label"]))

    stopped: dict[str, list[int]] = {}
    for service_key, service in config["services"].items():
        pids = pgrep(str(service["legacy_process_fragment"]))
        stopped[service_key] = pids
        stop_pids(pids)

    shutil.copy2(SOURCE_WORKER, paths["worker"])
    shutil.copy2(SOURCE_SUPERVISOR, paths["supervisor"])
    paths["worker"].chmod(0o755)
    paths["supervisor"].chmod(0o755)

    runtime = build_runtime_config(config, gh=gh, python=python, issue_9h=issue_9h, issue_9i=issue_9i)
    paths["config"].write_text(json.dumps(runtime, indent=2, sort_keys=True), encoding="utf-8")
    commands: dict[str, Path] = {}
    for service_key, service in runtime["services"].items():
        commands[service_key] = write_command(paths, service_key, str(service["terminal_title"]))

    LAUNCH_AGENTS.mkdir(parents=True, exist_ok=True)
    with paths["plist"].open("wb") as handle:
        plistlib.dump(supervisor_plist(runtime, paths), handle, sort_keys=True)
    boot = launchctl("bootstrap", domain(), str(paths["plist"]))
    failures: list[str] = []
    if boot.returncode != 0:
        failures.append(f"supervisor bootstrap failed rc={boot.returncode}: {(boot.stderr or boot.stdout).strip()}")
    else:
        launchctl("enable", f"{domain()}/{runtime['supervisor_label']}")

    opens: dict[str, int] = {}
    for service_key in ("9H_COLLECTOR", "9H_VALIDATOR", "9I_SHADOW"):
        result = run(
            ["/usr/bin/open", "-g", "-a", "Terminal", str(commands[service_key])],
            check=False,
            timeout=20,
        )
        opens[service_key] = result.returncode
        if result.returncode != 0:
            failures.append(f"{service_key} Terminal open failed rc={result.returncode}: {(result.stderr or result.stdout).strip()}")

    branch_after = run([git, "branch", "--show-current"], cwd=live).stdout.strip()
    status_after = run([git, "status", "--porcelain"], cwd=live).stdout.strip()
    if branch_after != branch_before or status_after != status_before:
        failures.append("Live Batch8 checkout changed during validation bridge activation")

    print("=" * 80)
    print("IIOS 9H/9I VALIDATION TERMINAL-BRIDGE ACTIVATED")
    print("=" * 80)
    print("Runtime root:", paths["root"])
    print("Supervisor:", runtime["supervisor_label"])
    print("Legacy 9H/9I LaunchAgents moved to:", paths["legacy_backup"])
    print("Prior validation PIDs stopped:", stopped)
    print("Initial Terminal opens:", opens)
    print("Seeded governed universe:", universe.get("symbol_count"), "symbols")
    print("9H issue:", issue_9h, "9I issue:", issue_9i)
    print("9A/9B/9E/9G/9J: UNTOUCHED")
    print("Live execution: FALSE / UNCHANGED")
    if failures:
        print("ACTIVATION ERRORS:")
        for failure in failures:
            print(" -", failure)
        return 2
    print("Activation: PASS")
    print("9H/9I now run under Terminal security context; launchd supervises only ~/.iios state.")
    return 0


def status(config: dict[str, Any]) -> int:
    paths = runtime_paths(config)
    result = launchctl("print", f"{domain()}/{config['supervisor_label']}")
    print("IIOS 9H/9I VALIDATION TERMINAL-BRIDGE STATUS")
    print(str(config["supervisor_label"]) + ":", "LOADED" if result.returncode == 0 else "NOT_LOADED")
    latest = paths["root"] / "latest_status.json"
    if latest.exists():
        print(latest.read_text(encoding="utf-8"))
    else:
        print("No supervisor status yet.")
    return 0 if result.returncode == 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Install IIOS Batch 9H/9I validation Terminal-Bridge supervision")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--activate", action="store_true")
    mode.add_argument("--status", action="store_true")
    parser.add_argument("--force-session-migration", action="store_true", help="Bypass regular-session migration guard; not recommended")
    args = parser.parse_args()
    config = read_source_config()
    if args.activate:
        return activate(config, force_session_migration=args.force_session_migration)
    if args.status:
        return status(config)
    return print_plan(config)


if __name__ == "__main__":
    raise SystemExit(main())
