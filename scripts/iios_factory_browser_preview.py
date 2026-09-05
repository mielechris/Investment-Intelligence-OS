#!/usr/bin/env python3
from __future__ import annotations

import argparse
import atexit
import copy
import json
import mimetypes
import os
import re
import stat
import subprocess
import sys
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Hashable
from urllib.error import HTTPError, URLError
from urllib.parse import quote, unquote, urlparse
from urllib.request import Request, urlopen

BACKEND_ROOT = Path(__file__).resolve().parents[1] / "BACK END" / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from factory_truth import build_factory_truth
from expansion_wing.acceptance_server import Compositor
from expansion_wing.projection_runtime import FixedProjectionReader

SCHEMA_VERSION = "batch9k-live-factory-browser-v1"
LIVING_SCHEMA_VERSION = "batch9l-living-factory-provenance-v1"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 5176
DEFAULT_BACKEND = "http://127.0.0.1:8002"
DEFAULT_STATE_DIR = Path.home() / "Library" / "Application Support" / "IIOS" / "market-validation"
DEFAULT_TELEMETRY_DIR = Path.home() / "Library" / "Application Support" / "IIOS" / "telemetry"
CASE_ID_PATTERN = re.compile(r"^[A-Za-z0-9_.:-]{1,160}$")
BACKEND_EXACT_PATHS = {
    "/experience/factory-intelligence/overview",
    "/intelligence/dislocation/status",
    "/system/status",
}
LIVING_CACHE_TTL_SECONDS = 15.0
LIVING_CACHE_STALE_SECONDS = 30.0
LIVING_CACHE_COLD_WAIT_SECONDS = 0.5
EXPANSION_CACHE_SECONDS = 15.0


def _living_snapshot_healthy(snapshot: dict[str, Any]) -> bool:
    return all(
        isinstance(snapshot.get(name), dict)
        and snapshot[name].get("availability") == "AVAILABLE"
        for name in ("factory", "jesse_dislocation")
    )


def _living_snapshot_valid(snapshot: dict[str, Any]) -> bool:
    """Validate the bounded browser contract without claiming sources are healthy."""
    safety = snapshot.get("safety")
    return (
        snapshot.get("schema_version") == LIVING_SCHEMA_VERSION
        and isinstance(snapshot.get("generated_at"), str)
        and _parse_time(snapshot.get("generated_at")) is not None
        and all(isinstance(snapshot.get(name), dict) for name in ("factory", "jesse_dislocation"))
        and isinstance(safety, dict)
        and safety.get("backend_write_permission") is False
        and safety.get("trade_execution_permission") is False
        and safety.get("live_execution") is False
    )


def _degraded_living_snapshot() -> dict[str, Any]:
    return {
        "schema_version": LIVING_SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "BACKEND_DEGRADED",
        "factory": {"availability": "WAITING", "payload": None},
        "jesse_dislocation": {"availability": "WAITING", "payload": None},
        "safety": {
            "preview_only": True,
            "localhost_only": True,
            "direct_ledger_access": False,
            "backend_access": "READ_ONLY_GET_ONLY",
            "backend_write_permission": False,
            "capital_authority": False,
            "trade_execution_permission": False,
            "live_execution": False,
        },
    }


def _sanitize_living_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    sanitized = copy.deepcopy(snapshot)
    for name in ("factory", "jesse_dislocation"):
        layer = sanitized.get(name)
        if not isinstance(layer, dict) or layer.get("availability") == "AVAILABLE":
            continue
        raw_category = f"{layer.pop('error_type', '')} {layer.pop('error', '')}".lower()
        layer["failure_category"] = (
            "BACKEND_TIMEOUT" if "timeout" in raw_category or "timed out" in raw_category
            else "BACKEND_UNAVAILABLE"
        )
    return sanitized


