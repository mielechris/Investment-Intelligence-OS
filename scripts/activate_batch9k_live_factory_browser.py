#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import plistlib
import shutil
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen

BRANCH = "feature/batch9k-live-factory-browser"
LIVE = Path(os.getenv("IIOS_LIVE_CHECKOUT", "/Users/crm/Documents/GitHub/Investment-Intelligence-OS-Batch8")).expanduser()
WORKTREE = Path(os.getenv("IIOS_9K_WORKTREE", "/Users/crm/Documents/GitHub/Investment-Intelligence-OS-batch9k-browser")).expanduser()
FRONTEND = WORKTREE / "FRONT END"
DIST = FRONTEND / "dist"
LABEL = "com.iios.factory-browser-preview"
PREVIEW_HOST = "127.0.0.1"
PREVIEW_PORT = 5176
LOG_DIR = Path.home() / "Library" / "Logs" / "IIOS"
LAUNCH_DIR = Path.home() / "Library" / "LaunchAgents"
PLIST = LAUNCH_DIR / f"{LABEL}.plist"
PROTECTED_PLISTS = (
    "com.iios.factory-telemetry.plist",
    "com.iios.market-benchmark.plist",
    "com.iios.market-validation.plist",
    "com.iios.shadow-counterfactual.plist",
    "com.iios.outcome-learning.plist",
)


def _run(args: list[str], *, cwd: Path | None = None, check: bool = True, capture: bool = False) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        args,
        cwd=str(cwd) if cwd else None,
        text=True,
        capture_output=capture,
        check=False,
    )
    if check and result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(f"Command failed ({result.returncode}): {' '.join(args[:8])}\n{detail[:3000]}")
    return result


def _capture(args: list[str], *, cwd: Path | None = None) -> str:
    return _run(args, cwd=cwd, capture=True).stdout.strip()


def _require_command(name: str) -> str:
    value = shutil.which(name)
    if not value:
        raise SystemExit(f"Required command not found: {name}")
    return value


def _hash(path: Path) -> str | None:
    if not path.exists():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _protected_hashes() -> dict[str, str | None]:
    return {name: _hash(LAUNCH_DIR / name) for name in PROTECTED_PLISTS}


def _prepare_worktree(git: str) -> tuple[str, str]:
    if not LIVE.exists():
        raise SystemExit(f"Live IIOS checkout not found: {LIVE}")
    branch_before = _capture([git, "branch", "--show-current"], cwd=LIVE)
    status_before = _capture([git, "status", "--porcelain"], cwd=LIVE)
    _run([git, "fetch", "origin", BRANCH], cwd=LIVE)
    remote_ref = f"origin/{BRANCH}"
    if WORKTREE.exists():
        if not (WORKTREE / ".git").exists():
            raise SystemExit(f"9K path exists but is not a git worktree: {WORKTREE}")
        if _capture([git, "status", "--porcelain"], cwd=WORKTREE):
            raise SystemExit("Refusing to replace 9K worktree because it has tracked local changes")
        _run([git, "fetch", "origin", BRANCH], cwd=WORKTREE)
        _run([git, "reset", "--hard", remote_ref], cwd=WORKTREE)
    else:
        _run([git, "worktree", "add", "--detach", str(WORKTREE), remote_ref], cwd=LIVE)
    if _capture([git, "branch", "--show-current"], cwd=LIVE) != branch_before:
        raise SystemExit("Refusing activation: live IIOS branch changed while preparing 9K")
    if _capture([git, "status", "--porcelain"], cwd=LIVE) != status_before:
        raise SystemExit("Refusing activation: live IIOS worktree changed while preparing 9K")
    return branch_before, status_before


def _resolve_python() -> Path:
    candidates = (
        LIVE / "BACK END" / "backend" / ".venv" / "bin" / "python",
        Path(sys.executable),
    )
    for candidate in candidates:
        if candidate.exists() and os.access(candidate, os.X_OK):
            return candidate
    raise SystemExit("No executable Python found for Batch 9K preview")


def _build_frontend(npm: str) -> None:
    if not FRONTEND.exists():
        raise SystemExit(f"9K frontend not found: {FRONTEND}")
    _run([npm, "ci"], cwd=FRONTEND)
    _run([npm, "run", "lint"], cwd=FRONTEND)
    _run([npm, "run", "build"], cwd=FRONTEND)
    if not (DIST / "index.html").exists():
        raise SystemExit("Batch 9K frontend build did not produce dist/index.html")


