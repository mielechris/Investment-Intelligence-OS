#!/usr/bin/env python3
from __future__ import annotations

import argparse
import signal
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND = REPO_ROOT / "BACK END" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

# Import the production app for installation side effects only: requirement-lineage,
# risk, generic evidence, and provider-hardening guards must match the live backend
# before the controller advances any case.
import app as _iios_bootstrap  # noqa: E402,F401

from governed_paper_trading_controller import (  # noqa: E402
    run_governed_paper_trading_cycle,
)


DEFAULT_INTERVAL_MINUTES = 15
_STOP = False


def _handle_stop(_signum, _frame) -> None:
    global _STOP
    _STOP = True


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run IIOS Batch 9B governed paper-trading operations"
    )
    parser.add_argument("--once", action="store_true", help="Run one cycle and exit")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Inspect/deepen according to flags but do not create a paper execution",
    )
    parser.add_argument(
        "--no-deepen",
        action="store_true",
        help="Do not run Evidence Gap Hunter this cycle",
    )
    parser.add_argument(
        "--interval-minutes",
        type=int,
        default=DEFAULT_INTERVAL_MINUTES,
        help="Continuous cadence; minimum 15 minutes",
    )
    args = parser.parse_args()

    interval = max(DEFAULT_INTERVAL_MINUTES, int(args.interval_minutes))
    signal.signal(signal.SIGINT, _handle_stop)
    signal.signal(signal.SIGTERM, _handle_stop)

    allow_execution = not args.dry_run
    allow_deepening = not args.no_deepen

    print("IIOS BATCH 9B — GOVERNED PAPER TRADING", flush=True)
    print(f"Repo: {REPO_ROOT}", flush=True)
    print(f"Cadence: every {interval} minutes", flush=True)
    print(f"Deepening enabled: {allow_deepening}", flush=True)
    print(f"Paper execution enabled: {allow_execution}", flush=True)
    print("Broker connected: FALSE", flush=True)
    print("Live execution: FALSE", flush=True)
    print(
        "Rule: only existing governed Qualification → Capital → Sizing → "
        "single-use Paper Authorization may create a mock position.",
        flush=True,
    )

    if args.once:
        run_governed_paper_trading_cycle(
            allow_deepening=allow_deepening,
            allow_paper_execution=allow_execution,
        )
        return 0

    while not _STOP:
        run_governed_paper_trading_cycle(
            allow_deepening=allow_deepening,
            allow_paper_execution=allow_execution,
        )

        print(
            f"[IDLE] Next 9B paper-trading cycle in {interval} minutes.",
            flush=True,
        )
        for _ in range(interval * 60):
            if _STOP:
                break
            time.sleep(1)

    print("Batch 9B paper-trading runner stopped cleanly.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
