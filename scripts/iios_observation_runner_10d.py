#!/usr/bin/env python3
"""Batch 10D wrapper for the existing 9A observation runner.

Discovery/orchestration remain in the isolated 9A worktree. Monitoring refreshes
are delegated to Backend 8002 so the authoritative installed chain runs:
base monitoring -> paper-fund portfolio context -> evidence watch -> Deep Watch.

If Backend 8002 is unavailable, the existing runner records the monitoring step
as an error and continues fail-closed. No broker or live execution authority is
added here.
"""
from __future__ import annotations

import json
from urllib.request import Request, urlopen

import iios_observation_runner as runner

BACKEND_BASE_URL = "http://127.0.0.1:8002"
MONITORING_PATH = "/monitoring/refresh-due"


def refresh_due_profiles_via_backend() -> dict:
    req = Request(
        f"{BACKEND_BASE_URL}{MONITORING_PATH}",
        data=b"",
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(req, timeout=900) as response:
        payload = json.load(response)
        status = int(getattr(response, "status", 200) or 200)

    if status != 200:
        raise RuntimeError(f"BACKEND_MONITORING_HTTP_{status}")
    if not isinstance(payload, dict):
        raise RuntimeError("BACKEND_MONITORING_INVALID_RESPONSE")

    return {
        **payload,
        "monitoring_authority": "BACKEND_8002",
        "paper_mode": True,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }


def install_backend_monitoring_bridge():
    runner.refresh_due_profiles = refresh_due_profiles_via_backend
    return runner


def main() -> int:
    install_backend_monitoring_bridge()
    return runner.main()


if __name__ == "__main__":
    raise SystemExit(main())
