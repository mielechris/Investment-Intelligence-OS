#!/usr/bin/env python3
from __future__ import annotations

import plistlib
import subprocess
import sys
from pathlib import Path

REMOTE_BRANCH = "integration/iios-experience-x0-x6"
SUPERVISOR_LABEL = "com.iios.batch-supervisor"
SUPERVISOR_PLIST = Path.home() / "Library" / "LaunchAgents" / f"{SUPERVISOR_LABEL}.plist"


def output(cmd: list[str], cwd: Path) -> str:
    return subprocess.check_output(cmd, cwd=cwd, text=True).strip()


def run(cmd: list[str], cwd: Path) -> None:
    print("+", " ".join(cmd), flush=True)
    result = subprocess.run(cmd, cwd=cwd)
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def repo_root() -> Path:
    try:
        return Path(output(["git", "rev-parse", "--show-toplevel"], Path.cwd())).resolve()
    except Exception as exc:
        raise SystemExit("Run this from inside an IIOS repository checkout.") from exc


def supervisor_dir() -> Path | None:
    if not SUPERVISOR_PLIST.exists():
        return None
    with SUPERVISOR_PLIST.open("rb") as handle:
        payload = plistlib.load(handle)
    value = payload.get("WorkingDirectory") if isinstance(payload, dict) else None
    return Path(str(value)).expanduser().resolve() if value else None


def main() -> int:
    source = repo_root()
    supervisor = supervisor_dir()

    print("=" * 80)
    print("IIOS INTEGRATION — PREPARE ISOLATED X0-X6 + BATCH 8F VALIDATION")
    print("=" * 80)

    if supervisor and source == supervisor:
        print("Source checkout is the supervisor checkout; only a ref fetch will occur here. No checkout or file mutation will be performed.")

    before_branch = output(["git", "branch", "--show-current"], source)
    run(["git", "fetch", "origin", REMOTE_BRANCH], source)
    after_branch = output(["git", "branch", "--show-current"], source)
    if before_branch != after_branch:
        raise SystemExit(f"STOP: source branch changed unexpectedly: {before_branch!r} -> {after_branch!r}")

    remote_head = output(["git", "rev-parse", f"origin/{REMOTE_BRANCH}"], source)
    short = remote_head[:10]
    target = (source.parent / f"Investment-Intelligence-OS-integration-validation-{short}").resolve()
    validation_branch = f"integration/iios-experience-x0-x6-validation-{short}"

    if supervisor and target == supervisor:
        raise SystemExit("STOP: validation target resolves to supervisor checkout.")
    if target.exists():
        raise SystemExit(
            f"STOP: validation target already exists: {target}\n"
            "Use the existing validation checkout or remove it deliberately before creating another."
        )

    print("Source checkout:", source)
    print("Source branch:", before_branch or "DETACHED")
    print("Remote integration head:", remote_head)
    print("Validation checkout:", target)
    print("Validation branch:", validation_branch)

    run(
        [
            "git", "worktree", "add", "-b", validation_branch,
            str(target), f"origin/{REMOTE_BRANCH}",
        ],
        source,
    )

    if output(["git", "rev-parse", "HEAD"], target) != remote_head:
        raise SystemExit("STOP: validation worktree HEAD does not match remote integration head.")

    print("\n=== RUNNING DUAL-GATE VALIDATION ===")
    run([sys.executable, "scripts/validate_integration_x0_x6.py"], target)

    print("\nValidation worktree retained for browser acceptance:")
    print(target)
    print("No source checkout branch was changed.")
    print("No operator backend or Batch Supervisor process was stopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
