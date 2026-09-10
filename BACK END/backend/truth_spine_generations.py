"""Append-only, shadow-local capture generations and canonical identities.

Live inputs are opened read-only. SQLite's backup API provides one consistent
snapshot per database, NOT a cross-database transaction. Abandoned captures are
retained and never selected. Selection and event admission share one transaction.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import stat
import time
import uuid
import copy
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from truth_spine_adapters import file_bytes, read_document, read_ledger, source, universe_version
from truth_spine_contract import canonical, digest, seal, utc, verified

KINDS = {"operational", "historical", "research", "event_reconstruction", "macro_regime",
         "validation_9h", "shadow_9i", "outcomes_9j", "universe", "source_cycle",
         "patterns", "professional_judgment", "price_archive"}
SOURCE_CYCLE_MAX_AGE_SECONDS = 900


def cycle_identity(value):
    """SHA-256 of canonical ASCII JSON + LF, excluding ONLY source_cycle_id."""
    return hashlib.sha256(canonical({k: v for k, v in value.items() if k != "source_cycle_id"})).hexdigest()


def source_cycle_record(generation, watermark, *, sequence, parent, phase, topology_hash,
                        authority_hash, owners, published_at):
    if (set(owners) != {"scheduler", "publisher"} or owners["scheduler"] == owners["publisher"]
            or not all(isinstance(v, str) and re.fullmatch(r"[A-Za-z0-9_.:-]{1,180}", v) for v in owners.values())
            or not all(re.fullmatch("[0-9a-f]{64}", v) for v in (topology_hash, authority_hash))):
        raise ValueError("SOURCE_CYCLE_OWNER_BINDING_INVALID")
    value = {"schema": "iios-shadow-capture-source-cycle-v1", "contract_version": 1,
             "sequence": sequence, "previous_source_cycle": parent,
             "session": generation["session"], "phase": phase,
             "generation": generation["content_hash"], "capture_identity": generation["identity"],
             "capture_start": generation["start"], "capture_end": generation["end"],
             "globally_simultaneous": False,
             "simultaneity_disclosure": "INDIVIDUALLY_CONSISTENT_NOT_GLOBALLY_SIMULTANEOUS",
             "stores": generation["files"], "admitted_watermark": watermark,
             "producer_role": "capture_scheduler", "producer_identity": owners["scheduler"],
             "consumer_identity": owners["publisher"], "topology_hash": topology_hash,
             "authority_hash": authority_hash, "published_at": published_at}
    value["ledger_captures"] = {f["kind"]: {"capture_identity": generation["identity"],
        "store": f["store"], "snapshot_sha256": f["sha256"], "source_identity": f["source_path_binding"]}
        for f in generation["files"] if f["kind"] in {"operational", "historical"}}
    if set(value["ledger_captures"]) != {"operational", "historical"}:
        raise ValueError("SOURCE_CYCLE_LEDGERS_REQUIRED")
    return {**value, "source_cycle_id": cycle_identity(value)}


def owner_path(path: Path, root: Path, *, directory=False):
    if (not path.is_absolute() or path != path.resolve() or not path.is_relative_to(root)
            or any(p.is_symlink() for p in (path, *path.parents))):
        raise ValueError("SHADOW_PATH_INVALID")
    info = path.lstat()
    if (info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != (0o700 if directory else 0o600)
            or not (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode))):
        raise ValueError("SHADOW_OWNER_MODE_INVALID")


def fsync_dir(path: Path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def immutable_file(path: Path, value: bytes):
    owner_path(path.parent, path.parent, directory=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as out:
        out.write(value)
        out.flush()
        os.fsync(out.fileno())
    fsync_dir(path.parent)


def registry_record(specs: list[dict]):
    """Fixed independently reviewed paths, never received from a browser request."""
    if (not specs or not {"operational", "historical"}.issubset({s.get("kind") for s in specs})
            or len({s.get("store") for s in specs}) != len(specs)
            or len({s.get("path") for s in specs}) != len(specs)):
        raise ValueError("SOURCE_REGISTRY_INVALID")
    for s in specs:
        if (set(s) != {"store", "kind", "path"} or s["kind"] not in KINDS
                or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,100}", s["store"])):
            raise ValueError("SOURCE_REGISTRY_INVALID")
        path = Path(s["path"])
        if any(part.lower() in {"credentials", "keychains"} for part in path.parts) or path.name.startswith(".env") or "keychain" in path.name.lower():
            raise PermissionError("CREDENTIAL_SOURCE_FORBIDDEN")
        file_bytes(Path(s["path"]))  # No symlinks, wrong ownership, special files.
    if sum(s["kind"] == "operational" for s in specs) != 1 or sum(s["kind"] == "historical" for s in specs) != 1:
        raise ValueError("EXPLICIT_LEDGERS_REQUIRED")
    return seal({"schema": "iios-shadow-source-registry-v1", "sources": specs})


class GenerationStore:
    def __init__(self, root: Path, session: str, registry: dict, approved_registry: str, *, readonly=False):
        owner_path(root, root, directory=True)
        if (verified(registry) != registry_record(registry["sources"])
                or registry["content_hash"] != approved_registry):
            raise ValueError("SOURCE_REGISTRY_PIN_INVALID")
        self.root, self.session, self.registry = root, session, registry
        if any(Path(s["path"]).is_relative_to(root) for s in registry["sources"]):
            raise ValueError("SOURCE_OUTPUT_COLLISION")
        self.path = root / "session-journal.db"
        self.captures = root / "captures"
        self.readonly = readonly
        self._verified_inputs = {}
        self.binding = digest({"session": session, "registry": approved_registry})
        if readonly:
            owner_path(self.captures, root, directory=True)
            owner_path(self.path, root)
            self.validate()
            return
        if not self.captures.exists():
            self.captures.mkdir(mode=0o700)
            fsync_dir(root)
        owner_path(self.captures, root, directory=True)
        if not self.path.exists():
            immutable_file(self.path, b"")
        owner_path(self.path, root)
        db = self.connect()
        try:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS binding (id TEXT PRIMARY KEY);
                CREATE TABLE IF NOT EXISTS captures (seq INTEGER PRIMARY KEY, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS events (id TEXT PRIMARY KEY, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS journal (seq INTEGER PRIMARY KEY, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS source_cycles (seq INTEGER PRIMARY KEY, capture TEXT UNIQUE NOT NULL, payload TEXT NOT NULL);
                CREATE TRIGGER IF NOT EXISTS cycle_no_update BEFORE UPDATE ON source_cycles BEGIN SELECT RAISE(ABORT,'IMMUTABLE'); END;
                CREATE TRIGGER IF NOT EXISTS cycle_no_delete BEFORE DELETE ON source_cycles BEGIN SELECT RAISE(ABORT,'IMMUTABLE'); END;
                CREATE TRIGGER IF NOT EXISTS event_no_update BEFORE UPDATE ON events BEGIN SELECT RAISE(ABORT,'IMMUTABLE'); END;
                CREATE TRIGGER IF NOT EXISTS event_no_delete BEFORE DELETE ON events BEGIN SELECT RAISE(ABORT,'IMMUTABLE'); END;
                CREATE TRIGGER IF NOT EXISTS capture_no_update BEFORE UPDATE ON captures BEGIN SELECT RAISE(ABORT,'IMMUTABLE'); END;
                CREATE TRIGGER IF NOT EXISTS capture_no_delete BEFORE DELETE ON captures BEGIN SELECT RAISE(ABORT,'IMMUTABLE'); END;
                CREATE TRIGGER IF NOT EXISTS journal_no_update BEFORE UPDATE ON journal BEGIN SELECT RAISE(ABORT,'IMMUTABLE'); END;
                CREATE TRIGGER IF NOT EXISTS journal_no_delete BEFORE DELETE ON journal BEGIN SELECT RAISE(ABORT,'IMMUTABLE'); END;
            """)
            self.binding = digest({"session": session, "registry": approved_registry})
            with db:
                rows = db.execute("SELECT id FROM binding").fetchall()
                if rows and rows != [(self.binding,)]:
                    raise ValueError("SHADOW_JOURNAL_BINDING_INVALID")
                db.execute("INSERT OR IGNORE INTO binding VALUES (?)", (self.binding,))
        finally:
            db.close()
        fsync_dir(root)
        self.validate()

    def connect(self, *, readonly=False):
        if self.readonly and not readonly:
            raise PermissionError("SHADOW_READER_WRITE_FORBIDDEN")
        owner_path(self.path, self.root)
        db = sqlite3.connect(self.path.as_uri() + ("?mode=ro" if readonly else "?mode=rw"), uri=True)
        db.execute("PRAGMA query_only=ON" if readonly else "PRAGMA synchronous=FULL")
        return db

    def entries(self):
        with closing(self.connect(readonly=True)) as db:
            return [verified(json.loads(p)) for p, in db.execute("SELECT payload FROM journal ORDER BY seq")]

    def record(self, kind, value, at: datetime):
        utc(at.isoformat())
        if kind not in {"LIFECYCLE", "CHECKPOINT", "INCIDENT", "SHUTDOWN", "REFRESH_FAILED"}:
            raise ValueError("JOURNAL_KIND_INVALID")
        db = self.connect()
        try:
            with db:
                db.execute("BEGIN IMMEDIATE")
                prior = db.execute("SELECT seq,payload FROM journal ORDER BY seq DESC LIMIT 1").fetchone()
                n, parent = (prior[0]+1, verified(json.loads(prior[1]))["content_hash"]) if prior else (1, self.binding)
                row = seal({"schema": "iios-shadow-journal-v1", "sequence": n, "parent": parent,
                            "session": self.session, "kind": kind, "at": at.isoformat(), "value": value})
                db.execute("INSERT INTO journal VALUES (?,?)", (n, canonical(row).decode()))
            return row
        finally:
            db.close()

    def selected(self):
        db = self.connect(readonly=True)
        try:
            row = db.execute("SELECT payload FROM captures ORDER BY seq DESC LIMIT 1").fetchone()
            return verified(json.loads(row[0])) if row else None
        finally:
            db.close()

    def watermark(self):
        db = self.connect(readonly=True)
        try:
            rows = db.execute("SELECT id,payload FROM events ORDER BY id").fetchall()
            return {"count": len(rows), "identity": digest({"rows": [[i, verified(json.loads(p))["content_hash"]] for i,p in rows]})}
        finally:
            db.close()

    def selected_events(self):
        """Only the validated selected capture, not cumulative historical totals."""
        self.validate()
        generation = self.selected()
        if generation is None:
            return []
        result = []
        for spec, item in zip(self.registry["sources"], generation["files"], strict=True):
            path = self.captures/generation["identity"]/item["file"]
            file_bytes(path, item["sha256"])
            events, _ = self._adapt(spec, path)
            file_bytes(path, item["sha256"])
            result.extend(events)
        if self.selected() != generation:
            raise ValueError("CAPTURE_SELECTION_CHANGED")
        return sorted(result, key=lambda e: e["id"])

    def _adapt(self, spec, dest):
        if spec["kind"] == "source_cycle":
            value = json.loads(file_bytes(dest))
            if (value.get("schema_version") != "iios-multi-asset-projection-manifest-v1"
                    or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,180}", value.get("source_cycle_id", ""))):
                raise ValueError("SOURCE_CYCLE_SCHEMA_INVALID")
            utc(value["generated_at"])
            if "content_hash" in value:
                verified(value)
            return [], None
        bound = source(dest, spec["kind"])
        if spec["kind"] == "universe":
            universe = universe_version(bound)
            return [], universe
        rows = read_ledger(bound) if spec["kind"] in {"operational", "historical"} else read_document(bound)
        events = []
        for row in rows:
            # A stable source object is independent of capture-file byte identity.
            identity = digest({"store": spec["store"], "object": row["source_object_identity"]})
            events.append(seal({"id": identity, "store": spec["store"],
                                "object": row["source_object_identity"],
                                "payload_hash": row["original_content_hash"],
                                "classification": row["classification"], "type": row["record_type"],
                                "coverage": row["coverage"],
                                "observation_time": row["observation_time"], "event_time": row["event_time"],
                                "publication_time": row["publication_time"]}))
        return events, None

    def capture(self, *, clock=lambda: datetime.now(timezone.utc), timeout_seconds=120, permit=None):
        """Actual SQLite backup and fixed retained-file readers; no provider adapter.

        Tests inject a clock directly. There is no environment or production CLI
        clock override. Authority must also be rechecked after this bounded I/O.
        """
        if not 1 <= timeout_seconds <= 120:
            raise ValueError("CAPTURE_TIMEOUT_INVALID")
        if self.readonly:
            raise PermissionError("SHADOW_READER_WRITE_FORBIDDEN")
        if permit is not None:
            permit()
        started = clock(); utc(started.isoformat())
        capture_id = "capture-" + uuid.uuid4().hex
        directory = self.captures/capture_id
        directory.mkdir(mode=0o700); fsync_dir(self.captures)
        monotonic_start = time.monotonic()
        deadline = monotonic_start + timeout_seconds
        manifests, all_events, universes = [], [], []
        for index, spec in enumerate(self.registry["sources"]):
            if permit is not None:
                permit()
            if time.monotonic() >= deadline:
                raise TimeoutError("CAPTURE_DEADLINE")
            src = Path(spec["path"])
            file_bytes(src)
            before = src.stat()
            begin = clock(); utc(begin.isoformat())
            dest = directory/(str(index) + (".db" if spec["kind"] in {"operational", "historical"} else ".json"))
            schema, integrity = None, "JSON_VALID"
            if spec["kind"] in {"operational", "historical"}:
                immutable_file(dest, b"")
                live = sqlite3.connect(src.as_uri()+"?mode=ro", uri=True)
                copy = sqlite3.connect(dest)
                def progress(*_):
                    if permit is not None:
                        permit()
                    if time.monotonic() >= deadline:
                        raise TimeoutError("CAPTURE_DEADLINE")
                try:
                    live.execute("PRAGMA query_only=ON")
                    live.backup(copy, pages=256, progress=progress, sleep=0.05)
                    integrity = copy.execute("PRAGMA quick_check").fetchall()
                    if integrity != [("ok",)]:
                        raise ValueError("SNAPSHOT_INTEGRITY_INVALID")
                    integrity = "SQLITE_QUICK_CHECK_OK"
                    schema = digest({"schema": copy.execute("SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name").fetchall()})
                finally:
                    live.close(); copy.close()
                fd = os.open(dest, os.O_RDONLY | os.O_NOFOLLOW)
                try:
                    os.fsync(fd)
                finally:
                    os.close(fd)
            else:
                immutable_file(dest, file_bytes(src))
            after = src.stat()
            if (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino):
                raise ValueError("SOURCE_REPLACED_DURING_CAPTURE")
            events, universe = self._adapt(spec, dest)
            all_events.extend(events)
            if universe:
                universes.append(universe)
            ended = clock(); utc(ended.isoformat())
            if ended < begin:
                raise ValueError("CAPTURE_CLOCK_REGRESSION")
            manifests.append({"store": spec["store"], "kind": spec["kind"], "file": dest.name,
                              "source_path_binding": digest(spec), "capture_start": begin.isoformat(),
                              "capture_end": ended.isoformat(), "schema": schema,
                              "integrity": integrity, "bytes": dest.stat().st_size,
                              "sha256": hashlib.sha256(file_bytes(dest)).hexdigest(),
                              "watermark": digest({"ids": sorted(e["id"] for e in events)}),
                              "records": len(events),
                              "clocks": {k: sorted({e[k] for e in events if e[k] is not None})
                                         for k in ("observation_time", "event_time", "publication_time")},
                              "classifications": sorted({e["classification"] for e in events})})
        end = clock(); utc(end.isoformat())
        elapsed = time.monotonic() - monotonic_start
        if (end < started or time.monotonic() >= deadline
                or abs((end-started).total_seconds() - elapsed) > 5):
            raise ValueError("CAPTURE_TIME_INVALID")
        prior = self.selected()
        generation = seal({"schema": "iios-shadow-capture-v1", "identity": capture_id,
                           "session": self.session, "registry": self.registry["content_hash"],
                           "parent": prior["content_hash"] if prior else self.binding,
                           "start": started.isoformat(), "end": end.isoformat(),
                           "globally_simultaneous": False, "files": manifests, "universes": universes})
        immutable_file(directory/"manifest.json", canonical(generation))
        if permit is not None:
            permit()
        # All canonical events and the selected generation become visible together.
        db = self.connect()
        try:
            with db:
                db.execute("BEGIN IMMEDIATE")
                last = db.execute("SELECT seq,payload FROM captures ORDER BY seq DESC LIMIT 1").fetchone()
                if (verified(json.loads(last[1]))["content_hash"] if last else self.binding) != generation["parent"]:
                    raise ValueError("CONCURRENT_CAPTURE_REJECTED")
                for event in all_events:
                    existing = db.execute("SELECT payload FROM events WHERE id=?", (event["id"],)).fetchone()
                    if existing and existing[0] != canonical(event).decode():
                        raise ValueError("SOURCE_IDENTITY_MUTATION")
                    db.execute("INSERT OR IGNORE INTO events VALUES (?,?)", (event["id"], canonical(event).decode()))
                db.execute("INSERT INTO captures VALUES (?,?)", (last[0]+1 if last else 1, canonical(generation).decode()))
        finally:
            db.close()
        fsync_dir(self.root)
        return generation

    def issue_source_cycle(self, session, *, topology_hash, authority_hash, owners, now, permit=None):
        """Capture-owner only, AFTER admission commit. Consumers open readonly.

        The FULL-synchronous append-only SQLite row is the immutable receipt.
        A crash after admission leaves a selected capture WITHOUT readiness;
        restart may complete its receipt within 30s, never freshen an old capture.
        """
        if self.readonly:
            raise PermissionError("SOURCE_CYCLE_READER_CANNOT_ISSUE")
        if permit is not None:
            permit()
        self.validate()
        with closing(self.connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            captures = [verified(json.loads(p)) for p, in db.execute("SELECT payload FROM captures ORDER BY seq")]
            if not captures:
                raise ValueError("SOURCE_CYCLE_CAPTURE_REQUIRED")
            cycles = self._cycle_chain(db, captures, session=session, topology_hash=topology_hash,
                                       authority_hash=authority_hash, owners=owners)
            if len(cycles) == len(captures):
                return cycles[-1]  # Never overwrite or retimestamp, even if stale.
            if len(cycles) != len(captures)-1:
                raise ValueError("SOURCE_CYCLE_PARENT_MISSING")
            generation = captures[-1]
            if not 0 <= (now-utc(generation["end"])).total_seconds() <= 30:
                raise ValueError("SOURCE_CYCLE_PUBLICATION_WINDOW_INVALID")
            phase = session.phase_at(utc(generation["end"]))
            if phase != session.phase_at(now):
                raise ValueError("SOURCE_CYCLE_PHASE_MISMATCH")
            value = source_cycle_record(generation, self._capture_watermarks[generation["content_hash"]],
                sequence=len(captures), parent=cycles[-1]["source_cycle_id"] if cycles else self.binding,
                phase=phase, topology_hash=topology_hash, authority_hash=authority_hash,
                owners=owners, published_at=now.isoformat())
            if permit is not None:
                permit()
            db.execute("INSERT INTO source_cycles VALUES (?,?,?)",
                       (len(captures), generation["content_hash"], canonical(value).decode()))
        fsync_dir(self.root)
        return value

    def _cycle_chain(self, db, captures, *, session=None, topology_hash=None, authority_hash=None, owners=None):
        cycles, parent = [], self.binding
        for index, (seq, capture, raw) in enumerate(db.execute("SELECT seq,capture,payload FROM source_cycles ORDER BY seq"), 1):
            value = json.loads(raw)
            if (index > len(captures) or seq != index or value.get("source_cycle_id") != cycle_identity(value)):
                raise ValueError("SOURCE_CYCLE_CHAIN_INVALID")
            generation = captures[index-1]
            if capture not in self._capture_watermarks:
                raise ValueError("CAPTURE_CHANGED_DURING_READ")
            if (capture != generation["content_hash"] or value["session"] != self.session
                    or not 0 <= (utc(value["published_at"])-utc(generation["end"])).total_seconds() <= 30):
                raise ValueError("SOURCE_CYCLE_CAPTURE_MISMATCH")
            expected = source_cycle_record(generation, self._capture_watermarks[capture],
                sequence=index, parent=parent,
                phase=session.phase_at(utc(generation["end"])) if session else value["phase"],
                topology_hash=topology_hash or value["topology_hash"], authority_hash=authority_hash or value["authority_hash"],
                owners=owners or {"scheduler": value["producer_identity"], "publisher": value["consumer_identity"]},
                published_at=value["published_at"])
            if canonical(value) != canonical(expected) or (session and session.identity != self.session):
                raise ValueError("SOURCE_CYCLE_BINDING_INVALID")
            if cycles and utc(value["published_at"]) < utc(cycles[-1]["published_at"]):
                raise ValueError("SOURCE_CYCLE_CLOCK_REGRESSION")
            cycles.append(value); parent = value["source_cycle_id"]
        return cycles

    def source_cycle(self, session, *, topology_hash, authority_hash, owners, now, require_fresh=True):
        self.validate()
        with closing(self.connect(readonly=True)) as db:
            db.execute("BEGIN")
            captures = [verified(json.loads(p)) for p, in db.execute("SELECT payload FROM captures ORDER BY seq")]
            cycles = self._cycle_chain(db, captures, session=session, topology_hash=topology_hash,
                                       authority_hash=authority_hash, owners=owners)
        if not captures or len(cycles) != len(captures):
            raise ValueError("SOURCE_CYCLE_CAPTURE_REQUIRED")
        value = cycles[-1]
        if require_fresh and (not 0 <= (now-utc(value["published_at"])).total_seconds() <= SOURCE_CYCLE_MAX_AGE_SECONDS
                              or not 0 <= (now-utc(value["capture_end"])).total_seconds() <= SOURCE_CYCLE_MAX_AGE_SECONDS):
            raise ValueError("SOURCE_CYCLE_STALE")
        return value

    def validate(self):
        db = self.connect(readonly=True)
        try:
            db.execute("BEGIN")
            if db.execute("PRAGMA quick_check").fetchall() != [("ok",)] or db.execute("SELECT id FROM binding").fetchall() != [(self.binding,)]:
                raise ValueError("JOURNAL_INTEGRITY_INVALID")
            generations = db.execute("SELECT seq,payload FROM captures ORDER BY seq").fetchall()
            expected_events, parent = {}, self.binding
            self._capture_watermarks = {}
            capture_records = []
            for index, (seq, raw) in enumerate(generations, 1):
                row = verified(json.loads(raw))
                if (seq != index or row["parent"] != parent or row["session"] != self.session
                        or row["schema"] != "iios-shadow-capture-v1" or row["globally_simultaneous"] is not False
                        or row["registry"] != self.registry["content_hash"]
                        or not re.fullmatch("capture-[0-9a-f]{32}", row["identity"])):
                    raise ValueError("CAPTURE_CHAIN_INVALID")
                directory = self.captures/row["identity"]
                owner_path(directory, self.root, directory=True)
                owner_path(directory/"manifest.json", self.root)
                if file_bytes(directory/"manifest.json") != canonical(row):
                    raise ValueError("CAPTURE_MANIFEST_MISMATCH")
                if {p.name for p in directory.iterdir()} != {f["file"] for f in row["files"]} | {"manifest.json"}:
                    raise ValueError("CAPTURE_INVENTORY_INVALID")
                if len(row["files"]) != len(self.registry["sources"]):
                    raise ValueError("CAPTURE_SOURCE_COUNT_INVALID")
                universes = []
                start, end = utc(row["start"]), utc(row["end"])
                if not 0 <= (end-start).total_seconds() <= 120:
                    raise ValueError("CAPTURE_INTERVAL_INVALID")
                for spec, f in zip(self.registry["sources"], row["files"], strict=True):
                    if f["store"] != spec["store"] or f["source_path_binding"] != digest(spec) or Path(f["file"]).name != f["file"]:
                        raise ValueError("CAPTURE_SOURCE_BINDING_INVALID")
                    path = directory/f["file"]
                    owner_path(path, self.root)
                    info = path.stat()
                    if info.st_size != f["bytes"] or f["kind"] != spec["kind"]:
                        raise ValueError("CAPTURE_BYTES_OR_KIND_INVALID")
                    token = (f["sha256"], info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
                    cached = self._verified_inputs.get(str(path))
                    if cached is not None and cached[0] == token:
                        events, universe, schema, integrity = copy.deepcopy(cached[1])
                    else:
                        if len(file_bytes(path, f["sha256"])) != f["bytes"]:
                            raise ValueError("CAPTURE_BYTES_INVALID")
                        events, universe = self._adapt(spec, path)
                        schema, integrity = None, "JSON_VALID"
                        if spec["kind"] in {"operational", "historical"}:
                            with closing(sqlite3.connect(path.as_uri()+"?mode=ro", uri=True)) as snapshot:
                                if snapshot.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
                                    raise ValueError("CAPTURE_INTEGRITY_INVALID")
                                schema = digest({"schema": snapshot.execute("SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name").fetchall()})
                                integrity = "SQLITE_QUICK_CHECK_OK"
                        self._verified_inputs[str(path)] = (token, copy.deepcopy((events, universe, schema, integrity)))
                    if (f["schema"] != schema or f["integrity"] != integrity
                            or not start <= utc(f["capture_start"]) <= utc(f["capture_end"]) <= end):
                        raise ValueError("CAPTURE_SCHEMA_OR_INTERVAL_INVALID")
                    if universe:
                        universes.append(universe)
                    clocks = {k: sorted({e[k] for e in events if e[k] is not None})
                              for k in ("observation_time", "event_time", "publication_time")}
                    if (f["records"] != len(events) or f["clocks"] != clocks
                            or f["classifications"] != sorted({e["classification"] for e in events})
                            or f["watermark"] != digest({"ids": sorted(e["id"] for e in events)})):
                        raise ValueError("CAPTURE_METADATA_INVALID")
                    for event in events:
                        if event["id"] in expected_events and expected_events[event["id"]] != event:
                            raise ValueError("SOURCE_IDENTITY_MUTATION")
                        expected_events[event["id"]] = event
                if universes != row["universes"]:
                    raise ValueError("UNIVERSE_CAPTURE_BINDING_INVALID")
                parent = row["content_hash"]
                capture_records.append(row)
                self._capture_watermarks[parent] = {"count": len(expected_events), "identity": digest({
                    "rows": [[i, e["content_hash"]] for i, e in sorted(expected_events.items())]})}
            actual = {i: verified(json.loads(p)) for i,p in db.execute("SELECT id,payload FROM events")}
            if actual != expected_events:
                raise ValueError("CANONICAL_LEDGER_PROVENANCE_INVALID")
            self._cycle_chain(db, capture_records)
            parent = self.binding
            for index, (i, raw) in enumerate(db.execute("SELECT seq,payload FROM journal ORDER BY seq"), 1):
                row = verified(json.loads(raw))
                if index != i or row["sequence"] != i or row["session"] != self.session or row["parent"] != parent:
                    raise ValueError("SESSION_JOURNAL_CHAIN_INVALID")
                parent = row["content_hash"]
        finally:
            db.close()
        return True
