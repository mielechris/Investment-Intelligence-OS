"""Uninstalled CLI boundary for the governed Tuesday controller."""
from __future__ import annotations

import argparse
import json
from .tuesday_controller import service_contract

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--operational", action="store_true")
    parser.add_argument("--activate", action="store_true")
    args = parser.parse_args(argv)
    if not args.operational or not args.activate:
        print(json.dumps({"status": "CONTROLLER_DISABLED", **service_contract()}, sort_keys=True))
        return 2
    print(json.dumps({"status": "ACTIVATION_REQUIRES_SEPARATE_AUTHORIZATION"}, sort_keys=True))
    return 3

if __name__ == "__main__": raise SystemExit(main())