class LivingOverviewCache:
    """Validated single-entry stale-while-revalidate cache with one worker."""

    def __init__(
        self,
        *,
        ttl_seconds: float = LIVING_CACHE_TTL_SECONDS,
        stale_seconds: float = LIVING_CACHE_STALE_SECONDS,
        cold_wait_seconds: float = LIVING_CACHE_COLD_WAIT_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.ttl_seconds = ttl_seconds
        self.stale_seconds = stale_seconds
        self.cold_wait_seconds = cold_wait_seconds
        self.clock = clock
        self._condition = threading.Condition()
        self._identity: Hashable | None = None
        self._snapshot: dict[str, Any] | None = None
        self._snapshot_at = 0.0
        self._last_good: dict[str, Any] | None = None
        self._last_good_at = 0.0
        self._refreshing = False
        self._refresh_count = 0
        self._refresh_generation = 0
        self._last_failure_category: str | None = None
        self._last_lock_wait_ms = 0.0
        self._last_refresh_duration_ms: float | None = None
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="living-overview-refresh")
        self._future: Future[None] | None = None
        self._closed = False

    def _decorate(
        self,
        snapshot: dict[str, Any],
        *,
        state: str,
        age_seconds: float | None,
    ) -> dict[str, Any]:
        result = copy.deepcopy(snapshot)
        served_at = datetime.now(timezone.utc).isoformat()
        freshness = (
            "UNAVAILABLE" if age_seconds is None
            else "CURRENT" if age_seconds <= self.stale_seconds
            else "STALE"
        )
        result["cache"] = {
            "state": state,
            "age_seconds": None if age_seconds is None else round(max(0.0, age_seconds), 3),
            "freshness_state": freshness,
            "evidence_current": freshness == "CURRENT",
            "served_at": served_at,
            "ttl_seconds": self.ttl_seconds,
            "stale_after_seconds": self.stale_seconds,
            "refresh_in_flight": self._refreshing,
            "backend_refresh_count": self._refresh_count,
            "refresh_generation": self._refresh_generation,
            "last_failure_category": self._last_failure_category,
            "cache_lock_wait_ms": round(self._last_lock_wait_ms, 3),
            "last_refresh_duration_ms": (
                None
                if self._last_refresh_duration_ms is None
                else round(self._last_refresh_duration_ms, 3)
            ),
            "bounded_entries": 1,
            "refresh_workers": 1,
        }
        return result

    def _unavailable(self) -> dict[str, Any]:
        unavailable = _degraded_living_snapshot()
        unavailable["status"] = "FACTORY_SOURCE_UNAVAILABLE"
        return self._decorate(unavailable, state="DEGRADED_NO_SNAPSHOT", age_seconds=None)

    def _run_refresh(
        self,
        identity: Hashable,
        loader: Callable[[], dict[str, Any]],
    ) -> None:
        refresh_started = time.monotonic()
        failure: str | None = None
        try:
            value = loader()
            if not isinstance(value, dict):
                failure = "FACTORY_SOURCE_INVALID"
                value = None
            else:
                value = _sanitize_living_snapshot(value)
                if not _living_snapshot_valid(value):
                    failure = "FACTORY_SOURCE_INVALID"
                    value = None
        except Exception:  # noqa: BLE001 - fixed category only
            failure = "FACTORY_SOURCE_UNAVAILABLE"
            value = None

        completed_at = self.clock()
        with self._condition:
            if identity == self._identity and not self._closed:
                self._refresh_count += 1
                if value is not None:
                    self._snapshot = copy.deepcopy(value)
                    self._snapshot_at = completed_at
                    self._last_good = copy.deepcopy(value)
                    self._last_good_at = completed_at
                    self._refresh_generation += 1
                    self._last_failure_category = None
                else:
                    self._last_failure_category = failure or "FACTORY_SOURCE_UNAVAILABLE"
                self._last_refresh_duration_ms = (time.monotonic() - refresh_started) * 1000.0
            self._refreshing = False
            self._future = None
            self._condition.notify_all()

    def _start_refresh_locked(
        self,
        identity: Hashable,
        loader: Callable[[], dict[str, Any]],
    ) -> Future[None]:
        self._refreshing = True
        self._future = self._executor.submit(self._run_refresh, identity, loader)
        return self._future

    def get(
        self,
        identity: Hashable,
        loader: Callable[[], dict[str, Any]],
    ) -> dict[str, Any]:
        future: Future[None] | None = None
        now = self.clock()
        lock_started = time.monotonic()
        with self._condition:
            self._last_lock_wait_ms = (time.monotonic() - lock_started) * 1000.0
            if self._closed:
                return self._unavailable()
            if identity != self._identity:
                if self._refreshing:
                    return self._unavailable()
                self._identity = identity
                self._snapshot = self._last_good = None
                self._snapshot_at = self._last_good_at = 0.0

            if self._snapshot is not None and not _living_snapshot_valid(self._snapshot):
                self._snapshot = None
                self._snapshot_at = 0.0
                self._last_failure_category = "FACTORY_CACHE_INVALID"

            if self._snapshot is not None:
                age = now - self._snapshot_at
                if age < self.ttl_seconds:
                    state = "FRESH" if _living_snapshot_healthy(self._snapshot) else "DEGRADED"
                    return self._decorate(self._snapshot, state=state, age_seconds=age)
                if not self._refreshing:
                    self._start_refresh_locked(identity, loader)
                state = "STALE_REFRESHING" if age <= self.stale_seconds else "DEGRADED_STALE"
                return self._decorate(self._snapshot, state=state, age_seconds=age)

            if not self._refreshing:
                future = self._start_refresh_locked(identity, loader)
            else:
                future = self._future

        if future is not None:
            try:
                future.result(timeout=self.cold_wait_seconds)
            except FutureTimeoutError:
                pass
        with self._condition:
            if identity == self._identity and self._snapshot is not None:
                age = self.clock() - self._snapshot_at
                state = "FRESH" if _living_snapshot_healthy(self._snapshot) else "DEGRADED"
                return self._decorate(self._snapshot, state=state, age_seconds=age)
            return self._unavailable()

    def close(self) -> None:
        with self._condition:
            if self._closed:
                return
            self._closed = True
        self._executor.shutdown(wait=True, cancel_futures=False)


