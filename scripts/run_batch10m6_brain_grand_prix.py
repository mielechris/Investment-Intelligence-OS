#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "scripts" / "iios_brain_grand_prix.py"
CANDIDATES = [
    Path("/Users/crm/Documents/GitHub/Investment-Intelligence-OS-Batch8/BACK END/backend/.venv/bin/python"),
    Path("/Users/crm/Documents/GitHub/Investment-Intelligence-OS/BACK END/backend/.venv/bin/python"),
]


def main() -> int:
    current = Path(sys.executable).resolve()
    if "backend/.venv/bin/python" in str(current):
        os.execv(str(current), [str(current), str(TARGET), *sys.argv[1:]])
    for candidate in CANDIDATES:
        if candidate.exists() and os.access(candidate, os.X_OK):
            print(f"Batch 10M.6 interpreter: {candidate}")
            os.execv(str(candidate), [str(candidate), str(TARGET), *sys.argv[1:]])
    raise SystemExit("Missing executable IIOS backend Python for TCC-safe Grand Prix ledger access")


if __name__ == "__main__":
    raise SystemExit(main())
