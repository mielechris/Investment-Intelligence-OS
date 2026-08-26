#!/usr/bin/env python3
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TARGET = REPO / "scripts" / "apply_batch8d.py"


def resolve_npm() -> str | None:
    common = [
        "/opt/homebrew/bin",
        "/usr/local/bin",
        "/usr/bin",
        "/bin",
        "/usr/sbin",
        "/sbin",
    ]
    current = [p for p in os.environ.get("PATH", "").split(":") if p]
    merged = []
    for p in common + current:
        if p and p not in merged:
            merged.append(p)
    os.environ["PATH"] = ":".join(merged)

    found = shutil.which("npm")
    if found:
        return found

    # Last resort: ask the user's login shell where npm lives, then export that
    # directory into this LaunchAgent child's environment. The resolved path is
    # never persisted as a secret; it is only process configuration.
    try:
        result = subprocess.run(
            ["/bin/zsh", "-lc", "command -v npm"],
            text=True,
            capture_output=True,
            timeout=15,
        )
        candidate = result.stdout.strip()
        if result.returncode == 0 and candidate and Path(candidate).exists():
            parent = str(Path(candidate).resolve().parent)
            os.environ["PATH"] = parent + ":" + os.environ["PATH"]
            return candidate
    except Exception:
        pass
    return None


def main() -> int:
    npm = resolve_npm()
    if not npm:
        print("STOP: npm could not be resolved for the background Batch 8D runner.")
        print("PATH:", os.environ.get("PATH", ""))
        return 127

    print("Background npm resolved:", npm)
    if not TARGET.exists():
        print("STOP: missing Batch 8D apply target:", TARGET)
        return 2

    # Run the reviewed apply artifact with the repaired PATH. All of the existing
    # branch/clean-tree/test/build/safety gates remain inside apply_batch8d.py.
    completed = subprocess.run([sys.executable, str(TARGET)], cwd=REPO, env=os.environ.copy())
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
