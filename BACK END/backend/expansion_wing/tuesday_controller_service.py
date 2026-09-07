"""Persistent, offline and application-level disabled Tuesday supervisor."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from .tuesday_controller import service_contract
from .tuesday_controller_state import ControllerStateStore, DisabledSupervisor
from .operational_rehearsal import record_authentic_rehearsal

def main(argv: list[str] | None = None, *, rehearsal_clock=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--supervisor", action="store_true")
    parser.add_argument("--state-root", type=Path)
    parser.add_argument("--activate", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--browser", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--rehearse-closed-holiday", action="store_true")
    parser.add_argument("--approval-identity")
    parser.add_argument("--approval-timestamp")
    args = parser.parse_args(argv)
    if args.activate or args.browser:
        print(json.dumps({"status": "ACTIVATION_REJECTED"}, sort_keys=True)); return 3
    if args.rehearse_closed_holiday:
        if args.supervisor or args.state_root is None or args.approval_identity is None or args.approval_timestamp is None:
            print(json.dumps({"status": "REHEARSAL_ARGUMENTS_INVALID"}, sort_keys=True)); return 5
        try:
            kwargs = {} if rehearsal_clock is None else {"clock": rehearsal_clock}
            record_authentic_rehearsal(ControllerStateStore(args.state_root), approval_identity=args.approval_identity, approval_timestamp=args.approval_timestamp, **kwargs)
            print(json.dumps({"status": "AUTHENTIC_REHEARSAL_RECORDED"}, sort_keys=True)); return 0
        except (OSError, ValueError):
            print(json.dumps({"status": "REHEARSAL_FAILED_CLOSED"}, sort_keys=True)); return 6
    if not args.supervisor or args.state_root is None:
        print(json.dumps({"status": "SUPERVISOR_MODE_REQUIRED", **service_contract()}, sort_keys=True)); return 2
    try: return DisabledSupervisor(ControllerStateStore(args.state_root)).run()
    except (OSError, ValueError):
        print(json.dumps({"status": "SUPERVISOR_FAILED_CLOSED"}, sort_keys=True)); return 4

if __name__ == "__main__": raise SystemExit(main())
