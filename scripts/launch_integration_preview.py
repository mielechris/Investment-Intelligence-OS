#!/usr/bin/env python3
from __future__ import annotations

import os
import plistlib
import shutil
import subprocess
import sys
from pathlib import Path

INTEGRATION_PREFIX = "integration/iios-experience-x0-x6"
SUPERVISOR_LABEL = "com.iios.batch-supervisor"
SUPERVISOR_PLIST = Path.home() / "Library" / "LaunchAgents" / f"{SUPERVISOR_LABEL}.plist"
PREVIEW_PORT = 5189


def output(cmd: list[str], cwd: Path) -> str:
    return subprocess.check_output(cmd, cwd=cwd, text=True).strip()


def run(cmd: list[str], cwd: Path, *, env: dict[str, str] | None = None, check: bool = True) -> int:
    print("+", " ".join(cmd), flush=True)
    code = subprocess.run(cmd, cwd=cwd, env=env).returncode
    if check and code != 0:
        raise SystemExit(code)
    return code


def supervisor_dir() -> Path | None:
    if not SUPERVISOR_PLIST.exists():
        return None
    with SUPERVISOR_PLIST.open("rb") as handle:
        payload = plistlib.load(handle)
    value = payload.get("WorkingDirectory") if isinstance(payload, dict) else None
    return Path(str(value)).expanduser().resolve() if value else None


def port_busy(port: int) -> bool:
    if shutil.which("lsof") is None:
        return False
    result = subprocess.run(
        ["lsof", f"-tiTCP:{port}", "-sTCP:LISTEN"],
        text=True,
        capture_output=True,
        check=False,
    )
    return bool(result.stdout.strip())


def main() -> int:
    repo = Path(__file__).resolve().parents[1]
    frontend = repo / "FRONT END"
    branch = output(["git", "branch", "--show-current"], repo)
    supervisor = supervisor_dir()

    print("=" * 76)
    print("IIOS X0-X6 INTEGRATION PREVIEW — OPERATOR LANE ISOLATED")
    print("=" * 76)

    if not branch.startswith(INTEGRATION_PREFIX):
        raise SystemExit(f"STOP: preview requires an integration validation branch; found {branch!r}")
    if supervisor and supervisor == repo.resolve():
        raise SystemExit("STOP: integration preview cannot run in the Batch Supervisor checkout.")
    if port_busy(PREVIEW_PORT):
        raise SystemExit(f"STOP: preview port {PREVIEW_PORT} is already in use.")

    if not (frontend / "node_modules").exists():
        run(["npm", "ci"] if (frontend / "package-lock.json").exists() else ["npm", "install"], frontend)

    print("Validation checkout:", repo)
    print("Validation branch:", branch)
    print("Batch Supervisor checkout:", supervisor or "not detected")
    print("Backend telemetry: existing operator backend http://127.0.0.1:8002")
    print(f"Integration preview: http://127.0.0.1:{PREVIEW_PORT}")
    print("No backend process will be started or stopped by this launcher.")
    print("Press Ctrl+C to stop only the 5189 integration frontend preview.")
    print("=" * 76)

    env = os.environ.copy()
    env["BROWSER"] = "none"
    return run(
        ["npm", "run", "dev", "--", "--host", "127.0.0.1", "--port", str(PREVIEW_PORT), "--strictPort"],
        frontend,
        env=env,
        check=False,
    )


if __name__ == "__main__":
    raise SystemExit(main())
