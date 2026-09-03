import assert from "node:assert/strict";
import test from "node:test";
import { AUCTION_ROOMS, EVENT_ROOM } from "./auctionRegistry.ts";
import { buildAuctionModel, normalizeEvent } from "./auctionSceneModel.ts";
import { deployedAvailableTruth } from "./livingWallTruthContract.fixture.ts";

const available = () => ({ source: "/living-wall/truth", fallback: false, data: structuredClone(deployedAvailableTruth) });

test("canonical registry contains every required room once with provenance", () => {
  assert.equal(AUCTION_ROOMS.length, 18);
  assert.equal(new Set(AUCTION_ROOMS.map((room) => room.id)).size, AUCTION_ROOMS.length);
  assert.ok(AUCTION_ROOMS.every((room) => room.source && room.purpose));
  for (const id of ["radar", "research", "policy", "macro", "external", "committee", "skeptic", "risk", "paper", "portfolio", "monitoring", "learning", "judgment", "evidence", "thesis", "control", "replay", "expansion"]) assert.ok(AUCTION_ROOMS.some((room) => room.id === id));
});

test("every exact event registry rule selects only its declared room", () => {
  for (const [type, room] of Object.entries(EVENT_ROOM)) {
    const event = normalizeEvent({ event_type: type, created_at: "2026-09-02T12:00:00Z", case_id: "case-1", receipt_id: "receipt-1" });
    assert.equal(event?.room, room);
    assert.equal(event?.animate, true);
  }
});

test("unknown event types are quarantined and never animate", () => {
  const event = normalizeEvent({ event_type: "headline_says_research_and_order", created_at: "2026-09-02T12:00:00Z", case_id: "case-1" });
  assert.equal(event?.room, null);
  assert.equal(event?.animate, false);
});

test("missing timestamp or lineage withholds the event entirely", () => {
  assert.equal(normalizeEvent({ event_type: "opportunity_detected", case_id: "case-1" }), null);
  assert.equal(normalizeEvent({ event_type: "opportunity_detected", created_at: "2026-09-02T12:00:00Z" }), null);
  assert.equal(normalizeEvent({ event_type: "opportunity_detected", created_at: "invalid", case_id: "case-1" }), null);
});

test("deployed aggregate truth produces a truthful quiet AVAILABLE factory", () => {
  const model = buildAuctionModel(available(), null, new Date("2026-09-02T12:00:00"));
  assert.equal(model.condition, "AVAILABLE");
  assert.equal(model.freshness, "CURRENT");
  assert.equal(model.quiet, true);
  assert.equal(model.nav, 10000);
  assert.equal(model.marketValidation, "AVAILABLE");
  assert.equal(model.rooms.paper, "locked");
  assert.equal(model.safety.telemetryReadOnly, true);
  assert.deepEqual([model.safety.ledger, model.safety.write, model.safety.trade, model.safety.live], [false, false, false, false]);
});

test("a complete exact receipt activates only its authoritative room", () => {
  const fixture = available();
  const data = fixture.data as Record<string, unknown>;
  const validation = data.validation as { layers: Record<string, { availability: string; age_seconds: number; payload?: object }> };
  validation.layers.factory_telemetry.payload = { recent_events: [{ event_type: "committee_completed", created_at: "2026-09-02T12:00:00Z", case_id: "case-1" }] };
  const model = buildAuctionModel(fixture, null);
  assert.equal(model.activeRoom, "committee");
  assert.equal(model.rooms.committee, "active");
  assert.equal(model.rooms.risk, "idle");
});

test("stale, unavailable, source-conflict, error, and unsafe inputs freeze movement", () => {
  for (const state of ["STALE", "SOURCE_CONFLICT", "UNAVAILABLE"] as const) {
    const fixture = available();
    const data = fixture.data as Record<string, unknown>;
    data.availability = state;
    data.source_conflict = state === "SOURCE_CONFLICT";
    data.freshness = { state: state === "UNAVAILABLE" ? "UNAVAILABLE" : "STALE", age_seconds: state === "UNAVAILABLE" ? null : 80 };
    const model = buildAuctionModel(fixture, null);
    assert.equal(model.quiet, true);
    assert.ok(Object.values(model.rooms).every((room) => ["degraded", "unavailable", "locked"].includes(room)));
  }
  assert.equal(buildAuctionModel(null, "failed").condition, "UNAVAILABLE");
  const unsafe = available();
  (unsafe.data.safety as Record<string, unknown>).live_execution = true;
  const unsafeModel = buildAuctionModel(unsafe, null);
  assert.equal(unsafeModel.quiet, true);
  assert.equal(unsafeModel.safety.live, true);
});

test("Story and Replay preserve explicit provenance boundaries", () => {
  const fixture = available();
  const data = fixture.data as Record<string, unknown>;
  const validation = data.validation as { layers: Record<string, { availability: string; age_seconds: number; payload?: object }> };
  validation.layers.factory_telemetry.payload = { recent_events: [
    { event_id: "now", event_type: "monitoring_update", created_at: "2026-09-02T12:00:00Z", case_id: "case-1", source_identity: "receipt-now" },
    { event_id: "then", event_type: "learning_outcome_update", created_at: "2026-09-01T12:00:00Z", case_id: "case-1", source_identity: "receipt-then", historical: true },
  ] };
  const model = buildAuctionModel(fixture, null);
  assert.equal(model.events.length, 2);
  assert.deepEqual(model.replay.map((event) => event.id), ["then"]);
  assert.equal(model.replay[0].provenance, "receipt-then");
});

test("case theater retains UNKNOWN for every absent field", () => {
  const fixture = available();
  const data = fixture.data as Record<string, unknown>;
  const validation = data.validation as { layers: Record<string, { availability: string; age_seconds: number; payload?: object }> };
  validation.layers.factory_telemetry.payload = { cases: [{ case_id: "case-1" }] };
  const item = buildAuctionModel(fixture, null).cases[0];
  assert.equal(item.ticker, "UNKNOWN");
  assert.equal(item.thesis, "UNKNOWN");
  assert.equal(item.paper, "UNKNOWN");
  assert.equal(item.provenance, "UNKNOWN");
});
