#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import plistlib
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

BRANCH = "feature/batch9h-autonomous-market-benchmark"
DEFAULT_OWNER = "mielechris"
DEFAULT_TELEMETRY_REPO_NAME = "IIOS-Telemetry"
VALIDATION_ISSUE_TITLE = "IIOS Market Validation - Latest"
COLLECTOR_LABEL = "com.iios.market-benchmark"
VALIDATOR_LABEL = "com.iios.market-validation"
COLLECTOR_INTERVAL_SECONDS = 300
VALIDATOR_INTERVAL_SECONDS = 900
UNIVERSE_MAX_AGE_HOURS = 36.0

LIVE = Path(
    os.getenv(
        "IIOS_LIVE_CHECKOUT",
        "/Users/crm/Documents/GitHub/Investment-Intelligence-OS-Batch8",
    )
).expanduser()
WORKTREE = Path(
    os.getenv(
        "IIOS_9H_WORKTREE",
        "/Users/crm/Documents/GitHub/Investment-Intelligence-OS-batch9h-market-benchmark",
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
    / "market-validation"
)
UNIVERSE_CACHE = STATE_DIR / "benchmark_universe.json"
LOG_DIR = Path.home() / "Library" / "Logs" / "IIOS"
LAUNCH_DIR = Path.home() / "Library" / "LaunchAgents"
COLLECTOR_PLIST = LAUNCH_DIR / f"{COLLECTOR_LABEL}.plist"
VALIDATOR_PLIST = LAUNCH_DIR / f"{VALIDATOR_LABEL}.plist"


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


def _capture(
    args: list[str],
    *,
    cwd: Path | None = None,
) -> str:
    return _run(args, cwd=cwd, capture=True).stdout.strip()


def _require_command(name: str) -> str:
    value = shutil.which(name)
    if not value:
        raise SystemExit(f"Required command not found: {name}")
    return value


def _parse_time(value) -> datetime | None:
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


def _atomic_write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


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
    if (
        result.returncode != 0
        or result.stdout.strip().lower() != "true"
    ):
        raise SystemExit(
            "Refusing Batch 9H activation: IIOS telemetry repository "
            "is unavailable or not private"
        )


def _ensure_validation_issue(gh: str) -> int:
    query = f"repos/{TELEMETRY_REPO}/issues?state=open&per_page=100"
    issue_text = _capture(
        [
            gh,
            "api",
            query,
            "--jq",
            f'.[] | select(.title == "{VALIDATION_ISSUE_TITLE}") | .number',
        ]
    )
    if issue_text:
        return int(issue_text.splitlines()[0].strip())
    body = (
        "IIOS MARKET VALIDATION — BATCH 9H READ ONLY\n\n"
        "Waiting for the first end-of-session autonomous market-validation report.\n\n"
        "Independent benchmark sidecar only. Recommendations are advisory. "
        "No broker or live execution authority."
    )
    created = _capture(
        [
            gh,
            "api",
            "--method",
            "POST",
            f"repos/{TELEMETRY_REPO}/issues",
            "-f",
            f"title={VALIDATION_ISSUE_TITLE}",
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
                f"9H path exists but is not a git worktree: {WORKTREE}"
            )
        if _capture(
            [git, "status", "--porcelain"],
            cwd=WORKTREE,
        ):
            raise SystemExit(
                "Refusing to replace 9H worktree because it has local changes"
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
            "Refusing activation: live IIOS checkout changed while preparing 9H"
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
        "No IIOS backend virtualenv Python found; refusing "
        "system-Python daemon fallback"
    )


def _seed_universe_cache_from_live_ledger() -> dict:
    """Seed collector membership only; collector itself never reads the ledger."""
    uri = f"file:{quote(str(LEDGER), safe='/')}?mode=ro"
    connection = sqlite3.connect(uri, uri=True, timeout=30)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            "SELECT payload_json, created_at FROM ledger_objects "
            "WHERE object_type = ? ORDER BY created_at DESC LIMIT 100",
            ("production_index_universe_snapshot",),
        ).fetchall()
    finally:
        connection.close()

    now = datetime.now(timezone.utc)
    selected = None
    selected_created_at = None
    for row in rows:
        try:
            payload = json.loads(row["payload_json"])
        except (TypeError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        if (
            payload.get("verified_complete") is not True
            or payload.get("strict_membership") is not True
            or not isinstance(payload.get("symbols"), list)
            or not payload.get("symbols")
        ):
            continue
        created_at = _parse_time(
            payload.get("created_at")
            or payload.get("as_of")
            or row["created_at"]
        )
        if created_at is None:
            continue
        age_hours = max(
            0.0,
            (now - created_at).total_seconds() / 3600.0,
        )
        if age_hours > UNIVERSE_MAX_AGE_HOURS:
            continue
        selected = payload
        selected_created_at = created_at
        break

    if selected is None or selected_created_at is None:
        raise SystemExit(
            "Refusing Batch 9H activation: no fresh verified production "
            "universe exists in the live ledger"
        )

    symbols: list[str] = []
    seen: set[str] = set()
    for row in selected.get("symbols") or []:
        ticker = str(
            row.get("ticker") if isinstance(row, dict) else row or ""
        ).strip().upper()
        if not ticker or ticker in seen:
            continue
        seen.add(ticker)
        symbols.append(ticker)

    if not symbols:
        raise SystemExit(
            "Refusing Batch 9H activation: verified production universe "
            "contained no usable symbols"
        )

    cache = {
        "schema_version": "batch9h-benchmark-universe-v1",
        "source": "LIVE_VERIFIED_PRODUCTION_UNIVERSE_SEED",
        "verified_complete": True,
        "strict_membership": True,
        "symbols": symbols,
        "symbol_count": len(symbols),
        "source_lineage": selected.get("source_lineage") or [],
        "source_snapshot_id": selected.get(
            "production_index_universe_snapshot_id"
        ),
        "official_capture_created_at": selected_created_at.isoformat(),
        "cached_at": now.isoformat(),
        "activation_seed_ledger_mode": "READ_ONLY",
        "collector_ledger_read": False,
        "collector_ledger_write": False,
        "independent_of_iios_promotion_decisions": True,
        "live_execution": False,
    }
    _atomic_write(UNIVERSE_CACHE, cache)
    return cache


def _collector_command(python: Path) -> list[str]:
    return [
        str(python),
        str(
            WORKTREE
            / "scripts"
            / "iios_market_benchmark_collector.py"
        ),
        "--state-dir",
        str(STATE_DIR),
    ]


def _validator_command(
    python: Path,
    issue_number: int,
) -> list[str]:
    return [
        str(python),
        str(
            WORKTREE
            / "scripts"
            / "iios_daily_market_validation.py"
        ),
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


def _first_benchmark_sample(python: Path) -> dict:
    result = _run(
        _collector_command(python),
        cwd=WORKTREE,
        check=False,
        capture=True,
    )
    if result.returncode not in (0,):
        raise SystemExit(
            "First Batch 9H independent benchmark sample failed:\n"
            + (result.stderr or result.stdout or "")[:3000]
        )
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise SystemExit(
            f"Could not parse first Batch 9H collector result: {exc}"
        ) from exc
    status = str(payload.get("status") or "")
    allowed = {
        "BENCHMARK_SAMPLE_RECORDED",
        "SKIPPED_OUTSIDE_REGULAR_SESSION",
        "SKIPPED_NON_MARKET_DAY",
    }
    if status not in allowed:
        raise SystemExit(
            f"Unexpected first Batch 9H collector status: {status}"
        )
    if status == "BENCHMARK_SAMPLE_RECORDED":
        if (
            payload.get("independent_of_iios_promotion_decisions")
            is not True
        ):
            raise SystemExit(
                "First Batch 9H sample did not prove independent "
                "benchmark provenance"
            )
        if (
            payload.get("ledger_read") is not False
            or payload.get("ledger_write") is not False
        ):
            raise SystemExit(
                "First Batch 9H benchmark sample violated the "
                "no-ledger collector contract"
            )
        if payload.get("live_execution") is not False:
            raise SystemExit(
                "First Batch 9H benchmark sample did not keep "
                "live execution false"
            )
    return payload


def _launch_path(gh: str) -> str:
    current_path = os.environ.get("PATH", "")
    parts = [
        str(Path(gh).parent),
        *[item for item in current_path.split(":") if item],
    ]
    return ":".join(dict.fromkeys(parts))


def _install_agent(
    *,
    label: str,
    plist: Path,
    program_arguments: list[str],
    interval_seconds: int,
    stdout_log: str,
    stderr_log: str,
    gh: str,
) -> None:
    LAUNCH_DIR.mkdir(parents=True, exist_ok=True)
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    backup = plist.with_suffix(".backup.plist")
    if plist.exists():
        shutil.copy2(plist, backup)
    payload = {
        "Label": label,
        "ProgramArguments": program_arguments,
        "WorkingDirectory": str(WORKTREE),
        "RunAtLoad": True,
        "StartInterval": int(interval_seconds),
        "ProcessType": "Background",
        "EnvironmentVariables": {
            "PATH": _launch_path(gh),
            "PYTHONUNBUFFERED": "1",
        },
        "StandardOutPath": str(LOG_DIR / stdout_log),
        "StandardErrorPath": str(LOG_DIR / stderr_log),
    }
    temporary = plist.with_suffix(".tmp.plist")
    with temporary.open("wb") as handle:
        plistlib.dump(payload, handle, sort_keys=True)
    temporary.replace(plist)
    domain = f"gui/{os.getuid()}"
    _run(
        ["launchctl", "bootout", domain, str(plist)],
        check=False,
        capture=True,
    )
    try:
        _run(["launchctl", "bootstrap", domain, str(plist)])
        _run(
            [
                "launchctl",
                "kickstart",
                "-k",
                f"{domain}/{label}",
            ]
        )
        _run(
            ["launchctl", "print", f"{domain}/{label}"],
            capture=True,
        )
    except Exception:
        _run(
            ["launchctl", "bootout", domain, str(plist)],
            check=False,
            capture=True,
        )
        if backup.exists():
            shutil.copy2(backup, plist)
            _run(
                ["launchctl", "bootstrap", domain, str(plist)],
                check=False,
                capture=True,
            )
            _run(
                [
                    "launchctl",
                    "kickstart",
                    "-k",
                    f"{domain}/{label}",
                ],
                check=False,
                capture=True,
            )
        raise


def main() -> int:
    if sys.platform != "darwin":
        raise SystemExit(
            "Batch 9H activation is intentionally macOS-only "
            "for this IIOS runtime"
        )
    git = _require_command("git")
    gh = _require_command("gh")
    _require_command("launchctl")
    _run([gh, "auth", "status"])

    print(
        "IIOS BATCH 9H — AUTONOMOUS MARKET BENCHMARK + "
        "MISS LEARNING ACTIVATION"
    )
    print(f"Live ledger: {LEDGER}")
    print(f"Private validation destination: {TELEMETRY_REPO}")
    print("Benchmark source: INDEPENDENT YAHOO SCREENER SIDECAR")
    print(
        "Benchmark universe: VERIFIED PRODUCTION MEMBERSHIP SEED, "
        "THEN OFFICIAL INDEX REFRESH"
    )
    print(
        f"Benchmark collection cadence: "
        f"{COLLECTOR_INTERVAL_SECONDS} seconds"
    )
    print(
        f"After-close validation check cadence: "
        f"{VALIDATOR_INTERVAL_SECONDS} seconds"
    )
    print("Collector ledger access: NONE")
    print("Universe seed ledger access: SQLITE READ ONLY")
    print("Scorecard ledger access: SQLITE READ ONLY")
    print("Threshold recommendations: ADVISORY ONLY")
    print("Broker connected: FALSE")
    print("Live execution: FALSE")

    branch_before, status_before = _prepare_worktree(git)
    _require_private_repo(gh)
    validation_issue = _ensure_validation_issue(gh)
    python = _resolve_python()
    universe_seed = _seed_universe_cache_from_live_ledger()
    first_sample = _first_benchmark_sample(python)

    _install_agent(
        label=COLLECTOR_LABEL,
        plist=COLLECTOR_PLIST,
        program_arguments=_collector_command(python),
        interval_seconds=COLLECTOR_INTERVAL_SECONDS,
        stdout_log="market-benchmark.out.log",
        stderr_log="market-benchmark.err.log",
        gh=gh,
    )
    _install_agent(
        label=VALIDATOR_LABEL,
        plist=VALIDATOR_PLIST,
        program_arguments=_validator_command(
            python,
            validation_issue,
        ),
        interval_seconds=VALIDATOR_INTERVAL_SECONDS,
        stdout_log="market-validation.out.log",
        stderr_log="market-validation.err.log",
        gh=gh,
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
            "Live IIOS checkout changed during Batch 9H activation"
        )

    summary = {
        "status": "BATCH9H_AUTONOMOUS_MARKET_VALIDATION_LIVE",
        "worktree": str(WORKTREE),
        "state_dir": str(STATE_DIR),
        "validation_repo": TELEMETRY_REPO,
        "validation_repo_private": True,
        "validation_issue": validation_issue,
        "collector_label": COLLECTOR_LABEL,
        "collector_interval_seconds": COLLECTOR_INTERVAL_SECONDS,
        "validator_label": VALIDATOR_LABEL,
        "validator_interval_seconds": VALIDATOR_INTERVAL_SECONDS,
        "first_collector_status": first_sample.get("status"),
        "benchmark_source": (
            "BATCH_9H_INDEPENDENT_YAHOO_SCREENER_SIDECAR"
        ),
        "benchmark_universe_seed_source": universe_seed.get("source"),
        "benchmark_universe_count": universe_seed.get("symbol_count"),
        "collector_ledger_access": "NONE",
        "universe_seed_ledger_mode": "READ_ONLY",
        "scorecard_ledger_mode": "READ_ONLY",
        "auto_apply_threshold_changes": False,
        "broker_connected": False,
        "live_execution": False,
        "live_checkout_unchanged": True,
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    print(
        "\nBatch 9H is active. 9G telemetry remains untouched; "
        "9H only adds independent benchmark collection and "
        "after-close validation."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
