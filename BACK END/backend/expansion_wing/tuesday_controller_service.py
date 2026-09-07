"""Persistent, offline and application-level disabled Tuesday supervisor."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from .tuesday_controller import service_contract
from .tuesday_controller_state import ControllerStateStore, DisabledSupervisor

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--supervisor", action="store_true")
    parser.add_argument("--state-root", type=Path)
    parser.add_argument("--activate", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--browser", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.activate or args.browser:
        print(json.dumps({"status": "ACTIVATION_REJECTED"}, sort_keys=True)); return 3
    if not args.supervisor or args.state_root is None:
        print(json.dumps({"status": "SUPERVISOR_MODE_REQUIRED", **service_contract()}, sort_keys=True)); return 2
    try: return DisabledSupervisor(ControllerStateStore(args.state_root)).run()
    except (OSError, ValueError):
        print(json.dumps({"status": "SUPERVISOR_FAILED_CLOSED"}, sort_keys=True)); return 4

if __name__ == "__main__": raise SystemExit(main())
