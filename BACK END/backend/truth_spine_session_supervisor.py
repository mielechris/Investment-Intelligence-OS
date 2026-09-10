"""Full-session supervision core; no automatic installation or CLI activation.

An installed runner must supply the existing OwnedChildren and its fixed launch
closure. Tests use isolated fake children, not operational processes. Restarts
are reserved durably before launch and cleanup uses the original OS fingerprint
checks even when session/authority validation has expired.
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import sqlite3
import re

from truth_spine_contract import digest, seal, utc, verified
from truth_spine_session import CADENCE, Lifecycle, Phase, validate_session_authority
from truth_spine_authority import CAPABILITIES

ROLES = ("scheduler", "publisher", "backend")
COUNTERS = ("provider", "model", "credential", "broker", "paper", "live_execution", "operational_ledger_write")
REQUIRED_PROBES = frozenset({"release", "runtime", "frontend", "backend_owner", "scheduler_owner",
                            "publisher_owner", "scheduler_heartbeat", "publisher_heartbeat",
                            "projection", "source_cycle"})


def health(kind, *, lifecycle, session, authority, authority_hash, release, owners,
           generation, watermark, probes, now):
    """Hash-bound probe evidence, not caller-supplied ready=True feature flags.

    Artifact/OS readers must produce independently verified probe documents.
    Every document binds this session, selected capture and canonical watermark.
    Nested times have their own deadlines; a fresh wrapper is insufficient.
    """
    if kind == "live":
        return 200, {"status": "LIVE", "readiness_claimed": False}
    result = {"status": "NOT_READY", "scope": "DENY_ONLY_SHADOW_OBSERVATION",
              "market_data_provider": False, "live_research_ready": False}
    try:
        validate_session_authority(authority, session, release, owners, authority_hash, now)
        verified(lifecycle)
        if set(lifecycle["capabilities"]) != set(CAPABILITIES) or any(v is not False for v in lifecycle["capabilities"].values()):
            raise ValueError("AUTHORITY_VIOLATION")
        if (lifecycle["session"] != session.identity or lifecycle["phase"] in
                (Phase.FAILED_CLOSED, Phase.SHUTDOWN_COMPLETE, Phase.SESSION_COMPLETE)
                or lifecycle["capture_status"] != "CURRENT"
                or now >= utc(lifecycle["next_capture"]) + timedelta(seconds=60)):
            raise ValueError("LIFECYCLE_NOT_CURRENT")
        verified(generation)
        if (generation["session"] != session.identity
                or lifecycle["last_capture"] != generation["content_hash"]
                or generation["globally_simultaneous"] is not False
                or not 0 <= (now-utc(generation["end"])).total_seconds() <= CADENCE[lifecycle["phase"]]+120):
            raise ValueError("INPUT_GENERATION_STALE")
        if set(probes) != REQUIRED_PROBES:
            raise ValueError("READINESS_PROBE_MISSING")
        for name, p in probes.items():
            verified(p)
            if (set(p) != {"schema", "kind", "session", "release", "generation", "watermark",
                           "observed_at", "expires_at", "evidence_hash", "content_hash"}
                    or p["schema"] != "iios-shadow-runtime-probe-v1" or p["kind"] != name
                    or p["session"] != session.identity or p["release"] != release
                    or p["generation"] != generation["content_hash"] or p["watermark"] != watermark
                    or not utc(p["observed_at"]) <= now < utc(p["expires_at"])
                    or not 0 < (utc(p["expires_at"])-utc(p["observed_at"])).total_seconds() <= 60
                    or not re.fullmatch("[0-9a-f]{64}", p["evidence_hash"])):
                raise ValueError("RUNTIME_PROBE_STALE_OR_UNBOUND")
        if kind == "market-readiness":
            return 503, {**result, "reason": "DENY_ONLY_NO_MARKET_AUTHORITY"}
        result["status"] = "SHADOW_OBSERVATION_READY" if kind == "research-readiness" else "READY"
        return 200, result
    except (ValueError, KeyError, TypeError, PermissionError):
        return 503, result


class SessionSupervisor:
    def __init__(self, *, session, store, children, authority, approved_authority_hash,
                 release, owners, topology_hash, start_child, probe_runtime, clock=None):
        self.session, self.store, self.children = session, store, children
        self.authority, self.authority_hash, self.release, self.owners = authority, approved_authority_hash, release, owners
        self.start_child, self.probe_runtime = start_child, probe_runtime
        self.topology_hash = topology_hash
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        entries = store.entries()
        states = [r["value"] for r in entries if r["kind"] == "LIFECYCLE"]
        self.lifecycle = Lifecycle(session, states[-1] if states else None)
        self.last_checkpoint = next((r["at"] for r in reversed(entries) if r["kind"] == "CHECKPOINT"), None)
        self.started = bool(states)
        self.closed = False
        self.projection_hash = None

    def authority_current(self, now):
        try:
            validate_session_authority(self.authority, self.session, self.release, self.owners, self.authority_hash, now)
            return True
        except (ValueError, KeyError, TypeError, PermissionError):
            return False

    def persist(self, now):
        self.store.record("LIFECYCLE", self.lifecycle.state, now)

    def permit_capture(self):
        if not self.authority_current(self.clock()):
            raise PermissionError("AUTHORITY_EXPIRED_DURING_CAPTURE")

    def checkpoint(self, name, now, readiness):
        generation = self.store.selected()
        fingerprints = {}
        for role, entry in self.children.active.items():
            if entry["fingerprint"] is not None:
                fingerprints[role] = digest(asdict(entry["fingerprint"]))
        value = seal({"schema": "iios-shadow-session-checkpoint-v1", "name": name,
                      "session": self.session.identity, "phase": self.lifecycle.state["phase"],
                      "source_generation": generation["content_hash"] if generation else None,
                      "watermark": self.store.watermark(), "projection_generation":
                      generation["content_hash"] if generation and self.projection_hash else None,
                      "projection_hash": self.projection_hash,
                      "owner_fingerprints": fingerprints, "authority_hash": self.authority_hash,
                      "authority_remaining_seconds": max(0, (self.session.shutdown_end-now).total_seconds()),
                      "readiness": readiness, "counters": dict.fromkeys(COUNTERS, 0),
                      "counter_scope": "THIS_DENY_ONLY_OBSERVER_NOT_RETAINED_EXECUTOR_HISTORY",
                      "incidents": list(self.lifecycle.state["incidents"]), "at": now.isoformat()})
        self.store.record("CHECKPOINT", value, now)
        self.last_checkpoint = now.isoformat()
        return value

    def cycle(self):
        now = self.clock(); utc(now.isoformat())
        before = self.lifecycle.state["phase"]
        current = self.authority_current(now)
        try:
            self.lifecycle.tick(now, authority_current=current)
            self.persist(now)
            if self.lifecycle.state["phase"] in (Phase.FAILED_CLOSED, Phase.SESSION_COMPLETE, Phase.SHUTDOWN_COMPLETE):
                return self.finish(now)
            if not self.started:
                self.checkpoint("startup", now, 503)
                for role in ROLES:
                    if role in self.children.active:
                        raise ValueError("DUPLICATE_RUNNER_OWNER")
                    if not self.authority_current(self.clock()):
                        raise PermissionError("AUTHORITY_EXPIRED_DURING_STARTUP")
                    self.start_child(role)
                self.started = True
            # Verify alive children independently; exit alone never grants kill authority.
            for role in ROLES:
                entry = self.children.active.get(role)
                if entry and entry["child"].poll() is None:
                    self.children.verify(entry)
                    continue
                pending = self.lifecycle.state["restart_after"].get(role)
                if not pending:
                    self.lifecycle.reserve_restart(role, now, authority_current=current)
                    self.persist(now)  # budget consumed before any launch, including a crash here
                    if self.lifecycle.state["phase"] == Phase.FAILED_CLOSED:
                        return self.finish(now)
                    if entry and not self.children.stop(role):
                        raise ValueError("DEAD_CHILD_IDENTITY_UNRESOLVED")
                    continue
                if now >= utc(pending):
                    if not self.authority_current(self.clock()):
                        raise PermissionError("AUTHORITY_EXPIRED_BEFORE_RESTART")
                    self.start_child(role)
                    del self.lifecycle.state["restart_after"][role]
                    self.lifecycle._save(); self.persist(now)
            if self.lifecycle.capture_due(now):
                try:
                    # Complete only a recent committed capture after an interrupted
                    # receipt publication. Never skip a parent or refresh old time.
                    if self.store.selected():
                        self.store.issue_source_cycle(self.session, topology_hash=self.topology_hash,
                            authority_hash=self.authority_hash, owners=self.owners, now=self.clock(), permit=self.permit_capture)
                    capture = self.store.capture(clock=self.clock, permit=self.permit_capture)
                    if not self.authority_current(self.clock()):
                        raise PermissionError("AUTHORITY_EXPIRED_DURING_CAPTURE")
                    self.store.issue_source_cycle(self.session, topology_hash=self.topology_hash,
                        authority_hash=self.authority_hash, owners=self.owners, now=self.clock(), permit=self.permit_capture)
                    self.lifecycle.captured(self.clock(), capture["content_hash"])
                except PermissionError:
                    raise
                except (OSError, ValueError, sqlite3.Error) as exc:
                    self.lifecycle.captured(now, None)
                    self.store.record("REFRESH_FAILED", {"category": type(exc).__name__, "stale": True}, now)
                self.persist(now)
            self.store.validate()
            # Read after capture and publisher work, not against a pre-I/O timestamp.
            probe_at = self.clock()
            try:
                probes = self.probe_runtime(probe_at, self.store.selected(), self.store.watermark())
            except (OSError, ValueError, KeyError, TypeError):
                probes = {}  # Missing/stale dependencies remain 503; no fabricated probe.
            status, _ = health("ready", lifecycle=self.lifecycle.state, session=self.session,
                               authority=self.authority, authority_hash=self.authority_hash,
                               release=self.release, owners=self.owners, generation=self.store.selected(),
                               watermark=self.store.watermark(), probes=probes, now=probe_at)
            self.projection_hash = probes["projection"]["evidence_hash"] if status == 200 else None
            if self.lifecycle.state["phase"] == Phase.POST_CLOSE_RECONCILIATION:
                # Publication can legitimately lag the atomic capture selection.
                # Wait within the fixed reconciliation window, never extend it.
                if status == 200 and not self.lifecycle.state["post_close_reconciled"]:
                    self.lifecycle.reconciled(); self.persist(now)
                    self.checkpoint("post-close reconciliation", now, status)
                elif status != 200 and self.lifecycle.state["post_close_reconciled"]:
                    self.lifecycle.state["post_close_reconciled"] = False
                    self.lifecycle._save(); self.persist(now)
            if (before != self.lifecycle.state["phase"] or self.last_checkpoint is None
                    or (now-utc(self.last_checkpoint)).total_seconds() >= 900):
                names = {Phase.PREMARKET_READY: "pre-market ready", Phase.OPENING_OBSERVATION: "market open",
                         Phase.CLOSING_OBSERVATION: "before close", Phase.POST_CLOSE_RECONCILIATION: "market close"}
                self.checkpoint(names.get(self.lifecycle.state["phase"], "regular-session interval"), now, status)
            return {"phase": self.lifecycle.state["phase"], "ready": status}
        except BaseException as exc:
            self.lifecycle.fail("SUPERVISOR_CYCLE_FAILED")
            try:
                self.store.record("INCIDENT", {"category": type(exc).__name__, "sanitized": True}, now)
                self.persist(now)
            finally:
                self.finish(now)
            raise

    def finish(self, now):
        # Expired authority and persistence failure must not skip verified cleanup.
        if self.closed:
            return self.lifecycle.state
        report = {}
        try:
            self.children.cleanup(report)
        finally:
            self.lifecycle.shutdown(unresolved=bool(self.children.active) or bool(report.get("cleanup_errors")),
                                    listener_clear=report.get("port_clear") is True)
            self.closed = True
            self.persist(now)
            self.checkpoint("final shutdown", now, 503)
            self.store.record("SHUTDOWN", {"phase": self.lifecycle.state["phase"],
                                          "result": self.lifecycle.state.get("session_result", "FAILED_CLOSED")}, now)
        return self.lifecycle.state


def browser_contract(lifecycle, generation, watermark, readiness, owner_probes):
    """Sanitized display design; no provider facts, raw cases or 9I bodies."""
    verified(lifecycle)
    if set(lifecycle["capabilities"]) != set(CAPABILITIES) or any(v is not False for v in lifecycle["capabilities"].values()):
        raise ValueError("AUTHORITY_VIOLATION")
    return {"schema": "iios-full-session-shadow-browser-v1", "phase": lifecycle["phase"],
            "session": lifecycle["session"], "scope": "SHADOW_OBSERVATION_NOT_LIVE_TRADING",
            "capture_status": lifecycle["capture_status"], "watermark": watermark,
            "source_generation": generation["content_hash"] if generation else None,
            "universes": [{k: v for k, v in u.items() if k != "members"} for u in generation["universes"]] if generation else [],
            "owners": owner_probes, "readiness": readiness, "incidents": lifecycle["incidents"],
            "capabilities": lifecycle["capabilities"], "counters": dict.fromkeys(COUNTERS, 0),
            "counter_scope": "DENY_ONLY_SHADOW", "narrative_classification": "NARRATIVE",
            "evidence_classes": ["HISTORICAL", "REPLAY", "SIMULATED", "NARRATIVE", "UNAVAILABLE"],
            "source_session_closed_is_not_installed_disabled": True}
