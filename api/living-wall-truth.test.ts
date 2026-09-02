import assert from "node:assert/strict";
import test from "node:test";
import { projectLivingWallTruth } from "./_livingWallTruth.js";
import { createLivingWallTruthHandler, type TruthReadFailure } from "./_livingWallTruthHandler.js";
import { createTelemetryIngestHandler } from "./_telemetryIngestHandler.js";
import { TELEMETRY_CACHE_KEY, validateSnapshot } from "./_telemetryPolicy.js";

const now = Date.parse("2026-09-01T12:00:00Z");
const snapshot = {
  schema_version: "iios_remote_telemetry.v1",
  generated_at: "2026-09-01T11:59:30Z",
  safety: { live_execution: false, authorization: "AUTHORIZATION-MARKER", access_token: "TOKEN-MARKER", credential: "CREDENTIAL-MARKER", backend_write_permission: true },
  source_conflict: false,
  validation: { layers: { factory_telemetry: { availability: "READY", age_seconds: 3, payload: { safety: { telemetry_read_only: true }, prompt: "PROMPT-MARKER", raw_evidence: "RAW-EVIDENCE-MARKER", provider_error: "PROVIDER-ERROR-MARKER" } } } },
  factory: { availability: "READY", payload: { cases: [{ case_id: "case-1" }], recent_events: [{ entity_id: "entity-1" }], desks: [{ path: "/private/path" }], portfolio: { nav: 100, cash: 50, positions: 1, exposure: 50, ledger: { account_number: "LEDGER-MARKER" } } } },
};
const safeSnapshot = {
  schema_version: "iios_remote_telemetry.v1",
  generated_at: "2026-09-01T11:59:30Z",
  safety: { live_execution: false, backend_write_permission: false, trade_execution_permission: false },
  source_conflict: false,
  validation: { layers: { factory_telemetry: { availability: "READY", age_seconds: 3, payload: { safety: { telemetry_read_only: true } } } } },
  factory: { availability: "READY", payload: { cases: [{ case_id: "case-1" }], recent_events: [], desks: [], portfolio: { nav: 100, cash: 50, positions: 1, exposure: 50 } } },
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

test("freshness boundaries remain current through 60s, stale through 120s, then expire", () => {
  const at = (seconds: number) => projectLivingWallTruth({ ...snapshot, generated_at: new Date(now - seconds * 1000).toISOString() }, now);
  assert.equal(at(60).freshness.state, "CURRENT");
  assert.equal(at(61).freshness.state, "STALE");
  assert.equal(at(120).freshness.state, "STALE");
  assert.throws(() => at(121), /expired snapshot/);
});

test("ingest rejects unsupported schemas and never writes unprojectable snapshots", async () => {
  let writes = 0;
  const handler = createTelemetryIngestHandler(
    { set: async () => { writes += 1; } },
    () => "ingest-token",
  );
  const request = (body: object) => new Request("https://example.test/telemetry/ingest", {
    method: "POST",
    headers: { "content-type": "application/json", "x-iios-telemetry-token": "Bearer ingest-token" },
    body: JSON.stringify(body),
  });

  assert.equal((await handler(request({ ...safeSnapshot, schema_version: "unsupported.v9" }))).status, 400);
  assert.equal((await handler(request({ ...safeSnapshot, generated_at: "not-a-date" }))).status, 400);
  assert.equal(writes, 0);
});

test("normalized publisher envelope flows through separate ingest and truth instances", async () => {
  const shared = new Map<string, unknown>();
  const writer = { set: async (key: string, value: unknown) => { shared.set(key, value); } };
  const reader = { get: async (key: string) => shared.get(key) };
  const ingest = createTelemetryIngestHandler(writer, () => "ingest-token");
  const truth = createLivingWallTruthHandler(reader, () => undefined);
  const published = { ...safeSnapshot, generated_at: new Date().toISOString(), source_schema_version: "batch9l-living-factory-provenance-v1" };
  const ingestResponse = await ingest(new Request("https://example.test/telemetry/ingest", {
    method: "POST",
    headers: { "content-type": "application/json", "x-iios-telemetry-token": "Bearer ingest-token" },
    body: JSON.stringify(published),
  }));

  assert.equal(ingestResponse.status, 202);
  assert.equal((await ingestResponse.json()).accepted, true);
  assert.equal(shared.has(TELEMETRY_CACHE_KEY), true);
  const truthResponse = await truth(new Request("https://example.test/living-wall/truth"));
  assert.equal(truthResponse.status, 200);
  assert.equal((await truthResponse.json()).schema_version, "living_wall_truth.v1");
});

test("unsafe authority and credential fields are rejected before cache writes", () => {
  assert.throws(() => validateSnapshot({ ...safeSnapshot, safety: { live_execution: true } }), /live_execution=false/);
  assert.throws(() => validateSnapshot({ ...safeSnapshot, credential: "forbidden" }), /forbidden telemetry field/);
  assert.throws(() => validateSnapshot({ ...safeSnapshot, trade_authority: "enabled" }), /trade_authority must remain disabled/);
  assert.throws(() => validateSnapshot({ ...safeSnapshot, write_authority: "enabled" }), /write_authority must remain disabled/);
});

test("endpoint is GET-only and returns a sanitized unavailable DTO without wildcard CORS", async () => {
  const failures: TruthReadFailure[] = [];
  const handler = createLivingWallTruthHandler({ get: async () => null }, (failure) => failures.push(failure));
  assert.equal((await handler(new Request("https://example.test", { method: "POST" }))).status, 405);
  const response = await handler(new Request("https://example.test"));
  assert.equal(response.status, 503);
  assert.equal(response.headers.get("access-control-allow-origin"), null);
  assert.equal((await response.json()).availability, "UNAVAILABLE");
  assert.deepEqual(failures, ["MISSING_SNAPSHOT"]);
});

test("truth handler internally distinguishes invalid snapshots and storage errors", async () => {
  const failures: TruthReadFailure[] = [];
  const invalid = createLivingWallTruthHandler({ get: async () => ({ ...snapshot, schema_version: "unsupported.v9" }) }, (failure) => failures.push(failure));
  const broken = createLivingWallTruthHandler({ get: async () => { throw new Error("private storage detail"); } }, (failure) => failures.push(failure));

  assert.equal((await invalid(new Request("https://example.test"))).status, 503);
  assert.equal((await broken(new Request("https://example.test"))).status, 503);
  assert.deepEqual(failures, ["INVALID_SNAPSHOT", "STORAGE_ERROR"]);
});

test("preserves stale and source-conflict states without changing authority", () => {
  const stale = projectLivingWallTruth({ ...snapshot, generated_at: "2026-09-01T11:58:59Z" }, now);
  const conflicted = projectLivingWallTruth({ ...snapshot, source_conflict: true }, now);
  assert.equal(stale.availability, "STALE");
  assert.equal(conflicted.availability, "SOURCE_CONFLICT");
  assert.equal(conflicted.safety.live_execution, false);
});
