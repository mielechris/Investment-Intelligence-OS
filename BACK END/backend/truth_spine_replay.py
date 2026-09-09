"""Append-only governed replay. Models are explicitly non-spending acceptance boundaries."""
from __future__ import annotations

import ast
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
from typing import Protocol

from truth_spine_contract import Topology, bind, canonical, digest, locked, seal, verified

STATES = ("OBSERVED", "EVIDENCE_NORMALIZED", "CANDIDATE", "CASE_OPEN", "RESEARCH_IN_PROGRESS",
          "CHALLENGE_COMPLETE", "COMMITTEE_COMPLETE", "RISK_COMPLETE", "WATCH", "OUTCOME_PENDING")
EDGES = {a: {b} for a, b in zip(STATES, STATES[1:])}
EDGES["RISK_COMPLETE"].add("NO_TRADE")
EDGES["NO_TRADE"] = {"OUTCOME_PENDING"}
EDGES["OUTCOME_PENDING"] = set()
REGISTERED = {"policy", "macro", "fundamentals", "market_structure", "commodities", "geo_weather", "skeptic", "portfolio"}


def registered_agents() -> dict:
    tree = ast.parse(Path(__file__).with_name("main.py").read_text())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "AGENT_CONFIGS" for t in node.targets):
            registry = ast.literal_eval(node.value)
            if set(registry) == REGISTERED:
                return registry
    raise ValueError("AGENT_REGISTRY_INVALID")


def routing(tags: tuple[str, ...]) -> dict:
    registry = registered_agents()
    primary = "fundamentals" if "fundamentals" in tags else "market_structure"
    selected = [primary, "skeptic"] + sorted((set(tags) & REGISTERED) - {primary, "skeptic"})
    return {k: {"name": v["name"], "invoked": k in selected,
                "reason": "PRIMARY_ANALYST" if k == primary else "INDEPENDENT_CHALLENGE" if k == "skeptic"
                else "RELEVANT_CASE_TAG" if k in selected else "IRRELEVANT_AGENT_SUPPRESSED"}
            for k, v in registry.items()}


class ModelBoundary(Protocol):
    def assess(self, role: str, context: dict) -> dict: ...


class AcceptanceModel:
    """Never claims real model research. No network, credentials, tools, or mutable conversational state."""
    def assess(self, role: str, context: dict) -> dict:
        return {"role": role, "classification": "REPLAY", "model": "DETERMINISTIC_ACCEPTANCE_ONLY",
                "citations": [context["evidence"]["evidence_id"]], "claims": [],
                "conclusion": "INSUFFICIENT_EVIDENCE", "reason": "PRICE_ALONE_DOES_NOT_ESTABLISH_THESIS",
                "memory_hash": digest({"memory": context["memory"]}),
                "input_hash": digest(context)}


def validate_output(output: dict, role: str, context: dict) -> None:
    required = {"role", "classification", "model", "citations", "claims", "conclusion", "reason", "memory_hash", "input_hash"}
    if (not isinstance(output, dict) or set(output) != required or output["role"] != role
            or output["classification"] != "REPLAY" or output["model"] != "DETERMINISTIC_ACCEPTANCE_ONLY"
            or output["citations"] != [context["evidence"]["evidence_id"]] or output["claims"] != []
            or output["conclusion"] != "INSUFFICIENT_EVIDENCE"
            or output["reason"] != "PRICE_ALONE_DOES_NOT_ESTABLISH_THESIS"
            or output["memory_hash"] != digest({"memory": context["memory"]})
            or output["input_hash"] != digest(context)):
        raise ValueError("UNSUPPORTED_AGENT_OUTPUT")


def transition(current: str, next_state: str) -> None:
    if next_state not in EDGES.get(current, set()):
        raise ValueError("DECISION_TRANSITION_INVALID")


def memory_context(path: Path) -> tuple[dict, ...]:
    """Only outcome-receipt-bound validated entries may enter this replay; no raw prose."""
    with connect(path, readonly=True) as db:
        rows = db.execute("SELECT payload_json FROM ledger_objects WHERE object_type='judgment_entry'").fetchall()
        outcomes = [json.loads(r[0]) for r in db.execute("SELECT payload_json FROM ledger_objects WHERE object_type='outcome_measurement_receipt'")]
    eligible = []
    for (raw,) in rows:
        row = json.loads(raw)
        if (row.get("human_validated") is True and row.get("outcome_receipt_hash")
                and row.get("content_hash") == digest(row)
                and any(o.get("content_hash") == row["outcome_receipt_hash"] == digest(o)
                        and o.get("case_id") == row.get("case_id") and o.get("status") == "MEASURED" for o in outcomes)):
            eligible.append({k: row[k] for k in ("content_hash", "outcome_receipt_hash", "case_id")})
    return tuple(sorted(eligible, key=lambda x: x["content_hash"]))


