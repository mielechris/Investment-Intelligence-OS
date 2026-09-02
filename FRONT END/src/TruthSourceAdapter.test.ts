import assert from "node:assert/strict";
import test from "node:test";
import { deployedAvailableTruth } from "./livingWallTruthContract.fixture";

const deployedDto = (generated_at: string | null, availability = "AVAILABLE") => {
  const dto = structuredClone(deployedAvailableTruth);
  return {
    ...dto,
    generated_at,
    availability,
    source_conflict: availability === "SOURCE_CONFLICT",
    freshness: {
      state: availability === "UNAVAILABLE" ? "UNAVAILABLE" : availability === "STALE" ? "STALE" : "CURRENT",
      age_seconds: availability === "UNAVAILABLE" ? null : 1,
    },
  };
};

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
  const fixture = await load("wall.vercel.app", [{ status: 503, body: deployedDto(null, "UNAVAILABLE") }]);
  const result = await fixture.load();
  assert.equal(result.source, "/living-wall/truth");
  assert.deepEqual(fixture.calls, ["/living-wall/truth"]);
});

test("rejects a regressing remote truth timestamp", async () => {
  const fixture = await load("wall.vercel.app", [{ status: 200, body: deployedDto("2026-09-01T12:00:00Z") }, { status: 200, body: deployedDto("2026-09-01T11:59:00Z") }]);
  await fixture.load();
  await assert.rejects(fixture.load(), /regressed/);
});

test("normalizes the deployed AVAILABLE/CURRENT contract for Gallery", async () => {
  const fixture = await load("wall.vercel.app", [{ status: 200, body: deployedDto("2026-09-01T12:00:00Z") }]);
  const result = await fixture.load();
  const adapter = await import(`./TruthSourceAdapter.ts?selector=${Math.random()}`);
  assert.deepEqual(adapter.selectGalleryTruth(result), {
    degraded: false,
    condition: "SANITIZED / OBSERVING",
    marketPhase: "AVAILABLE",
    paperNav: 10000,
  });
});

test("keeps missing, malformed, stale, unavailable, and unsafe truth fail-closed", async () => {
  const malformed = deployedDto("2026-09-01T12:00:00Z") as Record<string, unknown>;
  malformed.factory = { availability: "AVAILABLE", paper_fund: { nav: "10000" } };
  const unsafe = deployedDto("2026-09-01T12:00:00Z");
  unsafe.safety.live_execution = true;
  const missingFixture = await load("missing.vercel.app", [{ status: 200, body: {} }]);
  await assert.rejects(missingFixture.load(), /invalid/);
  const malformedFixture = await load("malformed.vercel.app", [{ status: 200, body: malformed }]);
  await assert.rejects(malformedFixture.load(), /invalid/);
  const unsafeFixture = await load("unsafe.vercel.app", [{ status: 200, body: unsafe }]);
  await assert.rejects(unsafeFixture.load(), /invalid/);

  const staleFixture = await load("stale.vercel.app", [{ status: 200, body: deployedDto("2026-09-01T12:00:00Z", "STALE") }]);
  const stale = await staleFixture.load();
  const adapter = await import(`./TruthSourceAdapter.ts?failclosed=${Math.random()}`);
  const missing = adapter.selectGalleryTruth(null);
  assert.equal(missing.degraded, true);
  assert.equal(missing.marketPhase, "UNKNOWN");
  assert.equal(missing.paperNav, null);
  assert.equal(adapter.selectGalleryTruth(stale).degraded, true);

  const unavailableFixture = await load("unavailable.vercel.app", [{ status: 503, body: deployedDto(null, "UNAVAILABLE") }]);
  const unavailable = await unavailableFixture.load();
  assert.equal(adapter.selectGalleryTruth(unavailable).degraded, true);
});
