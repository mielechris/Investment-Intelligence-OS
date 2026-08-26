#!/usr/bin/env python3
from __future__ import annotations

import plistlib
import subprocess
import sys
from pathlib import Path

BRANCH = "feature/iios-experience-x0-x1"
REMOTE = "origin"
LABEL = "com.iios.batch-supervisor"
PLIST = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"
DEFAULT_WORKTREE_NAME = "Investment-Intelligence-OS-experience-x3"


def run(cmd: list[str], cwd: Path, check: bool = True) -> subprocess.CompletedProcess:
    print("+", " ".join(cmd), flush=True)
    result = subprocess.run(cmd, cwd=cwd, text=True, capture_output=True)
    if result.stdout:
        print(result.stdout.rstrip())
    if result.stderr:
        print(result.stderr.rstrip())
    if check and result.returncode != 0:
        raise SystemExit(result.returncode)
    return result


def output(cmd: list[str], cwd: Path) -> str:
    return subprocess.check_output(cmd, cwd=cwd, text=True).strip()


def repo_root() -> Path:
    try:
        value = subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=Path.cwd(),
            text=True,
        ).strip()
    except subprocess.CalledProcessError as exc:
        raise SystemExit("Run this from inside the IIOS git repository.") from exc
    return Path(value).resolve()


def supervisor_repo() -> Path | None:
    if not PLIST.exists():
        return None
    try:
        with PLIST.open("rb") as handle:
            payload = plistlib.load(handle)
    except Exception as exc:
        raise SystemExit(f"Unable to inspect {PLIST}: {exc}") from exc
    working = payload.get("WorkingDirectory") if isinstance(payload, dict) else None
    return Path(str(working)).expanduser().resolve() if working else None


def main() -> int:
    repo = repo_root()
    target = repo.parent / DEFAULT_WORKTREE_NAME
    supervisor = supervisor_repo()

    print("=" * 72)
    print("IIOS EXPERIENCE X3 - SUPERVISOR-SAFE WORKTREE SETUP")
    print("=" * 72)
    print("Current repo:", repo)
    print("Supervisor repo:", supervisor or "not detected")
    print("Experience worktree:", target)

    if target.resolve() == repo:
        raise SystemExit("STOP: worktree target resolves to the active repo.")
    if supervisor and target.resolve() == supervisor:
        raise SystemExit("STOP: worktree target resolves to the batch supervisor checkout.")

    current_branch = output(["git", "branch", "--show-current"], repo)
    print("Current branch remains:", current_branch or "DETACHED")

    # Fetching updates refs only; it does not switch or rewrite the supervisor checkout.
    run(["git", "fetch", REMOTE, BRANCH], repo)

    existing = run(["git", "worktree", "list", "--porcelain"], repo, check=True).stdout
    if str(target) in existing:
        print("Experience worktree already exists; leaving it in place.")
    else:
        local_ref = run(["git", "show-ref", "--verify", "--quiet", f"refs/heads/{BRANCH}"], repo, check=False)
        if local_ref.returncode == 0:
            run(["git", "worktree", "add", str(target), BRANCH], repo)
        else:
            run(["git", "worktree", "add", "-b", BRANCH, str(target), f"{REMOTE}/{BRANCH}"], repo)

    final_branch = output(["git", "branch", "--show-current"], repo)
    if final_branch != current_branch:
        raise SystemExit(
            f"STOP: source checkout branch unexpectedly changed from {current_branch!r} to {final_branch!r}."
        )

    if supervisor and repo == supervisor:
        print("Supervisor checkout branch verified unchanged:", final_branch)

    print()
    print("SAFE WORKTREE READY")
    print("Supervisor checkout was not branch-switched, patched, or stopped.")
    print("Next commands:")
    print(f'  cd "{target}"')
    print("  python3 scripts/apply_experience_x2.py")
    print('  cd "FRONT END" && npm run dev')
    print()
    print("The preview gate will independently re-check LaunchAgent isolation before writing App.tsx.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