def analyze(evidence: dict, *, tags: tuple[str, ...] = (), memory: tuple[dict, ...] = (),
            boundary: ModelBoundary | None = None, budget: int = 9, timeout: float = 2) -> dict:
    route = routing(tags); roles = [k for k, v in route.items() if v["invoked"]]
    if budget < len(roles) + 1:
        return {"routing": route, "outputs": [], "committee": None, "failure": "MODEL_BUDGET_EXCEEDED"}
    model = boundary or AcceptanceModel()
    # Immutable copies explicitly cross thread boundaries; no thread-local inheritance.
    frozen = canonical({"evidence": evidence, "memory": list(memory)})
    pool = ThreadPoolExecutor(max_workers=len(roles))
    futures = {role: pool.submit(model.assess, role, json.loads(frozen)) for role in roles}
    outputs = []
    try:
        for role, future in futures.items():
            output = future.result(timeout=timeout)
            validate_output(output, role, json.loads(frozen)); outputs.append(output)
        # Committee has its own input, explicit prior outputs, and no shared hidden conversation.
        committee_context = {**json.loads(frozen), "independent_assessments": outputs}
        committee_future = pool.submit(model.assess, "committee", committee_context)
        futures["committee"] = committee_future
        committee = committee_future.result(timeout=timeout)
        validate_output(committee, "committee", committee_context)
        return {"routing": route, "outputs": outputs, "committee": committee, "failure": None}
    except (TimeoutError, ValueError, RuntimeError):
        return {"routing": route, "outputs": outputs, "committee": None, "failure": "REQUIRED_ANALYSIS_UNAVAILABLE"}
    finally:
        for future in futures.values():
            future.cancel()
        pool.shutdown(wait=False, cancel_futures=True)


@contextmanager
def connect(path: Path, *, readonly: bool = False):
    db = sqlite3.connect(f"file:{path}?mode={'ro' if readonly else 'rw'}", uri=True, timeout=5)
    db.execute("PRAGMA foreign_keys=ON")
    if not readonly:
        db.execute("PRAGMA synchronous=FULL")
    try:
        with db:
            yield db
    finally:
        db.close()


