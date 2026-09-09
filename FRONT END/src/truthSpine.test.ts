import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createHash } from "node:crypto";
import { validateProjection, projectionSelection, type Projection } from "./truthSpineProjection.ts";

function signed(updates: Record<string, unknown> = {}) {
  const x = { schema: "iios-truth-projection-v1", classification: "REPLAY", topology_identity: "a".repeat(64), ledger_identity: "b".repeat(64),
    receipt_id: "c".repeat(64), release_id: "release", runtime_id: "runtime", generation_id: "generation", session_id: "session", trace_id: "trace", case_id: "case",
    observed_at: new Date().toISOString(), phase: "SESSION_CLOSED", case_state: "WATCH", reason_codes: ["INSUFFICIENT_EVIDENCE"],
    event_ids: ["event"], evidence_ids: ["evidence"], agent_states: {},
    authority: Object.fromEntries(["broker", "paper_order", "promotion", "ledger_write", "live_execution"].map(k => [k, false])),
    risk: { decision: "NO_PAPER_AUTHORITY" }, paper: { state: "ABSTAINED", orders: 0 }, outcome: { state: "OUTCOME_PENDING" }, memory: { admissions: 0 },
    paper_fund: { nav: "10000.0", cash: "10000.0", source: "ISOLATED_LEDGER_SNAPSHOT", reconciled_at: null }, ...updates };
  function stable(v: unknown): unknown {
    if (Array.isArray(v)) return v.map(stable);
    if (v && typeof v === "object") return Object.fromEntries(Object.entries(v).sort().map(([k, val]) => [k, stable(val)]));
    return v;
  }
  return { ...x, content_hash: createHash("sha256").update(JSON.stringify(stable(x)) + "\n").digest("hex") };
}

test("truth preview explicitly labels replay, never has an order control", () => {
  const source = readFileSync(new URL("./TruthSpinePreview.tsx", import.meta.url), "utf8");
  assert.match(source, /REPLAY — NOT LIVE INVESTMENT RESEARCH/);
  assert.match(source, /Deterministic acceptance models/);
  assert.doesNotMatch(source, /method:\s*["']POST/);
  assert.match(source, /reconciled_at/);
  assert.match(source, /controller.abort/);
});
test("missing, unsigned and fabricated live projections fail closed", async () => {
  for (const value of [null, {}, { classification: "LIVE_VERIFIED" }, { classification: "REPLAY", content_hash: "wrong" }]) {
    await assert.rejects(validateProjection(value, null));
  }
});
test("responsive containment and focus remain explicit", () => {
  const source = readFileSync(new URL("./TruthSpinePreview.css", import.meta.url), "utf8");
  assert.match(source, /minmax\(0, 1fr\)/); assert.match(source, /overflow-wrap: anywhere/); assert.match(source, /:focus-visible/);
});
test("signed replay preserves decimal balance strings and closed phase", async () => {
  const x = await validateProjection(signed(), null);
  assert.equal(x.paper_fund.cash, "10000.0"); assert.equal(x.phase, "SESSION_CLOSED");
});
test("same claimed topology cannot mix different generation/release/runtime/ledger/session", async () => {
  const x = signed(); const selected = projectionSelection(x as unknown as Projection);
  for (const key of ["generation_id", "release_id", "runtime_id", "ledger_identity", "session_id", "topology_identity"]) {
    await assert.rejects(validateProjection(signed({ [key]: "wrong" }), selected));
  }
});
test("stale, future, simulated and authority-bearing projections rejected", async () => {
  for (const changes of [{ observed_at: new Date(Date.now() - 16000).toISOString() }, { observed_at: new Date(Date.now() + 30000).toISOString() },
    { classification: "SIMULATED" }, { classification: "LIVE_VERIFIED" }, { authority: { broker: true } }, { phase: "INSTALLED_DISABLED" }]) {
    await assert.rejects(validateProjection(signed(changes), null));
  }
});
