#!/usr/bin/env python3
from __future__ import annotations

import os
import shutil
from pathlib import Path

WORKTREE = Path(
    os.getenv(
        "IIOS_9O_WORKTREE",
        "/Users/crm/Documents/GitHub/Investment-Intelligence-OS-batch9o-daily-episode",
    )
).expanduser()


def _remove_generated_python_cache() -> None:
    scripts_dir = WORKTREE / "scripts"
    removed: list[str] = []
    cache_dir = scripts_dir / "__pycache__"
    if cache_dir.exists():
        shutil.rmtree(cache_dir)
        removed.append(str(cache_dir))
    if scripts_dir.exists():
        for pyc in scripts_dir.glob("*.pyc"):
            try:
                pyc.unlink()
            except FileNotFoundError:
                continue
            removed.append(str(pyc))
    if removed:
        print("Batch 9O recovery removed generated Python cache only:")
        for path in removed:
            print(f"  {path}")
    else:
        print("Batch 9O recovery found no generated Python cache to remove.")


def main() -> int:
    _remove_generated_python_cache()
    from activate_batch9o_daily_factory_episode import main as activate

    return activate()


if __name__ == "__main__":
    raise SystemExit(main())
