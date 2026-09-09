"""Runtime-backed liveness and readiness probes for the IIOS backend."""
from __future__ import annotations

import os
import sqlite3
import threading
import time
from datetime import datetime, timezone
from typing import Any


def live_probe() -> dict[str, Any]:
    started = time.monotonic_ns()
    return {
        "status": "LIVE",
        "pid": os.getpid(),
        "thread": threading.current_thread().name,
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "probe_monotonic_ns": started,
    }


def _ledger_probe() -> str:
    from ledger import DB_PATH
    if not DB_PATH.is_file():
        raise RuntimeError("LEDGER_UNAVAILABLE")
    connection = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, timeout=2)
    try:
        row = connection.execute("SELECT 1").fetchone()
    finally:
        connection.close()
    if row != (1,):
        raise RuntimeError("LEDGER_UNAVAILABLE")
    return "READY"


def ready_probe() -> tuple[bool, dict[str, Any]]:
    import jesse_scheduler
    import monitoring_engine
    import opportunity_scheduler
    from production_safety_freeze import production_freeze_manifest

    checks: dict[str, str] = {}
    try:
        checks["ledger"] = _ledger_probe()
    except (OSError, RuntimeError, sqlite3.Error):
        checks["ledger"] = "UNAVAILABLE"
    scheduler_threads = {
        "monitoring_scheduler": monitoring_engine._scheduler_thread,
        "opportunity_scheduler": opportunity_scheduler._scheduler_thread,
        "jesse_scheduler": jesse_scheduler._thread,
    }
    for name, thread in scheduler_threads.items():
        checks[name] = "READY" if thread is not None and thread.is_alive() else "UNAVAILABLE"
    try:
        safety = production_freeze_manifest()
        safe = (safety.get("all_invariants_pass") is True
                and safety.get("current_matches_proven_envelope") is True
                and all(safety.get(key) is False for key in (
                    "auto_trade_authority", "paper_order_permission",
                    "trade_execution_permission", "live_execution")))
        checks["authority_lock"] = "READY" if safe else "UNAVAILABLE"
    except (OSError, RuntimeError, ValueError, KeyError):
        checks["authority_lock"] = "UNAVAILABLE"
    ready = all(value == "READY" for value in checks.values())
    return ready, {"status": "READY" if ready else "NOT_READY", "checks": checks,
        "observed_at": datetime.now(timezone.utc).isoformat()}
