#!/usr/bin/env python3
from __future__ import annotations

import os
import plistlib
import subprocess
import sys
from pathlib import Path

BRANCH = "feature/iios-experience-x0-x1"
LABEL = "com.iios.batch-supervisor"
PLIST = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"
WORKTREE_NAME = "Investment-Intelligence-OS-experience-x3"
PREVIEW_PORT = 5188


def run(cmd: list[str], cwd: Path, *, check: bool = True) -> subprocess.CompletedProcess:
    print("+", " ".join(cmd), flush=True)
    result = subprocess.run(cmd, cwd=cwd, text=True)
    if check and result.returncode != 0:
        raise SystemExit(result.returncode)
    return result


def output(cmd: list[str], cwd: Path) -> str:
    return subprocess.check_output(cmd, cwd=cwd, text=True).strip()


def repo_root() -> Path:
    try:
        return Path(output(["git", "rev-parse", "--show-toplevel"], Path.cwd())).resolve()
    except Exception as exc:
        raise SystemExit("Run this from inside the IIOS repository.") from exc


def supervisor_repo() -> Path | None:
    if not PLIST.exists():
        return None
    try:
        with PLIST.open("rb") as handle:
            payload = plistlib.load(handle)
    except Exception as exc:
        raise SystemExit(f"Unable to inspect batch supervisor LaunchAgent: {exc}") from exc
    working = payload.get("WorkingDirectory") if isinstance(payload, dict) else None
    return Path(str(working)).expanduser().resolve() if working else None


def assert_supervisor_isolated(source: Path, target: Path) -> None:
    supervisor = supervisor_repo()
    if supervisor is None:
        print("Batch supervisor LaunchAgent: not detected")
        return

    if target == supervisor:
        raise SystemExit("STOP: experience target is the batch supervisor checkout.")

    print("Batch supervisor checkout:", supervisor)
    print("Experience checkout:", target)

    if source == supervisor:
        branch = output(["git", "branch", "--show-current"], source)
        print("Supervisor checkout branch before preview setup:", branch or "DETACHED")


def ensure_worktree(source: Path, target: Path) -> None:
    before_branch = output(["git", "branch", "--show-current"], source)

    # Ref-only update; does not checkout, reset, merge, or alter source working files.
    run(["git", "fetch", "origin", BRANCH], source)

    worktrees = output(["git", "worktree", "list", "--porcelain"], source)
    if str(target) not in worktrees:
        local_ref = run(
            ["git", "show-ref", "--verify", "--quiet", f"refs/heads/{BRANCH}"],
            source,
            check=False,
        )
        if local_ref.returncode == 0:
            run(["git", "worktree", "add", str(target), BRANCH], source)
        else:
            run(["git", "worktree", "add", "-b", BRANCH, str(target), f"origin/{BRANCH}"], source)
    else:
        print("Experience worktree already exists.")

    after_branch = output(["git", "branch", "--show-current"], source)
    if after_branch != before_branch:
        raise SystemExit(
            f"STOP: source checkout branch changed unexpectedly: {before_branch!r} -> {after_branch!r}"
        )

    target_branch = output(["git", "branch", "--show-current"], target)
    if target_branch != BRANCH:
        raise SystemExit(f"STOP: experience worktree is on {target_branch!r}, expected {BRANCH!r}.")


def main() -> int:
    source = repo_root()
    target = (source.parent / WORKTREE_NAME).resolve()

    print("=" * 76)
    print("IIOS X3 PREVIEW — BATCH SUPERVISOR ISOLATED")
    print("=" * 76)

    assert_supervisor_isolated(source, target)
    ensure_worktree(source, target)

    # The preview gate contains a second independent LaunchAgent working-directory guard.
    run([sys.executable, "scripts/apply_experience_x2.py"], target)

    frontend = target / "FRONT END"
    if not (frontend / "node_modules").exists():
        lockfile = frontend / "package-lock.json"
        run(["npm", "ci"] if lockfile.exists() else ["npm", "install"], frontend)

    print()
    print("=" * 76)
    print("X3 PREVIEW READY")
    print("Batch supervisor checkout was not switched or patched.")
    print(f"Preview URL: http://127.0.0.1:{PREVIEW_PORT}")
    print("Backend telemetry remains read-only from http://127.0.0.1:8002")
    print("Press Ctrl+C to stop only the X3 frontend preview.")
    print("=" * 76)
    print()

    env = os.environ.copy()
    env["BROWSER"] = "none"
    return run(
        ["npm", "run", "dev", "--", "--host", "127.0.0.1", "--port", str(PREVIEW_PORT), "--strictPort"],
        frontend,
        check=False,
    ).returncode


if __name__ == "__main__":
    raise SystemExit(main())
