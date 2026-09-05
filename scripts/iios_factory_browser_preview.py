#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import json
import mimetypes
import os
import re
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
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
LIVING_CACHE_TTL_SECONDS = 5.0
LIVING_CACHE_STALE_SECONDS = 30.0
EXPANSION_CACHE_SECONDS = 15.0


def _living_snapshot_healthy(snapshot: dict[str, Any]) -> bool:
    return all(
        isinstance(snapshot.get(name), dict)
        and snapshot[name].get("availability") == "AVAILABLE"
        for name in ("factory", "jesse_dislocation")
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
    """Single-entry, process-local cache with one coalesced refresh."""

    def __init__(
        self,
        *,
        ttl_seconds: float = LIVING_CACHE_TTL_SECONDS,
        stale_seconds: float = LIVING_CACHE_STALE_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.ttl_seconds = ttl_seconds
        self.stale_seconds = stale_seconds
        self.clock = clock
        self._condition = threading.Condition()
        self._identity: Hashable | None = None
        self._snapshot: dict[str, Any] | None = None
        self._snapshot_at = 0.0
        self._last_good: dict[str, Any] | None = None
        self._last_good_at = 0.0
        self._refreshing = False
        self._refresh_count = 0

    def _decorate(
        self,
        snapshot: dict[str, Any],
        *,
        state: str,
        age_seconds: float | None,
    ) -> dict[str, Any]:
        result = copy.deepcopy(snapshot)
        result["cache"] = {
            "state": state,
            "age_seconds": None if age_seconds is None else round(max(0.0, age_seconds), 3),
            "ttl_seconds": self.ttl_seconds,
            "stale_after_seconds": self.stale_seconds,
            "refresh_in_flight": self._refreshing,
            "backend_refresh_count": self._refresh_count,
            "bounded_entries": 1,
        }
        return result

    def get(
        self,
        identity: Hashable,
        loader: Callable[[], dict[str, Any]],
    ) -> dict[str, Any]:
        while True:
            now = self.clock()
            with self._condition:
                if identity != self._identity:
                    if self._refreshing:
                        self._condition.wait(timeout=self.ttl_seconds)
                        if self._refreshing:
                            return self._decorate(
                                _degraded_living_snapshot(),
                                state="DEGRADED_NO_SNAPSHOT",
                                age_seconds=None,
                            )
                        continue
                    self._identity = identity
                    self._snapshot = None
                    self._last_good = None
                    self._snapshot_at = self._last_good_at = 0.0

                if self._snapshot is not None:
                    age = now - self._snapshot_at
                    if age < self.ttl_seconds:
                        state = "FRESH" if _living_snapshot_healthy(self._snapshot) else "DEGRADED"
                        return self._decorate(self._snapshot, state=state, age_seconds=age)

                if self._refreshing:
                    if self._last_good is not None:
                        age = now - self._last_good_at
                        state = "STALE_REFRESHING" if age <= self.stale_seconds else "DEGRADED_STALE"
                        return self._decorate(self._last_good, state=state, age_seconds=age)
                    self._condition.wait(timeout=self.ttl_seconds)
                    if self._refreshing:
                        return self._decorate(
                            _degraded_living_snapshot(),
                            state="DEGRADED_NO_SNAPSHOT",
                            age_seconds=None,
                        )
                    continue

                self._refreshing = True
                break

        try:
            refreshed = loader()
            if not isinstance(refreshed, dict):
                refreshed = _degraded_living_snapshot()
        except Exception:  # noqa: BLE001 - never expose raw backend evidence
            refreshed = _degraded_living_snapshot()
        refreshed = _sanitize_living_snapshot(refreshed)

        now = self.clock()
        with self._condition:
            self._refresh_count += 1
            healthy = _living_snapshot_healthy(refreshed)
            if healthy:
                self._last_good = copy.deepcopy(refreshed)
                self._last_good_at = now
                self._snapshot = copy.deepcopy(refreshed)
            elif self._last_good is not None:
                self._snapshot = copy.deepcopy(self._last_good)
                self._snapshot["status"] = "BACKEND_DEGRADED"
            else:
                self._snapshot = copy.deepcopy(refreshed)
                self._snapshot["status"] = "BACKEND_DEGRADED"
            self._snapshot_at = now
            self._refreshing = False
            self._condition.notify_all()
            state = "FRESH" if healthy else "DEGRADED"
            return self._decorate(self._snapshot, state=state, age_seconds=0.0)


_living_overview_cache = LivingOverviewCache()


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists() or not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
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


def _layer(name: str, path: Path, *, fresh_seconds: int | None = None) -> dict[str, Any]:
    payload = _read_json(path)
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


def _outcome_learning_layer(state_dir: Path) -> dict[str, Any]:
    full_path = state_dir / "latest_outcome_learning.json"
    compact_path = state_dir / "browser" / "outcome_learning.json"
    path = full_path if full_path.exists() else compact_path
    layer = _layer(
        "BATCH_9J_OUTCOME_LEARNING",
        path,
        fresh_seconds=2 * 60 * 60,
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
) -> dict[str, Any]:
    layers = {
        "factory_telemetry": _layer(
            "BATCH_9G_FACTORY_TELEMETRY",
            telemetry_dir / "latest.json",
            fresh_seconds=10 * 60,
        ),
        "market_validation": _layer(
            "BATCH_9H_MARKET_VALIDATION",
            state_dir / "latest_market_validation.json",
        ),
        "shadow_strategy": _layer(
            "BATCH_9I_SHADOW_STRATEGY",
            state_dir / "browser" / "shadow_strategy.json",
        ),
        "outcome_learning": _outcome_learning_layer(state_dir),
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


def _backend_layer(name: str, path: str) -> dict[str, Any]:
    try:
        payload = _backend_get_json(path)
    except Exception as exc:  # noqa: BLE001 - fail closed into explicit waiting
        return {
            "name": name,
            "availability": "WAITING",
            "error_type": type(exc).__name__,
            "error": str(exc)[:800],
            "payload": None,
        }
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
    validation = build_validation_stack(
        telemetry_dir=telemetry_dir,
        state_dir=state_dir,
    )

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
        )
        jesse_future = pool.submit(
            _backend_layer,
            "JESSE_DISLOCATION_PERSISTED_STATUS",
            "/intelligence/dislocation/status",
        )
        factory = factory_future.result()
        jesse_dislocation = jesse_future.result()

    return {
        "schema_version": LIVING_SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "validation": validation,
        "factory": factory,
        "jesse_dislocation": jesse_dislocation,
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
            self.wfile.write(body)

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
            self._send_json(
                _living_overview_cache.get(
                    identity,
                    lambda: build_living_factory_snapshot(
                        telemetry_dir=self.preview_server.telemetry_dir,
                        state_dir=self.preview_server.state_dir,
                    ),
                )
            )
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
            DEFAULT_BACKEND + "/system/status",
            multi_asset_reader=FixedProjectionReader(enabled=expansion_enabled).read,
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
