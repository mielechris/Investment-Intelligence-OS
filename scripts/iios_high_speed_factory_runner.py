#!/usr/bin/env python3
from __future__ import annotations

import argparse
import signal
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND = REPO_ROOT / "BACK END" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

# Establish a normal certificate-verifying CA path before any official-source
# or external-provider HTTPS calls. This never disables TLS verification.
from index_tls_bootstrap import configure_verified_tls  # noqa: E402

_TLS_STATUS = configure_verified_tls()

# Load production patches / governed adapters before worker modules.
import app as _iios_bootstrap  # noqa: F401,E402
from high_speed_case_queue import run_case_floor_cycle  # noqa: E402
from high_speed_gemini_deep_worker import run_deep_once  # noqa: E402
from high_speed_gemini_pipeline import run_parallel_high_speed_cycle  # noqa: E402


DEFAULT_RADAR_MINUTES = 5
DEFAULT_CASE_FLOOR_SECONDS = 30
DEFAULT_DEEP_SECONDS = 60
_STOP = threading.Event()
_PRINT_LOCK = threading.Lock()


def _log(message: str) -> None:
    with _PRINT_LOCK:
        print(message, flush=True)


def _handle_stop(_signum: int, _frame: Any) -> None:
    _STOP.set()


def _sleep_interruptible(seconds: float) -> None:
    _STOP.wait(timeout=max(0.0, seconds))


def _loop(name: str, interval_seconds: float, fn: Callable[[], Any]) -> None:
    while not _STOP.is_set():
        started = time.time()
        try:
            result = fn()
            _log(f"[{name}] COMPLETE · {result}")
        except Exception as exc:  # noqa: BLE001
            _log(f"[{name}] FAILED_CLOSED · {type(exc).__name__}: {exc}")
        elapsed = time.time() - started
        _sleep_interruptible(max(1.0, interval_seconds - elapsed))


def run_once(*, dry_run: bool, no_models: bool, force_model_refresh: bool = False) -> int:
    _log("=== IIOS BATCH 9E · ONE-SHOT HIGH-SPEED RADAR ===")
    _log(f"Promotions enabled: {not dry_run}")
    _log(f"Grok/Gemini enabled: {not no_models}")
    _log(f"Force fresh model research: {bool(force_model_refresh)}")
    _log(f"Verified TLS mode: {_TLS_STATUS.get('mode')}")
    _log("Certificate verification: TRUE")
    _log("Broker connected: FALSE")
    _log("Live execution: FALSE")
    cycle = run_parallel_high_speed_cycle(
        enable_grok=not no_models,
        enable_gemini=not no_models,
        enable_promotions=not dry_run,
        force_model_refresh=bool(force_model_refresh),
    )
    _log(
        "RADAR COMPLETE · "
        f"universe={cycle.get('governed_universe_count')} "
        f"hits={cycle.get('screener_hit_count')} "
        f"grok={cycle.get('grok_candidate_count')} "
        f"gemini={cycle.get('gemini_candidate_count')} "
        f"promoted={cycle.get('promoted_case_count')} "
        f"seconds={cycle.get('cycle_duration_seconds')}"
    )
    return 0


def run_continuous(
    *,
    radar_minutes: int,
    case_floor_seconds: int,
    deep_seconds: int,
    no_models: bool,
) -> int:
    _log("=== IIOS BATCH 9E · HIGH-SPEED INTELLIGENCE FACTORY ===")
    _log(f"Radar cadence: {radar_minutes} minutes")
    _log(f"Case-floor cadence: {case_floor_seconds} seconds")
    _log(f"Gemini Pro deep-research queue cadence: {deep_seconds} seconds")
    _log("Grok Wire Room: X SEARCH + WEB SEARCH when configured")
    _log("Gemini Flash: Google Search grounding + URL Context + structured research")
    _log("Gemini Pro: selective complex finalists only, separate non-blocking lane")
    _log(f"Verified TLS mode: {_TLS_STATUS.get('mode')}")
    _log("Certificate verification: TRUE")
    _log("Maximum concurrent governed cases on 8-agent floor: 2")
    _log("Broker connected: FALSE")
    _log("Live execution: FALSE")
    _log("Paper / Shadow only")

    radar_fn = lambda: run_parallel_high_speed_cycle(  # noqa: E731
        enable_grok=not no_models,
        enable_gemini=not no_models,
        enable_promotions=True,
    )

    threads = [
        threading.Thread(
            target=_loop,
            args=("RADAR", radar_minutes * 60, radar_fn),
            name="iios-9e-radar",
            daemon=True,
        ),
        threading.Thread(
            target=_loop,
            args=("CASE FLOOR", case_floor_seconds, run_case_floor_cycle),
            name="iios-9e-case-floor",
            daemon=True,
        ),
        threading.Thread(
            target=_loop,
            args=("GEMINI PRO", deep_seconds, run_deep_once),
            name="iios-9e-gemini-pro",
            daemon=True,
        ),
    ]
    for thread in threads:
        thread.start()

    try:
        while not _STOP.is_set():
            alive = [thread.name for thread in threads if thread.is_alive()]
            if len(alive) != len(threads):
                missing = sorted(set(thread.name for thread in threads) - set(alive))
                raise RuntimeError(f"9E worker thread stopped unexpectedly: {missing}")
            _sleep_interruptible(5.0)
    except KeyboardInterrupt:
        _STOP.set()
    finally:
        _STOP.set()
        for thread in threads:
            thread.join(timeout=5)
        _log("Batch 9E stopped cleanly. Existing IIOS lanes were not stopped.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="IIOS Batch 9E high-speed intelligence factory")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--dry-run", action="store_true", help="Do not promote cases")
    parser.add_argument("--no-models", action="store_true", help="Skip Grok and Gemini provider calls")
    parser.add_argument(
        "--force-model-refresh",
        action="store_true",
        help="Ignore cached model context and require a fresh Grok/Gemini attempt for this cycle",
    )
    parser.add_argument("--radar-minutes", type=int, default=DEFAULT_RADAR_MINUTES)
    parser.add_argument("--case-floor-seconds", type=int, default=DEFAULT_CASE_FLOOR_SECONDS)
    parser.add_argument("--deep-seconds", type=int, default=DEFAULT_DEEP_SECONDS)
    # Compatibility alias for old operator commands; now controls Gemini Pro cadence.
    parser.add_argument("--swarm-seconds", type=int, default=None, help=argparse.SUPPRESS)
    args = parser.parse_args()

    signal.signal(signal.SIGINT, _handle_stop)
    signal.signal(signal.SIGTERM, _handle_stop)

    if args.once:
        return run_once(
            dry_run=args.dry_run,
            no_models=args.no_models,
            force_model_refresh=args.force_model_refresh,
        )

    deep_value = args.deep_seconds if args.swarm_seconds is None else args.swarm_seconds
    return run_continuous(
        radar_minutes=max(2, min(int(args.radar_minutes), 60)),
        case_floor_seconds=max(15, min(int(args.case_floor_seconds), 300)),
        deep_seconds=max(30, min(int(deep_value), 600)),
        no_models=bool(args.no_models),
    )


if __name__ == "__main__":
    raise SystemExit(main())
