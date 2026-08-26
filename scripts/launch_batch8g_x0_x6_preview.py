#!/usr/bin/env python3
from __future__ import annotations

import os
import plistlib
import shutil
import subprocess
from pathlib import Path

BRANCH = "integration/iios-experience-x0-x6-on-batch8g"
PREVIEW_PORT = 5189
BACKEND_PORT = 8002
SUPERVISOR_LABEL = "com.iios.batch-supervisor"
SUPERVISOR_PLIST = Path.home() / "Library" / "LaunchAgents" / f"{SUPERVISOR_LABEL}.plist"
PREVIEW_DIR_NAME = "Investment-Intelligence-OS-Batch8G-X0X6-preview"


def output(cmd: list[str], cwd: Path) -> str:
    return subprocess.check_output(cmd, cwd=cwd, text=True).strip()


def run(cmd: list[str], cwd: Path, *, env: dict[str, str] | None = None, check: bool = True) -> int:
    print("+", " ".join(cmd), flush=True)
    code = subprocess.run(cmd, cwd=cwd, env=env).returncode
    if check and code != 0:
        raise SystemExit(code)
    return code


def git_root(cwd: Path) -> Path:
    try:
        return Path(output(["git", "rev-parse", "--show-toplevel"], cwd)).resolve()
    except Exception as exc:
        raise SystemExit(f"STOP: run this launcher from an IIOS Git checkout: {exc}") from exc


def supervisor_dir() -> Path | None:
    if not SUPERVISOR_PLIST.exists():
        return None
    with SUPERVISOR_PLIST.open("rb") as handle:
        payload = plistlib.load(handle)
    value = payload.get("WorkingDirectory") if isinstance(payload, dict) else None
    return Path(str(value)).expanduser().resolve() if value else None


def listening_pids(port: int) -> list[int]:
    if shutil.which("lsof") is None:
        return []
    result = subprocess.run(
        ["lsof", f"-tiTCP:{port}", "-sTCP:LISTEN"],
        text=True,
        capture_output=True,
        check=False,
    )
    return [int(value) for value in result.stdout.split() if value.isdigit()]


def ensure_preview_worktree(source: Path, target: Path, supervisor: Path | None) -> None:
    run(["git", "fetch", "origin", BRANCH], source)
    ref = f"origin/{BRANCH}"
    sha = output(["git", "rev-parse", ref], source)

    if target.exists():
        if supervisor and target.resolve() == supervisor:
            raise SystemExit("STOP: preview target resolves to the Batch Supervisor checkout.")
        try:
            inside = output(["git", "rev-parse", "--is-inside-work-tree"], target)
        except Exception as exc:
            raise SystemExit(f"STOP: existing preview path is not a Git worktree: {target}") from exc
        if inside != "true":
            raise SystemExit(f"STOP: invalid preview worktree: {target}")
        dirty = output(["git", "status", "--porcelain"], target)
        if dirty:
            raise SystemExit(f"STOP: preview worktree has local changes; nothing was reset:\n{dirty}")
        run(["git", "checkout", "--detach", sha], target)
        return

    run(["git", "worktree", "add", "--detach", str(target), sha], source)


def main() -> int:
    source = git_root(Path.cwd())
    supervisor = supervisor_dir()
    if supervisor and source == supervisor:
        raise SystemExit(
            "STOP: do not launch the integration preview from the Batch Supervisor checkout. "
            "Use the cyan EXPERIENCE · RELEASE GATE terminal / experience checkout instead."
        )

    preview = source.parent / PREVIEW_DIR_NAME
    if supervisor and preview.resolve() == supervisor:
        raise SystemExit("STOP: preview path conflicts with the Batch Supervisor checkout.")

    backend_pids = listening_pids(BACKEND_PORT)
    if not backend_pids:
        raise SystemExit(
            f"STOP: backend port {BACKEND_PORT} is not listening. "
            "This launcher will not start or restart the backend."
        )
    if listening_pids(PREVIEW_PORT):
        raise SystemExit(
            f"STOP: preview port {PREVIEW_PORT} is already in use. "
            "Nothing was stopped."
        )

    print("=" * 78)
    print("IIOS BATCH 8G + X0-X6 — ISOLATED INTEGRATION PREVIEW")
    print("=" * 78)
    print("Source checkout:", source)
    print("Batch Supervisor checkout:", supervisor or "not detected")
    print("Operator backend 8002 PID(s):", ", ".join(map(str, backend_pids)))
    print("Existing UI 5175: NOT TOUCHED")
    print("Preview target:", preview)
    print("Preview URL: http://127.0.0.1:5189")
    print("Live execution authority: NOT CHANGED / FALSE")
    print("=" * 78)

    ensure_preview_worktree(source, preview, supervisor)
    frontend = preview / "FRONT END"
    if not (frontend / "node_modules").exists():
        run(["npm", "ci"], frontend)

    print("\n=== LOCAL BUILD CHECK ===")
    run(["npm", "run", "build"], frontend)

    backend_after = listening_pids(BACKEND_PORT)
    if backend_after != backend_pids:
        raise SystemExit(
            f"STOP: backend PID set changed before preview launch: {backend_pids} -> {backend_after}"
        )

    print("\nPREVIEW READY")
    print("  8G operator UI remains available on 5175.")
    print("  Existing backend remains on 8002.")
    print("  Integrated 8G + X0-X6 preview will run on 5189.")
    print("  Press Ctrl+C here to stop ONLY the 5189 preview.")

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
