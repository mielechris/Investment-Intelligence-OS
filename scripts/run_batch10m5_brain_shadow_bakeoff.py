#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "scripts" / "iios_brain_shadow_bakeoff.py"
VENV_CANDIDATES = (
    Path("/Users/crm/Documents/GitHub/Investment-Intelligence-OS-Batch8/BACK END/backend/.venv/bin/python3"),
    Path("/Users/crm/Documents/GitHub/Investment-Intelligence-OS-Batch8/BACK END/backend/.venv/bin/python"),
    Path("/Users/crm/Documents/GitHub/Investment-Intelligence-OS/BACK END/backend/.venv/bin/python3"),
    Path("/Users/crm/Documents/GitHub/Investment-Intelligence-OS/BACK END/backend/.venv/bin/python"),
)


def resolve_python() -> Path:
    for candidate in VENV_CANDIDATES:
        if candidate.exists() and os.access(candidate, os.X_OK):
            return candidate
    raise SystemExit("No IIOS backend venv Python found; refusing system-Python ledger access")


def main() -> int:
    python = resolve_python()
    print(f"Batch 10M.5 interpreter: {python}", flush=True)
    os.execv(str(python), [str(python), str(TARGET), *sys.argv[1:]])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