def initialize(path: Path, topology: Topology) -> None:
    """Only an explicitly isolated copied ledger is admitted; never the permanent database."""
    if topology.mode != "ISOLATED_SHADOW" or path.resolve() != Path(topology.ledger_path).resolve():
        raise ValueError("ISOLATED_LEDGER_REQUIRED")
    with connect(path) as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS spine_identity (identity TEXT PRIMARY KEY, schema TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS spine_events (
          event_id TEXT PRIMARY KEY, trace_id TEXT NOT NULL, ordinal INTEGER NOT NULL,
          state TEXT NOT NULL, payload TEXT NOT NULL, UNIQUE(trace_id,ordinal));
        CREATE TABLE IF NOT EXISTS spine_results (trace_id TEXT PRIMARY KEY, payload TEXT NOT NULL);
        CREATE TRIGGER IF NOT EXISTS spine_events_no_update BEFORE UPDATE ON spine_events
          BEGIN SELECT RAISE(ABORT,'APPEND_ONLY'); END;
        CREATE TRIGGER IF NOT EXISTS spine_events_no_delete BEFORE DELETE ON spine_events
          BEGIN SELECT RAISE(ABORT,'APPEND_ONLY'); END;
        CREATE TRIGGER IF NOT EXISTS spine_results_no_update BEFORE UPDATE ON spine_results
          BEGIN SELECT RAISE(ABORT,'APPEND_ONLY'); END;
        CREATE TRIGGER IF NOT EXISTS spine_results_no_delete BEFORE DELETE ON spine_results
          BEGIN SELECT RAISE(ABORT,'APPEND_ONLY'); END;
        """)
        rows = db.execute("SELECT identity,schema FROM spine_identity").fetchall()
        expected = (topology.ledger_identity, topology.ledger_schema)
        if rows and rows != [expected]:
            raise ValueError("LEDGER_IDENTITY_MISMATCH")
        db.execute("INSERT OR IGNORE INTO spine_identity VALUES (?,?)", expected)


def validate_ledger(path: Path, topology: Topology) -> dict | None:
    with connect(path, readonly=True) as db:
        if db.execute("SELECT identity,schema FROM spine_identity").fetchall() != [(topology.ledger_identity, topology.ledger_schema)]:
            raise ValueError("LEDGER_IDENTITY_MISMATCH")
        results = db.execute("SELECT trace_id,payload FROM spine_results").fetchall()
        for trace, payload in results:
            result = json.loads(payload); bind(result, topology); locked(result["authority"])
            events = db.execute("SELECT state,payload FROM spine_events WHERE trace_id=? ORDER BY ordinal", (trace,)).fetchall()
            prior = None
            ids = []
            for ordinal, (state, raw) in enumerate(events):
                event = json.loads(raw); bind(event, topology)
                if event["ordinal"] != ordinal or event["previous"] != prior or event["state"] != state or event["trace_id"] != trace:
                    raise ValueError("EVENT_CHAIN_INVALID")
                if ordinal == 0 and state != "OBSERVED" or ordinal and state not in EDGES.get(events[ordinal - 1][0], set()):
                    raise ValueError("DECISION_TRANSITION_INVALID")
                prior = event["content_hash"]
                ids.append(prior)
            if [e[0] for e in events] != list(STATES) or prior != result["event_tip"] or ids != result["event_ids"] or result["trace_id"] != trace:
                raise ValueError("DECISION_CHAIN_INCOMPLETE")
            bind(result["evidence"], topology)
            if result["decision"] != "WATCH" or result["paper"]["orders"] != 0 or result["risk"]["notional"] != 0:
                raise ValueError("REPLAY_DECISION_INVALID")
        return json.loads(results[-1][1]) if results else None


def replay(path: Path, topology: Topology, evidence: dict, *, boundary: ModelBoundary | None = None) -> dict:
    bind(evidence, topology)
    trace = evidence["trace_id"]
    with connect(path) as db:
        db.execute("BEGIN IMMEDIATE")
        existing = db.execute("SELECT payload FROM spine_results WHERE trace_id=?", (trace,)).fetchone()
        if existing:
            return verified(json.loads(existing[0]))
        analysis = analyze(evidence, boundary=boundary, memory=memory_context(path))
        missing = ["CURRENT_MARKET_EVIDENCE", "THESIS", "VALUATION", "VALIDATED_OUTCOME"]
        reason = analysis["failure"] or "INSUFFICIENT_EVIDENCE"
        common = {"topology_identity": topology.record()["content_hash"], "release_id": topology.release_id,
                  "generation_id": topology.generation_id, "session_id": topology.session_id, "trace_id": trace}
        prior = None; ids = []
        for ordinal, state in enumerate(STATES):
            if ordinal:
                transition(STATES[ordinal - 1], state)
            event = seal({**common, "schema": "iios-truth-event-v1", "ordinal": ordinal, "state": state,
                          "previous": prior, "evidence_ids": [evidence["evidence_id"]],
                          "classification": "REPLAY", "observed_at": topology.created_at,
                          "stage_result": "FAILED_CLOSED" if analysis["failure"] and state in {"CHALLENGE_COMPLETE", "COMMITTEE_COMPLETE"} else "COMPLETE",
                          "reason": reason if state in {"RISK_COMPLETE", "WATCH"} else "GOVERNED_REPLAY_STAGE"})
            prior = event["content_hash"]; ids.append(prior)
            db.execute("INSERT INTO spine_events VALUES (?,?,?,?,?)", (prior, trace, ordinal, state, canonical(event).decode()))
        result = seal({**common, "schema": "iios-truth-replay-result-v1", "classification": "REPLAY",
                       "case_id": "case-" + trace, "candidate_id": "candidate-" + trace,
                       "evidence": evidence, "analysis": analysis, "event_tip": prior, "event_ids": ids,
                       "decision": "WATCH", "reason_codes": [reason], "missing_evidence": missing,
                       "committee_state": "COMPLETE" if analysis["committee"] else "FAILED_CLOSED",
                       "risk": {"state": "COMPLETE", "decision": "NO_PAPER_AUTHORITY", "notional": 0},
                       "paper": {"state": "ABSTAINED", "orders": 0, "reason": reason},
                       "outcome": {"state": "OUTCOME_PENDING", "registration_id": "outcome-" + trace,
                                   "measurement": None, "window": "SEPARATE_AUTHORIZED_FORWARD_MEASUREMENT"},
                       "memory": {"state": "NO_VALIDATED_LESSON", "admissions": 0},
                       "authority": dict(topology.authorities)})
        db.execute("INSERT INTO spine_results VALUES (?,?)", (trace, canonical(result).decode()))
    return result
