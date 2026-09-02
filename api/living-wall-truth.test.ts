import assert from "node:assert/strict";
import test from "node:test";
import { projectLivingWallTruth } from "./_livingWallTruth.js";
import { createLivingWallTruthHandler } from "./_livingWallTruthHandler.js";

const now = Date.parse("2026-09-01T12:00:00Z");
const snapshot = {
  generated_at: "2026-09-01T11:59:30Z",
  safety: { live_execution: false, authorization: "AUTHORIZATION-MARKER", access_token: "TOKEN-MARKER", credential: "CREDENTIAL-MARKER", backend_write_permission: true },
  source_conflict: false,
  validation: { layers: { factory_telemetry: { availability: "READY", age_seconds: 3, payload: { safety: { telemetry_read_only: true }, prompt: "PROMPT-MARKER", raw_evidence: "RAW-EVIDENCE-MARKER", provider_error: "PROVIDER-ERROR-MARKER" } } } },
  factory: { availability: "READY", payload: { cases: [{ case_id: "case-1" }], recent_events: [{ entity_id: "entity-1" }], desks: [{ path: "/private/path" }], portfolio: { nav: 100, cash: 50, positions: 1, exposure: 50, ledger: { account_number: "LEDGER-MARKER" } } } },
};

test("projects an exact allow-listed DTO without private nested fields", () => {
  const dto = projectLivingWallTruth(snapshot, now);
  assert.deepEqual(Object.keys(dto), ["schema_version", "generated_at", "freshness", "availability", "source_conflict", "factory", "validation", "safety"]);
  for (const marker of ["AUTHORIZATION-MARKER", "TOKEN-MARKER", "CREDENTIAL-MARKER", "PROMPT-MARKER", "RAW-EVIDENCE-MARKER", "PROVIDER-ERROR-MARKER", "LEDGER-MARKER"]) assert.equal(JSON.stringify(dto).includes(marker), false);
  assert.equal(JSON.stringify(dto).includes("/private/path"), false);
  assert.deepEqual(dto.safety, { telemetry_read_only: true, direct_ledger_access: false, backend_write_permission: false, trade_execution_permission: false, live_execution: false });
  assert.equal(dto.factory.case_count, 1);
});

test("rejects unsupported, malformed, future, expired, and unsafe snapshots", () => {
  assert.throws(() => projectLivingWallTruth({}, now));
  assert.throws(() => projectLivingWallTruth({ ...snapshot, schema_version: "unsupported.v9" }, now));
  assert.throws(() => projectLivingWallTruth({ ...snapshot, generated_at: "bad" }, now));
  assert.throws(() => projectLivingWallTruth({ ...snapshot, generated_at: "2026-09-01T12:02:00Z" }, now));
  assert.throws(() => projectLivingWallTruth({ ...snapshot, generated_at: "2026-09-01T11:57:00Z" }, now));
  assert.throws(() => projectLivingWallTruth({ ...snapshot, safety: { live_execution: true } }, now));
});

test("endpoint is GET-only and returns a sanitized unavailable DTO without wildcard CORS", async () => {
  const handler = createLivingWallTruthHandler({ get: async () => null });
  assert.equal((await handler(new Request("https://example.test", { method: "POST" }))).status, 405);
  const response = await handler(new Request("https://example.test"));
  assert.equal(response.status, 503);
  assert.equal(response.headers.get("access-control-allow-origin"), null);
  assert.equal((await response.json()).availability, "UNAVAILABLE");
});

test("preserves stale and source-conflict states without changing authority", () => {
  const stale = projectLivingWallTruth({ ...snapshot, generated_at: "2026-09-01T11:58:59Z" }, now);
  const conflicted = projectLivingWallTruth({ ...snapshot, source_conflict: true }, now);
  assert.equal(stale.availability, "STALE");
  assert.equal(conflicted.availability, "SOURCE_CONFLICT");
  assert.equal(conflicted.safety.live_execution, false);
});