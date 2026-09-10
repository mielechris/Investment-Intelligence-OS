"""Future isolated full-session service; source tests do not install or run it.

The parent exclusively writes captures/lifecycle. The scheduler child attests
to the persisted schedule; the publisher writes only its isolated projection.
Backend requests never capture, publish, schedule, renew or repair anything.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import signal
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

from truth_spine_adapters import file_bytes
from truth_spine_contract import canonical, digest, seal, utc, verified
from truth_spine_generations import GenerationStore, owner_path
from truth_spine_integration import atomic
from truth_spine_integration_service import Lease, deny_external_io
from truth_spine_session import Lifecycle, parse_session, validate_session_authority
from truth_spine_session_package import PROTECTED_PORTS, captured_cycle, publish_payload, verify_artifacts
from truth_spine_session_supervisor import browser_contract, health

_READERS = {}


def load_config(path, *, now=None, permit_expired=False):
    root = path.parent
    owner_path(root, root, directory=True); owner_path(path, root)
    config = verified(json.loads(file_bytes(path)))
    if (set(config) != {"schema", "root", "host", "port", "manifest_hash", "session_hash",
                       "authority_hash", "registry_hash", "selector_hash", "owners", "content_hash"}
            or config["schema"] != "iios-full-day-shadow-topology-v1"
            or config["root"] != str(root) or config["host"] != "127.0.0.1"
            or type(config["port"]) is not int or not 1024 < config["port"] < 65536
            or config["port"] in PROTECTED_PORTS or set(config["owners"]) != {"scheduler", "publisher"}):
        raise ValueError("FULL_DAY_CONFIG_INVALID")
    def read(name, expected):
        p = root/name; owner_path(p, root)
        value = verified(json.loads(file_bytes(p)))
        if value["content_hash"] != expected:
            raise ValueError("FULL_DAY_CONFIG_PIN_MISMATCH")
        return value
    session = parse_session(read("session.json", config["session_hash"]))
    selector = read("session-selector.json", config["selector_hash"])
    if selector != seal({"schema": "iios-shadow-session-selector-v1", "session": session.identity,
                         "session_file": "session.json", "registry_hash": config["registry_hash"]}):
        raise ValueError("SESSION_SELECTOR_INVALID")
    manifest = read("release-manifest.json", config["manifest_hash"])
    verify_artifacts(root, manifest, config["manifest_hash"])
    if (manifest["session"] != session.identity or manifest["authority_hash"] != config["authority_hash"]
            or manifest["source_registry_hash"] != config["registry_hash"]):
        raise ValueError("FULL_DAY_MANIFEST_BINDING_INVALID")
    authority = read("authority.json", config["authority_hash"])
    validate_session_authority(authority, session, manifest["release"], config["owners"], config["authority_hash"],
                               utc(authority["issued_at"]) if permit_expired else now or datetime.now(timezone.utc))
    registry = read("sources.json", config["registry_hash"])
    # Optional permanent cycle inputs remain retained evidence, never the
    # independent shadow receipt or its freshness authority.
    return config, session, manifest, authority, registry


def read_state(root, session, registry):
    key = (root, session.identity, registry["content_hash"])
    if key not in _READERS:
        _READERS.clear()  # One configured isolated root per process; no unbounded cache.
        _READERS[key] = GenerationStore(root, session.identity, registry, registry["content_hash"], readonly=True)
    store = _READERS[key]
    store.validate()
    states = [r["value"] for r in store.entries() if r["kind"] == "LIFECYCLE"]
    if not states:
        raise ValueError("LIFECYCLE_MISSING")
    lifecycle = Lifecycle(session, states[-1]).state
    return store, lifecycle


def publish_once(root, session, manifest, registry, at):
    store, lifecycle = read_state(root, session, registry)
    generation = store.selected()
    if generation is None:
        raise ValueError("CAPTURE_UNAVAILABLE")
    cycle = captured_cycle(root, generation, store=store, session=session, now=at)
    if (lifecycle["capture_status"] != "CURRENT" or lifecycle["phase"] != session.phase_at(at)
            or cycle["phase"] != lifecycle["phase"]):
        raise ValueError("SOURCE_CYCLE_LIFECYCLE_MISMATCH")
    from truth_spine_factory_coverage import factory_coverage
    factory = factory_coverage(generation, store.selected_events(), cycle, lifecycle["phase"])
    if store.selected() != generation:
        raise ValueError("SOURCE_CYCLE_LIFECYCLE_MISMATCH")
    projection = publish_payload(session=session.identity, release=manifest["release"], lifecycle=lifecycle,
                                 generation=generation, watermark=store.watermark(), at=at,
                                 source_cycle=cycle["source_cycle_id"], factory=factory)
    owner_path(root/"projections", root, directory=True)
    atomic(root/"projections/current.json", projection)
    return projection


def service_response(path, request, *, now=None):
    """Pure GET handler boundary also used by offline HTTP contract tests."""
    now = now or datetime.now(timezone.utc)
    if request == "/health/live":
        return 200, {"status": "LIVE", "pid": os.getpid(), "readiness_claimed": False}
    if request not in {"/health/ready", "/health/market-readiness", "/health/research-readiness", "/truth-spine/full-session"}:
        return 404, {"status": "NOT_FOUND"}
    try:
        c, session, manifest, authority, registry = load_config(path, now=now, permit_expired=request == "/truth-spine/full-session")
        store, lifecycle = read_state(path.parent, session, registry)
        factory = None
        try:
            owner_path(path.parent/"runtime-probes.json", path.parent)
            report = verified(json.loads(file_bytes(path.parent/"runtime-probes.json")))
            probes = report["probes"]
            cycle = captured_cycle(path.parent, store.selected(), store=store, session=session, now=now)
            if (probes["source_cycle"]["evidence_hash"] != cycle["source_cycle_id"]
                    or cycle["phase"] != lifecycle["phase"] or cycle["phase"] != session.phase_at(now)
                    or cycle["admitted_watermark"] != store.watermark()):
                raise ValueError("SOURCE_CYCLE_PROBE_MISMATCH")
            from truth_spine_factory_coverage import factory_coverage
            generation = store.selected()
            expected_factory = factory_coverage(generation, store.selected_events(), cycle, lifecycle["phase"])
            owner_path(path.parent/"projections/current.json", path.parent)
            projection = verified(json.loads(file_bytes(path.parent/"projections/current.json")))
            expected_projection = publish_payload(session=session.identity, release=manifest["release"], lifecycle=lifecycle,
                generation=generation, watermark=store.watermark(), at=utc(projection["published_at"]),
                source_cycle=cycle["source_cycle_id"], factory=expected_factory)
            if (projection != expected_projection or not 0 <= (now-utc(projection["published_at"])).total_seconds() <= 30
                    or store.selected() != generation):
                raise ValueError("FACTORY_PROJECTION_UNAVAILABLE")
            factory = projection["factory"]
        except (OSError, ValueError, KeyError, TypeError):
            probes = {}
        kind = request.removeprefix("/health/") if request.startswith("/health/") else "ready"
        if kind not in {"ready", "research-readiness", "market-readiness"}:
            return 404, {"status": "NOT_FOUND"}
        code, body = health(kind, lifecycle=lifecycle, session=session, authority=authority,
                            authority_hash=c["authority_hash"], release=manifest["release"], owners=c["owners"],
                            generation=store.selected(), watermark=store.watermark(), probes=probes, now=now)
        if request == "/truth-spine/full-session":
            # The failed/stale state is still visible, never dressed as ready.
            view = browser_contract(lifecycle, store.selected(), store.watermark(), code,
                                    {k: p["evidence_hash"] for k,p in probes.items() if k.endswith("_owner")})
            view["published_at"] = now.isoformat()
            try:
                cycle = captured_cycle(path.parent, store.selected(), store=store, session=session,
                                       now=now, require_fresh=False) if store.selected() else None
            except (OSError, ValueError, KeyError, TypeError):
                cycle = None
                view["readiness"] = 503
            view["source_cycle"] = cycle["source_cycle_id"] if cycle else None
            view["source_cycle_generated_at"] = cycle["published_at"] if cycle else None
            view["factory"] = factory
            if factory is None:
                view["readiness"] = 503
            view["sources"] = [{"store": f["store"], "records": f["records"], "capture_end": f["capture_end"],
                                "classifications": f["classifications"],
                                **{k: max(v) if v else None for k,v in f["clocks"].items()}}
                               for f in store.selected()["files"]] if store.selected() else []
            return 200, view
        return code, body
    except (OSError, ValueError, KeyError, TypeError, PermissionError):
        return 503, {"status": "UNAVAILABLE", "scope": "DENY_ONLY_SHADOW", "live_research_ready": False}


def serve(path, port):
    c, *_ = load_config(path)
    if port != c["port"]:
        raise ValueError("PORT_BINDING_INVALID")
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_): pass
        def respond(self, code, body, media="application/json"):
            raw = canonical(body) if media == "application/json" else body
            self.send_response(code); self.send_header("Content-Type", media)
            self.send_header("Content-Length", str(len(raw))); self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff"); self.end_headers()
            if self.command != "HEAD": self.wfile.write(raw)
        def do_GET(self):
            requested = urlsplit(self.path).path
            if requested.startswith("/review/"):
                try:
                    _, _, manifest, _, _ = load_config(path)
                    rel = "release/frontend/" + requested.removeprefix("/review/")
                    row = next(r for r in manifest["files"] if r["path"] == rel)
                    media = {".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".svg": "image/svg+xml"}[Path(rel).suffix]
                    return self.respond(200, file_bytes(path.parent/rel, row["sha256"]), media)
                except (OSError, ValueError, KeyError, StopIteration):
                    return self.respond(404, {"status": "NOT_FOUND"})
            code, value = service_response(path, self.path)
            self.respond(code, value)
        do_HEAD = do_GET
        def denied(self): self.respond(405, {"status": "READ_ONLY"})
        do_POST = do_PUT = do_PATCH = do_DELETE = denied
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    try: server.serve_forever()
    finally: server.server_close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--role", choices=("backend", "scheduler", "publisher"), required=True)
    parser.add_argument("--port", type=int)
    for key in ("instance-id", "runner-id", "created-at"):
        parser.add_argument("--"+key, required=True)
    args = parser.parse_args()
    c, session, manifest, _, registry = load_config(args.config)
    root = args.config.parent
    if Path(__file__).resolve().parent != root/"release/backend" or Path(sys.executable) != root/"runtime/bin/python":
        raise ValueError("MIXED_CHECKOUT_RUNTIME")
    from truth_spine_process_identity import write_startup
    receipt = write_startup(root, args.instance_id, args.runner_id, args.role, args.port, args.created_at)
    deny_external_io()
    lease = Lease(root, args.role)
    try:
        if args.role == "backend":
            serve(args.config, args.port)
            return
        stopped = False
        def stop(*_):
            nonlocal stopped
            stopped = True
        signal.signal(signal.SIGTERM, stop); signal.signal(signal.SIGINT, stop)
        while not stopped:
            at = datetime.now(timezone.utc)
            load_config(args.config, now=at)
            store, lifecycle = read_state(root, session, registry)
            generation = store.selected()
            if args.role == "publisher" and generation:
                try:
                    publish_once(root, session, manifest, registry, at)
                except ValueError as exc:
                    # Selection/admission precedes the independent receipt. A
                    # bounded publication lag must stay 503, not kill/restart a
                    # healthy publisher or issue replacement upstream evidence.
                    if str(exc) not in {"SOURCE_CYCLE_CAPTURE_REQUIRED", "CAPTURE_CHANGED_DURING_READ",
                                        "SOURCE_CYCLE_CAPTURE_MISMATCH", "SOURCE_CYCLE_LIFECYCLE_MISMATCH",
                                        "SOURCE_CYCLE_STALE", "SESSION_PROJECTION_BINDING_INVALID"}:
                        raise
            atomic(root/(args.role+"-session-heartbeat.json"), seal({"session": session.identity,
                   "release": manifest["release"], "generation": generation["content_hash"] if generation else None,
                   "startup_receipt_hash": receipt["content_hash"], "at": at.isoformat(),
                   "next_wake": lifecycle["next_capture"], "role": args.role}))
            for _ in range(25):
                if stopped: break
                time.sleep(.2)
    finally:
        lease.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # Owner-only process logs receive no traceback, path or source payload.
        print(json.dumps({"status": "FAILED_CLOSED", "category": type(exc).__name__}))
        sys.exit(4)
