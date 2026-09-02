import assert from "node:assert/strict";
import test from "node:test";

const dto = (generated_at: string | null, availability: string = "AVAILABLE") => ({ schema_version: "living_wall_truth.v1", generated_at, availability, source_conflict: availability === "SOURCE_CONFLICT", freshness: { state: availability === "UNAVAILABLE" ? "UNAVAILABLE" : "CURRENT", age_seconds: 1 }, factory: {}, validation: { layers: {} }, safety: { telemetry_read_only: true, direct_ledger_access: false, backend_write_permission: false, trade_execution_permission: false, live_execution: false } });

async function load(hostname: string, responses: Array<{ status: number; body: object }>) {
  const calls: string[] = [];
  const values = new Map<string, string>();
  Object.assign(globalThis, {
    window: { location: { hostname, origin: `https://${hostname}` } },
    sessionStorage: { getItem: (key: string) => values.get(key) ?? null, setItem: (key: string, value: string) => values.set(key, value) },
  });
  globalThis.fetch = async (input: string | URL | Request) => { calls.push(String(input)); const next = responses.shift()!; return new Response(JSON.stringify(next.body), { status: next.status, headers: { "content-type": "application/json" } }); };
  const adapter = await import(`./TruthSourceAdapter.ts?test=${Math.random()}`);
  return { calls, load: adapter.loadFactoryTruth };
}

test("selects local overview only on localhost", async () => {
  const fixture = await load("localhost", [{ status: 200, body: {} }]);
  await fixture.load();
  assert.deepEqual(fixture.calls, ["/living/overview"]);
});

test("selects Vercel truth and never falls back after a failed remote request", async () => {
  const fixture = await load("wall.vercel.app", [{ status: 503, body: dto(null, "UNAVAILABLE") }]);
  const result = await fixture.load();
  assert.equal(result.source, "/living-wall/truth");
  assert.deepEqual(fixture.calls, ["/living-wall/truth"]);
});

test("rejects a regressing remote truth timestamp", async () => {
  const fixture = await load("wall.vercel.app", [{ status: 200, body: dto("2026-09-01T12:00:00Z") }, { status: 200, body: dto("2026-09-01T11:59:00Z") }]);
  await fixture.load();
  await assert.rejects(fixture.load(), /regressed/);
});