_living_overview_cache = LivingOverviewCache()
atexit.register(_living_overview_cache.close)


def _add_timing(timings: dict[str, float] | None, category: str, started: float) -> None:
    if timings is not None:
        timings[category] = timings.get(category, 0.0) + ((time.monotonic() - started) * 1000.0)


def _read_json(path: Path, *, timings: dict[str, float] | None = None) -> dict[str, Any] | None:
    started = time.monotonic()
    try:
        metadata = path.stat()
    except OSError:
        _add_timing(timings, "source_stat_ms", started)
        return None
    _add_timing(timings, "source_stat_ms", started)
    if not stat.S_ISREG(metadata.st_mode):
        return None
    started = time.monotonic()
    try:
        raw = path.read_bytes()
    except OSError:
        _add_timing(timings, "source_read_ms", started)
        return None
    _add_timing(timings, "source_read_ms", started)
    started = time.monotonic()
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        _add_timing(timings, "json_parse_ms", started)
        return None
    _add_timing(timings, "json_parse_ms", started)
    return value if isinstance(value, dict) else None


def _parse_time(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _age_seconds(payload: dict[str, Any] | None, path: Path) -> int | None:
    if not payload:
        return None
    observed = _parse_time(payload.get("heartbeat_at") or payload.get("generated_at"))
    if observed is None:
        try:
            observed = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        except OSError:
            return None
    return max(0, int((datetime.now(timezone.utc) - observed).total_seconds()))


def _layer(
    name: str,
    path: Path,
    *,
    fresh_seconds: int | None = None,
    timings: dict[str, float] | None = None,
) -> dict[str, Any]:
    payload = _read_json(path, timings=timings)
    if payload is None:
        return {
            "name": name,
            "availability": "WAITING",
            "path": str(path),
            "age_seconds": None,
            "payload": None,
        }
    age = _age_seconds(payload, path)
    availability = "AVAILABLE"
    if fresh_seconds is not None and age is not None and age > fresh_seconds:
        availability = "STALE"
    return {
        "name": name,
        "availability": availability,
        "path": str(path),
        "age_seconds": age,
        "payload": payload,
    }


def _normalize_outcome_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Keep 9K display compatibility while retaining exact 9J lineage fields."""
    normalized = dict(payload)
    recent: list[dict[str, Any]] = []
    for value in payload.get("recent_outcomes") or []:
        if not isinstance(value, dict):
            continue
        row = dict(value)
        if not row.get("decision_quality_label") and row.get("decision_quality"):
            row["decision_quality_label"] = row.get("decision_quality")
        if not row.get("market_outcome_label") and row.get("market_outcome"):
            row["market_outcome_label"] = row.get("market_outcome")
        recent.append(row)
    normalized["recent_outcomes"] = recent
    queue = payload.get("judgment_bank_review_queue")
    if isinstance(queue, list):
        normalized["judgment_bank_review_queue_count"] = len(queue)
    return normalized


def _outcome_learning_layer(
    state_dir: Path,
    *,
    timings: dict[str, float] | None = None,
) -> dict[str, Any]:
    full_path = state_dir / "latest_outcome_learning.json"
    compact_path = state_dir / "browser" / "outcome_learning.json"
    path = full_path if full_path.exists() else compact_path
    layer = _layer(
        "BATCH_9J_OUTCOME_LEARNING",
        path,
        fresh_seconds=2 * 60 * 60,
        timings=timings,
    )
    payload = layer.get("payload")
    if isinstance(payload, dict):
        layer["payload"] = _normalize_outcome_payload(payload)
        layer["lineage_mode"] = (
            "CASE_AND_CANDIDATE_LINKED"
            if path == full_path
            else "COMPACT_BROWSER_FALLBACK"
        )
    else:
        layer["lineage_mode"] = "WAITING"
    return layer


def build_validation_stack(
    *,
    telemetry_dir: Path = DEFAULT_TELEMETRY_DIR,
    state_dir: Path = DEFAULT_STATE_DIR,
    timings: dict[str, float] | None = None,
) -> dict[str, Any]:
    layers = {
        "factory_telemetry": _layer(
            "BATCH_9G_FACTORY_TELEMETRY",
            telemetry_dir / "latest.json",
            fresh_seconds=10 * 60,
            timings=timings,
        ),
        "market_validation": _layer(
            "BATCH_9H_MARKET_VALIDATION",
            state_dir / "latest_market_validation.json",
            timings=timings,
        ),
        "shadow_strategy": _layer(
            "BATCH_9I_SHADOW_STRATEGY",
            state_dir / "browser" / "shadow_strategy.json",
            timings=timings,
        ),
        "outcome_learning": _outcome_learning_layer(state_dir, timings=timings),
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "layers": layers,
        "safety": {
            "preview_only": True,
            "localhost_only": True,
            "ledger_access": "NONE",
            "github_credentials_exposed": False,
            "threshold_change_authority": False,
            "committee_gate_change_authority": False,
            "risk_gate_change_authority": False,
            "capital_authority": False,
            "trade_execution_permission": False,
            "live_execution": False,
        },
    }


def _validate_backend_path(path: str) -> str:
    if path in BACKEND_EXACT_PATHS:
        return path
    prefix = "/experience/factory-intelligence/case/"
    if path.startswith(prefix):
        case_id = unquote(path.removeprefix(prefix))
        if not CASE_ID_PATTERN.fullmatch(case_id):
            raise ValueError("Invalid IIOS case identifier")
        return prefix + quote(case_id, safe="")
    raise ValueError("Backend path is not allow-listed for Batch 9L")


def _backend_get_json(path: str, *, timeout_seconds: float = 3.0) -> dict[str, Any]:
    safe_path = _validate_backend_path(path)
    request = Request(
        f"{DEFAULT_BACKEND}{safe_path}",
        headers={
            "Accept": "application/json",
            "User-Agent": "IIOS-Batch9L-ReadOnly-Sidecar/1.2",
        },
        method="GET",
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            value = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:600]
        raise RuntimeError(
            f"Backend GET {safe_path} returned HTTP {exc.code}: {detail}"
        ) from exc
    except URLError as exc:
        raise RuntimeError(
            f"Backend GET {safe_path} unavailable: {exc.reason}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Backend GET {safe_path} returned non-JSON content"
        ) from exc
    if not isinstance(value, dict):
        raise RuntimeError(
            f"Backend GET {safe_path} returned a non-object payload"
        )
    return value


def _backend_layer(
    name: str,
    path: str,
    *,
    timings: dict[str, float] | None = None,
    timing_category: str = "backend_read_ms",
) -> dict[str, Any]:
    started = time.monotonic()
    try:
        payload = _backend_get_json(path)
    except Exception as exc:  # noqa: BLE001 - fail closed into explicit waiting
        _add_timing(timings, timing_category, started)
        return {
            "name": name,
            "availability": "WAITING",
            "error_type": type(exc).__name__,
            "error": str(exc)[:800],
            "payload": None,
        }
    _add_timing(timings, timing_category, started)
    return {
        "name": name,
        "availability": "AVAILABLE",
        "error_type": None,
        "error": None,
        "payload": payload,
    }


def _backend_truth_probe() -> dict[str, Any]:
    try:
        _backend_get_json("/system/status")
    except Exception as exc:  # noqa: BLE001 - response health must be explicit
        return {"responsive": False, "detail": f"{type(exc).__name__}: {exc}"}
    return {"responsive": True}


def _process_observation() -> dict[str, Any]:
    runners = {
        "9E": "iios_high_speed_factory_runner.py",
        "9A": "iios_observation_runner.py",
        "9B": "iios_paper_trading_runner.py",
    }
    try:
        result = subprocess.run(
            ["ps", "-axo", "pid=,command="],
            check=True,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return {key: {"observed": False, "pid": None} for key in runners}

    observed: dict[str, dict[str, Any]] = {}
    for key, marker in runners.items():
        match = next(
            (
                line.strip().split(maxsplit=1)
                for line in result.stdout.splitlines()
                if marker in line
            ),
            None,
        )
        observed[key] = {
            "observed": bool(match),
            "pid": int(match[0]) if match and match[0].isdigit() else None,
        }
    return observed


def _backend_runtime_identity() -> dict[str, Any]:
    try:
        listener = subprocess.run(
            ["lsof", "-t", "-nP", "-iTCP:8002", "-sTCP:LISTEN"],
            check=False,
            capture_output=True,
            text=True,
            timeout=2,
        )
        pid = next(
            (
                int(line.strip())
                for line in listener.stdout.splitlines()
                if line.strip().isdigit()
            ),
            None,
        )
        if pid is None:
            return {"pid": None, "checkout": None, "observed": False}
        cwd = subprocess.run(
            ["lsof", "-a", "-p", str(pid), "-d", "cwd", "-Fn"],
            check=False,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return {"pid": None, "checkout": None, "observed": False}
    checkout = next(
        (line[1:] for line in cwd.stdout.splitlines() if line.startswith("n")),
        None,
    )
    return {"pid": pid, "checkout": checkout, "observed": True}


def build_living_factory_snapshot(
    *,
    telemetry_dir: Path = DEFAULT_TELEMETRY_DIR,
    state_dir: Path = DEFAULT_STATE_DIR,
) -> dict[str, Any]:
    total_started = time.monotonic()
    timings: dict[str, float] = {
        "source_stat_ms": 0.0,
        "source_read_ms": 0.0,
        "json_parse_ms": 0.0,
        "backend_factory_read_ms": 0.0,
        "backend_dislocation_read_ms": 0.0,
    }
    assembly_started = time.monotonic()
    validation = build_validation_stack(
        telemetry_dir=telemetry_dir,
        state_dir=state_dir,
        timings=timings,
    )
    _add_timing(timings, "telemetry_assembly_ms", assembly_started)

    # The browser refreshes every five seconds. These two independent,
    # read-only Backend 8002 lookups each have a three-second fail-closed
    # timeout. Running them sequentially can exceed the browser refresh window
    # and cause an otherwise healthy request to be repeatedly aborted.
    # Parallelizing only these GETs preserves the exact read-only contract while
    # keeping worst-case sidecar latency inside one refresh window.
    with ThreadPoolExecutor(max_workers=2, thread_name_prefix="batch9l-readonly") as pool:
        factory_future = pool.submit(
            _backend_layer,
            "BACKEND_8002_FACTORY_INTELLIGENCE_READ_ONLY",
            "/experience/factory-intelligence/overview",
            timings=timings,
            timing_category="backend_factory_read_ms",
        )
        jesse_future = pool.submit(
            _backend_layer,
            "JESSE_DISLOCATION_PERSISTED_STATUS",
            "/intelligence/dislocation/status",
            timings=timings,
            timing_category="backend_dislocation_read_ms",
        )
        factory = factory_future.result()
        jesse_dislocation = jesse_future.result()

    # SQLite and story construction are owned by the Backend endpoint and are
    # intentionally not inferred by this read-only sidecar.
    timings["sqlite_connect_query_ms"] = None  # type: ignore[assignment]
    timings["ledger_reconstruction_ms"] = None  # type: ignore[assignment]
    timings["character_story_assembly_ms"] = None  # type: ignore[assignment]
    timings["total_refresh_ms"] = (time.monotonic() - total_started) * 1000.0
    sanitized_timings = {
        key: None if value is None else round(value, 3)
        for key, value in timings.items()
    }

    return {
        "schema_version": LIVING_SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "validation": validation,
        "factory": factory,
        "jesse_dislocation": jesse_dislocation,
        "diagnostics": {
            "schema_version": "living-overview-timing-v1",
            "categories_ms": sanitized_timings,
            "backend_internal_sqlite_timing": "UNAVAILABLE_AT_READ_ONLY_BOUNDARY",
        },
        "safety": {
            "preview_only": True,
            "localhost_only": True,
            "direct_ledger_access": False,
            "backend_access": "READ_ONLY_GET_ONLY",
            "backend_write_permission": False,
            "allowed_backend_paths": [
                "/experience/factory-intelligence/overview",
                "/experience/factory-intelligence/case/{case_id}",
                "/intelligence/dislocation/status",
            ],
            "threshold_change_authority": False,
            "committee_gate_change_authority": False,
            "risk_gate_change_authority": False,
            "capital_authority": False,
            "trade_execution_permission": False,
            "live_execution": False,
        },
    }


def build_isolated_living_factory_snapshot(
    *,
    telemetry_dir: Path,
    state_dir: Path,
) -> dict[str, Any]:
    """Build fixture acceptance truth without contacting Backend 8002."""
    total_started = time.monotonic()
    timings: dict[str, float] = {}
    assembly_started = time.monotonic()
    validation = build_validation_stack(
        telemetry_dir=telemetry_dir,
        state_dir=state_dir,
        timings=timings,
    )
    _add_timing(timings, "telemetry_assembly_ms", assembly_started)
    timings["total_refresh_ms"] = (time.monotonic() - total_started) * 1000.0
    return {
        "schema_version": LIVING_SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "FACTORY_SOURCE_UNAVAILABLE",
        "fixture_only": True,
        "validation": validation,
        "factory": {
            "availability": "WAITING",
            "payload": None,
            "failure_category": "FIXTURE_SOURCE_UNAVAILABLE",
        },
        "jesse_dislocation": {
            "availability": "WAITING",
            "payload": None,
            "failure_category": "FIXTURE_SOURCE_UNAVAILABLE",
        },
        "diagnostics": {
            "schema_version": "living-overview-timing-v1",
            "categories_ms": {
                **{key: round(value, 3) for key, value in timings.items()},
                "sqlite_connect_query_ms": None,
                "ledger_reconstruction_ms": None,
                "character_story_assembly_ms": None,
            },
            "backend_internal_sqlite_timing": "NOT_ACCESSED_FIXTURE_ISOLATION",
        },
        "safety": {
            "preview_only": True,
            "localhost_only": True,
            "direct_ledger_access": False,
            "backend_access": "NONE",
            "backend_write_permission": False,
            "capital_authority": False,
            "trade_execution_permission": False,
            "live_execution": False,
        },
    }


class PreviewHandler(SimpleHTTPRequestHandler):
    server_version = "IIOSBatch9LPreview/1.2"

    def __init__(self, *args, directory: str | None = None, **kwargs):
        super().__init__(*args, directory=directory, **kwargs)

    @property
    def preview_server(self) -> "PreviewServer":
        return self.server  # type: ignore[return-value]

    def _send_json(self, payload: dict[str, Any], status: int = 200) -> None:
        body = json.dumps(
            payload,
            indent=2,
            sort_keys=True,
            default=str,
        ).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                # A cancelled browser request must not affect cache ownership or
                # trigger an unbounded retry. No request/body data is logged.
                return

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self._send_json(
                {
                    "status": "BATCH9L_BROWSER_PREVIEW_HEALTHY",
                    "host": self.preview_server.server_address[0],
                    "port": self.preview_server.server_address[1],
                    "ledger_access": "NONE",
                    "backend_access": "NONE" if self.preview_server.fixture_isolated else "READ_ONLY_GET_ONLY",
                    "backend_write_permission": False,
                    "live_execution": False,
                    "runtime_capabilities": self.preview_server.runtime_capabilities(),
                }
            )
            return
        if parsed.path == "/expansion-wing/snapshot":
            if not self.preview_server.expansion_enabled:
                self._send_json({"status": "EXPANSION_WING_NOT_ACTIVATED"}, status=HTTPStatus.SERVICE_UNAVAILABLE)
                return
            self._send_json(self.preview_server.expansion_snapshot())
            return
        if parsed.path == "/validation/stack":
            self._send_json(
                build_validation_stack(
                    telemetry_dir=self.preview_server.telemetry_dir,
                    state_dir=self.preview_server.state_dir,
                )
            )
            return
        if parsed.path == "/truth/factory":
            if self.preview_server.fixture_isolated:
                self._send_json({"status": "FIXTURE_SOURCE_UNAVAILABLE", "fixture_only": True,
                    "ledger_access": "NONE", "backend_access": "NONE", "live_execution": False},
                    status=HTTPStatus.SERVICE_UNAVAILABLE)
                return
            self._send_json(
                build_factory_truth(
                    self.preview_server.ledger_path,
                    runtime_identity={
                        **_backend_runtime_identity(),
                        "ledger_path": str(self.preview_server.ledger_path),
                        "runners": _process_observation(),
                    },
                    sidecar_identity={
                        "pid": os.getpid(),
                        "checkout": str(Path(__file__).resolve().parents[1]),
                        "ledger_path": str(self.preview_server.ledger_path),
                    },
                    backend_probe=_backend_truth_probe,
                )
            )
            return
        if parsed.path == "/living/overview":
            identity = (
                LIVING_SCHEMA_VERSION,
                DEFAULT_BACKEND,
                str(self.preview_server.telemetry_dir.resolve()),
                str(self.preview_server.state_dir.resolve()),
            )
            if self.preview_server.fixture_isolated:
                loader = lambda: build_isolated_living_factory_snapshot(
                    telemetry_dir=self.preview_server.telemetry_dir,
                    state_dir=self.preview_server.state_dir,
                )
            else:
                loader = lambda: build_living_factory_snapshot(
                    telemetry_dir=self.preview_server.telemetry_dir,
                    state_dir=self.preview_server.state_dir,
                )
            payload = copy.deepcopy(
                _living_overview_cache.get(
                    identity,
                    loader,
                )
            )
            # Runtime capabilities are deliberately attached after the evidence
            # cache. A response cached before activation can therefore never
            # suppress an authenticated server configuration after restart.
            payload["runtime_capabilities"] = self.preview_server.runtime_capabilities()
            self._send_json(payload)
            return
        if parsed.path.startswith("/living/case/"):
            if self.preview_server.fixture_isolated:
                self._send_json({"status": "FIXTURE_SOURCE_UNAVAILABLE", "fixture_only": True,
                    "backend_access": "NONE", "live_execution": False}, status=HTTPStatus.SERVICE_UNAVAILABLE)
                return
            case_id = unquote(parsed.path.removeprefix("/living/case/"))
            if not CASE_ID_PATTERN.fullmatch(case_id):
                self._send_json(
                    {
                        "status": "INVALID_CASE_ID",
                        "detail": (
                            "Case identifier was rejected by the Batch 9L "
                            "read-only proxy."
                        ),
                        "live_execution": False,
                    },
                    status=HTTPStatus.BAD_REQUEST,
                )
                return
            try:
                payload = _backend_get_json(
                    "/experience/factory-intelligence/case/"
                    + quote(case_id, safe="")
                )
            except Exception as exc:  # noqa: BLE001 - explicit warm-up response
                self._send_json(
                    {
                        "status": "CASE_DETAIL_WAITING",
                        "error_type": type(exc).__name__,
                        "detail": str(exc)[:800],
                        "trade_execution_permission": False,
                        "live_execution": False,
                    },
                    status=HTTPStatus.SERVICE_UNAVAILABLE,
                )
                return
            self._send_json(payload)
            return

        target = self.translate_path(parsed.path)
        if parsed.path != "/" and not Path(target).exists():
            index_path = self.preview_server.static_root / "index.html"
            if index_path.exists():
                try:
                    data = index_path.read_bytes()
                except OSError:
                    self.send_error(HTTPStatus.INTERNAL_SERVER_ERROR)
                    return
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(data)
                return
        if self.command == "HEAD":
            super().do_HEAD()
        else:
            super().do_GET()

    def do_HEAD(self) -> None:  # noqa: N802
        self.do_GET()

    def _method_not_allowed(self) -> None:
        self._send_json({"status": "METHOD_NOT_ALLOWED", "read_only": True}, status=HTTPStatus.METHOD_NOT_ALLOWED)

    do_POST = _method_not_allowed
    do_PUT = _method_not_allowed
    do_PATCH = _method_not_allowed
    do_DELETE = _method_not_allowed

    def end_headers(self) -> None:
        self.send_header("X-IIOS-Preview", "BATCH9L_READ_ONLY")
        super().end_headers()

    def log_message(self, format: str, *args: Any) -> None:
        message = format % args
        print(f"[batch9l] {self.address_string()} {message}", flush=True)


class PreviewServer(ThreadingHTTPServer):
    def __init__(
        self,
        server_address: tuple[str, int],
        static_root: Path,
        telemetry_dir: Path,
        state_dir: Path,
        ledger_path: Path,
        expansion_enabled: bool = False,
        expansion_compositor: Any | None = None,
        fixture_isolated: bool = False,
    ) -> None:
        self.static_root = static_root
        self.telemetry_dir = telemetry_dir
        self.state_dir = state_dir
        self.ledger_path = ledger_path.resolve()
        self.expansion_enabled = expansion_enabled
        self.fixture_isolated = fixture_isolated
        self._expansion_lock = threading.Lock()
        self._expansion_cached: dict[str, Any] | None = None
        self._expansion_cached_at = 0.0
        self._expansion_compositor = expansion_compositor or Compositor(
            telemetry_dir / "latest.json",
            state_dir / "latest_market_validation.json",
            state_dir / "browser" / "shadow_strategy.json",
            state_dir / "browser" / "outcome_learning.json",
            (
                "http://127.0.0.1:1/system/status"
                if fixture_isolated
                else DEFAULT_BACKEND + "/system/status"
            ),
            multi_asset_reader=(
                None
                if fixture_isolated
                else FixedProjectionReader(enabled=expansion_enabled).read
            ),
        )

        def handler(*args, **kwargs):
            return PreviewHandler(
                *args,
                directory=str(static_root),
                **kwargs,
            )

        super().__init__(server_address, handler)

    def expansion_snapshot(self) -> dict[str, Any]:
        now = time.monotonic()
        with self._expansion_lock:
            if self._expansion_cached is None or now - self._expansion_cached_at >= EXPANSION_CACHE_SECONDS:
                self._expansion_cached = self._expansion_compositor.snapshot()
                self._expansion_cached_at = now
            return copy.deepcopy(self._expansion_cached)

    def runtime_capabilities(self) -> dict[str, Any]:
        """Return a fixed, scalar-only projection of authenticated server configuration."""
        return {
            "schema_version": "iios-runtime-capabilities-v1",
            "configuration_source": "SERVER_COMMAND_LINE",
            "configuration_authenticated": True,
            "expansion_wing_enabled": bool(self.expansion_enabled),
            "expansion_snapshot_path": "/expansion-wing/snapshot" if self.expansion_enabled else None,
            "read_only": True,
            "publisher_control": False,
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Serve the Batch 9L localhost-only living IIOS browser preview."
        )
    )
    parser.add_argument("--root", required=True, help="Built frontend dist directory")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--telemetry-dir", default=str(DEFAULT_TELEMETRY_DIR))
    parser.add_argument("--state-dir", default=str(DEFAULT_STATE_DIR))
    parser.add_argument("--enable-expansion-wing", action="store_true")
    parser.add_argument("--fixture-isolated", action="store_true",
        help="Disable every backend-dependent route for synthetic fixture review")
    parser.add_argument(
        "--ledger-path",
        default=str(BACKEND_ROOT / "iios_ledger.db"),
        help="SQLite ledger read only by the Factory Truth endpoint",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    static_root = Path(args.root).expanduser().resolve()
    if not (static_root / "index.html").exists():
        raise SystemExit(f"Built frontend index.html not found: {static_root}")
    host = str(args.host).strip()
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise SystemExit("Batch 9L preview must bind to localhost only")
    telemetry_dir = Path(args.telemetry_dir).expanduser()
    state_dir = Path(args.state_dir).expanduser()
    ledger_path = Path(args.ledger_path).expanduser().resolve()
    mimetypes.init()
    server = PreviewServer(
        (host, int(args.port)),
        static_root,
        telemetry_dir,
        state_dir,
        ledger_path,
        expansion_enabled=args.enable_expansion_wing,
        fixture_isolated=args.fixture_isolated,
    )
    print(
        json.dumps(
            {
                "status": "BATCH9L_BROWSER_PREVIEW_SERVING",
                "url": f"http://{host}:{int(args.port)}",
                "static_root": str(static_root),
                "ledger_access": "NONE",
                "backend_access": "NONE" if args.fixture_isolated else "READ_ONLY_GET_ONLY",
                "backend_write_permission": False,
                "live_execution": False,
            },
            sort_keys=True,
        ),
        flush=True,
    )
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
