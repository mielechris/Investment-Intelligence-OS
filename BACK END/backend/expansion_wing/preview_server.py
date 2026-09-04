from __future__ import annotations

import argparse
import fcntl
import json
import mimetypes
import signal
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

from .acceptance_server import Compositor
from .knowledge_operations import knowledge_operations_projection

HOST = "127.0.0.1"
SERVICE_SCHEMA = "expansion-wing-preview-health-v1"
MAX_RESPONSE_BYTES = 2_000_000
ALLOWED_METHODS = {"GET", "HEAD"}


class PreviewApplication:
    def __init__(self, static_root: Path, compositor: Compositor, *, cache_seconds: float = 15.0) -> None:
        self.static_root = static_root.resolve(strict=True)
        if not self.static_root.is_dir() or not (self.static_root / "index.html").is_file():
            raise ValueError("STATIC_ROOT_INVALID")
        self.compositor = compositor
        self.cache_seconds = max(1.0, min(cache_seconds, 60.0))
        self._lock = threading.Lock()
        self._cached: dict[str, Any] | None = None
        self._cached_at = 0.0

    def snapshot(self, now: float | None = None) -> dict[str, Any]:
        instant = time.monotonic() if now is None else now
        with self._lock:
            if self._cached is None or instant - self._cached_at >= self.cache_seconds:
                self._cached = self.compositor.snapshot()
                self._cached_at = instant
            return self._cached

    def health(self) -> dict[str, Any]:
        snapshot = self.snapshot()
        sections = snapshot.get("sections") if isinstance(snapshot.get("sections"), dict) else {}
        states = {key: value.get("state", "UNAVAILABLE") for key, value in sections.items() if isinstance(value, dict)}
        truth = "CURRENT" if states and all(value == "CURRENT" for value in states.values()) else (
            "INCOMPLETE" if "INCOMPLETE" in states.values() else "UNAVAILABLE")
        return {"service_status": "HEALTHY", "schema_version": SERVICE_SCHEMA, "snapshot_truth_state": truth,
                "generated_at": datetime.now(timezone.utc).isoformat(), "source_availability_categories": states,
                "backend_reachability_category": states.get("service_health", "UNAVAILABLE"), "read_only": True,
                "ledger_write": False, "trade_execution_permission": False, "broker_connected": False,
                "live_execution": False}

    def static_file(self, request_path: str) -> Path | None:
        path = unquote(urlsplit(request_path).path)
        if path in ("", "/"): path = "/index.html"
        if "\x00" in path or any(part == ".." for part in Path(path).parts): return None
        candidate = (self.static_root / path.lstrip("/")).resolve()
        try: candidate.relative_to(self.static_root)
        except ValueError: return None
        if not candidate.is_file() or candidate.stat().st_size > MAX_RESPONSE_BYTES: return None
        return candidate


def handler_for(app: PreviewApplication):
    class Handler(BaseHTTPRequestHandler):
        def _headers(self, status: int, content_type: str, length: int) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(length))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Security-Policy", "default-src 'self'; connect-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Frame-Options", "DENY")
            self.end_headers()

        def _json(self, value: dict[str, Any], status: int = 200, *, body: bool = True) -> None:
            encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
            if len(encoded) > MAX_RESPONSE_BYTES: encoded = b'{"status":"RESPONSE_LIMIT_EXCEEDED"}'; status = 503
            self._headers(status, "application/json", len(encoded))
            if body: self.wfile.write(encoded)

        def _route(self, *, body: bool) -> None:
            path = urlsplit(self.path).path
            if path == "/snapshot": return self._json(app.snapshot(), body=body)
            if path == "/health": return self._json(app.health(), body=body)
            asset = app.static_file(path)
            if asset is None: return self._json({"status": "NOT_FOUND"}, 404, body=body)
            encoded = asset.read_bytes(); self._headers(200, mimetypes.guess_type(asset.name)[0] or "application/octet-stream", len(encoded))
            if body: self.wfile.write(encoded)

        def do_GET(self) -> None:
            try: self._route(body=True)
            except Exception: self._json({"status": "SERVICE_UNAVAILABLE"}, 503)
        def do_HEAD(self) -> None:
            try: self._route(body=False)
            except Exception: self._json({"status": "SERVICE_UNAVAILABLE"}, 503, body=False)
        def __getattr__(self, name: str):
            if name.startswith("do_"): return lambda: self._json({"status": "METHOD_NOT_ALLOWED"}, 405)
            raise AttributeError(name)
        def log_message(self, _format: str, *_args: Any) -> None: return
    return Handler


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=5177)
    parser.add_argument("--static-root", required=True, type=Path)
    parser.add_argument("--state-dir", required=True, type=Path)
    parser.add_argument("--telemetry", required=True, type=Path)
    parser.add_argument("--validation", required=True, type=Path)
    parser.add_argument("--shadow", required=True, type=Path)
    parser.add_argument("--outcome", required=True, type=Path)
    parser.add_argument("--backend", default="http://127.0.0.1:8002/system/status")
    parser.add_argument("--security-root", type=Path)
    parser.add_argument("--archive-root", type=Path)
    args = parser.parse_args()
    args.state_dir.mkdir(mode=0o700, parents=True, exist_ok=True); args.state_dir.chmod(0o700)
    lock_file = (args.state_dir / "preview.lock").open("w")
    try: fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError: raise SystemExit("DUPLICATE_INSTANCE") from None
    knowledge_reader = None
    if args.security_root is not None or args.archive_root is not None:
        if args.security_root is None or args.archive_root is None: raise SystemExit("KNOWLEDGE_ROOT_PAIR_REQUIRED")
        knowledge_reader = lambda: knowledge_operations_projection(args.security_root, args.archive_root)
    compositor = Compositor(args.telemetry, args.validation, args.shadow, args.outcome, args.backend, knowledge_reader)
    app = PreviewApplication(args.static_root, compositor)
    server = ThreadingHTTPServer((HOST, args.port), handler_for(app))
    server.daemon_threads = True
    signal.signal(signal.SIGTERM, lambda *_: threading.Thread(target=server.shutdown, daemon=True).start())
    signal.signal(signal.SIGINT, lambda *_: threading.Thread(target=server.shutdown, daemon=True).start())
    try: server.serve_forever(poll_interval=.25)
    finally: server.server_close(); fcntl.flock(lock_file, fcntl.LOCK_UN); lock_file.close()


if __name__ == "__main__":
    try: main()
    except SystemExit: raise
    except Exception: raise SystemExit("STARTUP_VALIDATION_FAILED") from None
