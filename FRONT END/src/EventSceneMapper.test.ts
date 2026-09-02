import assert from "node:assert/strict";
import test from "node:test";
import { mapEventToScene } from "./EventSceneMapper.ts";

test("maps opportunity intake to Radar and its character", () => {
  const scene = mapEventToScene({ event_type: "opportunity_detected", created_at: "2026-09-01T10:00:00Z", entity_id: "asset-1" });
  assert.equal(scene.room, "radar");
  assert.equal(scene.character, "market_structure");
  assert.equal(scene.animate, true);
});

test("maps downstream governed rooms without inferring later stages", () => {
  assert.equal(mapEventToScene({ event_type: "research_evidence_received", created_at: "2026-09-01T10:00:00Z", case_id: "case-1" }).room, "research");
  assert.equal(mapEventToScene({ event_type: "agent_analysis_completed", created_at: "2026-09-01T10:00:00Z", case_id: "case-1" }).room, "agents");
  assert.equal(mapEventToScene({ event_type: "committee_completed", created_at: "2026-09-01T10:00:00Z", case_id: "case-1" }).room, "committee");
  assert.equal(mapEventToScene({ event_type: "risk_veto", created_at: "2026-09-01T10:00:00Z", case_id: "case-1" }).room, "risk");
  assert.equal(mapEventToScene({ event_type: "paper_decision_recorded", created_at: "2026-09-01T10:00:00Z", case_id: "case-1" }).room, "paper");
  assert.equal(mapEventToScene({ event_type: "monitoring_update", created_at: "2026-09-01T10:00:00Z", case_id: "case-1" }).room, "monitoring");
  assert.equal(mapEventToScene({ event_type: "learning_outcome_update", created_at: "2026-09-01T10:00:00Z", case_id: "case-1" }).room, "learning");
});

test("keeps unknown events visible but does not invent their stage", () => {
  const scene = mapEventToScene({ event_type: "unclassified_signal", created_at: "2026-09-01T10:00:00Z", case_id: "case-1" });
  assert.equal(scene.room, "radar");
  assert.equal(scene.animate, true);
  assert.match(scene.unknowns, /unknown/i);
});

test("withholds incomplete lineage movement", () => {
  const scene = mapEventToScene({ event_type: "opportunity_promoted_to_case", case_id: "case-1" });
  assert.equal(scene.room, "research");
  assert.equal(scene.animate, false);
  assert.match(scene.reason, /incomplete/i);
});

test("routes stale and source-conflict truth to Watch investigation posture", () => {
  for (const truthState of ["stale", "source_conflict"]) {
    const scene = mapEventToScene({ event_type: "committee_completed", created_at: "2026-09-01T10:00:00Z", case_id: "case-1", truth_state: truthState }, true);
    assert.equal(scene.room, "watch");
    assert.equal(scene.lighting, "amber");
    assert.equal(scene.animate, false);
  }
});

test("represents no event as dignified idle", () => {
  const scene = mapEventToScene(null);
  assert.equal(scene.room, "idle");
  assert.equal(scene.character, "max");
  assert.equal(scene.animate, false);
});

test("labels replay receipts as historical presentation", () => {
  const scene = mapEventToScene({ event_type: "committee_completed", created_at: "2026-09-01T10:00:00Z", case_id: "case-1", historical: true });
  assert.equal(scene.historical, true);
  assert.equal(scene.room, "committee");
});
