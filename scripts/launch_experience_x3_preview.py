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
PREVIEW_MUTATION_PATH = "FRONT END/src/App.tsx"


def run(
    cmd: list[str],
    cwd: Path,
    *,
    check: bool = True,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess:
    print("+", " ".join(cmd), flush=True)
    result = subprocess.run(cmd, cwd=cwd, text=True, env=env)
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


def launchagent_loaded() -> bool | None:
    if sys.platform != "darwin" or not PLIST.exists():
        return None
    result = subprocess.run(
        ["launchctl", "print", f"gui/{os.getuid()}/{LABEL}"],
        text=True,
        capture_output=True,
    )
    return result.returncode == 0


def git_branch(path: Path) -> str:
    if not path.exists():
        return "MISSING"
    try:
        return output(["git", "branch", "--show-current"], path) or "DETACHED"
    except Exception:
        return "UNREADABLE"


def assert_supervisor_isolated(source: Path, target: Path) -> tuple[Path | None, str | None]:
    supervisor = supervisor_repo()
    loaded = launchagent_loaded()

    if supervisor is None:
        print("Batch supervisor LaunchAgent: not detected")
        return None, None

    if target == supervisor:
        raise SystemExit("STOP: experience target is the batch supervisor checkout.")

    supervisor_branch = git_branch(supervisor)
    print("Batch supervisor checkout:", supervisor)
    print("Batch supervisor branch:", supervisor_branch)
    print("Batch supervisor LaunchAgent:", "LOADED" if loaded is True else "NOT LOADED" if loaded is False else "UNKNOWN")
    print("Experience checkout:", target)

    if loaded is False:
        raise SystemExit("STOP: batch supervisor LaunchAgent is not loaded. Preview not started.")

    return supervisor, supervisor_branch


def dirty_paths(target: Path) -> list[str]:
    raw = subprocess.check_output(
        ["git", "status", "--porcelain=v1", "-z", "--untracked-files=all"],
        cwd=target,
    )
    records = raw.split(b"\0")
    paths: list[str] = []
    index = 0
    while index < len(records):
        record = records[index]
        index += 1
        if not record:
            continue
        text = record.decode("utf-8", errors="replace")
        if len(text) < 4:
            continue
        status = text[:2]
        path = text[3:]
        # Rename/copy records in -z mode are followed by the second path record.
        if "R" in status or "C" in status:
            if index < len(records) and records[index]:
                path = records[index].decode("utf-8", errors="replace")
                index += 1
        paths.append(path)
    return paths


def sync_existing_worktree(target: Path) -> None:
    changed = dirty_paths(target)
    unexpected = [path for path in changed if path != PREVIEW_MUTATION_PATH]
    if unexpected:
        print("STOP: experience worktree has unexpected local changes:")
        for path in unexpected:
            print(" ", path)
        print("Nothing was reset. Resolve those changes before previewing.")
        raise SystemExit(4)

    if PREVIEW_MUTATION_PATH in changed:
        print("Resetting prior preview-only App.tsx mount before fast-forward update.")
        run(["git", "restore", "--", PREVIEW_MUTATION_PATH], target)

    print("Fast-forwarding existing experience worktree to the fetched branch head.")
    run(["git", "merge", "--ff-only", f"origin/{BRANCH}"], target)


def ensure_worktree(source: Path, target: Path) -> None:
    before_branch = git_branch(source)

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
        sync_existing_worktree(target)

    after_branch = git_branch(source)
    if after_branch != before_branch:
        raise SystemExit(
            f"STOP: source checkout branch changed unexpectedly: {before_branch!r} -> {after_branch!r}"
        )

    target_branch = git_branch(target)
    if target_branch != BRANCH:
        raise SystemExit(f"STOP: experience worktree is on {target_branch!r}, expected {BRANCH!r}.")


def verify_supervisor_unchanged(supervisor: Path | None, original_branch: str | None) -> None:
    if supervisor is None or original_branch is None:
        return
    current_branch = git_branch(supervisor)
    loaded = launchagent_loaded()
    if current_branch != original_branch:
        raise SystemExit(
            f"STOP: supervisor checkout branch changed: {original_branch!r} -> {current_branch!r}."
        )
    if loaded is False:
        raise SystemExit("STOP: batch supervisor LaunchAgent became unloaded during preview setup.")
    print("Supervisor verification: branch unchanged and LaunchAgent loaded.")


def main() -> int:
    source = repo_root()
    target = (source.parent / WORKTREE_NAME).resolve()

    print("=" * 76)
    print("IIOS X3 PREVIEW — BATCH SUPERVISOR ISOLATED")
    print("=" * 76)

    supervisor, supervisor_branch = assert_supervisor_isolated(source, target)
    ensure_worktree(source, target)

    frontend = target / "FRONT END"
    if not (frontend / "node_modules").exists():
        lockfile = frontend / "package-lock.json"
        print("Frontend dependencies missing in experience worktree; installing before build gate.")
        run(["npm", "ci"] if lockfile.exists() else ["npm", "install"], frontend)

    # The preview gate contains a second independent LaunchAgent working-directory guard.
    run([sys.executable, "scripts/apply_experience_x2.py"], target)

    verify_supervisor_unchanged(supervisor, supervisor_branch)

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
        env=env,
    ).returncode


if __name__ == "__main__":
    raise SystemExit(main())