def _install_preview_agent(python: Path) -> None:
    LAUNCH_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "Label": LABEL,
        "ProgramArguments": [
            str(python),
            str(WORKTREE / "scripts" / "iios_factory_browser_preview.py"),
            "--root",
            str(DIST),
            "--host",
            PREVIEW_HOST,
            "--port",
            str(PREVIEW_PORT),
        ],
        "WorkingDirectory": str(WORKTREE),
        "RunAtLoad": True,
        "KeepAlive": True,
        "ProcessType": "Background",
        "EnvironmentVariables": {
            "PYTHONUNBUFFERED": "1",
        },
        "StandardOutPath": str(LOG_DIR / "factory-browser-preview.out.log"),
        "StandardErrorPath": str(LOG_DIR / "factory-browser-preview.err.log"),
    }
    temporary = PLIST.with_suffix(".tmp.plist")
    with temporary.open("wb") as handle:
        plistlib.dump(payload, handle, sort_keys=True)
    temporary.replace(PLIST)
    domain = f"gui/{os.getuid()}"
    _run(["launchctl", "bootout", domain, str(PLIST)], check=False, capture=True)
    _run(["launchctl", "bootstrap", domain, str(PLIST)])
    _run(["launchctl", "kickstart", "-k", f"{domain}/{LABEL}"])
    _run(["launchctl", "print", f"{domain}/{LABEL}"], capture=True)


def _json_url(url: str, attempts: int = 30) -> dict:
    last_error: Exception | None = None
    for _ in range(attempts):
        try:
            request = Request(url, headers={"Accept": "application/json"})
            with urlopen(request, timeout=3) as response:
                value = json.loads(response.read().decode("utf-8"))
            if isinstance(value, dict):
                return value
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            time.sleep(0.5)
    raise RuntimeError(f"Could not read {url}: {last_error}")


def main() -> int:
    if sys.platform != "darwin":
        raise SystemExit("Batch 9K activation is intentionally macOS-only for this IIOS runtime")
    git = _require_command("git")
    npm = _require_command("npm")
    _require_command("launchctl")

    print("IIOS BATCH 9K — LIVE FACTORY BROWSER PREVIEW ACTIVATION")
    print(f"Live IIOS checkout: {LIVE}")
    print("Existing Backend 8002: UNCHANGED")
    print(f"Preview URL: http://{PREVIEW_HOST}:{PREVIEW_PORT}")
    print("Validation bridge ledger access: NONE")
    print("Preview bind: LOCALHOST ONLY")
    print("Broker connected: FALSE")
    print("Live execution: FALSE")

    protected_before = _protected_hashes()
    branch_before, status_before = _prepare_worktree(git)
    python = _resolve_python()
    _build_frontend(npm)

    backend_status = _json_url("http://127.0.0.1:8002/experience/factory-intelligence/status", attempts=4)
    if backend_status.get("read_only_aggregation") is not True:
        raise SystemExit("Backend 8002 Factory Intelligence contract is not reporting read-only aggregation")

    _install_preview_agent(python)
    health = _json_url(f"http://{PREVIEW_HOST}:{PREVIEW_PORT}/health")
    stack = _json_url(f"http://{PREVIEW_HOST}:{PREVIEW_PORT}/validation/stack")
    if health.get("ledger_access") != "NONE" or health.get("live_execution") is not False:
        raise SystemExit("Batch 9K preview health did not preserve read-only/no-execution boundary")
    if stack.get("schema_version") != "batch9k-live-factory-browser-v1":
        raise SystemExit("Batch 9K validation bridge schema mismatch")
    if (stack.get("safety") or {}).get("ledger_access") != "NONE":
        raise SystemExit("Batch 9K validation stack unexpectedly reports ledger access")

    protected_after = _protected_hashes()
    if protected_after != protected_before:
        raise SystemExit("Refusing Batch 9K activation: one or more 9G/9H/9I/9J LaunchAgents changed")
    if _capture([git, "branch", "--show-current"], cwd=LIVE) != branch_before:
        raise SystemExit("Live IIOS branch changed during Batch 9K activation")
    if _capture([git, "status", "--porcelain"], cwd=LIVE) != status_before:
        raise SystemExit("Live IIOS worktree changed during Batch 9K activation")

    opener = shutil.which("open")
    if opener:
        _run([opener, f"http://{PREVIEW_HOST}:{PREVIEW_PORT}"], check=False)

    layers = stack.get("layers") or {}
    summary = {
        "status": "BATCH9K_LIVE_FACTORY_BROWSER_PREVIEW",
        "preview_url": f"http://{PREVIEW_HOST}:{PREVIEW_PORT}",
        "backend_8002_unchanged": True,
        "live_checkout_unchanged": True,
        "protected_launch_agents_unchanged": True,
        "validation_bridge_ledger_access": "NONE",
        "preview_localhost_only": True,
        "factory_telemetry_state": (layers.get("factory_telemetry") or {}).get("availability"),
        "market_validation_state": (layers.get("market_validation") or {}).get("availability"),
        "shadow_strategy_state": (layers.get("shadow_strategy") or {}).get("availability"),
        "outcome_learning_state": (layers.get("outcome_learning") or {}).get("availability"),
        "broker_connected": False,
        "live_execution": False,
        "worktree": str(WORKTREE),
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    print("\nBatch 9K preview is live. The browser should open automatically; Backend 8002 and all market workers remain untouched.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
