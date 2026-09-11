"""Uninstalled full-day package contract and independently reading probe adapter.

No builder or installer is run on import. Runtime wiring must provide fixed,
reviewed paths and independent manifest/authority pins; no auto-discovery of a
permanent root, port, source ledger, credentials or provider is permitted.
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import timedelta
import json
from pathlib import Path
import re
import hashlib
import os
import stat

from truth_spine_adapters import file_bytes
from truth_spine_contract import digest, seal, utc, verified
from truth_spine_generations import owner_path
from truth_spine_factory_coverage import factory_coverage
from truth_spine_session_supervisor import REQUIRED_PROBES

DIRECTORIES = ("release", "runtime", "captures", "projections", "logs", "receipts", "rollback")
FILES = ("topology.json", "session.json", "session-selector.json", "authority.json", "sources.json",
         "release-manifest.json", "session-journal.db", "runner.lock", "backend.lock", "scheduler.lock", "publisher.lock",
         "shutdown-receipt.json", "runtime-probes.json", "scheduler-session-heartbeat.json", "publisher-session-heartbeat.json",
         "acceptance.json", "runner-incidents.json", "emergency-incident.json", "startup-<bound-instance-id>.json")
PROTECTED_PORTS = frozenset({5176, 5177, 5184, 5185, 5186, 5290, 8002})
BACKEND_FILES = tuple(name+".py" for name in (
    "truth_spine_adapters", "truth_spine_authority", "truth_spine_contract", "truth_spine_process_identity",
    "truth_spine_integration", "truth_spine_integration_service", "truth_spine_session", "truth_spine_generations",
    "truth_spine_session_supervisor", "truth_spine_session_package", "truth_spine_full_day_service",
    "truth_spine_integration_runner", "truth_spine_full_day_runner", "truth_spine_factory_coverage", "truth_spine_frontend_graph",
    "truth_spine_sqlite_capture"))


def installation_template():
    return {"schema": "iios-full-day-shadow-template-v1", "installed": False,
            "host": "127.0.0.1", "proposed_port": 5291,
            "root": "OWNER_MUST_AUTHORIZE_NEW_ABSOLUTE_ROOT",
            "session": "OWNER_MUST_AUTHORIZE_EXCHANGE_DATE_AND_CALENDAR_HASH",
            "manifest_pin": "REQUIRED_BEFORE_CREATION", "authority_pin": "INDEPENDENT_OWNER_PIN_REQUIRED",
            "directories": list(DIRECTORIES), "files": list(FILES),
            "dir_mode": "0700", "file_mode": "0600", "immutable_release_file_mode": "0400",
            "launch_agents": False, "review_url": "http://127.0.0.1:5291/review/northstar-session.html?fullSession=1",
            "source_cycle_schema": "iios-shadow-capture-source-cycle-v1",
            "source_cycle_store": "session-journal.db:source_cycles",
            "source_cycle_producer": "capture_scheduler", "source_cycle_max_age_seconds": 900,
            "maximum_authority_seconds": 86400, "restart_per_role": 1, "restart_total": 3,
            "restart_cooldown_seconds": 60, "loop_seconds": 5, "cleanup_seconds": 300,
            "installation_authorized_by_template": False}


def capacity_budget(session, registry):
    """Conservative reservation: 110 captures, 2x source growth, 64 MiB journal.

    A normal session needs fewer than 60 scheduled captures. The extra reserve
    covers phase boundaries and bounded restarts; it never authorizes retries.
    This is a preflight estimate, not a guarantee against concurrent disk use.
    """
    from truth_spine_session import parse_session
    parse_session(session.record()); verified(registry)
    source_bytes = sum(Path(s["path"]).stat().st_size for s in registry["sources"])
    return {"maximum_capture_reservation": 110, "source_bytes": source_bytes,
            "required_free_bytes": source_bytes * 220 + 64 * 1024 * 1024}


def deployment_documents(root, session, manifest, registry, authority, owners):
    """Pure candidate documents; creates no directory, selector or permission.

    A subsequent owner approval must independently pin the complete topology
    bytes. A template or a self-computed hash is not execution authorization.
    """
    from truth_spine_session import parse_session, validate_session_authority
    from truth_spine_generations import registry_record
    parse_session(session.record()); verified(manifest); verified(registry)
    from truth_spine_session import HistoricalSession
    historical = isinstance(session, HistoricalSession)
    valid_root = root.name == 'iios-northstar-installed-shadow-sb37' if historical else root.name.startswith('iios-truth-spine-full-day-')
    if (root.parent != Path("/private/tmp") or not valid_root
            or root != root.resolve() or registry != registry_record(registry["sources"])
            or manifest["session"] != session.identity or manifest["source_registry_hash"] != digest(registry)
            or manifest["authority_hash"] != digest(authority)):
        raise ValueError("DEPLOYMENT_BINDING_INVALID")
    validate_session_authority(authority, session, manifest["release"], owners, digest(authority), session.start)
    selector = seal({"schema": "iios-shadow-session-selector-v1", "session": session.identity,
                     "session_file": "session.json", "registry_hash": digest(registry)})
    topology = seal({"schema": "iios-full-day-shadow-topology-v1", "root": str(root), "host": "127.0.0.1", "port": 5291,
                    "manifest_hash": digest(manifest), "session_hash": digest(session.record()),
                    "authority_hash": digest(authority), "registry_hash": digest(registry),
                    "selector_hash": digest(selector), "owners": owners})
    return {"session.json": session.record(), "session-selector.json": selector, "topology.json": topology,
            "sources.json": registry, "authority.json": authority, "release-manifest.json": manifest}


def verify_artifacts(root, manifest, expected_hash):
    """Complete immutable inventories, not a fresh manifest wrapper alone."""
    owner_path(root, root, directory=True)
    verified(manifest)
    required = {"schema", "release", "source_commit", "runtime_identity", "frontend_provenance",
                "session", "authority_hash", "source_registry_hash", "files", "content_hash"}
    if (set(manifest) != required or manifest["schema"] != "iios-full-day-shadow-package-v1"
            or manifest["content_hash"] != expected_hash
            or not re.fullmatch("[0-9a-f]{40}", manifest["source_commit"])
            or not manifest["runtime_identity"] or not manifest["frontend_provenance"]):
        raise ValueError("SESSION_PACKAGE_PIN_INVALID")
    paths = set()
    for row in manifest["files"]:
        p = Path(row["path"])
        if (set(row) != {"path", "bytes", "sha256", "mode"} or p.is_absolute() or ".." in p.parts
                or not p.parts or p.parts[0] not in {"release", "runtime"}
                or p.as_posix() in paths or row["mode"] not in {"0400", "0500", "0600", "0700"}
                or any(x in {"__pycache__", "node_modules", ".git"} for x in p.parts)
                or p.suffix in {".pyc", ".map"}):
            raise ValueError("SESSION_PACKAGE_INVENTORY_INVALID")
        data = file_bytes(root/p, row["sha256"])
        if len(data) != row["bytes"] or (root/p).stat().st_mode & 0o777 != int(row["mode"], 8):
            raise ValueError("SESSION_PACKAGE_ARTIFACT_INVALID")
        paths.add(p.as_posix())
    actual = set()
    for directory in ("release", "runtime"):
        owner_path(root/directory, root, directory=True)
        for p in (root/directory).rglob("*"):
            if p.is_symlink() or not (p.is_dir() or p.is_file()):
                raise ValueError("SESSION_PACKAGE_SPECIAL_FILE")
            if p.is_dir() and (p.stat().st_uid != os.getuid() or p.stat().st_mode & 0o777 not in {0o500, 0o700}):
                raise ValueError("SESSION_PACKAGE_DIRECTORY_MODE_INVALID")
            if p.is_file(): actual.add(p.relative_to(root).as_posix())
    if paths != actual or not paths:
        raise ValueError("SESSION_PACKAGE_INVENTORY_MISMATCH")
    if {p for p in paths if p.startswith("release/backend/")} != {"release/backend/"+p for p in BACKEND_FILES}:
        raise ValueError("SESSION_BACKEND_GRAPH_INVALID")
    from truth_spine_integration import validate_frontend_provenance
    p = manifest["frontend_provenance"]
    package_files = [{"path": r["path"].removeprefix("release/"), "bytes": r["bytes"], "sha256": r["sha256"]}
                     for r in manifest["files"] if r["path"].startswith("release/")]
    validate_frontend_provenance({"source_state": "CLEAN_COMMITTED_SOURCE", "source_base": manifest["source_commit"],
        "frontend_provenance": p, "frontend_input_hash": p["input_hash"], "frontend_content_hash": p["output_hash"],
        "files": package_files, "source_inventory_hash": digest({"files": [r for r in package_files if r["path"].startswith("backend/")]})})
    frontend = {r["path"].removeprefix("frontend/") for r in package_files if r["path"].startswith("frontend/")}
    if p['inputs']['policy'].get('entry') == 'northstar-session.html':
        from truth_spine_frontend_graph import validate_northstar_graph
        validate_northstar_graph({name: file_bytes(root/'release/frontend'/name) for name in frontend})
    else:
        verify_engineering_graph(root, frontend)
    verify_runtime_graph(root, manifest)
    return manifest


def verify_engineering_graph(root, frontend):
    js = {name for name in frontend if re.fullmatch(r"assets/truth-integration-[A-Za-z0-9_-]+\.js", name)}
    css = {name for name in frontend if re.fullmatch(r"assets/truth-integration-[A-Za-z0-9_-]+\.css", name)}
    if (len(js) != 1 or len(css) != 1 or frontend != js | css |
            {"truth-integration.html", "favicon.svg", "icons.svg", "fixtures/expansion-wing.json"}):
        raise ValueError("SESSION_FRONTEND_GRAPH_INVALID")
    html = file_bytes(root/"release/frontend/truth-integration.html").decode()
    if set(re.findall(r'''(?:src|href)=["']([^"']+)["']''', html)) != {"/review/"+name for name in js | css}:
        raise ValueError("SESSION_FRONTEND_GRAPH_INVALID")
    for name in js | css | {"truth-integration.html"}:
        if re.search(r"/Users/|/home/|/private/tmp/|sourceMappingURL|sourceURL", file_bytes(root/"release/frontend"/name).decode()):
            raise ValueError("SESSION_FRONTEND_LEAKAGE")


def verify_runtime_graph(root, manifest):
    runtime = verified(json.loads(file_bytes(root/"runtime/runtime-manifest.json")))
    if runtime["runtime_id"] != manifest["runtime_identity"]:
        raise ValueError("SESSION_RUNTIME_IDENTITY_INVALID")
    runtime_rows = {r["path"]: r for r in manifest["files"] if r["path"].startswith("runtime/")
                    and r["path"] != "runtime/runtime-manifest.json"}
    if len(runtime["file_inventory"]) != len(runtime_rows):
        raise ValueError("SESSION_RUNTIME_INVENTORY_INVALID")
    for row in runtime["file_inventory"]:
        installed = runtime_rows.get("runtime/"+row["path"])
        if (installed is None or installed["bytes"] != row["size"] or installed["sha256"] != row["sha256"]
                or int(installed["mode"], 8) != row["mode"]):
            raise ValueError("SESSION_RUNTIME_INVENTORY_INVALID")
    executable = runtime_rows.get("runtime/bin/python")
    if executable is None or executable["sha256"] != runtime["interpreter_sha256"]:
        raise ValueError("SESSION_RUNTIME_EXECUTABLE_INVALID")
    for dependency in runtime["platform_dependencies"]:
        path = Path(dependency["path"])
        info = path.lstat()
        if (not path.is_absolute() or any(p.is_symlink() for p in (path, *path.parents))
                or not stat.S_ISREG(info.st_mode) or info.st_uid not in {0, os.getuid()}
                or info.st_mode & 0o022 or hashlib.sha256(path.read_bytes()).hexdigest() != dependency["sha256"]):
            raise ValueError("SESSION_PLATFORM_DEPENDENCY_INVALID")
    return manifest


def publish_payload(*, session, release, lifecycle, generation, watermark, at, source_cycle, factory):
    """The publisher derives these fields; a harness cannot supply probe booleans."""
    verified(lifecycle); verified(generation); utc(at.isoformat())
    verified(factory)
    if (lifecycle["session"] != session or generation["session"] != session
            or lifecycle["last_capture"] != generation["content_hash"]
            or not isinstance(source_cycle, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,180}", source_cycle)
            or factory["source_cycle_id"] != source_cycle or factory["session"] != session
            or factory["generation_id"] != generation["content_hash"] or factory["phase"] != lifecycle["phase"]):
        raise ValueError("SESSION_PROJECTION_BINDING_INVALID")
    return seal({"schema": "iios-full-day-shadow-projection-v1", "session": session, "release": release,
                 "generation": generation["content_hash"], "factory": factory,
                 "phase": lifecycle["phase"], "watermark": watermark, "source_cycle": source_cycle,
                 "published_at": at.isoformat(), "capture_end": generation["end"],
                 "capture_status": lifecycle["capture_status"],
                 "sources": [{"store": f["store"], "capture_start": f["capture_start"],
                              "capture_end": f["capture_end"], "clocks": f["clocks"],
                              "classifications": f["classifications"], "records": f["records"],
                              "nested_evidence": "SOURCE_RECORD_TIMES_NOT_CAPTURE_TIMES"} for f in generation["files"]],
                 "authority": lifecycle["capabilities"], "market_data_provider": False,
                 "scope": "SHADOW_OBSERVATION_READY_NOT_PROVIDER_BACKED_RESEARCH"})


class RuntimeProbeReader:
    """Reads real package, child fingerprints, heartbeat and publisher artifacts.

    The caller cannot pass an evidence dictionary or readiness booleans. For
    tests, OS children and file fixtures are isolated boundary substitutions.
    """
    def __init__(self, *, root, manifest, manifest_pin, children, session, store):
        self.root, self.manifest, self.manifest_pin = root, manifest, manifest_pin
        self.children, self.session, self.store = children, session, store

    def collect(self, now, generation, watermark):
        manifest = verify_artifacts(self.root, self.manifest, self.manifest_pin)
        if manifest["session"] != self.session.identity:
            raise ValueError("RUNTIME_SESSION_MISMATCH")
        self.store.validate()
        states = [r["value"] for r in self.store.entries() if r["kind"] == "LIFECYCLE"]
        evidence = {"release": manifest["content_hash"], "runtime": digest({"runtime": manifest["runtime_identity"]}),
                    "frontend": digest({"provenance": manifest["frontend_provenance"]})}
        for role in ("backend", "scheduler", "publisher"):
            entry = self.children.active[role]
            fingerprint = self.children.verify(entry)
            evidence[role+"_owner"] = digest(asdict(fingerprint))
            if role == "backend": continue
            path = self.root/(role+"-session-heartbeat.json")
            owner_path(path, self.root)
            h = verified(json.loads(file_bytes(path)))
            if (h.get("session") != self.session.identity or h.get("release") != manifest["release"]
                    or h.get("role") != role
                    or h.get("next_wake") != states[-1]["next_capture"]
                    or h.get("generation") != generation["content_hash"]
                    or h.get("startup_receipt_hash") != fingerprint.startup_receipt_hash
                    or not 0 <= (now-utc(h["at"])).total_seconds() <= 30):
                raise ValueError("SESSION_HEARTBEAT_INVALID")
            evidence[role+"_heartbeat"] = h["content_hash"]
        path = self.root/"projections/current.json"
        owner_path(path, self.root)
        p = verified(json.loads(file_bytes(path)))
        if not 0 <= (now-utc(p["published_at"])).total_seconds() <= 30:
            raise ValueError("SESSION_PROJECTION_STALE")
        cycle = captured_cycle(self.root, generation, store=self.store, session=self.session, now=now)
        factory = factory_coverage(generation, self.store.selected_events(), cycle, states[-1]["phase"])
        expected = publish_payload(session=self.session.identity, release=manifest["release"], lifecycle=states[-1],
                                   generation=generation, watermark=watermark, at=utc(p["published_at"]),
                                   source_cycle=p["source_cycle"], factory=factory)
        if p != expected:
            raise ValueError("SESSION_PROJECTION_NOT_DERIVED")
        # The cycle source must be captured and hash-bound independently; using
        # the projection's own cycle value as its proof is prohibited.
        cycle = captured_cycle(self.root, generation, store=self.store, session=self.session, now=now)
        if (cycle["source_cycle_id"] != p["source_cycle"] or cycle["admitted_watermark"] != watermark
                or cycle["phase"] != states[-1]["phase"] or cycle["phase"] != self.session.phase_at(now)):
            raise ValueError("SOURCE_CYCLE_UNAUTHENTICATED")
        evidence.update(projection=p["content_hash"], source_cycle=cycle["source_cycle_id"])
        if set(evidence) != REQUIRED_PROBES:
            raise ValueError("PROBE_INVENTORY_INVALID")
        return {key: seal({"schema": "iios-shadow-runtime-probe-v1", "kind": key,
                           "session": self.session.identity, "release": manifest["release"],
                           "generation": generation["content_hash"], "watermark": watermark,
                           "observed_at": now.isoformat(), "expires_at": (now+timedelta(seconds=15)).isoformat(),
                           "evidence_hash": value}) for key,value in evidence.items()}


def captured_cycle(root, generation, *, store, session, now, require_fresh=True):
    """Consume a capture-owner receipt, NEVER the retained permanent manifest.

    Topology/authority/owner bindings are independently package-pinned. This
    function has no write or issuance path; publisher stores are readonly.
    """
    owner_path(root/"topology.json", root)
    topology = verified(json.loads(file_bytes(root/"topology.json")))
    if (topology["session_hash"] != digest(session.record())
            or topology["registry_hash"] != store.registry["content_hash"]):
        raise ValueError("SOURCE_CYCLE_TOPOLOGY_INVALID")
    value = store.source_cycle(session, topology_hash=topology["content_hash"],
        authority_hash=topology["authority_hash"], owners=topology["owners"], now=now, require_fresh=require_fresh)
    if value["generation"] != generation["content_hash"]:
        raise ValueError("SOURCE_CYCLE_CAPTURE_MISMATCH")
    return value
