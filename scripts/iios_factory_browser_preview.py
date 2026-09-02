#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import mimetypes
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, unquote, urlparse
from urllib.request import Request, urlopen

BACKEND_ROOT = Path(__file__).resolve().parents[1] / "BACK END" / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from factory_truth import build_factory_truth

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
            state_dir / "shadow_strategy" / "latest_shadow_counterfactual.json",
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
                    "backend_access": "READ_ONLY_GET_ONLY",
                    "backend_write_permission": False,
                    "live_execution": False,
                }
            )
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
            self._send_json(
                build_factory_truth(
                    self.preview_server.ledger_path,
                    runtime_identity={
                        "pid": None,
                        "checkout": str(BACKEND_ROOT.parents[1]),
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
            self._send_json(
                build_living_factory_snapshot(
                    telemetry_dir=self.preview_server.telemetry_dir,
                    state_dir=self.preview_server.state_dir,
                )
            )
            return
        if parsed.path.startswith("/living/case/"):
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
        super().do_GET()

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
    ) -> None:
        self.static_root = static_root
        self.telemetry_dir = telemetry_dir
        self.state_dir = state_dir
        self.ledger_path = ledger_path.resolve()

        def handler(*args, **kwargs):
            return PreviewHandler(
                *args,
                directory=str(static_root),
                **kwargs,
            )

        super().__init__(server_address, handler)


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
    )
    print(
        json.dumps(
            {
                "status": "BATCH9L_BROWSER_PREVIEW_SERVING",
                "url": f"http://{host}:{int(args.port)}",
                "static_root": str(static_root),
                "ledger_access": "NONE",
                "backend_access": "READ_ONLY_GET_ONLY",
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
